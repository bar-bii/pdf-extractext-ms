import httpx
import pytest

from application.pdf_extractor import (
    ExtractorRejectedError,
    ExtractorTimeoutError,
    ExtractorUnavailableError,
)
from data.extractor_client import HttpPDFExtractor

PDF_BYTES = b"%PDF-1.4 fake"


def extractor_with(handler) -> HttpPDFExtractor:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://extractor")
    return HttpPDFExtractor(client)


@pytest.mark.asyncio
async def test_extract_returns_content_from_microservice():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": "Hola Mundo", "page_count": 1})

    assert await extractor_with(handler).extract(PDF_BYTES) == "Hola Mundo"


@pytest.mark.asyncio
async def test_extract_posts_pdf_as_multipart_file_field():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"content": "", "page_count": 0})

    await extractor_with(handler).extract(PDF_BYTES)

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/extract"
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b'name="file"' in request.content
    assert b"Content-Type: application/pdf" in request.content
    assert PDF_BYTES in request.content


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 413, 415])
async def test_extract_raises_rejected_when_microservice_refuses_the_file(status_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "nope"})

    with pytest.raises(ExtractorRejectedError) as exc_info:
        await extractor_with(handler).extract(PDF_BYTES)

    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == "nope"


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 503, 500])
async def test_extract_raises_unavailable_on_overload_or_server_error(status_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, headers={"Retry-After": "1"})

    with pytest.raises(ExtractorUnavailableError) as exc_info:
        await extractor_with(handler).extract(PDF_BYTES)

    assert exc_info.value.retry_after == "1"


@pytest.mark.asyncio
async def test_extract_raises_unavailable_when_connection_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ExtractorUnavailableError):
        await extractor_with(handler).extract(PDF_BYTES)


@pytest.mark.asyncio
async def test_extract_raises_timeout_when_microservice_is_too_slow():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ExtractorTimeoutError):
        await extractor_with(handler).extract(PDF_BYTES)
