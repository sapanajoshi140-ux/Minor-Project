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
    OCR_FORMAT_MAX_RETRIES,
    FORMAT_CONCURRENCY,
    FORMAT_QUEUE_SIZE,
    FORMAT_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

# ── Shared in-process queue ───────────────────────────────────────────────────
# Populated by enqueue_page() from upload.py.
# Drained by run_formatting_worker() started in main.py lifespan.
FORMAT_QUEUE: asyncio.Queue[int] = asyncio.Queue(maxsize=FORMAT_QUEUE_SIZE)


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
    """
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

_FORMAT_SYSTEM_PROMPT = """You are a precise OCR text formatter. 
Your ONLY job is to fix the structure and readability of OCR-extracted text.

Rules you MUST follow:
- DO NOT add, invent, or hallucinate any content that was not in the input.
- DO NOT summarize, paraphrase, or omit any content.
- DO NOT add commentary, explanations, or preamble.
- Output ONLY the reformatted text — nothing else.

What you SHOULD fix:
- Detect and mark headings/subheadings using Markdown (# H1, ## H2, ### H3).
- Restore broken paragraphs: if a sentence is split across lines by a stray
  newline, join the lines back into one paragraph.
- Remove random mid-sentence line breaks caused by OCR column detection.
- Preserve intentional paragraph breaks (blank lines between topics).
- Detect and format bullet/numbered lists properly.
- Fix obvious OCR spacing errors (e.g. "w ord" → "word", "hel lo" → "hello").
- Preserve the original word order and meaning exactly.
- Group related sentences into coherent paragraphs."""


def _build_format_prompt(raw_chunk: str) -> str:
    return (
        "Reformat the following OCR-extracted text to improve readability. "
        "Fix structure only — do not change meaning or add content.\n\n"
        "--- BEGIN OCR TEXT ---\n"
        f"{raw_chunk}\n"
        "--- END OCR TEXT ---"
    )


def _call_ollama(raw_text: str) -> str:
    """
    Send raw_text to Ollama and return the formatted string.

    Splits into chunks so very long pages are handled without exceeding
    Ollama's context window.  Chunks are rejoined with a blank line.

    Raises requests.RequestException on connection/timeout errors.
    Raises ValueError if Ollama returns an unexpected response shape.
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
                "temperature": 0.0,   # deterministic — no creative variation
                "num_predict": int(len(chunk) * 1.5),  # generous token budget
            },
        }

        for attempt in range(1, OCR_FORMAT_MAX_RETRIES + 2):
            try:
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
                    raise ValueError("Ollama returned empty content.")

                formatted_chunks.append(formatted_chunk)
                logger.debug(
                    f"Formatter chunk {idx+1}/{len(chunks)}: "
                    f"{len(chunk)} → {len(formatted_chunk)} chars."
                )
                break  # success

            except (requests.RequestException, ValueError) as exc:
                if attempt <= OCR_FORMAT_MAX_RETRIES:
                    wait = attempt * 2
                    logger.warning(
                        f"Formatter chunk {idx+1} attempt {attempt} failed: {exc}. "
                        f"Retrying in {wait}s…"
                    )
                    time.sleep(wait)
                else:
                    # All retries exhausted for this chunk — use raw text.
                    logger.error(
                        f"Formatter chunk {idx+1} exhausted retries: {exc}. "
                        f"Using raw text for this chunk."
                    )
                    formatted_chunks.append(chunk)

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
    global _loop
    loop = asyncio.get_event_loop()
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
                for _ in batch:
                    FORMAT_QUEUE.task_done()
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