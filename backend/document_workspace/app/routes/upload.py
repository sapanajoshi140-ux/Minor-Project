"""
POST /upload

Accepts a file upload from an authenticated user, saves it to disk,
classifies it, processes it through the appropriate service, stores
metadata + pages in MySQL, generates a searchable PDF, and returns the
document_id.

OCR Formatting integration
--------------------------
After each page is committed to the DB the page ID is pushed onto the
shared formatting queue (services.ocr_formatter.enqueue_page).  A
background worker (started in main.py lifespan) drains that queue
asynchronously using Ollama, so:

  1. Upload completes and returns immediately — workspace shows raw OCR text.
  2. Background worker formats pages one by one via Ollama.
  3. Workspace switches to formatted_text once formatting_status=="completed".

Digital pages (ocr_type=="digital") are marked "skipped" — they are already
well-structured text from LibreOffice/PyMuPDF and need no OCR cleanup.

Auth & quota
------------
- Every request must carry a valid Bearer access token (Authorization header).
- The document is stored under the authenticated user's account and is only
  visible to that user.
- Each user may store at most USER_STORAGE_LIMIT_BYTES (default 500 MB) of
  uploaded files.  Attempting to exceed this limit returns HTTP 413.
"""

import logging
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB, PAGE_COMMIT_BATCH_SIZE
from database import Document, DocumentPage, User, USER_STORAGE_LIMIT_BYTES, get_db
from schemas import UploadResponse
from services.parser_service import FileType, detect_file_type, stream_document
from services.classifier_service import classify_document
from services.pdf_generator_service import generate_searchable_pdf
from services.ocr_formatter import enqueue_page, notify_page_event
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Upload"])

# ── RAG path setup ────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parent.parent   # document_workspace/app
_RAG_DIR = _APP_DIR.parent / "rag"                  # document_workspace/rag

if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))


def _needs_formatting(ocr_type: str | None) -> bool:
    """
    Return True when a page should be queued for Ollama formatting.

    Digital pages already have clean, structured text (embedded PDF/DOCX).
    Only printed/handwritten OCR output benefits from reformatting.
    """
    return ocr_type in ("printed", "handwritten")


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a document (auth required)",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, DOC, DOCX, PPT, PPTX, TXT, PNG, JPG, or JPEG"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadResponse:
    """
    Full pipeline:
    1. Validate extension
    2. Enforce per-user storage quota
    3. Save to disk
    4. Classify: "text" or "scanned"
    5. Extract / OCR all pages (streamed to DB in batches)
    6. Generate searchable PDF
    7. Ingest into RAG
    8. Finalise document record and update user storage counter
    9. Enqueue OCR pages for async Ollama formatting
    """

    # ── 1. Validate filename / extension ──────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    try:
        file_type: FileType = detect_file_type(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── 2. Save file to disk (stream + size check) ────────────────────────────
    doc_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    stored_filename = f"{doc_id}{ext}"
    file_path = Path(UPLOAD_DIR) / stored_filename

    try:
        total_bytes = 0
        with open(file_path, "wb") as fh:
            while chunk := await file.read(65_536):
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE_BYTES:
                    fh.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the maximum allowed size of {MAX_FILE_SIZE_MB} MB.",
                    )
                fh.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"File save error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # ── 3. Enforce per-user storage quota ─────────────────────────────────────
    db.refresh(current_user)
    if current_user.used_storage_bytes + total_bytes > USER_STORAGE_LIMIT_BYTES:
        file_path.unlink(missing_ok=True)
        used_mb  = round(current_user.used_storage_bytes / (1024 * 1024), 1)
        limit_mb = round(USER_STORAGE_LIMIT_BYTES / (1024 * 1024), 0)
        raise HTTPException(
            status_code=413,
            detail=(
                f"Storage quota exceeded. "
                f"You have used {used_mb} MB of your {int(limit_mb)} MB allowance. "
                f"Please delete some documents before uploading more."
            ),
        )

    # ── 4. Classify ───────────────────────────────────────────────────────────
    document_category = classify_document(str(file_path))
    logger.info(f"Document {doc_id} classified as: {document_category}")

    # ── 5. Create pending DB record ───────────────────────────────────────────
    document = Document(
        id=doc_id,
        user_id=current_user.id,
        filename=file.filename,
        file_type=file_type.value,
        file_path=str(file_path),
        file_size_bytes=total_bytes,
        document_category=document_category,
        processing_status="processing",
    )
    db.add(document)
    db.commit()

    # ── 6. Process and stream pages into DB ───────────────────────────────────
    confidences:   list[float] = []
    total_pages    = 0
    all_pages:     list[dict]  = []
    is_pure_text   = (document_category == "text")

    # Collect DB page IDs that need async formatting after commit.
    pages_to_format: list[int] = []   # DocumentPage.id values

    try:
        for page in stream_document(str(file_path), file_type):
            total_pages += 1
            all_pages.append(page)

            ocr_type      = page.get("ocr_type")
            raw_text      = page.get("extracted_text")
            needs_fmt     = _needs_formatting(ocr_type)

            # Determine the initial formatting_status for this page.
            if is_pure_text or not needs_fmt:
                fmt_status = "skipped"
            else:
                fmt_status = "pending"

            if not is_pure_text and raw_text is not None:
                db_page = DocumentPage(
                    document_id             = doc_id,
                    page_number             = page["page_number"],
                    extracted_text          = raw_text,
                    raw_ocr_text            = raw_text,   # immutable original copy
                    formatted_text          = None,
                    formatting_status       = fmt_status,
                    ocr_type                = ocr_type,
                    confidence_score        = page.get("confidence_score"),
                )
                db.add(db_page)

                if page.get("confidence_score") is not None:
                    confidences.append(page["confidence_score"])

                # Flush to get the auto-generated PK without closing the
                # transaction, so we can collect IDs for the formatter queue.
                # Both pending and skipped pages are flushed so the PK exists
                # before we push the SSE event.
                db.flush()
                if fmt_status == "pending":
                    pages_to_format.append(db_page.id)

                # ── Progressive streaming: notify SSE subscribers immediately.
                # Raw OCR text is in the DB (flushed) and ready to display;
                # the workspace should render this page without waiting for the
                # rest of the document or for Ollama formatting to complete.
                notify_page_event(doc_id, {
                    "event_type":        "ocr_ready",
                    "page_number":       page["page_number"],
                    "formatting_status": fmt_status,
                    "display_text":      raw_text,
                    "ocr_type":          ocr_type,
                    "confidence_score":  page.get("confidence_score"),
                })

            if total_pages % PAGE_COMMIT_BATCH_SIZE == 0:
                db.commit()
                logger.info(f"Document {doc_id} — committed batch up to page {total_pages}.")

        db.commit()
        logger.info(f"Document {doc_id} — final page batch committed ({total_pages} total).")

        # Notify subscribers that all OCR pages have been extracted and stored.
        # The stream will remain open until Ollama formatting completes.
        notify_page_event(doc_id, {
            "event_type":  "upload_complete",
            "total_pages": total_pages,
        })

    except Exception as exc:
        logger.error(f"Processing failed for document {doc_id}: {exc}", exc_info=True)
        document.processing_status = "failed"
        db.commit()
        try:
            file_path.unlink(missing_ok=True)
        except OSError as unlink_exc:
            logger.warning(f"Could not delete orphaned file '{file_path}': {unlink_exc}")
        raise HTTPException(status_code=422, detail="Document processing failed.")

    # ── 7. Generate searchable PDF ────────────────────────────────────────────
    generated_pdf_path: str | None = None
    try:
        generated_pdf_path = generate_searchable_pdf(
            document_id=doc_id,
            document_category=document_category,
            original_file_path=str(file_path),
            pages=all_pages,
            original_filename=file.filename,
        )
        logger.info(f"Document {doc_id} — searchable PDF: {generated_pdf_path}")
    except Exception as exc:
        logger.error(f"PDF generation failed for {doc_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}")

    # ── 8. Ingest into RAG ────────────────────────────────────────────────────
    try:
        import importlib
        _rag_ingest           = importlib.import_module("ingest")
        ingest_from_db_pages  = _rag_ingest.ingest_from_db_pages
        ingest_from_file_path = _rag_ingest.ingest_from_file_path

        if document_category == "text":
            rag_result = ingest_from_file_path(
                doc_id,
                str(file_path),
                generated_pdf_path=generated_pdf_path,
            )
        else:
            rag_result = ingest_from_db_pages(doc_id, all_pages)

        logger.info(
            f"Document {doc_id} — RAG ingested: "
            f"{rag_result['chunks']} chunks from {rag_result['pages']} page(s)."
        )
    except Exception as exc:
        logger.error(f"RAG ingestion failed for {doc_id}: {exc}", exc_info=True)

    # ── 9. Finalise document record + update quota counter ────────────────────
    document.total_pages        = total_pages
    document.average_confidence = (
        round(sum(confidences) / len(confidences), 4) if confidences else None
    )
    document.generated_pdf_path = generated_pdf_path
    document.processing_status  = "completed"

    current_user.used_storage_bytes = User.used_storage_bytes + total_bytes
    db.commit()

    logger.info(
        f"Document {doc_id} completed — "
        f"{total_pages} page(s), category={document_category}, "
        f"user={current_user.email}, size={total_bytes} bytes"
    )

    # ── 10. Enqueue OCR pages for async Ollama formatting ─────────────────────
    # Done AFTER the document is fully committed so the worker always finds
    # valid FK references when it opens its own session.
    if pages_to_format:
        try:
            for page_id in pages_to_format:
                enqueue_page(page_id)
                enqueue_page(page_id)
            logger.info(
                f"Document {doc_id} — {len(pages_to_format)} page(s) enqueued "
                f"for Ollama formatting."
            )
        except Exception as exc:
            # Formatter unavailable — workspace will still show raw OCR text.
            logger.warning(
                f"Could not enqueue formatting for document {doc_id}: {exc}. "
                f"Raw OCR text will be displayed."
            )

    return UploadResponse(
        document_id=doc_id,
        message="Document uploaded and processed successfully.",
        total_pages=total_pages,
        processing_status="completed",
        document_category=document_category,
        generated_pdf_path=generated_pdf_path,
    )