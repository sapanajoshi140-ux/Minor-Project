"""
ppt_service.py — extracts text from PowerPoint presentations via python-pptx.

Mixed-content handling
----------------------
For each slide the service first attempts to extract text (digital path).
If a slide has NO text shapes but DOES have picture shapes, it is treated
as an image-based slide:
  - the slide is rendered to a PIL image (via LibreOffice + PyMuPDF)
  - run through the standard OCR pipeline (Tesseract → TrOCR)

Output dict keys use DB-aligned names:
    extracted_text   (was "content")
    confidence_score (was "confidence")
    ocr_json         None for digital slides; OCR JSON for image slides
"""

from __future__ import annotations

import io
import logging
import tempfile
from typing import List, Optional

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

logger = logging.getLogger(__name__)


# ── Shape text extraction ─────────────────────────────────────────────────────

def _extract_shape_text(shape) -> str:
    lines: List[str] = []

    if shape.has_table:
        for row in shape.table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
        return "\n".join(lines)

    if shape.has_text_frame:
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            level  = para.level or 0
            indent = "  " * level
            prefix = f"{indent}• " if level > 0 else ""
            lines.append(f"{prefix}{text}")

    return "\n".join(lines)


def _is_title_shape(shape, slide) -> bool:
    try:
        return shape == slide.shapes.title
    except Exception:
        return False


def _has_picture(slide) -> bool:
    for shape in slide.shapes:
        try:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                return True
        except Exception:
            pass
    return False


# ── Slide rendering (for image-only slides) ───────────────────────────────────

def _render_slide_to_pil(pptx_path: str, slide_index: int) -> Optional[object]:
    """
    Render a PPTX slide to a PIL Image by converting the deck to PDF first
    (via LibreOffice if available), then rasterising with PyMuPDF.

    FIX: previously returned a 1×1 white pixel on failure, which caused
    OCR to run on a blank image and store empty text with 0.0 confidence
    silently.  Now returns None so the caller can skip the slide explicitly.
    """
    try:
        import subprocess
        import shutil

        if not shutil.which("libreoffice") and not shutil.which("soffice"):
            raise RuntimeError("LibreOffice not found — cannot render PPTX slide to image.")

        lo_bin = shutil.which("libreoffice") or "soffice"

        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [lo_bin, "--headless", "--convert-to", "pdf",
                 "--outdir", tmp, pptx_path],
                capture_output=True, timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"LibreOffice conversion failed (exit {result.returncode}): "
                    f"{result.stderr.decode(errors='replace')}"
                )

            import fitz
            from pathlib import Path
            from PIL import Image

            pdf_files = list(Path(tmp).glob("*.pdf"))
            if not pdf_files:
                raise RuntimeError("LibreOffice produced no PDF output.")

            doc = fitz.open(str(pdf_files[0]))
            if slide_index >= len(doc):
                doc.close()
                raise IndexError(
                    f"Slide index {slide_index} out of range "
                    f"(document has {len(doc)} page(s))."
                )

            page = doc[slide_index]
            mat  = fitz.Matrix(2.0, 2.0)
            pix  = page.get_pixmap(matrix=mat)
            doc.close()

            return Image.open(io.BytesIO(pix.tobytes("png")))

    except Exception as exc:
        # FIX: was silently returning a 1×1 blank image.  Log clearly and
        #      return None so the caller can skip this slide rather than
        #      storing empty OCR results.
        logger.warning(
            f"Slide rendering failed (slide index {slide_index}, file '{pptx_path}'): "
            f"{exc} — slide will be skipped."
        )
        return None


# ── OCR for image slide ───────────────────────────────────────────────────────

def _ocr_slide(pptx_path: str, slide_index: int) -> Optional[dict]:
    """
    Render and OCR a single image-only slide.
    Returns a page-data dict, or None if rendering failed.
    """
    from services.image_service import preprocess_for_printed
    from services.ocr_service import ocr_with_fallback

    pil_image = _render_slide_to_pil(pptx_path, slide_index)

    # FIX: propagate None from renderer — caller skips the slide.
    if pil_image is None:
        return None

    preprocessed = preprocess_for_printed(pil_image)
    result       = ocr_with_fallback(preprocessed)

    return {
        "extracted_text":   result.text,
        "ocr_type":         result.ocr_type,
        "confidence_score": round(result.confidence, 4),
    }


# ── Public entry point ────────────────────────────────────────────────────────

def process_ppt_file(file_path: str) -> List[dict]:
    """
    Parse a .ppt / .pptx file and return one page dict per (non-blank) slide.
    Image-only slides are OCR-processed automatically; slides that cannot be
    rendered (e.g. LibreOffice unavailable) are skipped with a warning.
    """
    logger.info(f"Processing PowerPoint: {file_path}")

    try:
        prs   = Presentation(file_path)
        pages : List[dict] = []

        for slide_num, slide in enumerate(prs.slides, start=1):
            slide_idx = slide_num - 1          # 0-based for rendering
            parts: List[str] = []

            # ── Title ──────────────────────────────────────────────────────
            title_text = ""
            try:
                if slide.shapes.title and slide.shapes.title.has_text_frame:
                    title_text = slide.shapes.title.text.strip()
            except Exception:
                pass

            if title_text:
                parts.append(f"# {title_text}")

            # ── Body shapes ────────────────────────────────────────────────
            for shape in slide.shapes:
                if _is_title_shape(shape, slide):
                    continue
                text = _extract_shape_text(shape)
                if text.strip():
                    parts.append(text)

            # ── Speaker notes ──────────────────────────────────────────────
            try:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    parts.append(f"[Notes]: {notes}")
            except Exception:
                pass

            combined = "\n\n".join(parts).strip()

            # ── Image-only slide → OCR ────────────────────────────────────
            if not combined and _has_picture(slide):
                logger.info(f"Slide {slide_num}: image-only — running OCR.")
                ocr_data = _ocr_slide(file_path, slide_idx)

                # FIX: skip slide if rendering returned None (LibreOffice
                #      unavailable or conversion failed) rather than storing
                #      empty text silently.
                if ocr_data is None:
                    logger.warning(
                        f"Slide {slide_num}: skipped (rendering unavailable)."
                    )
                    continue

                pages.append({
                    "page_number": slide_num,
                    **ocr_data,
                })
                continue

            # ── Blank slide (no text, no image) → skip ────────────────────
            if not combined:
                logger.debug(f"Slide {slide_num}: blank, skipping.")
                continue

            pages.append({
                "page_number":      slide_num,
                "extracted_text":   combined,
                "ocr_type":         "digital",
                "confidence_score": 1.0,
            })
            logger.debug(f"Slide {slide_num}: {len(combined)} chars extracted.")

        if not pages:
            return [{
                "page_number":      1,
                "extracted_text":   "",
                "ocr_type":         "digital",
                "confidence_score": 1.0,
            }]

        logger.info(f"PowerPoint: {len(pages)} slide(s) processed.")
        return pages

    except Exception as exc:
        logger.error(f"PPT processing error for {file_path}: {exc}", exc_info=True)
        raise