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

── Dashboard ──────────────────────────────────────────────────────────────────
GET    /me/dashboard                               — all dashboard data in one call
PUT    /me/reading-goal                            — set daily reading goal (minutes)
POST   /reading-session/start                      — call when user opens a document
POST   /reading-session/end                        — call when user closes a document
GET    /me/vocabulary                              — paginated vocabulary list
GET    /me/vocabulary/search                       — search vocabulary words

── Dictionary ─────────────────────────────────────────────────────────────────
GET    /dictionary/{word}/meaning                  — meaning, synonym, example
GET    /dictionary/{word}/pronounce                — MP3 audio + phonetic header

── RAG ────────────────────────────────────────────────────────────────────────
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
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional

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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func, case
from sqlalchemy.orm import Session

load_dotenv()

# ── Path setup ────────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parent
_RAG_DIR = _APP_DIR.parent / "rag"
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

# ── App-local imports ─────────────────────────────────────────────────────────
from config import setup_logging
from database import (
    Document,
    DocumentPage,
    ReadingSession,
    ReadingGoal,
    RevokedToken,
    SessionLocal,
    User,
    UserVocabulary,
    USER_STORAGE_LIMIT_BYTES,
    get_db,
)
from dependencies import get_current_user, get_current_user_flexible
from routes.upload import router as upload_router
from schemas import (
    # existing
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
    # dashboard
    ReadingSessionStartRequest,
    ReadingSessionStartResponse,
    ReadingSessionEndRequest,
    ReadingSessionEndResponse,
    ReadingGoalRequest,
    ReadingGoalResponse,
    DashboardResponse,
    DashboardStatsResponse,
    DailyReadingEntry,
    DocumentTimeEntry,
    VocabularyEntry,
    VocabularyListResponse,
    # dictionary
    WordMeaningResponse,
    # rag
    ChatRequest,
    ChatResponse,
    SummarizeRequest,
    SummarizeResponse,
    SessionHistoryResponse,
    # health
    HealthResponse,
)
from services.pdf_generator_service import generate_searchable_pdf

# ── RAG imports ───────────────────────────────────────────────────────────────
from generate import (
    build_context,
    generate_answer,
    generate_answer_stream,
    summarize_text,
    summarize_text_stream,
)
from retrieve import retrieve, TOP_K, USE_HYBRID

logger = logging.getLogger(__name__)

SESSIONS: dict[str, list[dict]] = {}

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# ── Tuneable constants (all env-configurable) ─────────────────────────────────
DEFAULT_DAILY_GOAL_MIN      = int(os.getenv("DEFAULT_DAILY_GOAL_MIN",   "60"))
MIN_SESSION_DURATION_SECS   = int(os.getenv("MIN_SESSION_DURATION_SECS", "5"))
DASHBOARD_CHART_DAYS        = int(os.getenv("DASHBOARD_CHART_DAYS",     "14"))
DASHBOARD_RECENT_DOCS_LIMIT = int(os.getenv("DASHBOARD_RECENT_DOCS_LIMIT", "5"))
DASHBOARD_VOCAB_LIMIT       = int(os.getenv("DASHBOARD_VOCAB_LIMIT",    "7"))


# ── Text cleaning ─────────────────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    text = text.replace('\f',   '\n')
    text = text.replace('\r\n', '\n')
    text = text.replace('\r',   '\n')
    text = text.replace('\x00', '')
    text = _re.sub(r'[\x01-\x08\x0b\x0e-\x1f\x7f]', '', text)
    return text.strip()


# ── Startup / shutdown ────────────────────────────────────────────────────────
def _cleanup_revoked_tokens() -> None:
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
def _get_owned_document(document_id: str, db: Session, current_user: User) -> Document:
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


# ── Dashboard helpers ─────────────────────────────────────────────────────────

def _get_daily_goal(user_id: int, db: Session) -> int:
    """Return user's daily goal in minutes, defaulting to 60."""
    goal = db.query(ReadingGoal).filter(ReadingGoal.user_id == user_id).first()
    return goal.daily_goal_min if goal else DEFAULT_DAILY_GOAL_MIN


def _compute_streaks(user_id: int, db: Session) -> tuple[int, int]:
    """
    Compute (current_streak, best_streak) in days.

    A day counts toward the streak if the user has at least one completed
    reading session (duration_seconds is not None) on that calendar day.
    Sessions are grouped by date in the DB's local timezone.
    """
    # Pull all distinct dates (UTC) on which the user completed a session.
    rows = (
        db.query(func.date(ReadingSession.started_at).label("day"))
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.duration_seconds.isnot(None),
        )
        .distinct()
        .order_by(func.date(ReadingSession.started_at).desc())
        .all()
    )

    if not rows:
        return 0, 0

    active_dates = sorted({row.day for row in rows}, reverse=True)
    today = date.today()

    # ── Current streak ────────────────────────────────────────────────────────
    current = 0
    # Allow today OR yesterday as the most recent active day so that a user
    # who read yesterday but not yet today doesn't lose their streak.
    expected = today if active_dates[0] == today else today - timedelta(days=1)

    for d in active_dates:
        if d == expected:
            current += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break   # gap — streak ends

    # ── Best streak ───────────────────────────────────────────────────────────
    best    = 0
    run     = 0
    prev    = None
    for d in sorted(active_dates):
        if prev is None or d == prev + timedelta(days=1):
            run += 1
        else:
            run = 1
        best = max(best, run)
        prev = d

    return current, best


def _build_daily_chart(user_id: int, db: Session, days: int = 14) -> List[DailyReadingEntry]:
    """
    Return one DailyReadingEntry per calendar day for the last `days` days
    (including today), with minutes read on that day (0 if none).
    """
    since = datetime.utcnow().date() - timedelta(days=days - 1)

    rows = (
        db.query(
            func.date(ReadingSession.started_at).label("day"),
            func.sum(ReadingSession.duration_seconds).label("total_secs"),
        )
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.duration_seconds.isnot(None),
            func.date(ReadingSession.started_at) >= since,
        )
        .group_by(func.date(ReadingSession.started_at))
        .all()
    )

    day_map: dict[date, float] = {row.day: (row.total_secs or 0) / 60 for row in rows}

    chart: List[DailyReadingEntry] = []
    for i in range(days):
        d = since + timedelta(days=i)
        chart.append(DailyReadingEntry(
            date=d.strftime("%Y-%m-%d"),
            minutes=round(day_map.get(d, 0.0), 1),
        ))
    return chart


def _build_recent_documents(
    user_id: int, db: Session, limit: int = 5
) -> List[DocumentTimeEntry]:
    """
    Return the most recently uploaded documents for the user,
    each annotated with total seconds spent reading it.
    """
    docs = (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
        .limit(limit)
        .all()
    )

    if not docs:
        return []

    doc_ids = [d.id for d in docs]

    # Sum of duration_seconds per document for this user.
    time_rows = (
        db.query(
            ReadingSession.document_id,
            func.sum(ReadingSession.duration_seconds).label("total_secs"),
        )
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.document_id.in_(doc_ids),
            ReadingSession.duration_seconds.isnot(None),
        )
        .group_by(ReadingSession.document_id)
        .all()
    )
    time_map: dict[str, int] = {r.document_id: (r.total_secs or 0) for r in time_rows}

    return [
        DocumentTimeEntry(
            id=d.id,
            filename=d.filename,
            file_type=d.file_type or "",
            file_size_bytes=d.file_size_bytes,
            total_pages=d.total_pages,
            created_at=d.created_at,
            time_spent_seconds=time_map.get(d.id, 0),
        )
        for d in docs
    ]


def _build_vocabulary_entries(
    user_id: int, db: Session, limit: int = 7
) -> List[VocabularyEntry]:
    """
    Return the most recently looked-up vocabulary words for the user,
    enriched with meanings from the dictionary table.
    """
    from wordlogic import get_meaning

    rows = (
        db.query(UserVocabulary)
        .filter(UserVocabulary.user_id == user_id)
        .order_by(UserVocabulary.looked_up_at.desc())
        .limit(limit)
        .all()
    )

    entries: List[VocabularyEntry] = []
    for row in rows:
        meaning_data = get_meaning(row.word)
        doc_name = None
        if row.document_id and row.document:
            doc_name = row.document.filename

        entries.append(VocabularyEntry(
            word=row.word,
            meaning=meaning_data.get("meaning", ""),
            synonym=meaning_data.get("synonym"),
            document_name=doc_name,
            document_id=row.document_id,
            looked_up_at=row.looked_up_at,
        ))
    return entries


# ═════════════════════════════════════════════════════════════════════════════
# DOCUMENT ROUTES
# ═════════════════════════════════════════════════════════════════════════════

# ── Storage usage ─────────────────────────────────────────────────────────────

@app.get("/me/storage", response_model=StorageUsageResponse, tags=["User"])
def get_storage_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
    q: Optional[str] = Query(default=None, description="Search by filename (partial match)."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if limit > 100:
        limit = 100
    offset = (page - 1) * limit

    base_filter = db.query(Document).filter(Document.user_id == current_user.id)

    if q and q.strip():
        base_filter = base_filter.filter(Document.filename.like(f"%{q.strip()}%"))

    total = base_filter.count()
    docs  = (
        base_filter
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

    try:
        from ingest import delete_document as rag_delete
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
            "Content-Disposition": f'inline; filename="{filename}"',
            "Content-Length": str(len(content)),
            "Cache-Control": "private, max-age=3600",
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
# DASHBOARD ROUTES
# ═════════════════════════════════════════════════════════════════════════════

# ── Full dashboard (single call) ──────────────────────────────────────────────

@app.get(
    "/me/dashboard",
    response_model=DashboardResponse,
    tags=["Dashboard"],
    summary="Get all dashboard data in one request",
    description=(
        "Returns the four stat cards, the 14-day reading chart, the 5 most recent "
        "documents with time-spent, and the 7 most recently looked-up vocabulary words. "
        "This is the primary endpoint for the dashboard page — one call, everything."
    ),
)
@limiter.limit("30/minute")
def get_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user.id

    # ── All-time total seconds ─────────────────────────────────────────────
    total_secs_row = (
        db.query(func.sum(ReadingSession.duration_seconds))
        .filter(
            ReadingSession.user_id == uid,
            ReadingSession.duration_seconds.isnot(None),
        )
        .scalar()
    )
    total_secs = total_secs_row or 0

    # ── Today's seconds ───────────────────────────────────────────────────
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_secs_row = (
        db.query(func.sum(ReadingSession.duration_seconds))
        .filter(
            ReadingSession.user_id == uid,
            ReadingSession.duration_seconds.isnot(None),
            ReadingSession.started_at >= today_start,
        )
        .scalar()
    )
    today_secs = today_secs_row or 0

    # ── Documents read (with at least 1 session) ──────────────────────────
    docs_read = (
        db.query(func.count(func.distinct(ReadingSession.document_id)))
        .filter(
            ReadingSession.user_id == uid,
            ReadingSession.duration_seconds.isnot(None),
        )
        .scalar()
    ) or 0

    # ── Total docs uploaded ───────────────────────────────────────────────
    total_docs = (
        db.query(func.count(Document.id))
        .filter(Document.user_id == uid)
        .scalar()
    ) or 0

    # ── Streak ────────────────────────────────────────────────────────────
    current_streak, best_streak = _compute_streaks(uid, db)

    # ── Daily goal ────────────────────────────────────────────────────────
    daily_goal = _get_daily_goal(uid, db)

    stats = DashboardStatsResponse(
        total_time_read_minutes=round(total_secs / 60, 1),
        today_read_minutes=round(today_secs / 60, 1),
        daily_goal_minutes=daily_goal,
        documents_read=docs_read,
        total_documents_uploaded=total_docs,
        current_streak_days=current_streak,
        best_streak_days=best_streak,
    )

    return DashboardResponse(
        stats=stats,
        daily_chart=_build_daily_chart(uid, db, days=DASHBOARD_CHART_DAYS),
        recent_documents=_build_recent_documents(uid, db, limit=DASHBOARD_RECENT_DOCS_LIMIT),
        vocabulary=_build_vocabulary_entries(uid, db, limit=DASHBOARD_VOCAB_LIMIT),
    )


# ── Reading goal ──────────────────────────────────────────────────────────────

@app.put(
    "/me/reading-goal",
    response_model=ReadingGoalResponse,
    tags=["Dashboard"],
    summary="Set your daily reading goal",
    description="Set or update your daily reading goal in minutes. Default is 60 minutes.",
)
@limiter.limit("10/minute")
def set_reading_goal(
    request: Request,
    data: ReadingGoalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.query(ReadingGoal).filter(ReadingGoal.user_id == current_user.id).first()

    if goal:
        goal.daily_goal_min = data.daily_goal_min
    else:
        goal = ReadingGoal(user_id=current_user.id, daily_goal_min=data.daily_goal_min)
        db.add(goal)

    db.commit()

    return ReadingGoalResponse(
        user_id=current_user.id,
        daily_goal_min=data.daily_goal_min,
        message=f"Daily reading goal set to {data.daily_goal_min} minutes.",
    )


# ── Reading session — start ───────────────────────────────────────────────────

@app.post(
    "/reading-session/start",
    response_model=ReadingSessionStartResponse,
    tags=["Dashboard"],
    summary="Start a reading session",
    description=(
        "Call this when the user opens a document to read. "
        "Returns a session_id that must be passed to POST /reading-session/end "
        "when the user finishes reading."
    ),
)
@limiter.limit("30/minute")
def start_reading_session(
    request: Request,
    data: ReadingSessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify the document exists and belongs to this user.
    _get_owned_document(data.document_id, db, current_user)

    session = ReadingSession(
        user_id=current_user.id,
        document_id=data.document_id,
        started_at=datetime.utcnow(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    logger.info(
        f"Reading session {session.id} started — "
        f"user={current_user.email}, doc={data.document_id}"
    )

    return ReadingSessionStartResponse(
        session_id=session.id,
        document_id=data.document_id,
        started_at=session.started_at,
        message="Reading session started.",
    )


# ── Reading session — end ─────────────────────────────────────────────────────

@app.post(
    "/reading-session/end",
    response_model=ReadingSessionEndResponse,
    tags=["Dashboard"],
    summary="End a reading session",
    description=(
        "Call this when the user closes or navigates away from a document. "
        "Computes and stores the duration. "
        "Sessions shorter than 5 seconds are silently discarded to filter accidental opens."
    ),
)
@limiter.limit("30/minute")
def end_reading_session(
    request: Request,
    data: ReadingSessionEndRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    MIN_DURATION_SECONDS = MIN_SESSION_DURATION_SECS

    session = (
        db.query(ReadingSession)
        .filter(
            ReadingSession.id == data.session_id,
            ReadingSession.user_id == current_user.id,   # ownership check
        )
        .first()
    )

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Reading session not found or does not belong to you.",
        )

    if session.ended_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Reading session has already been ended.",
        )

    ended_at         = datetime.utcnow()
    duration_seconds = int((ended_at - session.started_at).total_seconds())

    if duration_seconds < MIN_DURATION_SECONDS:
        # Discard the session — don't pollute stats with accidental opens.
        db.delete(session)
        db.commit()
        logger.debug(
            f"Reading session {data.session_id} discarded "
            f"(duration {duration_seconds}s < {MIN_DURATION_SECONDS}s minimum)."
        )
        return ReadingSessionEndResponse(
            session_id=data.session_id,
            document_id=session.document_id,
            duration_seconds=0,
            duration_minutes=0.0,
            message="Session too short — discarded.",
        )

    session.ended_at         = ended_at
    session.duration_seconds = duration_seconds
    db.commit()

    logger.info(
        f"Reading session {session.id} ended — "
        f"user={current_user.email}, duration={duration_seconds}s"
    )

    return ReadingSessionEndResponse(
        session_id=session.id,
        document_id=session.document_id,
        duration_seconds=duration_seconds,
        duration_minutes=round(duration_seconds / 60, 2),
        message="Reading session recorded.",
    )


# ── Vocabulary — paginated list ───────────────────────────────────────────────

@app.get(
    "/me/vocabulary",
    response_model=VocabularyListResponse,
    tags=["Dashboard"],
    summary="List your vocabulary words",
    description="Returns all words you have looked up, most recent first, paginated.",
)
@limiter.limit("30/minute")
def list_vocabulary(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from wordlogic import get_meaning

    offset = (page - 1) * limit

    total = (
        db.query(func.count(UserVocabulary.id))
        .filter(UserVocabulary.user_id == current_user.id)
        .scalar()
    ) or 0

    rows = (
        db.query(UserVocabulary)
        .filter(UserVocabulary.user_id == current_user.id)
        .order_by(UserVocabulary.looked_up_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    entries: List[VocabularyEntry] = []
    for row in rows:
        meaning_data = get_meaning(row.word)
        doc_name = None
        if row.document_id and row.document:
            doc_name = row.document.filename

        entries.append(VocabularyEntry(
            word=row.word,
            meaning=meaning_data.get("meaning", ""),
            synonym=meaning_data.get("synonym"),
            document_name=doc_name,
            document_id=row.document_id,
            looked_up_at=row.looked_up_at,
        ))

    return VocabularyListResponse(
        total=total,
        page=page,
        limit=limit,
        words=entries,
    )


# ── Vocabulary — search ───────────────────────────────────────────────────────

@app.get(
    "/me/vocabulary/search",
    response_model=VocabularyListResponse,
    tags=["Dashboard"],
    summary="Search your vocabulary words",
    description="Search through your looked-up words by partial word match.",
)
@limiter.limit("30/minute")
def search_vocabulary(
    request: Request,
    q: str = Query(..., min_length=1, description="Search term (partial word match)."),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from wordlogic import get_meaning

    offset  = (page - 1) * limit
    pattern = f"%{q.lower()}%"

    total = (
        db.query(func.count(UserVocabulary.id))
        .filter(
            UserVocabulary.user_id == current_user.id,
            UserVocabulary.word.like(pattern),
        )
        .scalar()
    ) or 0

    rows = (
        db.query(UserVocabulary)
        .filter(
            UserVocabulary.user_id == current_user.id,
            UserVocabulary.word.like(pattern),
        )
        .order_by(UserVocabulary.looked_up_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    entries: List[VocabularyEntry] = []
    for row in rows:
        meaning_data = get_meaning(row.word)
        doc_name = None
        if row.document_id and row.document:
            doc_name = row.document.filename

        entries.append(VocabularyEntry(
            word=row.word,
            meaning=meaning_data.get("meaning", ""),
            synonym=meaning_data.get("synonym"),
            document_name=doc_name,
            document_id=row.document_id,
            looked_up_at=row.looked_up_at,
        ))

    return VocabularyListResponse(
        total=total,
        page=page,
        limit=limit,
        words=entries,
    )


# ═════════════════════════════════════════════════════════════════════════════
# DICTIONARY ROUTES
# ═════════════════════════════════════════════════════════════════════════════


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
    document_id: Optional[str] = Query(
        default=None,
        description="ID of the document the user is currently reading (used to link vocabulary).",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Look up a word and automatically log it to the user's vocabulary.

    Pass `document_id` as a query param when the user looks up a word
    while reading a specific document — this links the word to that doc
    in the vocabulary panel.

    Example: GET /dictionary/ephemeral/meaning?document_id=<uuid>
    """
    from wordlogic import get_meaning, log_vocabulary_lookup

    result = get_meaning(word)
    if result["source"] == "Error":
        raise HTTPException(status_code=404, detail=f"No definition found for '{word}'.")

    # Log the lookup — links the word to the user and optionally to a document.
    log_vocabulary_lookup(
        user_id=current_user.id,
        word=word,
        document_id=document_id,
        db_session=db,
    )

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
# RAG — Chat & Summarize routes
# ═════════════════════════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse, tags=["RAG"])
def chat(req: ChatRequest):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    history    = SESSIONS.setdefault(session_id, [])

    chunks = retrieve(query=question, doc_ids=req.doc_ids, top_k=req.top_k, use_hybrid=req.use_hybrid)
    if not chunks:
        raise HTTPException(status_code=404, detail="No indexed documents found. Please upload a document first.")

    answer, citations = generate_answer(question, chunks, history)
    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": answer})

    return ChatResponse(answer=answer, session_id=session_id, citations=citations, sources_used=len(chunks))


@app.post("/chat/stream", tags=["RAG"])
def chat_stream(req: ChatRequest):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    history    = SESSIONS.setdefault(session_id, [])

    chunks = retrieve(query=question, doc_ids=req.doc_ids, top_k=req.top_k, use_hybrid=req.use_hybrid)
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


@app.post("/summarize", response_model=SummarizeResponse, tags=["RAG"])
def summarize(req: SummarizeRequest):
    cleaned = _clean_text(req.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    try:
        summary = summarize_text(cleaned, length=req.length)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {e}")

    return SummarizeResponse(summary=summary, length=req.length, char_count=len(cleaned))


@app.post("/summarize/stream", tags=["RAG"])
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


@app.get("/session/{session_id}/history", response_model=SessionHistoryResponse, tags=["RAG"])
def get_history(session_id: str):
    return SessionHistoryResponse(session_id=session_id, history=SESSIONS.get(session_id, []))


@app.delete("/session/{session_id}", tags=["RAG"])
def clear_session(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"status": "cleared", "session_id": session_id}


# ═════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health():
    return HealthResponse(status="ok", sessions=len(SESSIONS))