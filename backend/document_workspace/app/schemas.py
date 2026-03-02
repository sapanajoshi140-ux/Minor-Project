from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ---------- PAGE ----------
class PageResponse(BaseModel):
    page_number: int
    content: Optional[str] = None
    ocr_type: Optional[str] = None       # "digital" | "printed" | "handwritten"
    confidence: Optional[float] = None

    model_config = {"from_attributes": True}


# ---------- DOCUMENT METADATA (no pages — lightweight) ----------
# Used by GET /document/{id} so the frontend doesn't receive
# all page content in one heavy response.
class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    file_path: str
    total_pages: int
    processing_status: str
    average_confidence: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------- PAGINATED PAGES ----------
# Used by GET /document/{id}/pages?page=1&limit=10
class PaginatedPagesResponse(BaseModel):
    document_id: str
    total_pages: int        # total pages in the document
    page: int               # current page number (1-based)
    limit: int              # page size requested
    pages: List[PageResponse]


# ---------- UPLOAD ----------
class UploadResponse(BaseModel):
    document_id: str
    message: str
    total_pages: int
    processing_status: str


# ---------- PAGE UPDATE ----------
class PageUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class PageUpdateResponse(BaseModel):
    document_id: str
    page_number: int
    content: str
    message: str


# ---------- DELETE ----------
class DeleteResponse(BaseModel):
    message: str