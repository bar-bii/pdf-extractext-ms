from typing import Annotated, Optional
from contextlib import asynccontextmanager
import os

import httpx
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, model_validator

from application.document_service import DocumentDTO, DocumentRepository, get_document, get_all_documents, update_document, delete_document
from application.checksum import calculate_checksum, ensure_unique_checksum, save_document_if_unique
from application.exceptions import DuplicateDocumentError

from application.pdf_extractor import (
    ExtractorRejectedError,
    ExtractorTimeoutError,
    ExtractorUnavailableError,
    PDFExtractor,
)
from data.config import ExtractorSettings
from data.connection import get_database_connection
from data.extractor_client import HttpPDFExtractor
from data.models import ExtractedDocument
from data.repositories import MongoChecksumRepository


# Solo los campos actualizables que pide la consigna (text/checksum), sin exponer
# campos especulativos que ningún caso de uso necesita todavía (YAGNI).
class UpdateDocumentRequest(BaseModel):
    text: Optional[str] = None
    checksum: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateDocumentRequest":
        if self.text is None and self.checksum is None:
            raise ValueError("At least one of 'text' or 'checksum' must be provided")
        return self


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Debe completarse antes de que la app empiece a servir: los modelos de Beanie
    # no se pueden usar en queries hasta que init_beanie() corra contra una conexión activa.
    await get_database_connection([ExtractedDocument])
    settings = ExtractorSettings()
    # Un único cliente HTTP por proceso: reutiliza conexiones hacia el extractor.
    async with httpx.AsyncClient(
        base_url=settings.url, timeout=settings.timeout_seconds
    ) as client:
        app.state.pdf_extractor = HttpPDFExtractor(client)
        yield


app = FastAPI(
    title="PDF Extractext API",
    description="API for PDF text extraction using Clean Architecture",
    version="0.1.0",
    lifespan=lifespan,
    # El front se sirve en otro contenedor y nginx reenvía /api/* acá.
    # root_path hace que Swagger y OpenAPI generen URLs con ese prefijo.
    root_path=os.getenv("ROOT_PATH", ""),
)


# Los endpoints declaran su dependencia como el Protocol (DocumentRepository),
# no como BeanieDocumentRepository: la implementación concreta se resuelve acá,
# en el único punto de wiring (SOLID: DIP).
async def get_document_repo() -> DocumentRepository:
    from data.repository import BeanieDocumentRepository
    return BeanieDocumentRepository()


def get_checksum_repo() -> MongoChecksumRepository:
    return MongoChecksumRepository()


def get_pdf_extractor(request: Request) -> PDFExtractor:
    return request.app.state.pdf_extractor


@app.exception_handler(ExtractorRejectedError)
async def extractor_rejected_handler(_request: Request, exc: ExtractorRejectedError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(ExtractorUnavailableError)
async def extractor_unavailable_handler(_request: Request, exc: ExtractorUnavailableError):
    headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
    return JSONResponse(
        status_code=503, content={"detail": "PDF extractor is unavailable"}, headers=headers
    )


@app.exception_handler(ExtractorTimeoutError)
async def extractor_timeout_handler(_request: Request, _exc: ExtractorTimeoutError):
    return JSONResponse(status_code=504, content={"detail": "PDF extractor timed out"})


# Evita repetir la construcción del dict de respuesta en los 4 endpoints de
# documentos (DRY).
def _doc_to_response(doc: DocumentDTO) -> dict:
    return {"id": doc.id, "text": doc.text, "checksum": doc.checksum}


@app.get("/")
async def root():
    """Redirect to the Swagger UI, honoring the public root path."""
    return RedirectResponse(url=f"{app.root_path}/docs")

@app.get("/health")
async def health_check():
    """Report that the API is up and reachable."""
    return {"status": "ok", "message": "pong"}


@app.post("/extract")
async def extract_text(
    file: UploadFile = File(...),
    repository: MongoChecksumRepository = Depends(get_checksum_repo),
    extractor: PDFExtractor = Depends(get_pdf_extractor),
):
    """Extract text from an uploaded PDF (via the extractor microservice) and persist it if its checksum is not already stored.

    Returns 409 if a document with the same SHA-256 checksum already exists.
    """
    pdf_bytes = await file.read()
    # El checksum se calcula sobre el upload crudo, antes de extraer: la deduplicación
    # debe basarse en el archivo original, ya que la extracción no está garantizada idempotente.
    checksum = calculate_checksum(pdf_bytes)
    # El duplicado se descarta antes de llamar al extractor: evita gastar CPU
    # del microservicio en archivos que igual se van a rechazar.
    try:
        await ensure_unique_checksum(checksum, repository)
        text = await extractor.extract(pdf_bytes)
        await save_document_if_unique(text, checksum, repository)
    except DuplicateDocumentError:
        raise HTTPException(status_code=409, detail=f"Duplicate document: {checksum}")
    return {"text": text, "checksum": checksum}


@app.get("/documents")
async def list_documents(repo: Annotated[DocumentRepository, Depends(get_document_repo)]):
    """List all persisted documents."""
    docs = await get_all_documents(repo)
    return [_doc_to_response(d) for d in docs]


@app.get("/documents/{id}")
async def read_document(id: str, repo: Annotated[DocumentRepository, Depends(get_document_repo)]):
    """Retrieve a single document by id. Returns 404 if it doesn't exist."""
    doc = await get_document(id, repo)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_to_response(doc)


@app.patch("/documents/{id}")
async def update_document_endpoint(
    id: str,
    body: UpdateDocumentRequest,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
):
    """Update a document's text and/or checksum. Returns 404 if it doesn't exist."""
    doc = await update_document(id, body.text, body.checksum, repo)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_to_response(doc)


@app.delete("/documents/{id}", status_code=204)
async def delete_document_endpoint(
    id: str,
    repo: Annotated[DocumentRepository, Depends(get_document_repo)],
):
    """Delete a document by id. Returns 404 if it doesn't exist."""
    deleted = await delete_document(id, repo)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return None
