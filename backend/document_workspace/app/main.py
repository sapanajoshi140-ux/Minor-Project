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

POST   /chat                                       — Q&A over indexed documents (full JSON)
POST   /chat/stream                                — Q&A over indexed documents (SSE streaming)
POST   /summarize                                  — Summarize arbitrary text (full JSON)
POST   /summarize/stream                           — Summarize arbitrary text (SSE streaming)
GET    /session/{session_id}/history               — Retrieve chat history for a session
DELETE /session/{session_id}                       — Clear chat history for a session

GET    /health                                     — Health check
"""

from __future__ import annotations

import logging
import os
import re as _re
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

load_dotenv()

# ── Path setup ────────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parent          # document_workspace/app
_RAG_DIR = _APP_DIR.parent / "rag"                  # document_workspace/rag
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

# ── App-local imports (resolved from document_workspace/app) ──────────────────
from config import setup_logging
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

# ── RAG imports (resolved from document_workspace/rag) ────────────────────────
from generate import (
    build_context,
    generate_answer,
    generate_answer_stream,
    summarize_text,
    summarize_text_stream,
)
from retrieve import retrieve, TOP_K, USE_HYBRID

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Session store (RAG multi-turn) ────────────────────────────────────────────
SESSIONS: dict[str, list[dict]] = {}

# ── Config ────────────────────────────────────────────────────────────────────
FRONTEND_URL  = os.getenv("FRONTEND_URL",  "http://localhost:5173")
CORS_ORIGINS  = os.getenv("CORS_ORIGINS",  "http://localhost:5173").split(",")


# ── Text cleaning (RAG) ───────────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    """Strip control characters that break JSON encoding (common in PDF text)."""
    text = text.replace('\f',   '\n')
    text = text.replace('\r\n', '\n')
    text = text.replace('\r',   '\n')
    text = text.replace('\x00', '')
    text = _re.sub(r'[\x01-\x08\x0b\x0e-\x1f\x7f]', '', text)
    return text.strip()


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
    from wordlogic import init_db
    init_db()
    logger.info("Dictionary table initialised.")
    _scheduler.add_job(_cleanup_revoked_tokens, "interval", hours=24, id="cleanup_revoked")
    _scheduler.start()
    logger.info("Startup complete — scheduler running.")
    yield
    _scheduler.shutdown(wait=False)
    logger.info("Shutdown complete.")


# ── App ───────────────────────────────────────────────────────────────────────

security = HTTPBearer()

app = FastAPI(
    title="Document Workspace API",
    version="2.0.0",
    description=(
        "RAG-powered document workspace: OCR, Q&A, summarization, and more. "
        "Document ingestion is handled by POST /upload. "
        "All document routes require JWT authentication."
    ),
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)

# Custom OpenAPI schema — adds the 🔒 Authorize button to Swagger UI
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title="Document Workspace API",
        version="2.0.0",
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


# ═════════════════════════════════════════════════════════════════════════════
# DOCUMENT ROUTES
# ═════════════════════════════════════════════════════════════════════════════

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

    # Remove RAG chunks for this document
    try:
        from ingest import delete_document as rag_delete  # document_workspace/rag/ingest.py
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


# ═════════════════════════════════════════════════════════════════════════════
# DICTIONARY ROUTES
# ═════════════════════════════════════════════════════════════════════════════

class WordMeaningResponse(BaseModel):
    word:    str
    meaning: str
    synonym: str = ""
    example: str = ""
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


# ═════════════════════════════════════════════════════════════════════════════
# RAG — Pydantic models
# ═════════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="The question to ask against the indexed documents.",
        examples=["What is the main topic of the document?"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Session ID for multi-turn conversation. "
            "Omit on the first message — the server will generate one and return it. "
            "Pass the returned session_id in all follow-up messages to maintain history."
        ),
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    doc_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "Restrict retrieval to specific document IDs. "
            "Omit (or pass null) to search across all indexed documents."
        ),
        examples=[["doc-uuid-1", "doc-uuid-2"]],
    )
    top_k: int = Field(
        default=TOP_K,
        ge=1,
        le=20,
        description="Number of document chunks to retrieve and pass to the LLM as context.",
        examples=[5],
    )
    use_hybrid: bool = Field(
        default=USE_HYBRID,
        description=(
            "Enable hybrid retrieval (dense vector search + BM25 keyword search fused via RRF). "
            "Set to false to use dense-only retrieval."
        ),
        examples=[True],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "question":   "What are the key findings of the report?",
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "doc_ids":    ["your-document-uuid-here"],
                "top_k":      5,
                "use_hybrid": True,
            }
        }
    }


class ChatResponse(BaseModel):
    answer: str = Field(description="The LLM-generated answer to the question.")
    session_id: str = Field(
        description="Session ID — pass this back in subsequent requests to maintain conversation history."
    )
    citations: List[dict] = Field(
        description=(
            "List of source chunks used to generate the answer. "
            "Each entry contains fields returned by generate_answer — "
            "typically: source_n, doc_id, page, score, text_snippet."
        )
    )
    sources_used: int = Field(
        description="Total number of chunks retrieved and passed to the LLM."
    )


class SummarizeRequest(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="The text to summarize. Maximum 50,000 characters.",
        examples=["Paste the document text or selected passage here..."],
    )
    length: Literal["short", "medium", "long", "bullets"] = Field(
        default="medium",
        description=(
            "Controls the output length and style:\n"
            "- **short** — 2-3 sentences\n"
            "- **medium** — 1 concise paragraph\n"
            "- **long** — detailed multi-paragraph summary\n"
            "- **bullets** — bullet-point list of key points"
        ),
        examples=["medium"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "text":   "The quarterly report shows revenue grew by 12% year-over-year...",
                "length": "medium",
            }
        }
    }


class SummarizeResponse(BaseModel):
    summary:    str = Field(description="The generated summary.")
    length:     str = Field(description="The length/style used.")
    char_count: int = Field(description="Character count of the input text.")


class SessionHistoryResponse(BaseModel):
    session_id: str        = Field(description="The session ID.")
    history:    List[dict] = Field(description="Ordered list of user/assistant turns.")


# ═════════════════════════════════════════════════════════════════════════════
# RAG — Chat & Summarize routes
# ═════════════════════════════════════════════════════════════════════════════

@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a question (full JSON response)",
    description=(
        "Send a question and get a full JSON response with the answer and citations. "
        "Use `session_id` to maintain multi-turn conversation history. "
        "Use `doc_ids` to restrict retrieval to specific documents."
    ),
    tags=["RAG"],
)
def chat(req: ChatRequest):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    history    = SESSIONS.setdefault(session_id, [])

    chunks = retrieve(
        query=question,
        doc_ids=req.doc_ids,
        top_k=req.top_k,
        use_hybrid=req.use_hybrid,
    )
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No indexed documents found. Please upload a document first.",
        )

    answer, citations = generate_answer(question, chunks, history)
    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": answer})

    return ChatResponse(
        answer=answer,
        session_id=session_id,
        citations=citations,
        sources_used=len(chunks),
    )


@app.post(
    "/chat/stream",
    summary="Ask a question (SSE streaming)",
    description=(
        "Same as POST `/chat` but streams the answer token-by-token via Server-Sent Events (SSE).\n\n"
        "**SSE event format:**\n"
        "- First event: `event: meta` — JSON with `session_id` and `citations`\n"
        "- Subsequent events: `data: <token>` — answer tokens as they are generated\n"
        "- Final event: `data: [DONE]` — signals end of stream"
    ),
    tags=["RAG"],
)
def chat_stream(req: ChatRequest):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    history    = SESSIONS.setdefault(session_id, [])

    chunks = retrieve(
        query=question,
        doc_ids=req.doc_ids,
        top_k=req.top_k,
        use_hybrid=req.use_hybrid,
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="No indexed documents found.")

    full_answer: list[str] = []

    def event_stream():
        import json as _json
        _, citations = build_context(chunks)
        yield f"event: meta\ndata: {_json.dumps({'session_id': session_id, 'citations': citations})}\n\n"

        for token in generate_answer_stream(question, chunks, history):
            full_answer.append(token)
            yield f"data: {token}\n\n"

        history.append({"role": "user",      "content": question})
        history.append({"role": "assistant", "content": "".join(full_answer)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post(
    "/summarize",
    response_model=SummarizeResponse,
    summary="Summarize text (full JSON response)",
    description=(
        "Pass any text (e.g. a copied passage from a document) and receive a concise summary. "
        "Use the `length` field to control output style."
    ),
    tags=["RAG"],
)
def summarize(req: SummarizeRequest):
    cleaned = _clean_text(req.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    try:
        summary = summarize_text(cleaned, length=req.length)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {e}")

    return SummarizeResponse(
        summary=summary,
        length=req.length,
        char_count=len(cleaned),
    )


@app.post(
    "/summarize/stream",
    summary="Summarize text (SSE streaming)",
    description=(
        "Same as POST `/summarize` but streams the summary token-by-token via SSE.\n\n"
        "**SSE event format:**\n"
        "- `data: <token>` — summary tokens as they are generated\n"
        "- `data: [DONE]` — signals end of stream\n"
        "- `event: error` — emitted if summarization fails mid-stream"
    ),
    tags=["RAG"],
)
def summarize_stream(req: SummarizeRequest):
    cleaned = _clean_text(req.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    def event_stream():
        try:
            for token in summarize_text_stream(cleaned, length=req.length):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"event: error\ndata: {e}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Session management ────────────────────────────────────────────────────────

@app.get(
    "/session/{session_id}/history",
    response_model=SessionHistoryResponse,
    summary="Get conversation history",
    description="Retrieve the full ordered chat history for a given session ID.",
    tags=["RAG"],
)
def get_history(session_id: str):
    return SessionHistoryResponse(
        session_id=session_id,
        history=SESSIONS.get(session_id, []),
    )


@app.delete(
    "/session/{session_id}",
    summary="Clear conversation history",
    description="Delete all chat history for the given session. The session ID can be reused afterwards.",
    tags=["RAG"],
)
def clear_session(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}


# ═════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═════════════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status:   str = Field(description="Service status — always 'ok' if reachable.")
    sessions: int = Field(description="Number of active in-memory RAG sessions.")


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns service status and the number of active in-memory RAG sessions.",
    tags=["Health"],
)
def health():
    return HealthResponse(
        status="ok",
        sessions=len(SESSIONS),
    )