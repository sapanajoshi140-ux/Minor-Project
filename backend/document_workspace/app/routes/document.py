"""
document.py — DEPRECATED / REMOVED

All document routes are defined directly in main.py:

  GET    /document/{document_id}                    — metadata
  GET    /document/{document_id}/page/{page_number} — single OCR page (scanned only)
  GET    /document/{document_id}/pages              — paginated OCR pages (scanned only)
  GET    /document/{document_id}/page/{n}/lines     — NDJSON line stream (scanned only)
  PUT    /document/{document_id}/page/{page_number} — update OCR page (scanned only)
  PUT    /document/{document_id}/edit               — bulk edit (scanned only)
  DELETE /document/{document_id}                    — delete document + files

  GET    /documents/{document_id}/view              — unified view endpoint
  POST   /documents/{document_id}/generate-pdf      — build / rebuild output PDF
  GET    /document/{document_id}/pdf                — download viewer-ready PDF

This file previously defined an APIRouter with a subset of these routes,
which caused duplicate route registration when main.py was also defining them.
It has been removed. Do not re-add a router here — all routing lives in main.py.
"""