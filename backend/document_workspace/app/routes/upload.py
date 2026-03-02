"""
POST /upload

Accepts a file upload, saves it to disk, processes it through the
appropriate service, stores metadata + pages in MySQL, and returns
the document_id.
"""

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.database import Document, DocumentPage
from document_workspace.app.schemas import UploadResponse
from app.services.parser_service import FileType, detect_file_type, stream_document

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Upload"])

# How many pages to accumulate before flushing to DB.
# Matches the same constant in main.py — override via PAGE_COMMIT_BATCH_SIZE in .env.
PAGE_COMMIT_BATCH_SIZE = int(os.getenv("PAGE_COMMIT_BATCH_SIZE", "10"))


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a document",
)
async def upload_document(
    file: UploadFile = File(..., description="PDF, DOC, DOCX, PPT, PPTX, TXT, PNG, JPG, or JPEG"),
    db: Session = Depends(get_db),
) -> UploadResponse:

    # ── 1. Validate filename / extension ──────────────────────────────────────
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    try:
        file_type: FileType = detect_file_type(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── 2. Save file to disk ──────────────────────────────────────────────────
    doc_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower()
    stored_filename = f"{doc_id}{ext}"
    file_path = settings.UPLOAD_PATH / stored_filename

    try:
        total_bytes = 0
        with open(file_path, "wb") as fh:
            while chunk := await file.read(65_536):   # 64 KB chunks
                total_bytes += len(chunk)
                if total_bytes > settings.MAX_FILE_SIZE_BYTES:
                    fh.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of "
                               f"{settings.MAX_FILE_SIZE_MB} MB.",
                    )
                fh.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"File save error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # ── 3. Create pending DB record ───────────────────────────────────────────
    document = Document(
        id=doc_id,
        filename=file.filename,
        file_type=file_type.value,
        file_path=str(file_path),
        processing_status="processing",
    )
    db.add(document)
    db.commit()

    # ── 4. Process and stream pages into DB ───────────────────────────────────
    # Uses stream_document() (generator) instead of process_document() (loads
    # all pages into memory at once). Pages are committed in batches of
    # PAGE_COMMIT_BATCH_SIZE to balance durability and DB round-trips.
    confidences = []
    total_pages = 0
    try:
        for page in stream_document(str(file_path), file_type):
            db.add(DocumentPage(
                document_id=doc_id,
                page_number=page["page_number"],
                content=page.get("content"),
                ocr_type=page.get("ocr_type"),
                confidence=page.get("confidence"),
            ))
            if page.get("confidence") is not None:
                confidences.append(page["confidence"])
            total_pages += 1

            # Batch commit every N pages — avoids one DB round-trip per page
            if total_pages % PAGE_COMMIT_BATCH_SIZE == 0:
                db.commit()
                logger.info(f"Document {doc_id} — committed batch up to page {total_pages}.")

        # Flush any remaining pages not caught by the batch boundary
        db.commit()
        logger.info(f"Document {doc_id} — final page batch committed ({total_pages} total).")

    except Exception as exc:
        logger.error(f"Processing failed for document {doc_id}: {exc}", exc_info=True)
        document.processing_status = "failed"
        db.commit()
        # FIX: delete the uploaded file so it doesn't orphan on disk
        file_path.unlink(missing_ok=True)
        logger.info(f"Cleaned up orphaned file after processing failure: {file_path}")
        raise HTTPException(
            status_code=422,
            detail="Document processing failed.",
        )

    # ── 5. Finalise document record ───────────────────────────────────────────
    document.total_pages = total_pages
    document.average_confidence = (
        round(sum(confidences) / len(confidences), 4) if confidences else None
    )
    document.processing_status = "completed"
    db.commit()

    logger.info(
        f"Document {doc_id} completed — "
        f"{total_pages} page(s), "
        f"avg confidence: {document.average_confidence}"
    )

    return UploadResponse(
        document_id=doc_id,
        message="Document uploaded and processed successfully.",
        total_pages=total_pages,
        processing_status="completed",
    )