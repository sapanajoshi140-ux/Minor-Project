"""
pdf_service.py — handles both digital and scanned PDFs.

OCR routing
-----------
Digital pages    → text extracted directly by PyMuPDF; no OCR.
Scanned pages    → hybrid_ocr_page() (PaddleOCR/EasyOCR detection + TrOCR):
    If detection yields lines         → TrOCR recognises each crop; lines merged.
    If detection yields nothing       → Tesseract with TrOCR fallback (conf < 0.60).
Handwritten      → ocr_handwritten() (TrOCR only, no Tesseract).

Output includes per-line bounding boxes and confidence scores when the hybrid
pipeline runs, stored in ocr_metadata for downstream use (search, highlighting).

Streaming
---------
process_pdf_file() is a *generator* that yields one page dict at a time so
callers can persist and stream each page immediately without holding all pages
in memory.  Use list(process_pdf_file(...)) if you need all pages at once.
"""

from __future__ import annotations

import io
import logging
from typing import Any, Dict, Generator, List, Optional

import fitz
from PIL import Image

from services.image_service import preprocess_for_printed, preprocess_for_handwriting
from services.ocr_service import (
    hybrid_ocr_page,
    ocr_handwritten,
    HybridOCRResult,
    DetectedLine,
)

logger = logging.getLogger(__name__)

_DIGITAL_MIN_CHARS = 20

# Render resolution: 3× gives ~300 DPI for a standard A4 page scanned at 72 DPI.
# Higher values improve OCR quality but increase memory and processing time.
_RENDER_ZOOM = 3.0


def _is_digital(page: fitz.Page) -> bool:
    """Return True when the page has sufficient embedded text (not an image scan)."""
    return len(page.get_text("text").strip()) >= _DIGITAL_MIN_CHARS


def _render_page_to_pil(page: fitz.Page) -> Image.Image:
    """Rasterise a PDF page to a PIL Image at _RENDER_ZOOM resolution."""
    mat = fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM)
    pix = page.get_pixmap(matrix=mat)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def _serialise_lines(lines: List[DetectedLine]) -> List[Dict[str, Any]]:
    """
    Convert DetectedLine objects to plain dicts for JSON-serialisable storage.

    Each dict contains:
        bbox       : [x0, y0, x1, y1] in page-image pixel coordinates.
        text       : recognised text for the line.
        confidence : TrOCR per-line confidence (0–1).
    """
    return [
        {
            "bbox":       list(line.bbox),
            "text":       line.text,
            "confidence": line.confidence,
        }
        for line in lines
    ]


def process_pdf_file(
    file_path: str,
    document_category: str = "scanned",
) -> Generator[dict, None, None]:
    """
    Process every page of a PDF, yielding one page dict per page.

    Yields immediately after each page is processed so callers can stream
    results to the database and frontend without waiting for the whole document.

    document_category:
        "text"        → digital PDF; extracted_text=None, no OCR run.
        "scanned"     → hybrid pipeline (detection + TrOCR) with Tesseract fallback.
        "handwritten" → TrOCR only via ocr_handwritten().

    Page dict schema (all keys always present):
        page_number     : int
        extracted_text  : str | None  (None for digital pages)
        ocr_type        : "digital" | "printed" | "handwritten"
        confidence_score: float (0–1; 1.0 for digital)
        ocr_metadata    : dict | None
            {
              "lines"   : list of {bbox, text, confidence}  (hybrid path only)
              "fallback": bool  (True when Tesseract was used instead of detection)
            }
    """
    logger.info(
        f"Processing PDF '{file_path}' "
        f"(category='{document_category}', streaming=True)."
    )

    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        logger.error(f"Cannot open PDF '{file_path}': {exc}", exc_info=True)
        raise

    try:
        for page_num, page in enumerate(doc, start=1):
            logger.info(f"PDF page {page_num}: processing…")

            # ── Digital page — skip OCR entirely ─────────────────────────────
            if _is_digital(page):
                logger.debug(f"Page {page_num}: digital (embedded text).")
                yield {
                    "page_number":      page_num,
                    "extracted_text":   None,
                    "ocr_type":         "digital",
                    "confidence_score": 1.0,
                    "ocr_metadata":     None,
                }
                continue

            # ── Scanned / handwritten page — run OCR ──────────────────────────
            logger.info(
                f"Page {page_num}: scanned — OCR mode='{document_category}'."
            )
            pil_image = _render_page_to_pil(page)

            if document_category == "handwritten":
                # ── TrOCR only path ───────────────────────────────────────────
                preprocessed = preprocess_for_handwriting(pil_image)
                result       = ocr_handwritten(preprocessed)
                logger.info(
                    f"Page {page_num}: handwritten TrOCR, "
                    f"confidence={result.confidence:.3f}."
                )
                yield {
                    "page_number":      page_num,
                    "extracted_text":   result.text,
                    "ocr_type":         "handwritten",
                    "confidence_score": round(result.confidence, 4),
                    "ocr_metadata":     None,
                }

            else:
                # ── Hybrid pipeline (printed / scanned) ───────────────────────
                # Preprocess before detection: deskew, denoise, adaptive threshold.
                preprocessed = preprocess_for_printed(pil_image)

                hybrid: HybridOCRResult = hybrid_ocr_page(
                    preprocessed, ocr_type="printed"
                )

                logger.info(
                    f"Page {page_num}: hybrid OCR "
                    f"({'fallback' if hybrid.fallback else 'detection'}), "
                    f"confidence={hybrid.confidence:.3f}, "
                    f"lines={len(hybrid.lines)}, "
                    f"chars={len(hybrid.text)}."
                )

                ocr_metadata: Optional[Dict[str, Any]] = {
                    "lines":    _serialise_lines(hybrid.lines),
                    "fallback": hybrid.fallback,
                }

                yield {
                    "page_number":      page_num,
                    "extracted_text":   hybrid.text,
                    "ocr_type":         hybrid.ocr_type,
                    "confidence_score": round(hybrid.confidence, 4),
                    "ocr_metadata":     ocr_metadata,
                }

    finally:
        doc.close()