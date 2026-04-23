"""
main.py — FastAPI application for document_workspace.

All document routes are protected by JWT authentication.
A user can only see, edit, and delete their own documents.

Routes
------
POST   /upload                                     — upload & process a document
GET    /document/{document_id}                     — document metadata
GET    /document/{document_id}/page/{page_number}  — single OCR page
GET    /document/{document_id}/pages               — paginated OCR pages
GET    /document/{document_id}/page/{n}/lines      — NDJSON line stream
PUT    /document/{document_id}/page/{page_number}  — update OCR page text
PUT    /document/{document_id}/edit                — bulk-edit OCR pages
DELETE /document/{document_id}                     — delete document + files

GET    /documents/{document_id}/view               — unified view endpoint
POST   /documents/{document_id}/generate-pdf       — build / rebuild output PDF
GET    /document/{document_id}/pdf                 — download viewer-ready PDF

GET    /me/storage                                 — current user's storage usage
GET    /documents                                  — list all documents for the user
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from config import setup_logging
from datetime import datetime
from database import (
    Document,
    DocumentPage,
    RevokedToken,
    SessionLocal,
    User,
    USER_STORAGE_LIMIT_BYTES,
    get_db,
)
from dependencies import get_current_user, get_current_user_flexible
from routes.upload import router as upload_router
from schemas import (
    DeleteResponse,
    DocumentEditRequest,
    DocumentEditResponse,
    DocumentResponse,
    DocumentViewResponse,
    GeneratePdfResponse,
    OcrLine,
    PageResponse,
    PageUpdateRequest,
    PageUpdateResponse,
    PaginatedPagesResponse,
    StorageUsageResponse,
    DocumentListResponse,
)
from services.pdf_generator_service import generate_searchable_pdf

from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

# ── RAG path setup ────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parent          # document_workspace/app
_RAG_DIR = _APP_DIR.parent / "rag"                  # document_workspace/rag
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

logger = logging.getLogger(__name__)

# ── Startup / shutdown ────────────────────────────────────────────────────────

def _cleanup_revoked_tokens() -> None:
    """Delete expired blacklist rows — runs daily via APScheduler."""
    db = SessionLocal()
    try:
        deleted = (
            db.query(RevokedToken)
            .filter(RevokedToken.expires_at < datetime.utcnow())
            .delete()
        )
        db.commit()
        if deleted:
            logger.info(f"Revoked-token cleanup: removed {deleted} expired row(s).")
    except Exception as exc:
        logger.error(f"Revoked-token cleanup failed: {exc}", exc_info=True)
        db.rollback()
    finally:
        db.close()

_scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level=os.getenv("LOG_LEVEL", "INFO"))
    _scheduler.add_job(_cleanup_revoked_tokens, "interval", hours=24, id="cleanup_revoked")
    _scheduler.start()
    logger.info("Startup complete — scheduler running.")
    yield
    _scheduler.shutdown(wait=False)
    logger.info("Shutdown complete.")

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
CORS_ORIGINS  = os.getenv("CORS_ORIGINS",  "http://localhost:3000").split(",")

# ── App ───────────────────────────────────────────────────────────────────────

security = HTTPBearer()

app = FastAPI(
    title="Document Workspace API",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)

# Custom OpenAPI schema — adds the 🔒 Authorize button to Swagger UI
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title="Document Workspace API",
        version="0.1.0",
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your access_token from POST /login here.",
        }
    }
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)


# ── Ownership guard ───────────────────────────────────────────────────────────

def _get_owned_document(
    document_id: str,
    db: Session,
    current_user: User,
) -> Document:
    """
    Return the Document if it exists AND belongs to current_user.
    Raises 404 for missing documents and for documents owned by other users
    (we never reveal that another user's document exists).
    """
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


# ── Storage usage ─────────────────────────────────────────────────────────────

@app.get("/me/storage", response_model=StorageUsageResponse, tags=["User"])
def get_storage_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the authenticated user's current storage usage and quota."""
    db.refresh(current_user)
    used  = current_user.used_storage_bytes or 0
    limit = USER_STORAGE_LIMIT_BYTES
    return StorageUsageResponse(
        used_bytes=used,
        limit_bytes=limit,
        used_mb=round(used / (1024 * 1024), 2),
        limit_mb=round(limit / (1024 * 1024), 2),
        available_bytes=max(limit - used, 0),
    )


# ── Document list ─────────────────────────────────────────────────────────────

@app.get("/documents", response_model=DocumentListResponse, tags=["Documents"])
@limiter.limit("30/minute")
def list_documents(
    request: Request,
    page: int = 1,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all documents belonging to the authenticated user (paginated)."""
    if limit > 100:
        limit = 100
    offset = (page - 1) * limit

    total = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .count()
    )
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return DocumentListResponse(
        total=total,
        page=page,
        limit=limit,
        documents=[DocumentResponse.model_validate(d) for d in docs],
    )


# ── Document metadata ─────────────────────────────────────────────────────────

@app.get("/document/{document_id}", response_model=DocumentResponse, tags=["Documents"])
@limiter.limit("30/minute")
def get_document(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)
    return DocumentResponse.model_validate(doc)


# ── Single OCR page ───────────────────────────────────────────────────────────

@app.get(
    "/document/{document_id}/page/{page_number}",
    response_model=PageResponse,
    tags=["Pages"],
)
@limiter.limit("60/minute")
def get_page(
    request: Request,
    document_id: str,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if doc.document_category == "text":
        raise HTTPException(
            status_code=400,
            detail="Page-level OCR data is only available for scanned documents.",
        )

    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")
    return PageResponse.model_validate(page)


# ── Paginated OCR pages ───────────────────────────────────────────────────────

@app.get(
    "/document/{document_id}/pages",
    response_model=PaginatedPagesResponse,
    tags=["Pages"],
)
@limiter.limit("30/minute")
def get_pages(
    request: Request,
    document_id: str,
    page: int = 1,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if doc.document_category == "text":
        raise HTTPException(
            status_code=400,
            detail="Page-level OCR data is only available for scanned documents.",
        )

    if limit > 50:
        limit = 50
    offset = (page - 1) * limit

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return PaginatedPagesResponse(
        document_id=document_id,
        total_pages=doc.total_pages or 0,
        page=page,
        limit=limit,
        pages=[PageResponse.model_validate(p) for p in pages],
    )


# ── NDJSON line stream ────────────────────────────────────────────────────────

@app.get("/document/{document_id}/page/{page_number}/lines", tags=["Pages"])
@limiter.limit("30/minute")
def stream_lines(
    request: Request,
    document_id: str,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream OCR lines for a single page as NDJSON."""
    import json

    doc = _get_owned_document(document_id, db, current_user)

    if doc.document_category == "text":
        raise HTTPException(
            status_code=400,
            detail="Line streaming is only available for scanned documents.",
        )

    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")

    def _generate():
        text = page.extracted_text or ""
        for line_num, line in enumerate(text.split("\n"), start=1):
            if line.strip():
                yield json.dumps({
                    "page_number":      page_number,
                    "line_number":      line_num,
                    "text":             line,
                    "ocr_type":         page.ocr_type,
                    "confidence_score": page.confidence_score,
                }) + "\n"

    return StreamingResponse(_generate(), media_type="application/x-ndjson")


# ── Update single OCR page ────────────────────────────────────────────────────

@app.put(
    "/document/{document_id}/page/{page_number}",
    response_model=PageUpdateResponse,
    tags=["Pages"],
)
@limiter.limit("20/minute")
def update_page(
    request: Request,
    document_id: str,
    page_number: int,
    data: PageUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if doc.document_category == "text":
        raise HTTPException(
            status_code=400,
            detail="Only scanned document pages can be edited.",
        )

    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
        .first()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found.")

    page.extracted_text = data.extracted_text
    db.commit()

    return PageUpdateResponse(
        document_id=document_id,
        page_number=page_number,
        extracted_text=data.extracted_text,
        message="Page updated successfully.",
    )


# ── Bulk edit ─────────────────────────────────────────────────────────────────

@app.put(
    "/document/{document_id}/edit",
    response_model=DocumentEditResponse,
    tags=["Documents"],
)
@limiter.limit("10/minute")
def bulk_edit_document(
    request: Request,
    document_id: str,
    data: DocumentEditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if doc.document_category == "text":
        raise HTTPException(
            status_code=400,
            detail="Only scanned document pages can be edited.",
        )

    updated: list[int] = []
    skipped: list[int] = []

    for entry in data.pages:
        page = (
            db.query(DocumentPage)
            .filter(
                DocumentPage.document_id == document_id,
                DocumentPage.page_number == entry.page_number,
            )
            .first()
        )
        if page:
            page.extracted_text = entry.extracted_text
            updated.append(entry.page_number)
        else:
            skipped.append(entry.page_number)

    db.commit()
    return DocumentEditResponse(
        document_id=document_id,
        updated_pages=updated,
        skipped_pages=skipped,
        message=f"Updated {len(updated)} page(s); skipped {len(skipped)} page(s).",
    )


# ── Delete document ───────────────────────────────────────────────────────────

@app.delete(
    "/document/{document_id}",
    response_model=DeleteResponse,
    tags=["Documents"],
)
@limiter.limit("10/minute")
def delete_document(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    file_size = doc.file_size_bytes or 0

    for path_str in (doc.file_path, doc.generated_pdf_path):
        if path_str:
            try:
                Path(path_str).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(f"Could not delete file '{path_str}': {exc}")

    db.delete(doc)

    current_user.used_storage_bytes = max(
        (current_user.used_storage_bytes or 0) - file_size, 0
    )

    db.commit()

    # ── Remove RAG chunks for this document ───────────────────────────────────
    try:
        from rag.ingest import delete_document as rag_delete
        rag_delete(document_id)
        logger.info(f"Document {document_id} — RAG chunks deleted.")
    except Exception as exc:
        logger.warning(f"RAG chunk deletion failed for {document_id}: {exc}")

    logger.info(
        f"Document {document_id} deleted by user {current_user.email}; "
        f"freed {file_size} bytes."
    )
    return DeleteResponse(message="Document deleted successfully.")


# ── Unified view ──────────────────────────────────────────────────────────────

@app.get(
    "/documents/{document_id}/view",
    response_model=DocumentViewResponse,
    tags=["Documents"],
)
@limiter.limit("30/minute")
def view_document(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if doc.document_category == "text":
        pdf_url = (
            f"/document/{document_id}/pdf"
            if doc.generated_pdf_path
            else None
        )
        return DocumentViewResponse(
            document_id=document_id,
            filename=doc.filename,
            document_category="text",
            total_pages=doc.total_pages,
            pdf_url=pdf_url,
            ocr_lines=[],
        )

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
        .all()
    )

    ocr_lines: list[OcrLine] = []
    for page in pages:
        for line_num, line in enumerate((page.extracted_text or "").split("\n"), start=1):
            if line.strip():
                ocr_lines.append(OcrLine(
                    page_number=page.page_number,
                    line_number=line_num,
                    text=line,
                    ocr_type=page.ocr_type,
                    confidence_score=page.confidence_score,
                ))

    return DocumentViewResponse(
        document_id=document_id,
        filename=doc.filename,
        document_category="scanned",
        total_pages=doc.total_pages,
        pdf_url=None,
        ocr_lines=ocr_lines,
    )


# ── Generate / rebuild PDF ────────────────────────────────────────────────────

@app.post(
    "/documents/{document_id}/generate-pdf",
    response_model=GeneratePdfResponse,
    tags=["Documents"],
)
@limiter.limit("5/minute")
def generate_pdf(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if doc.document_category == "text" and doc.generated_pdf_path:
        return GeneratePdfResponse(
            document_id=document_id,
            pdf_url=f"/document/{document_id}/pdf",
            message="PDF already generated at upload time.",
        )

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
        .all()
    )
    pages_data = [
        {
            "page_number":      p.page_number,
            "extracted_text":   p.extracted_text,
            "ocr_type":         p.ocr_type,
            "confidence_score": p.confidence_score,
        }
        for p in pages
    ]

    try:
        pdf_path = generate_searchable_pdf(
            document_id=document_id,
            document_category=doc.document_category,
            original_file_path=doc.file_path,
            pages=pages_data,
            original_filename=doc.filename,
        )
    except Exception as exc:
        logger.error(f"PDF generation failed for {document_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="PDF generation failed.")

    doc.generated_pdf_path = pdf_path
    db.commit()

    return GeneratePdfResponse(
        document_id=document_id,
        pdf_url=f"/document/{document_id}/pdf",
        message="PDF generated successfully.",
    )


# ── Download PDF ──────────────────────────────────────────────────────────────

@app.get("/document/{document_id}/pdf", tags=["Documents"])
@limiter.limit("20/minute")
def download_pdf(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user_flexible),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if not doc.generated_pdf_path or not Path(doc.generated_pdf_path).exists():
        raise HTTPException(
            status_code=404,
            detail="PDF not available. Use POST /documents/{id}/generate-pdf first.",
        )

    pdf_path = Path(doc.generated_pdf_path)
    filename = f"{Path(doc.filename).stem}.pdf"

    # Read file and return with inline Content-Disposition so the
    # browser renders it inside the iframe instead of downloading it
    with open(pdf_path, "rb") as f:
        content = f.read()

    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=\"{filename}\"",
            "Content-Length": str(len(content)),
            "Cache-Control": "private, max-age=3600",
        },
    )

# ── Dictionary — Meaning ──────────────────────────────────────────────────────

from pydantic import BaseModel

class WordMeaningResponse(BaseModel):
    word:    str
    meaning: str
    synonym: str
    example: str
    source:  str

@app.get(
    "/dictionary/{word}/meaning",
    response_model=WordMeaningResponse,
    tags=["Dictionary"],
    summary="Get meaning, synonym and example for a word",
)
@limiter.limit("30/minute")
def word_meaning(
    request: Request,
    word: str,
    current_user: User = Depends(get_current_user),
):
    """
    Look up a word:
    - Checks the local MySQL dictionary table first (fast indexed lookup).
    - Falls back to the free dictionary API if not cached, then saves it.
    - Returns meaning, synonym, and example if available.
    - No audio — pronunciation is handled by the frontend (Web Speech API).
    """
    from wordlogic import get_meaning
    result = get_meaning(word)
    if result["source"] == "Error":
        raise HTTPException(status_code=404, detail=f"No definition found for '{word}'.")
    return WordMeaningResponse(**result)



# ── Dictionary — Pronunciation ──────────────────────────────────────────────────────────────────────────────

@app.get(
    "/dictionary/{word}/pronounce",
    tags=["Dictionary"],
    summary="Stream pronunciation audio and return phonetic text for a word",
)
@limiter.limit("30/minute")
def word_pronounce(
    request: Request,
    word: str,
    current_user: User = Depends(get_current_user),
):
    """
    Returns MP3 audio stream + phonetic text for the given word.
    - No database interaction whatsoever.
    - Audio is streamed back as audio/mpeg.
    - Phonetic text (e.g. /prə-nʌnsɪeɪʃən/) is returned in the
      `X-Phonetic` response header.

    Frontend usage:
        const res = await fetch(`/dictionary/${word}/pronounce`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        const phonetic = res.headers.get("X-Phonetic"); // e.g. /nɛbjʊlə/
        const blob = await res.blob();
        const audio = new Audio(URL.createObjectURL(blob));
        audio.play();
    """
    from urllib.parse import quote
    from wordlogic import get_phonetic, get_pronunciation_audio

    phonetic   = get_phonetic(word)
    mp3_buffer = get_pronunciation_audio(word)

    # Phonetic strings contain Unicode (e.g. /həˈloʊ/) which cannot be
    # encoded as latin-1 headers. URL-encode so it stays ASCII-safe.
    safe_phonetic = quote(phonetic, safe="/ˈˌ") if phonetic else ""

    return StreamingResponse(
        mp3_buffer,
        media_type="audio/mpeg",
        headers={
            "Content-Disposition":           f'inline; filename="{word}.mp3"',
            "X-Phonetic":                    safe_phonetic,
            "Access-Control-Expose-Headers": "X-Phonetic",
        },
    )