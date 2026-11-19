import hashlib

import pytest
from httpx import ASGITransport, AsyncClient

from application.pdf_extractor import (
    ExtractorRejectedError,
    ExtractorTimeoutError,
    ExtractorUnavailableError,
)
from presentation.main import app, get_checksum_repo, get_pdf_extractor

PDF_BYTES = b"%PDF-1.4 contenido"
CHECKSUM = hashlib.sha256(PDF_BYTES).hexdigest()


class FakeExtractor:
    def __init__(self, text: str = "texto extraido", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.calls = 0

    async def extract(self, pdf_bytes: bytes) -> str:
        self.calls += 1
        if self.error:
            raise self.error
        return self.text


class FakeChecksumRepo:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.saved: list[tuple[str, str]] = []

    async def exists(self, checksum: str) -> bool:
        return checksum in self.existing

    async def save(self, text: str, checksum: str) -> None:
        self.saved.append((text, checksum))


@pytest.fixture
def wire():
    def _wire(extractor: FakeExtractor, repo: FakeChecksumRepo) -> None:
        app.dependency_overrides[get_pdf_extractor] = lambda: extractor
        app.dependency_overrides[get_checksum_repo] = lambda: repo

    yield _wire
    app.dependency_overrides.clear()


async def post_pdf():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/extract", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")}
        )


@pytest.mark.asyncio
async def test_extract_persists_text_returned_by_the_extractor(wire):
    repo = FakeChecksumRepo()
    wire(FakeExtractor("hola"), repo)

    response = await post_pdf()

    assert response.status_code == 200
    assert response.json() == {"text": "hola", "checksum": CHECKSUM}
    assert repo.saved == [("hola", CHECKSUM)]


@pytest.mark.asyncio
async def test_extract_rejects_duplicate_without_calling_the_extractor(wire):
    extractor = FakeExtractor()
    repo = FakeChecksumRepo(existing={CHECKSUM})
    wire(extractor, repo)

    response = await post_pdf()

    assert response.status_code == 409
    assert extractor.calls == 0
    assert repo.saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 413, 415])
async def test_extract_forwards_extractor_rejection(wire, status_code):
    repo = FakeChecksumRepo()
    wire(FakeExtractor(error=ExtractorRejectedError(status_code, "no es un pdf")), repo)

    response = await post_pdf()

    assert response.status_code == status_code
    assert response.json() == {"detail": "no es un pdf"}
    assert repo.saved == []


@pytest.mark.asyncio
async def test_extract_returns_503_with_retry_after_when_extractor_is_overloaded(wire):
    wire(FakeExtractor(error=ExtractorUnavailableError("1")), FakeChecksumRepo())

    response = await post_pdf()

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"


@pytest.mark.asyncio
async def test_extract_returns_503_without_retry_after_when_extractor_is_down(wire):
    wire(FakeExtractor(error=ExtractorUnavailableError()), FakeChecksumRepo())

    response = await post_pdf()

    assert response.status_code == 503
    assert "retry-after" not in response.headers


@pytest.mark.asyncio
async def test_extract_returns_504_when_extractor_times_out(wire):
    wire(FakeExtractor(error=ExtractorTimeoutError()), FakeChecksumRepo())

    response = await post_pdf()

    assert response.status_code == 504
