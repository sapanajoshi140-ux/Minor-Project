"""
Document routes:
  GET    /document/{document_id}                      — document metadata (no page content)
  GET    /document/{document_id}/page/{page_number}   — single page content
  GET    /document/{document_id}/pages?page=1&limit=10 — paginated page content
  PUT    /document/{document_id}/page/{page_number}   — update page content
  DELETE /document/{document_id}                      — delete from DB + disk
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.database import Document, DocumentPage
from document_workspace.app.schemas import (
    DeleteResponse,
    DocumentResponse,
    PageResponse,
    PaginatedPagesResponse,
    PageUpdateRequest,
    PageUpdateResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Documents"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_doc_or_404(document_id: str, db: Session) -> Document:
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return doc


# ── GET /document/{document_id} ───────────────────────────────────────────────

@router.get(
    "/document/{document_id}",
    response_model=DocumentResponse,
    summary="Retrieve document metadata (no page content)",
)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> Document:
    """
    Returns document metadata only — filename, file type, total pages,
    processing status, average confidence, timestamps.

    Page content is intentionally excluded to keep this response lightweight.
    Use /page/{n} or /pages to fetch content.
    """
    return _get_doc_or_404(document_id, db)


# ── GET /document/{document_id}/page/{page_number} ───────────────────────────

@router.get(
    "/document/{document_id}/page/{page_number}",
    response_model=PageResponse,
    summary="Retrieve a single page by page number",
)
def get_page(
    document_id: str,
    page_number: int,
    db: Session = Depends(get_db),
) -> PageResponse:
    """
    Returns the content of one specific page (1-based page number).
    Ideal for rendering pages one at a time in the frontend viewer.
    """
    if page_number < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Page number must be 1 or greater.",
        )

    doc = _get_doc_or_404(document_id, db)

    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
        .first()
    )
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_number} not found. Document has {doc.total_pages} page(s).",
        )
    return page


# ── GET /document/{document_id}/pages ────────────────────────────────────────

@router.get(
    "/document/{document_id}/pages",
    response_model=PaginatedPagesResponse,
    summary="Retrieve pages with pagination",
)
def get_pages(
    document_id: str,
    page: int = Query(default=1, ge=1, description="Batch number to return (1-based)"),
    limit: int = Query(default=10, ge=1, le=50, description="Number of pages per batch (max 50)"),
    db: Session = Depends(get_db),
) -> PaginatedPagesResponse:
    """
    Returns a paginated slice of document pages.

    Query params:
      page  — which batch to fetch (1-based, default: 1)
      limit — pages per batch (default: 10, max: 50)

    Examples:
      GET /document/{id}/pages             → pages 1–10
      GET /document/{id}/pages?page=2      → pages 11–20
      GET /document/{id}/pages?page=1&limit=5 → pages 1–5

    Use total_pages in the response to calculate how many batches exist:
      total_batches = ceil(total_pages / limit)
    """
    doc = _get_doc_or_404(document_id, db)

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
        total_pages=doc.total_pages,
        page=page,
        limit=limit,
        pages=pages,
    )


# ── PUT /document/{document_id}/page/{page_number} ────────────────────────────

@router.put(
    "/document/{document_id}/page/{page_number}",
    response_model=PageUpdateResponse,
    summary="Update the text content of a specific page",
)
def update_page(
    document_id: str,
    page_number: int,
    payload: PageUpdateRequest,
    db: Session = Depends(get_db),
) -> PageUpdateResponse:
    _get_doc_or_404(document_id, db)

    page = (
        db.query(DocumentPage)
        .filter(
            DocumentPage.document_id == document_id,
            DocumentPage.page_number == page_number,
        )
        .first()
    )
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Page {page_number} not found for document '{document_id}'.",
        )

    page.content = payload.content
    db.commit()
    logger.info(f"Page {page_number} of document {document_id} updated.")

    return PageUpdateResponse(
        document_id=document_id,
        page_number=page_number,
        content=page.content,
        message="Page updated successfully.",
    )


# ── DELETE /document/{document_id} ────────────────────────────────────────────

@router.delete(
    "/document/{document_id}",
    response_model=DeleteResponse,
    summary="Delete a document from the database and disk",
)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> DeleteResponse:
    doc = _get_doc_or_404(document_id, db)

    file_path = Path(doc.file_path)
    if file_path.exists():
        file_path.unlink()
        logger.info(f"Deleted file from disk: {file_path}")
    else:
        logger.warning(f"File not found on disk (skipping): {file_path}")

    db.delete(doc)
    db.commit()
    logger.info(f"Document {document_id} deleted from database.")

    return DeleteResponse(
        message=f"Document '{document_id}' deleted successfully."
    )