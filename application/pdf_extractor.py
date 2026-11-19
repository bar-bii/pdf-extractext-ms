from typing import Protocol


class ExtractorRejectedError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ExtractorUnavailableError(Exception):
    def __init__(self, retry_after: str | None = None) -> None:
        super().__init__("PDF extractor is unavailable")
        self.retry_after = retry_after


class ExtractorTimeoutError(Exception):
    def __init__(self) -> None:
        super().__init__("PDF extractor timed out")


class PDFExtractor(Protocol):
    async def extract(self, pdf_bytes: bytes) -> str: ...
