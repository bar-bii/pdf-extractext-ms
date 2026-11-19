import httpx

from application.pdf_extractor import (
    ExtractorRejectedError,
    ExtractorTimeoutError,
    ExtractorUnavailableError,
)

PDF_MIME_TYPE = "application/pdf"
REJECTION_STATUS_CODES = frozenset({400, 413, 415})


class HttpPDFExtractor:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def extract(self, pdf_bytes: bytes) -> str:
        try:
            response = await self._client.post(
                "/extract",
                files={"file": ("document.pdf", pdf_bytes, PDF_MIME_TYPE)},
            )
        except httpx.TimeoutException as exc:
            raise ExtractorTimeoutError from exc
        except httpx.TransportError as exc:
            raise ExtractorUnavailableError from exc

        if response.status_code in REJECTION_STATUS_CODES:
            raise ExtractorRejectedError(response.status_code, _detail_of(response))

        if response.status_code != 200:
            raise ExtractorUnavailableError(response.headers.get("Retry-After"))

        return response.json()["content"]


def _detail_of(response: httpx.Response) -> str:
    return response.json().get("detail", response.reason_phrase)
