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

── Notes ──────────────────────────────────────────────────────────────────────
GET    /documents/{document_id}/notes              — fetch all page notes for a document
PUT    /documents/{document_id}/pages/{n}/note     — create or update a page note
DELETE /documents/{document_id}/pages/{n}/note     — delete a page note

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

import asyncio
import logging
import os
import re as _re
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, date, timedelta
from itertools import zip_longest
from pathlib import Path
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
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

# ── Path setup ────────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parent
_RAG_DIR = _APP_DIR.parent / "rag"
if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))

# ── App-local imports ─────────────────────────────────────────────────────────
from config import (
    setup_logging,
    FRONTEND_URL,
    CORS_ORIGINS,
    DEFAULT_DAILY_GOAL_MIN,
    MIN_SESSION_DURATION_SECS,
    DASHBOARD_CHART_DAYS,
    DASHBOARD_RECENT_DOCS_LIMIT,
    DASHBOARD_VOCAB_LIMIT,
    USER_STORAGE_LIMIT_BYTES,
)
from database import (
    Document,
    DocumentPage,
    PageNote,
    ReadingSession,
    ReadingGoal,
    RevokedToken,
    SessionLocal,
    User,
    UserVocabulary,
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
    FormattingSummary,
    GeneratePdfResponse,
    OcrLine,
    PageResponse,
    PageUpdateRequest,
    PageUpdateResponse,
    PaginatedPagesResponse,
    StorageUsageResponse,
    DocumentListResponse,
    # formatting
    FormattingStatusResponse,
    PageFormattingEntry,
    ReformatResponse,
    # dashboard
    ReadingSessionStartRequest,
    ReadingSessionStartResponse,
    ReadingSessionEndRequest,
    ReadingSessionEndResponse,
    ReadingSessionHeartbeatRequest,
    ReadingGoalRequest,
    ReadingGoalResponse,
    DashboardResponse,
    DashboardStatsResponse,
    DailyReadingEntry,
    DocumentTimeEntry,
    VocabularyEntry,
    VocabularyListResponse,
    # notes
    PageNoteUpsertRequest,
    PageNoteResponse,
    DocumentNotesResponse,
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
    # streaming
    PageStreamEvent,
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


def _session_key(user_id: int, session_id: str) -> str:
    """Namespace chat history by user so users cannot read each other's sessions."""
    return f"{user_id}:{session_id}"




# ── Text cleaning ─────────────────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    text = text.replace('\f',   '\n')
    text = text.replace('\r\n', '\n')
    text = text.replace('\r',   '\n')
    text = text.replace('\x00', '')
    text = _re.sub(r'[\x01-\x08\x0b\x0e-\x1f\x7f]', '', text)
    return text.strip()


# Patterns that match LLM meta-commentary lines that must never appear in
# stored formatted_text.  Each pattern is matched against individual lines
# (case-insensitive).  A line that matches ANY pattern is dropped entirely.
_LLM_ARTIFACT_PATTERNS: list[_re.Pattern] = [
    # "Note: …" / "Note — …" footnotes added by Ollama
    _re.compile(r'^\s*note\s*[:\-\u2013\u2014]', _re.IGNORECASE),
    # "Here is the reformatted text:" / "Here's the cleaned version:"
    _re.compile(r'^\s*here\s+(is|are|\'s)\s+the\s+', _re.IGNORECASE),
    # "I fixed …" / "I restored …" / "I corrected …" / "I removed …"
    _re.compile(r'^\s*i\s+(fixed|restored|corrected|removed|cleaned|rewrote)', _re.IGNORECASE),
    # "The following …" preamble lines
    _re.compile(r'^\s*the following (text|content|document)', _re.IGNORECASE),
    # Markdown fences that the model may wrap output in
    _re.compile(r'^\s*```'),
    # Lone OCR artifact numbers that TrOCR often prepends (e.g. "1903", "1940s.")
    # Only strip if the entire line is a bare year/decade token with no other words.
    _re.compile(r'^\s*\d{4}s?\.?\s*$'),
]


def _strip_llm_artifacts(text: str) -> str:
    """
    Remove LLM meta-commentary lines from Ollama-formatted OCR output.

    Drops lines that match ``_LLM_ARTIFACT_PATTERNS`` and collapses runs of
    three or more consecutive blank lines down to two (preserves paragraph
    breaks without leaving gaping whitespace).

    This is called on every ``formatted_text`` value before it is stored in
    the database, so the artefacts can never reach the client.
    """
    lines = text.splitlines()
    cleaned: list[str] = []
    blank_run = 0

    for line in lines:
        # Drop lines that are LLM commentary.
        if any(p.search(line) for p in _LLM_ARTIFACT_PATTERNS):
            logger.debug(f"_strip_llm_artifacts: dropped line: {line!r}")
            continue

        if line.strip() == "":
            blank_run += 1
            # Allow at most 2 consecutive blank lines (paragraph separator).
            if blank_run <= 2:
                cleaned.append(line)
        else:
            blank_run = 0
            cleaned.append(line)

    return "\n".join(cleaned).strip()


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
    setup_logging()
    from wordlogic import init_db
    init_db()
    logger.info("Dictionary table initialised.")
    _scheduler.add_job(_cleanup_revoked_tokens, "interval", hours=24, id="cleanup_revoked")
    _scheduler.start()

    # ── Start the OCR Ollama formatting background worker ─────────────────────
    # The worker drains the in-process FORMAT_QUEUE that upload.py populates.
    # It runs for the entire lifetime of the server and is cancelled on shutdown.
    _fmt_task = None
    try:
        from services.ocr_formatter import run_formatting_worker
        _fmt_task = asyncio.create_task(run_formatting_worker(), name="ocr_formatter")
        logger.info("OCR formatting worker task created.")
    except Exception as exc:
        logger.warning(
            f"OCR formatting worker could not start: {exc}. "
            f"Uploaded documents will display raw OCR text only."
        )

    logger.info("Startup complete — scheduler running.")
    yield

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    if _fmt_task and not _fmt_task.done():
        _fmt_task.cancel()
        try:
            await _fmt_task
        except asyncio.CancelledError:
            pass
        logger.info("OCR formatting worker stopped.")

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


# Minimum active reading seconds required for a day to count toward a streak.
_STREAK_MIN_SECONDS = 20 * 60  # 20 minutes


def _compute_streaks(user_id: int, db: Session) -> tuple[int, int]:
    """
    Compute (current_streak, best_streak) in days.

    A day counts toward the streak only if the user's total *active* reading
    time on that calendar day reaches at least 20 minutes.  Sessions that are
    shorter than the threshold individually still aggregate — it's the daily
    total that must hit 20 min.

    "Active" means duration_seconds is not None (i.e. the session was properly
    ended and was long enough to survive the MIN_SESSION_DURATION_SECS filter
    applied in end_reading_session).
    """
    # Aggregate total seconds per calendar day across ALL documents.
    rows = (
        db.query(
            func.date(ReadingSession.started_at).label("day"),
            func.sum(ReadingSession.duration_seconds).label("total_secs"),
        )
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.duration_seconds.isnot(None),
        )
        .group_by(func.date(ReadingSession.started_at))
        .all()
    )

    if not rows:
        return 0, 0

    # Keep only days that meet the 20-minute threshold.
    active_dates = sorted(
        {row.day for row in rows if (row.total_secs or 0) >= _STREAK_MIN_SECONDS},
        reverse=True,
    )

    if not active_dates:
        return 0, 0

    today = date.today()

    # ── Current streak ────────────────────────────────────────────────────────
    current = 0
    expected = today if active_dates[0] == today else today - timedelta(days=1)

    for d in active_dates:
        if d == expected:
            current += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break

    # ── Best streak ───────────────────────────────────────────────────────────
    best = 0
    run  = 0
    prev = None
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


def _build_documents_with_time(
    user_id: int,
    db: Session,
    *,
    limit: Optional[int] = None,
) -> List[DocumentTimeEntry]:
    """
    Return documents for the user, each annotated with total *active* seconds
    spent reading it, aggregated across ALL sessions with no document cap.

    Pass limit=N to cap the display list (most-recently-uploaded first).
    The time aggregation always covers every document regardless of limit.
    """
    # Aggregate time for ALL documents in one query — not capped to recent docs.
    time_rows = (
        db.query(
            ReadingSession.document_id,
            func.sum(ReadingSession.duration_seconds).label("total_secs"),
        )
        .filter(
            ReadingSession.user_id == user_id,
            ReadingSession.duration_seconds.isnot(None),
        )
        .group_by(ReadingSession.document_id)
        .all()
    )
    time_map: dict[str, int] = {r.document_id: (r.total_secs or 0) for r in time_rows}

    # Fetch documents for display (optionally capped).
    q = (
        db.query(Document)
        .filter(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    )
    if limit is not None:
        q = q.limit(limit)
    docs = q.all()

    if not docs:
        return []

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

    Uses a single JOIN query to fetch meanings in bulk instead of one
    get_meaning() call per word (which would cause N+1 DB round-trips).
    Falls back to the API only for words not yet in the dictionary table.
    """
    from wordlogic import Dictionary, get_meaning

    rows = (
        db.query(UserVocabulary)
        .filter(UserVocabulary.user_id == user_id)
        .order_by(UserVocabulary.looked_up_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []

    # Bulk-fetch dictionary rows for all words in one query.
    words = [row.word for row in rows]
    dict_rows = (
        db.query(Dictionary)
        .filter(Dictionary.word.in_(words))
        .all()
    )
    dict_map: dict[str, Dictionary] = {d.word: d for d in dict_rows}

    entries: List[VocabularyEntry] = []
    for row in rows:
        d = dict_map.get(row.word)
        if d:
            meaning = d.meaning or "Meaning not found."
            synonym = d.synonym or None
        else:
            # Word not cached yet — hit the API (and let get_meaning persist it).
            api = get_meaning(row.word)
            meaning = api.get("meaning", "Meaning not found.")
            synonym = api.get("synonym") or None

        doc_name = None
        if row.document_id and row.document:
            doc_name = row.document.filename

        entries.append(VocabularyEntry(
            word=row.word,
            meaning=meaning,
            synonym=synonym,
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

    # Compute display_text: prefer formatted_text when formatting is complete.
    raw_fmt = (
        page.formatted_text
        if page.formatting_status == "completed" and page.formatted_text
        else None
    )
    display = _strip_llm_artifacts(raw_fmt) if raw_fmt else (page.extracted_text or "")
    response = PageResponse.model_validate(page)
    response.display_text = display
    return response


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

    def _to_page_response(p) -> PageResponse:
        raw_fmt = (
            p.formatted_text
            if p.formatting_status == "completed" and p.formatted_text
            else None
        )
        display = _strip_llm_artifacts(raw_fmt) if raw_fmt else (p.extracted_text or "")
        r = PageResponse.model_validate(p)
        r.display_text = display
        return r

    return PaginatedPagesResponse(
        document_id=document_id,
        total_pages=doc.total_pages or 0,
        page=page,
        limit=limit,
        pages=[_to_page_response(p) for p in pages],
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
        # Use formatted_text when available for better line quality.
        raw_fmt = (
            page.formatted_text
            if page.formatting_status == "completed" and page.formatted_text
            else None
        )
        display_text = (
            _strip_llm_artifacts(raw_fmt) if raw_fmt else (page.extracted_text or "")
        )
        for line_num, line in enumerate(display_text.split("\n"), start=1):
            if line.strip():
                yield json.dumps({
                    "page_number":      page_number,
                    "line_number":      line_num,
                    "text":             line,
                    "ocr_type":         page.ocr_type,
                    "confidence_score": page.confidence_score,
                    "formatting_status": page.formatting_status,
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
            if page.formatting_status == "completed" and page.formatted_text:
              page.formatted_text = entry.extracted_text
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

    # ── Build formatting summary for UX status banner ─────────────────────────
    status_counts: dict[str, int] = {
        "pending": 0, "processing": 0, "completed": 0,
        "failed": 0, "skipped": 0,
    }
    for pg in pages:
        key = pg.formatting_status or "pending"
        status_counts[key] = status_counts.get(key, 0) + 1

    total_pg = len(pages)
    all_done = total_pg > 0 and status_counts["pending"] == 0 and status_counts["processing"] == 0

    fmt_summary = FormattingSummary(
        total_pages=total_pg,
        pending=status_counts["pending"],
        processing=status_counts["processing"],
        completed=status_counts["completed"],
        failed=status_counts["failed"],
        skipped=status_counts["skipped"],
        all_done=all_done,
    )

    # ── Build OcrLine list, preferring formatted_text when ready ─────────────
    ocr_lines: list[OcrLine] = []
    for page in pages:
        # display_text: formatted_text when complete, else raw OCR text.
        # _strip_llm_artifacts is applied here as a safety net in case the
        # formatting worker stored commentary before the fix was deployed.
        raw_formatted = (
            page.formatted_text
            if page.formatting_status == "completed" and page.formatted_text
            else None
        )
        display_text = (
            _strip_llm_artifacts(raw_formatted) if raw_formatted else (page.extracted_text or "")
        )

        raw_text = page.extracted_text or ""

        for line_num, (disp_line, raw_line) in enumerate(
            zip_longest(
                display_text.split("\n"),
                raw_text.split("\n"),
                fillvalue="",
            ),
            start=1,
        ):
            if disp_line.strip():
                ocr_lines.append(OcrLine(
                    page_number=page.page_number,
                    line_number=line_num,
                    text=disp_line,
                    raw_text=raw_line if raw_line != disp_line else None,
                    ocr_type=page.ocr_type,
                    confidence_score=page.confidence_score,
                    formatting_status=page.formatting_status,
                ))

    return DocumentViewResponse(
        document_id=document_id,
        filename=doc.filename,
        document_category="scanned",
        total_pages=doc.total_pages,
        pdf_url=f"/document/{document_id}/pdf" if doc.generated_pdf_path else None,
        ocr_lines=ocr_lines,
        formatting_summary=fmt_summary,
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
            "page_number": p.page_number,
            # User edits are saved to extracted_text.
            # If formatting ran after the edit it lives in formatted_text —
            # prefer extracted_text (user edit) first, then formatted_text,
            # then fall back to raw OCR.
            "extracted_text": (
                p.extracted_text
                if p.extracted_text and p.extracted_text.strip()
                else p.formatted_text or ""
            ),
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
# OCR FORMATTING ROUTES
# ═════════════════════════════════════════════════════════════════════════════

# ── Formatting status ─────────────────────────────────────────────────────────

@app.get(
    "/document/{document_id}/formatting-status",
    response_model=FormattingStatusResponse,
    tags=["Documents"],
    summary="Get Ollama formatting progress for all pages of a document",
    description=(
        "Poll this endpoint every 3–5 seconds while "
        "summary.all_done is False.  Once all_done is True, "
        "refresh GET /documents/{id}/view to display formatted text.\n\n"
        "Page formatting_status values:\n"
        "- **pending**    — queued, not yet started\n"
        "- **processing** — Ollama call in flight\n"
        "- **completed**  — formatted_text available\n"
        "- **failed**     — retries exhausted; workspace shows raw OCR text\n"
        "- **skipped**    — digital page; no formatting needed"
    ),
)
@limiter.limit("60/minute")
def get_formatting_status(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, db, current_user)  # ownership guard

    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
        .all()
    )

    status_counts: dict[str, int] = {
        "pending": 0, "processing": 0, "completed": 0,
        "failed": 0, "skipped": 0,
    }
    page_entries: list[PageFormattingEntry] = []

    for pg in pages:
        key = pg.formatting_status or "pending"
        status_counts[key] = status_counts.get(key, 0) + 1
        page_entries.append(PageFormattingEntry.model_validate(pg))

    total = len(pages)
    all_done = total > 0 and status_counts["pending"] == 0 and status_counts["processing"] == 0

    return FormattingStatusResponse(
        document_id=document_id,
        summary=FormattingSummary(
            total_pages=total,
            pending=status_counts["pending"],
            processing=status_counts["processing"],
            completed=status_counts["completed"],
            failed=status_counts["failed"],
            skipped=status_counts["skipped"],
            all_done=all_done,
        ),
        pages=page_entries,
    )



# ── Progressive page stream (SSE) ─────────────────────────────────────────────

@app.get(
    "/documents/{document_id}/stream",
    tags=["Documents"],
    summary="Stream page events as OCR and formatting complete (SSE)",
    description=(
        "Server-Sent Events stream that pushes one JSON event per page as soon as "
        "its raw OCR text is extracted, and again when Ollama formatting completes.\n\n"
        "**Event types**\n"
        "- `ocr_ready`      — raw OCR text is stored; render page immediately.\n"
        "- `formatted`      — Ollama formatted text is ready; replace raw text.\n"
        "- `failed`         — formatting failed; keep showing raw OCR text.\n"
        "- `upload_complete`— all OCR pages extracted (formatting may continue).\n"
        "- `stream_end`     — document fully processed; close the connection.\n\n"
        "**Frontend usage**\n"
        "1. Start the SSE connection immediately after calling POST /upload.\n"
        "2. On `ocr_ready`: append the page to the workspace.\n"
        "3. On `formatted`: replace that page's text with display_text.\n"
        "4. On `stream_end` or connection close: stop listening.\n\n"
        "**Backward compatibility**\n"
        "For already-uploaded documents, the stream immediately replays all "
        "completed pages then closes. Pages still pending formatting remain "
        "visible via their raw OCR text from GET /documents/{id}/view."
    ),
)
@limiter.limit("30/minute")
async def stream_document_pages(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    SSE endpoint for progressive document rendering.

    Architecture
    ------------
    1. Ownership guard — reject unauthorised access immediately.
    2. Register a subscriber queue with ocr_formatter._DOC_STREAMS so that
       both upload.py (ocr_ready events) and the formatting worker
       (formatted/failed events) can push events to this connection.
    3. Replay already-completed pages from the DB so clients that connect
       after upload starts (or re-open a finished document) see all pages.
    4. Drain the subscriber queue until all pages are in a terminal state
       (completed | failed | skipped) — then send stream_end and close.
    5. Detect client disconnect via request.is_disconnected() and clean up.

    The stream never blocks the event loop: all DB access is either done
    upfront (replay) or via awaitable queue.get() with a timeout.
    """
    import json as _json

    _get_owned_document(document_id, db, current_user)

    from services.ocr_formatter import (
        get_doc_stream_queue,
        release_doc_stream,
    )

    def _serialize_event(event_dict: dict) -> str:
        """Serialise one event dict as an SSE data line."""
        return f"data: {_json.dumps(event_dict)}\n\n"

    async def _event_generator():
        # ── Register subscriber queue ──────────────────────────────────────
        queue = get_doc_stream_queue(document_id)

        try:
            # ── Replay already-stored pages (backward compat + reconnects) ─
            existing_pages = (
                db.query(DocumentPage)
                .filter(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
                .all()
            )

            # Re-fetch the document to check processing_status.
            # If the upload pipeline already finished (processing_status ==
            # "completed"), treat upload as done so _all_terminal() can fire
            # even if no "upload_complete" event arrives on the queue.
            # This fixes the hang when a client reconnects mid-formatting or
            # opens a previously uploaded document.
            doc_record = (
                db.query(Document)
                .filter(Document.id == document_id)
                .first()
            )
            upload_done = (
                doc_record is not None
                and doc_record.processing_status == "completed"
            )

            replayed_pages: set[int] = set()
            pending_count = 0

            for pg in existing_pages:
                status = pg.formatting_status or "pending"
                if status in ("completed", "failed", "skipped"):
                    if status == "completed" and pg.formatted_text:
                        display = pg.formatted_text
                        evt_type = "formatted"
                    else:
                        display = pg.extracted_text or ""
                        evt_type = "ocr_ready"

                    yield _serialize_event({
                        "event_type":        evt_type,
                        "page_number":       pg.page_number,
                        "formatting_status": status,
                        "display_text":      display,
                        "ocr_type":          pg.ocr_type,
                        "confidence_score":  pg.confidence_score,
                    })
                    replayed_pages.add(pg.page_number)
                elif status in ("pending", "processing"):
                    if pg.extracted_text:
                        yield _serialize_event({
                            "event_type":        "ocr_ready",
                            "page_number":       pg.page_number,
                            "formatting_status": status,
                            "display_text":      pg.extracted_text,
                            "ocr_type":          pg.ocr_type,
                            "confidence_score":  pg.confidence_score,
                        })
                        replayed_pages.add(pg.page_number)
                    pending_count += 1

            total_db_pages = len(existing_pages)

            # If everything is already in a terminal state, close immediately.
            if total_db_pages > 0 and pending_count == 0:
                yield _serialize_event({"event_type": "stream_end", "total_pages": total_db_pages})
                return

            # ── Drain live events ──────────────────────────────────────────
            page_statuses: dict[int, str] = {
                pg.page_number: (pg.formatting_status or "pending")
                for pg in existing_pages
            }
            needs_fmt_pages: set[int] = {
                pg.page_number
                for pg in existing_pages
                if pg.formatting_status not in ("skipped", "completed", "failed")
            }

            # upload_done was seeded from doc_record.processing_status above.
            total_pages_known = total_db_pages or None

            def _all_terminal() -> bool:
                """True when every known page is in a terminal state."""
                if not upload_done:
                    return False
                return all(
                    s in ("completed", "failed", "skipped")
                    for s in page_statuses.values()
                )

            # Stream events until all pages are terminal or client disconnects.
            while True:
                if await request.is_disconnected():
                    logger.debug(f"Stream: client disconnected for doc {document_id}.")
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    # No new event — check termination condition and loop.
                    if _all_terminal():
                        yield _serialize_event({
                            "event_type":  "stream_end",
                            "total_pages": total_pages_known,
                        })
                        break
                    continue

                if event is None:
                    # Sentinel — producer signals end of stream.
                    yield _serialize_event({
                        "event_type":  "stream_end",
                        "total_pages": total_pages_known,
                    })
                    break

                evt_type = event.get("event_type")

                if evt_type == "upload_complete":
                    upload_done = True
                    total_pages_known = event.get("total_pages", total_pages_known)
                    yield _serialize_event(event)
                    if _all_terminal():
                        yield _serialize_event({
                            "event_type":  "stream_end",
                            "total_pages": total_pages_known,
                        })
                        break
                    continue

                page_num = event.get("page_number")

                if evt_type == "ocr_ready":
                    # Only forward if we haven't already replayed this page.
                    if page_num not in replayed_pages:
                        page_statuses[page_num] = event.get("formatting_status", "pending")
                        if event.get("formatting_status") in ("skipped",):
                            # Digital / skipped — no further update expected.
                            pass
                        else:
                            needs_fmt_pages.add(page_num)
                        yield _serialize_event(event)
                    else:
                        # Update our internal status tracker even if we skip
                        # re-emitting (client already has this page from replay).
                        new_status = event.get("formatting_status", "pending")
                        page_statuses[page_num] = new_status

                elif evt_type in ("formatted", "failed"):
                    page_statuses[page_num] = event.get("formatting_status", evt_type)
                    needs_fmt_pages.discard(page_num)
                    yield _serialize_event(event)

                    if _all_terminal():
                        yield _serialize_event({
                            "event_type":  "stream_end",
                            "total_pages": total_pages_known,
                        })
                        break

        finally:
            release_doc_stream(document_id, queue)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",   # disable nginx buffering
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── Re-trigger formatting (retry failed / pending pages) ─────────────────────

@app.post(
    "/document/{document_id}/reformat",
    response_model=ReformatResponse,
    tags=["Documents"],
    summary="Re-enqueue failed or pending pages for Ollama formatting",
    description=(
        "Resets all **failed** and **pending** pages back to pending and "
        "pushes them onto the formatting queue.  Use when Ollama was "
        "temporarily unavailable during the initial upload.\n\n"
        "Returns immediately — formatting happens in the background.\n"
        "Track progress via GET /document/{id}/formatting-status."
    ),
)
@limiter.limit("5/minute")
def reformat_document(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, db, current_user)  # ownership guard

    try:
        from services.ocr_formatter import enqueue_pending_pages_for_document
        count = enqueue_pending_pages_for_document(document_id)
        logger.info(f"Reformat: {count} page(s) enqueued for document {document_id}.")
        return ReformatResponse(
            document_id=document_id,
            pages_enqueued=count,
            message=(
                f"{count} page(s) enqueued for formatting. "
                "Poll GET /document/{id}/formatting-status for progress."
            ),
        )
    except Exception as exc:
        logger.error(f"Reformat failed for {document_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reformat request failed: {exc}")


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
        recent_documents=_build_documents_with_time(uid, db, limit=DASHBOARD_RECENT_DOCS_LIMIT),
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
        "Pass `active_seconds` — the number of seconds during which the tab was "
        "visible **and** the user was actively interacting (tracked on the frontend "
        "with a 5-minute inactivity timeout).  The backend stores this value "
        "directly so that idle open tabs do not inflate read-time statistics. "
        "Sessions shorter than the configured minimum are silently discarded."
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
            ReadingSession.user_id == current_user.id,
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

    ended_at = datetime.utcnow()

    # Prefer the frontend-reported active seconds (excludes idle/background
    # time) when provided.  Fall back to wall-clock duration only as a safety
    # net so older clients that don't yet send the field still work.
    if data.active_seconds is not None:
        # Clamp: active time cannot exceed the actual wall-clock elapsed time
        # (guards against frontend bugs / clock skew).
        wall_clock = int((ended_at - session.started_at).total_seconds())
        duration_seconds = max(0, min(data.active_seconds, wall_clock))
    else:
        duration_seconds = int((ended_at - session.started_at).total_seconds())

    if duration_seconds < MIN_DURATION_SECONDS:
        db.delete(session)
        db.commit()
        logger.debug(
            f"Reading session {data.session_id} discarded "
            f"(active duration {duration_seconds}s < {MIN_DURATION_SECONDS}s minimum)."
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
        f"user={current_user.email}, active_duration={duration_seconds}s"
    )

    return ReadingSessionEndResponse(
        session_id=session.id,
        document_id=session.document_id,
        duration_seconds=duration_seconds,
        duration_minutes=round(duration_seconds / 60, 2),
        message="Reading session recorded.",
    )


# ── Reading session — heartbeat (incremental active time) ─────────────────────

@app.post(
    "/reading-session/heartbeat",
    tags=["Dashboard"],
    summary="Increment active reading time for an open session",
    description=(
        "Called by the frontend every 30 s while the tab is visible and the "
        "user is active.  Each call adds `active_seconds` to the session's "
        "running total without closing it.  This lets the server reflect "
        "partial progress for long reading sessions that span page refreshes "
        "or browser crashes without waiting for /reading-session/end.  "
        "The value stored here is overwritten (not double-counted) when "
        "/reading-session/end is later called with its own `active_seconds`."
    ),
    status_code=204,
)
@limiter.limit("120/minute")
def reading_session_heartbeat(
    request: Request,
    data: ReadingSessionHeartbeatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = (
        db.query(ReadingSession)
        .filter(
            ReadingSession.id == data.session_id,
            ReadingSession.user_id == current_user.id,
        )
        .first()
    )

    if not session or session.ended_at is not None:
        # Session missing or already closed — silently ignore.
        return Response(status_code=204)

    # Clamp against wall-clock elapsed time.
    wall_clock = int((datetime.utcnow() - session.started_at).total_seconds())
    session.duration_seconds = max(0, min(data.active_seconds, wall_clock))
    db.commit()

    return Response(status_code=204)


# ── Per-document read time — all documents ─────────────────────────────────────

@app.get(
    "/me/documents/time",
    tags=["Dashboard"],
    summary="Get total read time per document (all documents)",
    description=(
        "Returns total active reading seconds for every document the user has "
        "ever opened, aggregated in the database layer.  No document cap is "
        "applied — this is used by analytics views that must reflect the full "
        "library.  Results are sorted by time_spent_seconds descending."
    ),
)
@limiter.limit("30/minute")
def get_all_documents_time(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = current_user.id

    # Single aggregation query — O(sessions) not O(documents × sessions).
    time_rows = (
        db.query(
            ReadingSession.document_id,
            func.sum(ReadingSession.duration_seconds).label("total_secs"),
        )
        .filter(
            ReadingSession.user_id == uid,
            ReadingSession.duration_seconds.isnot(None),
        )
        .group_by(ReadingSession.document_id)
        .all()
    )
    time_map: dict[str, int] = {r.document_id: (r.total_secs or 0) for r in time_rows}

    if not time_map:
        return {"total_documents": 0, "documents": []}

    # Fetch only documents that have at least one session recorded.
    docs = (
        db.query(Document.id, Document.filename, Document.file_type,
                 Document.file_size_bytes, Document.total_pages, Document.created_at)
        .filter(
            Document.user_id == uid,
            Document.id.in_(list(time_map.keys())),
        )
        .all()
    )

    results = sorted(
        [
            {
                "id":                 d.id,
                "filename":           d.filename,
                "file_type":          d.file_type or "",
                "file_size_bytes":    d.file_size_bytes,
                "total_pages":        d.total_pages,
                "created_at":         d.created_at.isoformat() if d.created_at else None,
                "time_spent_seconds": time_map.get(d.id, 0),
            }
            for d in docs
        ],
        key=lambda x: x["time_spent_seconds"],
        reverse=True,
    )

    return {"total_documents": len(results), "documents": results}

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
    from wordlogic import Dictionary, get_meaning

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

    # Bulk-fetch meanings in one query instead of N get_meaning() calls.
    words = [row.word for row in rows]
    dict_map: dict[str, object] = {}
    if words:
        dict_rows = db.query(Dictionary).filter(Dictionary.word.in_(words)).all()
        dict_map = {d.word: d for d in dict_rows}

    entries: List[VocabularyEntry] = []
    for row in rows:
        d = dict_map.get(row.word)
        if d:
            meaning = d.meaning or "Meaning not found."
            synonym = d.synonym or None
        else:
            api = get_meaning(row.word)
            meaning = api.get("meaning", "Meaning not found.")
            synonym = api.get("synonym") or None

        doc_name = None
        if row.document_id and row.document:
            doc_name = row.document.filename

        entries.append(VocabularyEntry(
            word=row.word,
            meaning=meaning,
            synonym=synonym,
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
    from wordlogic import Dictionary, get_meaning

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

    # Bulk-fetch meanings in one query instead of N get_meaning() calls.
    words = [row.word for row in rows]
    dict_map: dict[str, object] = {}
    if words:
        dict_rows = db.query(Dictionary).filter(Dictionary.word.in_(words)).all()
        dict_map = {d.word: d for d in dict_rows}

    entries: List[VocabularyEntry] = []
    for row in rows:
        d = dict_map.get(row.word)
        if d:
            meaning = d.meaning or "Meaning not found."
            synonym = d.synonym or None
        else:
            api = get_meaning(row.word)
            meaning = api.get("meaning", "Meaning not found.")
            synonym = api.get("synonym") or None

        doc_name = None
        if row.document_id and row.document:
            doc_name = row.document.filename

        entries.append(VocabularyEntry(
            word=row.word,
            meaning=meaning,
            synonym=synonym,
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
# PAGE NOTES ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@app.get(
    "/documents/{document_id}/notes",
    response_model=DocumentNotesResponse,
    tags=["Notes"],
    summary="Fetch all saved notes for a document",
    description=(
        "Called once when the user opens a document. "
        "Returns every saved note for this (user, document) pair so the frontend "
        "can pre-populate the correct textarea under each page in a single request. "
        "Pages with no saved note are simply absent from the list."
    ),
)
@limiter.limit("30/minute")
def get_document_notes(
    request: Request,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, db, current_user)

    notes = (
        db.query(PageNote)
        .filter(
            PageNote.user_id     == current_user.id,
            PageNote.document_id == document_id,
        )
        .order_by(PageNote.page_number)
        .all()
    )

    return DocumentNotesResponse(
        document_id=document_id,
        notes=[
            PageNoteResponse(
                document_id=n.document_id,
                page_number=n.page_number,
                note_text=n.note_text,
                updated_at=n.updated_at,
            )
            for n in notes
        ],
    )


@app.put(
    "/documents/{document_id}/pages/{page_number}/note",
    response_model=PageNoteResponse,
    tags=["Notes"],
    summary="Create or update the note for a specific page",
    description=(
        "Upsert the note for page `page_number` of document `document_id`. "
        "Creates a new note row if none exists, or updates the existing one. "
        "Sending an empty string clears the note text without deleting the row. "
        "Call this on every textarea blur / auto-save event."
    ),
)
@limiter.limit("30/minute")
def upsert_page_note(
    request: Request,
    document_id: str,
    page_number: int,
    body: PageNoteUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned_document(document_id, db, current_user)

    if doc.total_pages is not None and not (1 <= page_number <= doc.total_pages):
        raise HTTPException(
            status_code=400,
            detail=f"page_number must be between 1 and {doc.total_pages}.",
        )

    note = (
        db.query(PageNote)
        .filter(
            PageNote.user_id     == current_user.id,
            PageNote.document_id == document_id,
            PageNote.page_number == page_number,
        )
        .first()
    )

    now = datetime.utcnow()

    if note:
        note.note_text  = body.note_text
        note.updated_at = now
    else:
        note = PageNote(
            user_id     = current_user.id,
            document_id = document_id,
            page_number = page_number,
            note_text   = body.note_text,
            created_at  = now,
            updated_at  = now,
        )
        db.add(note)

    db.commit()
    db.refresh(note)

    return PageNoteResponse(
        document_id=note.document_id,
        page_number=note.page_number,
        note_text=note.note_text,
        updated_at=note.updated_at,
    )


@app.delete(
    "/documents/{document_id}/pages/{page_number}/note",
    status_code=204,
    tags=["Notes"],
    summary="Delete the note for a specific page",
    description=(
        "Hard-deletes the note row for (user, document, page_number). "
        "Returns 204 No Content whether or not a note existed — idempotent."
    ),
)
@limiter.limit("20/minute")
def delete_page_note(
    request: Request,
    document_id: str,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned_document(document_id, db, current_user)

    db.query(PageNote).filter(
        PageNote.user_id     == current_user.id,
        PageNote.document_id == document_id,
        PageNote.page_number == page_number,
    ).delete()

    db.commit()
    return Response(status_code=204)


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
def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    key        = _session_key(current_user.id, session_id)
    history    = SESSIONS.setdefault(key, [])

    chunks = retrieve(query=question, doc_ids=req.doc_ids, top_k=req.top_k, use_hybrid=req.use_hybrid)
    if not chunks:
        raise HTTPException(status_code=404, detail="No indexed documents found. Please upload a document first.")

    answer, citations = generate_answer(question, chunks, history)
    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": answer})

    return ChatResponse(answer=answer, session_id=session_id, citations=citations, sources_used=len(chunks))


@app.post("/chat/stream", tags=["RAG"])
def chat_stream(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    question = _clean_text(req.question)
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    session_id = req.session_id or str(uuid.uuid4())
    key        = _session_key(current_user.id, session_id)
    history    = SESSIONS.setdefault(key, [])

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
def summarize(
    req: SummarizeRequest,
    current_user: User = Depends(get_current_user),
):
    cleaned = _clean_text(req.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    try:
        summary = summarize_text(cleaned, length=req.length)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {e}")

    return SummarizeResponse(summary=summary, length=req.length, char_count=len(cleaned))


@app.post("/summarize/stream", tags=["RAG"])
def summarize_stream(
    req: SummarizeRequest,
    current_user: User = Depends(get_current_user),
):
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
def get_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    key = _session_key(current_user.id, session_id)
    return SessionHistoryResponse(session_id=session_id, history=SESSIONS.get(key, []))


@app.delete("/session/{session_id}", tags=["RAG"])
def clear_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    key = _session_key(current_user.id, session_id)
    SESSIONS.pop(key, None)
    return {"status": "cleared", "session_id": session_id}


# ═════════════════════════════════════════════════════════════════════════════
# HEALTH
# ═════════════════════════════════════════════════════════════════════════════

@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health():
    return HealthResponse(status="ok", sessions=len(SESSIONS))