"""
services/ocr_formatter.py — Async Ollama-based OCR text formatter.

Architecture
------------
This module owns three things:

1. A thread-safe in-process queue (FORMAT_QUEUE) of DocumentPage IDs
   that need Ollama formatting.

2. enqueue_page(page_id)  — called by upload.py immediately after each
   OCR page is committed; non-blocking, drops excess pages gracefully.

3. run_formatting_worker() — async coroutine started by main.py lifespan;
   drains the queue in batches, calling Ollama for each page with retries.

Formatting strategy
-------------------
• Each page's extracted_text is split into chunks of OCR_FORMAT_CHUNK_CHARS
  characters (default 3 000) to stay within Ollama's context window.
• Each chunk is sent to Ollama with a strict prompt that preserves meaning
  while fixing structure (headings, paragraphs, bullets, spacing).
• Chunks are rejoined and written to formatted_text.
• On success: formatting_status → "completed".
• On failure after FORMAT_MAX_RETRIES: formatting_status → "failed";
  workspace falls back to extracted_text automatically.

Thread-safety
-------------
The queue is asyncio-safe (asyncio.Queue).  DB work runs in the same
async event loop via run_in_executor so it never blocks the server.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

import requests

from config import (
    OLLAMA_BASE_URL,
    LLM_MODEL,
    LLM_TIMEOUT,
    OCR_FORMAT_CHUNK_CHARS,
    FORMAT_CONCURRENCY,
    FORMAT_QUEUE_SIZE,
    FORMAT_MAX_RETRIES,
)

import re as _re

logger = logging.getLogger(__name__)

# ── Artifact patterns (mirrors main._LLM_ARTIFACT_PATTERNS) ──────────────────
# Defined here so ocr_formatter can strip commentary before writing to the DB,
# independently of the read-path guard in main.py.
_ARTIFACT_LINE_PATTERNS: list[_re.Pattern] = [
    _re.compile(r'^\s*note\s*[:\-\u2013\u2014]', _re.IGNORECASE),
    _re.compile(r'^\s*here\s+(is|are|\'s)\s+the\s+', _re.IGNORECASE),
    _re.compile(r'^\s*i\s+(fixed|restored|corrected|removed|cleaned|rewrote)', _re.IGNORECASE),
    _re.compile(r'^\s*the following (text|content|document)', _re.IGNORECASE),
    _re.compile(r'^\s*corrected text\s*[:\-]?\s*$', _re.IGNORECASE),
    _re.compile(r'^\s*```'),
    _re.compile(r'^\s*\d{4}s?\.?\s*$'),
]


def _strip_formatter_artifacts(text: str) -> str:
    """
    Remove LLM meta-commentary lines from an Ollama response chunk.

    Called on every chunk returned by _call_ollama before it is stored,
    so commentary never reaches formatted_text in the database.
    Also strips the "Corrected text:" label that the user-turn prompt
    elicits as a prefix on some models.
    """
    lines = text.splitlines()
    cleaned: list[str] = []
    blank_run = 0
    for line in lines:
        if any(p.search(line) for p in _ARTIFACT_LINE_PATTERNS):
            logger.debug(f"ocr_formatter: stripped artifact line: {line!r}")
            continue
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                cleaned.append(line)
        else:
            blank_run = 0
            cleaned.append(line)
    return "\n".join(cleaned).strip()

# ── Shared in-process queue ───────────────────────────────────────────────────
# Lazily initialised inside run_formatting_worker() which runs after the
# asyncio event loop is started.  asyncio.Queue must NOT be created at module
# import time — in Python 3.10+ this raises a DeprecationWarning and in
# future versions will be an error.
#
# enqueue_page() guards against the queue not yet existing so it is safe to
# call before the worker starts (pages are silently dropped, which is
# acceptable — the /reformat endpoint can re-enqueue them).
FORMAT_QUEUE: Optional[asyncio.Queue] = None


# ── Per-document SSE stream registry ─────────────────────────────────────────
# Maps document_id → list of asyncio.Queue instances (one per active SSE
# subscriber).  Both upload.py (ocr_ready events) and the formatting worker
# (formatted / failed events) push PageStreamEvent dicts onto these queues.
# The SSE endpoint in main.py drains the queue and forwards to the client.
#
# Lifecycle:
#   1. SSE endpoint calls get_doc_stream_queue(doc_id) → gets a fresh Queue.
#   2. upload.py and _format_one_page push events via notify_page_event().
#   3. SSE endpoint calls release_doc_stream(doc_id, queue) when the client
#      disconnects or the document is fully processed.
#
# Thread-safety: all mutations are done from the asyncio event loop only.
# _DOC_STREAMS is never touched from a thread-pool executor.

_DOC_STREAMS: dict[str, list[asyncio.Queue]] = {}


def get_doc_stream_queue(document_id: str) -> "asyncio.Queue[Optional[dict]]":
    """
    Register a new SSE subscriber for *document_id*.

    Returns a fresh asyncio.Queue.  Each event pushed via notify_page_event()
    will be placed on ALL registered queues for that document.  A sentinel
    value of None signals end-of-stream to the consumer.

    Must be called from the asyncio event loop.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _DOC_STREAMS.setdefault(document_id, []).append(q)
    logger.debug(f"Stream: registered subscriber for doc {document_id} "
                 f"(total={len(_DOC_STREAMS[document_id])}).")
    return q


def notify_page_event(document_id: str, event: dict) -> None:
    """
    Broadcast *event* to all SSE subscribers of *document_id*.

    *event* is a plain dict; callers must set at minimum:
        event_type : "ocr_ready" | "formatted" | "failed" | "upload_complete"
        page_number: int  (omit only for "upload_complete")

    Non-blocking: full queues are skipped with a debug log — slow or
    disconnected clients should not stall the upload or formatter.

    Must be called from the asyncio event loop (use loop.call_soon_threadsafe
    when calling from a thread-pool executor).
    """
    queues = _DOC_STREAMS.get(document_id)
    if not queues:
        return
    for q in queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug(
                f"Stream: subscriber queue full for doc {document_id}; "
                f"dropping event {event.get('event_type')}."
            )


def release_doc_stream(document_id: str, queue: "asyncio.Queue") -> None:
    """
    Deregister *queue* from *document_id*'s subscriber list.

    Called by the SSE endpoint when the client disconnects or the stream ends.
    If no subscribers remain, the entry is removed from _DOC_STREAMS.

    Must be called from the asyncio event loop.
    """
    queues = _DOC_STREAMS.get(document_id)
    if queues is None:
        return
    try:
        queues.remove(queue)
    except ValueError:
        pass
    if not queues:
        _DOC_STREAMS.pop(document_id, None)
    logger.debug(f"Stream: released subscriber for doc {document_id}.")


def notify_page_processing(document_id: str, page_number: int) -> None:
    """
    Broadcast a "processing" event to all SSE subscribers of *document_id*.

    Called by upload.py / the streaming loop immediately before OCR starts on
    a page so the frontend can display "Processing page X…" without waiting for
    the result.

    Must be called from the asyncio event loop.
    """
    notify_page_event(document_id, {
        "event_type":  "processing",
        "page_number": page_number,
        "status":      "ocr_started",
    })



# Event-loop reference — set once by run_formatting_worker() at startup.
# Used by thread-pool DB helpers to schedule SSE notifications safely.
_loop: Optional[asyncio.AbstractEventLoop] = None


def _notify_from_thread(document_id: str, event: dict) -> None:
    """
    Thread-safe wrapper around notify_page_event().

    DB helper functions run in thread-pool executors and cannot call
    notify_page_event() directly (asyncio data structures are not thread-safe).
    This helper uses the stored event-loop reference to schedule the call
    back on the event-loop thread via call_soon_threadsafe.
    """
    loop = _loop
    if loop is not None and not loop.is_closed():
        loop.call_soon_threadsafe(notify_page_event, document_id, event)


# ══════════════════════════════════════════════════════════════════════════════
# Public enqueue helper
# ══════════════════════════════════════════════════════════════════════════════

def enqueue_page(page_id: int) -> None:
    """
    Push a DocumentPage ID onto the formatting queue.

    Non-blocking: if the queue is full the page is skipped with a warning —
    the workspace will display raw OCR text for that page.

    Safe to call from sync or async contexts.
    If the worker has not started yet (FORMAT_QUEUE is None) the call is a
    no-op; use POST /reformat to re-enqueue after the worker is running.
    """
    if FORMAT_QUEUE is None:
        logger.warning(
            f"Formatter queue not initialised; page {page_id} will not be "
            f"formatted automatically. Use POST /reformat after server startup."
        )
        return
    try:
        FORMAT_QUEUE.put_nowait(page_id)
        logger.debug(f"Formatter: enqueued page_id={page_id} (queue depth={FORMAT_QUEUE.qsize()})")
    except asyncio.QueueFull:
        logger.warning(
            f"Formatter queue full (maxsize={FORMAT_QUEUE_SIZE}). "
            f"Page {page_id} will not be formatted — raw OCR text will be shown."
        )


# ══════════════════════════════════════════════════════════════════════════════
# Ollama formatting call
# ══════════════════════════════════════════════════════════════════════════════

_FORMAT_SYSTEM_PROMPT = """\
You are an OCR text formatter. Your job is to clean up the structure of \
OCR-extracted text and return it — nothing more.

ABSOLUTE OUTPUT RULES — violating any of these is a critical failure:
1. Output ONLY the corrected document text. No other content whatsoever.
2. Do NOT start your reply with any preamble. Your first character must be \
the first character of the corrected text.
3. Do NOT end your reply with any footnote, note, comment, or explanation. \
Your last character must be the last character of the corrected text.
4. NEVER write lines starting with: "Note:", "Note —", "Here is", "Here's", \
"I fixed", "I restored", "I corrected", "I removed", "The following".
5. NEVER wrap the output in markdown code fences (```).

Fixes to apply:
- Mark headings with Markdown (# H1, ## H2, ### H3) where clearly indicated.
- Re-join sentences that were broken across lines by OCR column errors.
- Preserve intentional paragraph breaks (blank lines between topics).
- Format bullet or numbered lists correctly.
- Fix obvious OCR spacing artefacts ("w ord" → "word", "hel lo" → "hello").
- Preserve original word order, meaning, and all content exactly."""


def _build_format_prompt(raw_chunk: str) -> str:
    return (
        "Reformat the OCR text below. Fix structure only — do not change meaning "
        "or add content. Return the corrected text immediately with no preamble, "
        "no trailing note, and no explanation of what you changed.\n\n"
        "--- BEGIN OCR TEXT ---\n"
        f"{raw_chunk}\n"
        "--- END OCR TEXT ---\n\n"
        "Corrected text (start immediately, no preamble, no trailing note):"
    )


def _call_ollama(raw_text: str) -> str:
    """
    Send raw_text to Ollama and return the formatted string.

    Splits into chunks so very long pages stay within Ollama's context window.
    Chunks are rejoined with a blank line.

    Raises requests.RequestException on connection/timeout errors.
    Raises ValueError if Ollama returns an unexpected response shape.

    NOTE: No retry sleep here — this function is called from a thread-pool
    executor by _format_one_page.  Sleeping inside an executor thread wastes
    a thread-pool slot and can starve other work.  All retry back-off is
    handled by the async _format_one_page caller via asyncio.sleep().
    """
    if not raw_text or not raw_text.strip():
        return raw_text

    chunks = _split_into_chunks(raw_text, OCR_FORMAT_CHUNK_CHARS)
    formatted_chunks: list[str] = []

    for idx, chunk in enumerate(chunks):
        if not chunk.strip():
            formatted_chunks.append(chunk)
            continue

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": _FORMAT_SYSTEM_PROMPT},
                {"role": "user",   "content": _build_format_prompt(chunk)},
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": int(len(chunk) * 1.5),
            },
        }

        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        formatted_chunk = (
            data.get("message", {}).get("content", "")
            or data.get("response", "")
        ).strip()

        if not formatted_chunk:
            raise ValueError(f"Ollama returned empty content for chunk {idx + 1}.")

        # Strip any meta-commentary the model appended despite the prompt rules.
        formatted_chunk = _strip_formatter_artifacts(formatted_chunk)

        # If stripping consumed everything, fall back to the raw chunk rather
        # than storing blank — better to show slightly rough OCR than nothing.
        if not formatted_chunk.strip():
            logger.warning(
                f"Formatter chunk {idx+1}: entire response was artifact text; "
                f"keeping raw OCR chunk as fallback."
            )
            formatted_chunk = chunk.strip()

        formatted_chunks.append(formatted_chunk)
        logger.debug(
            f"Formatter chunk {idx+1}/{len(chunks)}: "
            f"{len(chunk)} → {len(formatted_chunk)} chars."
        )

    return "\n\n".join(formatted_chunks)


def _split_into_chunks(text: str, max_chars: int) -> list[str]:
    """
    Split text into chunks of at most max_chars characters, breaking on
    paragraph boundaries (blank lines) where possible.
    """
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = [para]
            current_len   = len(para)
        else:
            current_parts.append(para)
            current_len += len(para)

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks


# ══════════════════════════════════════════════════════════════════════════════
# DB helpers  (run in executor to avoid blocking the event loop)
# ══════════════════════════════════════════════════════════════════════════════

def _db_fetch_page(page_id: int) -> Optional[dict]:
    """
    Fetch the page row from DB.
    Returns a plain dict (not an ORM object) to avoid session-boundary issues.
    Returns None if the page no longer exists.
    """
    from database import SessionLocal, DocumentPage
    db = SessionLocal()
    try:
        page = db.query(DocumentPage).filter(DocumentPage.id == page_id).first()
        if page is None:
            return None
        return {
            "id":               page.id,
            "document_id":      page.document_id,
            "page_number":      page.page_number,
            "extracted_text":   page.extracted_text,
            "formatting_status": page.formatting_status,
            "ocr_type":         page.ocr_type,
            "confidence_score": page.confidence_score,
        }
    finally:
        db.close()


def _db_mark_processing(page_id: int) -> bool:
    """
    Atomically set formatting_status → "processing".
    Returns False if the page was already processed (idempotency guard).
    """
    from database import SessionLocal, DocumentPage
    db = SessionLocal()
    try:
        page = db.query(DocumentPage).filter(DocumentPage.id == page_id).first()
        if page is None:
            return False
        if page.formatting_status not in ("pending", "failed"):
            logger.debug(
                f"Page {page_id} has status '{page.formatting_status}'; skipping."
            )
            return False
        page.formatting_status     = "processing"
        page.formatting_started_at = datetime.utcnow()
        db.commit()
        return True
    except Exception as exc:
        logger.error(f"DB mark_processing failed for page {page_id}: {exc}")
        db.rollback()
        return False
    finally:
        db.close()


def _db_save_formatted(page_id: int, formatted_text: str) -> None:
    """Write formatted_text and mark the page completed."""
    from database import SessionLocal, DocumentPage
    db = SessionLocal()
    try:
        page = db.query(DocumentPage).filter(DocumentPage.id == page_id).first()
        if page is None:
            return
        page.formatted_text          = formatted_text
        page.formatting_status       = "completed"
        page.formatting_completed_at = datetime.utcnow()
        db.commit()
        logger.info(f"Formatter: page {page_id} completed ({len(formatted_text)} chars).")
        # Notify SSE subscribers that this page's formatted text is ready.
        _notify_from_thread(page.document_id, {
            "event_type":        "formatted",
            "page_number":       page.page_number,
            "formatting_status": "completed",
            "display_text":      formatted_text or page.extracted_text or "",
        })
    except Exception as exc:
        logger.error(f"DB save_formatted failed for page {page_id}: {exc}")
        db.rollback()
    finally:
        db.close()


def _db_mark_failed(page_id: int) -> None:
    """Mark a page as failed so it stays displayable via extracted_text."""
    from database import SessionLocal, DocumentPage
    db = SessionLocal()
    try:
        page = db.query(DocumentPage).filter(DocumentPage.id == page_id).first()
        if page is None:
            return
        page.formatting_status       = "failed"
        page.formatting_completed_at = datetime.utcnow()
        db.commit()
        logger.warning(f"Formatter: page {page_id} marked failed.")
        # Notify subscribers: formatting failed, workspace keeps raw OCR text.
        _notify_from_thread(page.document_id, {
            "event_type":        "failed",
            "page_number":       page.page_number,
            "formatting_status": "failed",
            "display_text":      page.extracted_text or "",
        })
    except Exception as exc:
        logger.error(f"DB mark_failed failed for page {page_id}: {exc}")
        db.rollback()
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# Per-page formatting coroutine
# ══════════════════════════════════════════════════════════════════════════════

async def _format_one_page(page_id: int, loop: asyncio.AbstractEventLoop) -> None:
    """
    Fetch, format, and save one page.  Retries FORMAT_MAX_RETRIES times on
    transient errors before marking the page failed.
    """
    # Mark processing (idempotency check inside).
    marked = await loop.run_in_executor(None, _db_mark_processing, page_id)
    if not marked:
        return   # Already handled; skip.

    page_data = await loop.run_in_executor(None, _db_fetch_page, page_id)
    if page_data is None:
        logger.warning(f"Formatter: page {page_id} not found in DB; skipping.")
        return

    raw_text = page_data.get("extracted_text") or ""
    if not raw_text.strip():
        # Nothing to format — just mark completed with empty formatted_text.
        await loop.run_in_executor(None, _db_save_formatted, page_id, "")
        return

    t0 = time.perf_counter()

    for attempt in range(1, FORMAT_MAX_RETRIES + 2):
        try:
            # Ollama is synchronous; run in thread executor.
            formatted = await loop.run_in_executor(None, _call_ollama, raw_text)
            await loop.run_in_executor(None, _db_save_formatted, page_id, formatted)
            elapsed = time.perf_counter() - t0
            logger.info(
                f"Formatter: page {page_id} done in {elapsed:.1f}s "
                f"(attempt {attempt})."
            )
            return

        except Exception as exc:
            if attempt <= FORMAT_MAX_RETRIES:
                wait = attempt * 3
                logger.warning(
                    f"Formatter: page {page_id} attempt {attempt} failed: {exc}. "
                    f"Retrying in {wait}s…"
                )
                await asyncio.sleep(wait)
            else:
                logger.error(
                    f"Formatter: page {page_id} exhausted {FORMAT_MAX_RETRIES} "
                    f"retries. Marking failed. Last error: {exc}"
                )
                await loop.run_in_executor(None, _db_mark_failed, page_id)


# ══════════════════════════════════════════════════════════════════════════════
# Background worker  (started once in main.py lifespan)
# ══════════════════════════════════════════════════════════════════════════════

async def run_formatting_worker() -> None:
    """
    Drain FORMAT_QUEUE continuously.

    Processes up to FORMAT_CONCURRENCY pages concurrently, then waits 1 s
    before checking for more work.  This keeps CPU/memory usage bounded while
    providing near-real-time formatting for newly uploaded documents.

    Call once from the FastAPI lifespan coroutine:

        asyncio.create_task(run_formatting_worker())
    """
    global _loop, FORMAT_QUEUE

    # Initialise the queue here — inside a running event loop — to avoid the
    # Python 3.10+ deprecation/error for asyncio.Queue() at module import time.
    FORMAT_QUEUE = asyncio.Queue(maxsize=FORMAT_QUEUE_SIZE)

    # asyncio.get_running_loop() is the correct call inside a coroutine;
    # get_event_loop() is deprecated in Python 3.10+ when there is a running loop.
    loop = asyncio.get_running_loop()
    _loop = loop   # store for use by thread-pool DB helpers

    logger.info(
        f"OCR formatting worker started "
        f"(concurrency={FORMAT_CONCURRENCY}, "
        f"queue_maxsize={FORMAT_QUEUE_SIZE})."
    )

    while True:
        try:
            batch: list[int] = []

            # Collect up to FORMAT_CONCURRENCY IDs non-blocking.
            for _ in range(FORMAT_CONCURRENCY):
                try:
                    page_id = FORMAT_QUEUE.get_nowait()
                    batch.append(page_id)
                except asyncio.QueueEmpty:
                    break

            if batch:
                logger.debug(f"Formatter worker: processing batch of {len(batch)} page(s).")
                await asyncio.gather(
                    *[_format_one_page(pid, loop) for pid in batch],
                    return_exceptions=True,  # one failure must not kill others
                )
            else:
                # Queue was empty — sleep briefly before polling again.
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            logger.info("OCR formatting worker cancelled; shutting down.")
            return
        except Exception as exc:
            # Unexpected error in the worker loop itself — log and continue.
            logger.error(f"Formatting worker unexpected error: {exc}", exc_info=True)
            await asyncio.sleep(5)


# ══════════════════════════════════════════════════════════════════════════════
# Retry helper  (called by POST /document/{id}/reformat)
# ══════════════════════════════════════════════════════════════════════════════

def enqueue_pending_pages_for_document(document_id: str) -> int:
    """
    Re-enqueue all pages for *document_id* whose formatting_status is
    "pending" or "failed".  Returns the number of pages enqueued.

    Called by POST /document/{id}/reformat so users can trigger a retry
    without re-uploading the document.
    """
    from database import SessionLocal, DocumentPage

    db = SessionLocal()
    try:
        pages = (
            db.query(DocumentPage)
            .filter(
                DocumentPage.document_id     == document_id,
                DocumentPage.formatting_status.in_(["pending", "failed"]),
            )
            .all()
        )
        count = 0
        for page in pages:
            # Reset to pending so _db_mark_processing allows reprocessing.
            page.formatting_status     = "pending"
            page.formatting_started_at = None
            page.formatting_completed_at = None
        db.commit()

        for page in pages:
            enqueue_page(page.id)
            count += 1

        return count
    except Exception as exc:
        logger.error(
            f"enqueue_pending_pages_for_document failed for {document_id}: {exc}"
        )
        db.rollback()
        return 0
    finally:
        db.close()