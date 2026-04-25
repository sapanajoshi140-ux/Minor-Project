"""
POST /upload

Accepts a file upload from an authenticated user, saves it to disk,
classifies it, processes it through the appropriate service, stores
metadata + pages in MySQL, generates a searchable PDF, and returns the
document_id.

Auth & quota
------------
- Every request must carry a valid Bearer access token (Authorization header).
- The document is stored under the authenticated user's account and is only
  visible to that user.
- Each user may store at most USER_STORAGE_LIMIT_BYTES (default 500 MB) of
  uploaded files.  Attempting to exceed this limit returns HTTP 413.
"""

import logging
import os
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB
from database import Document, DocumentPage, User, USER_STORAGE_LIMIT_BYTES, get_db
from schemas import UploadResponse
from services.parser_service import FileType, detect_file_type, stream_document
from services.classifier_service import classify_document
from services.pdf_generator_service import generate_searchable_pdf
from dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Upload"])

PAGE_COMMIT_BATCH_SIZE = int(os.getenv("PAGE_COMMIT_BATCH_SIZE", "10"))

# ── RAG path setup ────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parent.parent   # document_workspace/app
_RAG_DIR = _APP_DIR.parent / "rag"                  # document_workspace/rag

if str(_RAG_DIR) not in sys.path:
    sys.path.insert(0, str(_RAG_DIR))


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
    confidences: list[float] = []
    total_pages = 0
    all_pages: list[dict] = []
    is_pure_text = (document_category == "text")

    try:
        for page in stream_document(str(file_path), file_type):
            total_pages += 1
            all_pages.append(page)

            if not is_pure_text and page.get("extracted_text") is not None:
                db.add(DocumentPage(
                    document_id      = doc_id,
                    page_number      = page["page_number"],
                    extracted_text   = page.get("extracted_text"),
                    ocr_type         = page.get("ocr_type"),
                    confidence_score = page.get("confidence_score"),
                ))

                if page.get("confidence_score") is not None:
                    confidences.append(page["confidence_score"])

            if total_pages % PAGE_COMMIT_BATCH_SIZE == 0:
                db.commit()
                logger.info(f"Document {doc_id} — committed batch up to page {total_pages}.")

        db.commit()
        logger.info(f"Document {doc_id} — final page batch committed ({total_pages} total).")

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
            # Text doc (PDF / TXT / DOCX / PPTX) — load via generated PDF where needed.
            rag_result = ingest_from_file_path(
                doc_id,
                str(file_path),
                generated_pdf_path=generated_pdf_path,
            )
        else:
            # Scanned doc — chunk from OCR text already in all_pages.
            rag_result = ingest_from_db_pages(doc_id, all_pages)

        logger.info(
            f"Document {doc_id} — RAG ingested: "
            f"{rag_result['chunks']} chunks from {rag_result['pages']} page(s)."
        )
    except Exception as exc:
        # RAG failure must NOT fail the upload — document is already saved.
        logger.error(f"RAG ingestion failed for {doc_id}: {exc}", exc_info=True)

    # ── 9. Finalise document record + update quota counter ────────────────────
    document.total_pages        = total_pages
    document.average_confidence = (
        round(sum(confidences) / len(confidences), 4) if confidences else None
    )
    document.generated_pdf_path = generated_pdf_path
    document.processing_status  = "completed"

    # Atomically increment the user's storage counter.
    current_user.used_storage_bytes = User.used_storage_bytes + total_bytes
    db.commit()

    logger.info(
        f"Document {doc_id} completed — "
        f"{total_pages} page(s), category={document_category}, "
        f"user={current_user.email}, size={total_bytes} bytes"
    )

    return UploadResponse(
        document_id=doc_id,
        message="Document uploaded and processed successfully.",
        total_pages=total_pages,
        processing_status="completed",
        document_category=document_category,
        generated_pdf_path=generated_pdf_path,
    )