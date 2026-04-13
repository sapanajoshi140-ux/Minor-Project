"""
schemas.py — Pydantic request / response models for all API endpoints.

Changes
-------
- StorageUsageResponse added : for GET /me/storage
- DocumentListResponse added  : for GET /documents
- DocumentResponse updated    : includes file_size_bytes
- PageResponse / PageUpdateResponse: ocr_json field removed (was already gone)
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════════════════════
# Storage
# ══════════════════════════════════════════════════════════════════════════════

class StorageUsageResponse(BaseModel):
    used_bytes:      int
    limit_bytes:     int
    used_mb:         float
    limit_mb:        float
    available_bytes: int


# ══════════════════════════════════════════════════════════════════════════════
# Page-level schemas  (scanned documents only)
# ══════════════════════════════════════════════════════════════════════════════

class PageResponse(BaseModel):
    page_number:      int
    extracted_text:   Optional[str]   = None
    ocr_type:         Optional[str]   = None
    confidence_score: Optional[float] = None

    model_config = {"from_attributes": True}


class PaginatedPagesResponse(BaseModel):
    document_id: str
    total_pages: int
    page:        int
    limit:       int
    pages:       List[PageResponse]


# ══════════════════════════════════════════════════════════════════════════════
# Document-level schemas
# ══════════════════════════════════════════════════════════════════════════════

class DocumentResponse(BaseModel):
    id:                 str
    filename:           str
    file_type:          str
    file_path:          str
    file_size_bytes:    Optional[int]   = None
    document_category:  Optional[str]   = None
    total_pages:        Optional[int]   = None
    processing_status:  str
    average_confidence: Optional[float] = None
    generated_pdf_path: Optional[str]   = None
    created_at:         datetime
    updated_at:         datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    total:     int
    page:      int
    limit:     int
    documents: List[DocumentResponse]


# ══════════════════════════════════════════════════════════════════════════════
# View endpoint  — GET /documents/{id}/view
# ══════════════════════════════════════════════════════════════════════════════

class OcrLine(BaseModel):
    page_number:      int
    line_number:      int
    text:             str
    ocr_type:         Optional[str]   = None
    confidence_score: Optional[float] = None


class DocumentViewResponse(BaseModel):
    document_id:       str
    filename:          str
    document_category: str
    total_pages:       Optional[int]  = None
    pdf_url:           Optional[str]  = None
    ocr_lines:         List[OcrLine]  = []


# ══════════════════════════════════════════════════════════════════════════════
# Upload
# ══════════════════════════════════════════════════════════════════════════════

class UploadResponse(BaseModel):
    document_id:        str
    message:            str
    total_pages:        int
    processing_status:  str
    document_category:  Optional[str]  = None
    generated_pdf_path: Optional[str]  = None


# ══════════════════════════════════════════════════════════════════════════════
# Page update (single)
# ══════════════════════════════════════════════════════════════════════════════

class PageUpdateRequest(BaseModel):
    extracted_text: str = Field(..., min_length=1)


class PageUpdateResponse(BaseModel):
    document_id:    str
    page_number:    int
    extracted_text: str
    message:        str


# ══════════════════════════════════════════════════════════════════════════════
# Bulk edit
# ══════════════════════════════════════════════════════════════════════════════

class PageEditEntry(BaseModel):
    page_number:    int = Field(..., ge=1)
    extracted_text: str = Field(..., min_length=0)


class DocumentEditRequest(BaseModel):
    pages: List[PageEditEntry] = Field(..., min_length=1)


class DocumentEditResponse(BaseModel):
    document_id:   str
    updated_pages: List[int]
    skipped_pages: List[int]
    message:       str


# ══════════════════════════════════════════════════════════════════════════════
# PDF generation
# ══════════════════════════════════════════════════════════════════════════════

class GeneratePdfResponse(BaseModel):
    document_id: str
    pdf_url:     str
    message:     str


# ══════════════════════════════════════════════════════════════════════════════
# Delete
# ══════════════════════════════════════════════════════════════════════════════

class DeleteResponse(BaseModel):
    message: str


# ══════════════════════════════════════════════════════════════════════════════
# Line streaming
# ══════════════════════════════════════════════════════════════════════════════

class LineResponse(BaseModel):
    page_number: int
    line_number: int
    text:        str