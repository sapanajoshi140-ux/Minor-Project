"""
PDF Service — handles both digital and scanned PDFs.

Logic per page:
  - If the page contains enough extractable text  → "digital" (PyMuPDF direct extract)
  - If the page is image-only / scanned           → render to PIL image
                                                   → preprocess with OpenCV
                                                   → OCR via Tesseract + EasyOCR fallback

Install:
  pip install pymupdf easyocr pytesseract
"""

import io
import logging
from typing import List

import fitz  # PyMuPDF
from PIL import Image

from services.image_service import preprocess_for_printed, preprocess_for_handwriting
from services.ocr_service import ocr_image

logger = logging.getLogger(__name__)

# Minimum character count to consider a page "digital" (not scanned)
_DIGITAL_MIN_CHARS = 20
# Render zoom factor — higher = better OCR quality, slower processing
_RENDER_ZOOM = 3.0


def _is_digital(page: fitz.Page) -> bool:
    """Return True if the page has enough embedded text to skip OCR."""
    return len(page.get_text("text").strip()) >= _DIGITAL_MIN_CHARS


def _render_page_to_pil(page: fitz.Page) -> Image.Image:
    """Render a PDF page to a PIL Image at _RENDER_ZOOM resolution."""
    mat = fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM)
    pix = page.get_pixmap(matrix=mat)
    return Image.open(io.BytesIO(pix.tobytes("png")))


def process_pdf_file(file_path: str) -> List[dict]:
    """
    Process every page of a PDF file.

    Digital pages: text extracted directly via PyMuPDF (confidence=1.0).
    Scanned pages: rendered to image → both preprocessing pipelines tried
                   → Tesseract run first, EasyOCR used as fallback if needed
                   → best confidence result is kept.

    Returns a list of page dicts compatible with the parser_service format.
    """
    logger.info(f"Processing PDF: {file_path}")
    pages_data: List[dict] = []

    try:
        doc = fitz.open(file_path)

        for page_num, page in enumerate(doc, start=1):
            if _is_digital(page):
                text = page.get_text("text").strip()
                pages_data.append({
                    "page_number": page_num,
                    "content": text,
                    "ocr_type": "digital",
                    "confidence": 1.0,
                })
                logger.debug(f"Page {page_num}: digital text extracted ({len(text)} chars).")

            else:
                logger.info(f"Page {page_num}: scanned — running OCR.")
                pil_image = _render_page_to_pil(page)

                # Run both preprocessing pipelines; ocr_image() handles
                # the Tesseract → EasyOCR fallback internally
                hw_result      = ocr_image(preprocess_for_handwriting(pil_image))
                printed_result = ocr_image(preprocess_for_printed(pil_image))
                result = (
                    hw_result
                    if hw_result.confidence >= printed_result.confidence
                    else printed_result
                )

                logger.info(
                    f"Page {page_num}: "
                    f"hw_conf={hw_result.confidence:.2f}, "
                    f"print_conf={printed_result.confidence:.2f} "
                    f"→ using {'handwriting' if result is hw_result else 'printed'} pipeline"
                )
                pages_data.append({
                    "page_number": page_num,
                    "content": result.text,
                    "ocr_type": result.ocr_type,
                    "confidence": round(result.confidence, 4),
                })

        doc.close()

    except Exception as exc:
        logger.error(f"PDF processing error for {file_path}: {exc}", exc_info=True)
        raise

    return pages_data