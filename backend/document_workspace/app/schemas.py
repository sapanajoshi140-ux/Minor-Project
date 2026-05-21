"""
schemas.py — Pydantic request / response models for all API endpoints.

Changes (notes update)
--------------------------
New schemas added:
  - PageNoteUpsertRequest   : body for PUT /documents/{id}/pages/{n}/note
  - PageNoteResponse        : single note returned after save
  - DocumentNotesResponse   : all notes for a document (bulk fetch on open)
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


# ══════════════════════════════════════════════════════════════════════════════
# Reading Sessions
# ══════════════════════════════════════════════════════════════════════════════

class ReadingSessionStartRequest(BaseModel):
    document_id: str = Field(..., description="UUID of the document being opened.")


class ReadingSessionStartResponse(BaseModel):
    session_id:  int
    document_id: str
    started_at:  datetime
    message:     str


class ReadingSessionEndRequest(BaseModel):
    session_id: int = Field(..., description="ID returned by POST /reading-session/start.")


class ReadingSessionEndResponse(BaseModel):
    session_id:       int
    document_id:      str
    duration_seconds: int
    duration_minutes: float
    message:          str


# ══════════════════════════════════════════════════════════════════════════════
# Reading Goal
# ══════════════════════════════════════════════════════════════════════════════

class ReadingGoalRequest(BaseModel):
    daily_goal_min: int = Field(..., ge=1, le=1440, description="Daily reading goal in minutes (1–1440).")


class ReadingGoalResponse(BaseModel):
    user_id:        int
    daily_goal_min: int
    message:        str


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard sub-schemas
# ══════════════════════════════════════════════════════════════════════════════

class DailyReadingEntry(BaseModel):
    """One bar in the Daily Reading Time chart."""
    date:    str   # "YYYY-MM-DD"
    minutes: float


class DocumentTimeEntry(BaseModel):
    id:               str
    filename:         str
    file_type:        str
    file_size_bytes:  Optional[int]  = None
    total_pages:      Optional[int]  = None
    created_at:       datetime
    time_spent_seconds: int


class VocabularyEntry(BaseModel):
    """One row in the Your Vocabulary panel."""
    word:          str
    meaning:       str
    synonym:       Optional[str] = None
    document_name: Optional[str] = None
    document_id:   Optional[str] = None
    looked_up_at:  datetime


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard  — GET /me/dashboard
# ══════════════════════════════════════════════════════════════════════════════

class DashboardStatsResponse(BaseModel):
    total_time_read_minutes:  float
    today_read_minutes:       float
    daily_goal_minutes:       int
    documents_read:           int
    total_documents_uploaded: int
    current_streak_days:      int
    best_streak_days:         int


class DashboardResponse(BaseModel):
    stats:            DashboardStatsResponse
    daily_chart:      List[DailyReadingEntry]
    recent_documents: List[DocumentTimeEntry]
    vocabulary:       List[VocabularyEntry]


# ══════════════════════════════════════════════════════════════════════════════
# Vocabulary list  — GET /me/vocabulary
# ══════════════════════════════════════════════════════════════════════════════

class VocabularyListResponse(BaseModel):
    total: int
    page:  int
    limit: int
    words: List[VocabularyEntry]


# ══════════════════════════════════════════════════════════════════════════════
# Dictionary
# ══════════════════════════════════════════════════════════════════════════════

class WordMeaningResponse(BaseModel):
    word:    str
    meaning: str
    synonym: str = ""
    example: str = ""
    source:  str


# ══════════════════════════════════════════════════════════════════════════════
# RAG — Chat
# ══════════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    question:   str              = Field(..., min_length=1)
    session_id: Optional[str]   = Field(default=None)
    doc_ids:    Optional[List[str]] = Field(default=None)
    top_k:      int              = Field(default=5,     ge=1, le=20)
    use_hybrid: bool             = Field(default=True)


class ChatResponse(BaseModel):
    answer:       str
    session_id:   str
    citations:    List[dict]
    sources_used: int


# ══════════════════════════════════════════════════════════════════════════════
# RAG — Summarize
# ══════════════════════════════════════════════════════════════════════════════

class SummarizeRequest(BaseModel):
    text:   str = Field(..., min_length=1, max_length=50_000)
    length: str = Field(default="medium")


class SummarizeResponse(BaseModel):
    summary:    str
    length:     str
    char_count: int


# ══════════════════════════════════════════════════════════════════════════════
# RAG — Session history
# ══════════════════════════════════════════════════════════════════════════════

class SessionHistoryResponse(BaseModel):
    session_id: str
    history:    List[dict]


# ══════════════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════════════

class HealthResponse(BaseModel):
    status:   str
    sessions: int


# ══════════════════════════════════════════════════════════════════════════════
# Page Notes  — per-page sticky notes in the document viewer
# ══════════════════════════════════════════════════════════════════════════════

class PageNoteUpsertRequest(BaseModel):
    """
    Body for PUT /documents/{document_id}/pages/{page_number}/note.
    An empty string is valid — it clears an existing note.
    """
    note_text: str = Field(
        ...,
        max_length=50_000,
        description="Note text for this page. Empty string clears the note.",
    )


class PageNoteResponse(BaseModel):
    """
    Returned after a successful note save (PUT) or single-page fetch (GET).
    """
    document_id: str
    page_number: int
    note_text:   str
    updated_at:  datetime

    model_config = {"from_attributes": True}


class DocumentNotesResponse(BaseModel):
    """
    Returned by GET /documents/{document_id}/notes.
    Contains ALL saved notes for this document for the current user so the
    frontend can pre-populate every page textarea in a single request.
    """
    document_id: str
    notes:       List[PageNoteResponse]