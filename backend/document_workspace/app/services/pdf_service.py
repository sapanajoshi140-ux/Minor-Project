"""
pdf_service.py — handles both digital and scanned PDFs.

OCR routing (fixed)
-------------------
Digital pages  → text extracted by PyMuPDF, stored as None (not saved to DB).
Scanned pages  → ocr_with_fallback():
    Tesseract confidence >= 0.60  → Tesseract result kept.
    Tesseract confidence <  0.60  → TrOCR also runs; best result kept.
Handwritten    → ocr_handwritten() (TrOCR only, no Tesseract).

The threshold is read from OCR_HANDWRITTEN_FALLBACK_THRESHOLD in .env.
"""

from __future__ import annotations

import io
import logging
from typing import List

import fitz
from PIL import Image

from services.image_service import preprocess_for_printed, preprocess_for_handwriting
from services.ocr_service import ocr_with_fallback, ocr_handwritten

logger = logging.getLogger(__name__)

_DIGITAL_MIN_CHARS = 20
_RENDER_ZOOM       = 3.0


def _is_digital(page: fitz.Page) -> bool:
    return len(page.get_text("text").strip()) >= _DIGITAL_MIN_CHARS


def _render_page_to_pil(page: fitz.Page) -> Image.Image:
    mat = fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM)
    pix = page.get_pixmap(matrix=mat)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def process_pdf_file(
    file_path: str,
    document_category: str = "scanned",
) -> List[dict]:
    """
    Process every page of a PDF.

    document_category:
        "text"        → digital PDF; extracted_text=None, no DocumentPage rows.
        "scanned"     → Tesseract with TrOCR fallback when confidence < 0.60.
        "handwritten" → TrOCR only.
    """
    logger.info(f"Processing PDF '{file_path}' (category='{document_category}').")
    pages_data: List[dict] = []

    try:
        doc = fitz.open(file_path)
        try:
            for page_num, page in enumerate(doc, start=1):

                if _is_digital(page):
                    pages_data.append({
                        "page_number":      page_num,
                        "extracted_text":   None,
                        "ocr_type":         "digital",
                        "confidence_score": 1.0,
                    })
                    logger.debug(f"Page {page_num}: digital.")

                else:
                    logger.info(f"Page {page_num}: scanned — OCR mode='{document_category}'.")
                    pil_image = _render_page_to_pil(page)

                    if document_category == "handwritten":
                        preprocessed = preprocess_for_handwriting(pil_image)
                        result       = ocr_handwritten(preprocessed)
                    else:
                        # "scanned": Tesseract first, TrOCR fallback if conf < 0.60.
                        preprocessed = preprocess_for_printed(pil_image)
                        result       = ocr_with_fallback(preprocessed)

                    logger.info(
                        f"Page {page_num}: ocr_type={result.ocr_type}, "
                        f"confidence={result.confidence:.3f}"
                    )
                    pages_data.append({
                        "page_number":      page_num,
                        "extracted_text":   result.text,
                        "ocr_type":         result.ocr_type,
                        "confidence_score": round(result.confidence, 4),
                    })

        finally:
            doc.close()

    except Exception as exc:
        logger.error(f"PDF processing error for '{file_path}': {exc}", exc_info=True)
        raise

    return pages_data