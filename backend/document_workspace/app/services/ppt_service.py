"""
PPT / PPTX Service — extracts text from PowerPoint presentations via python-pptx.

Features:
  - Each slide becomes one logical "page"
  - Extracts text from all shapes (text boxes, titles, content placeholders)
  - Preserves slide title as a header (Markdown # style)
  - Extracts speaker notes if present
  - Handles tables: each cell's text is extracted row by row
  - Skips blank slides
"""

import logging
from typing import List

from pptx import Presentation
from pptx.util import Pt
from pptx.enum.text import PP_ALIGN

logger = logging.getLogger(__name__)


def _extract_shape_text(shape) -> str:
    """
    Extract text from a single shape.
    Handles text frames and tables.
    Returns empty string if the shape has no text.
    """
    lines = []

    # Table shapes
    if shape.has_table:
        for row in shape.table.rows:
            row_texts = [
                cell.text.strip()
                for cell in row.cells
                if cell.text.strip()
            ]
            if row_texts:
                lines.append(" | ".join(row_texts))
        return "\n".join(lines)

    # Text frame shapes
    if shape.has_text_frame:
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Detect bullet level — indent with spaces
            level = para.level or 0
            indent = "  " * level
            prefix = f"{indent}• " if level > 0 else ""
            lines.append(f"{prefix}{text}")

    return "\n".join(lines)


def _is_title_shape(shape, slide) -> bool:
    """Return True if this shape is the slide's title placeholder."""
    try:
        return shape == slide.shapes.title
    except Exception:
        return False


def process_ppt_file(file_path: str) -> List[dict]:
    """
    Parse a .ppt / .pptx file and return one page dict per slide.
    Returns a list of page dicts compatible with parser_service output format.

    Each dict has:
        page_number  : slide number (1-based)
        content      : extracted text (title as # heading + body + notes)
        ocr_type     : always "digital"
        confidence   : always 1.0
    """
    logger.info(f"Processing PowerPoint file: {file_path}")

    try:
        prs = Presentation(file_path)
        pages: List[dict] = []

        for slide_num, slide in enumerate(prs.slides, start=1):
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

            # ── Body shapes (skip title, already handled) ──────────────────
            for shape in slide.shapes:
                if _is_title_shape(shape, slide):
                    continue
                text = _extract_shape_text(shape)
                if text.strip():
                    parts.append(text)

            # ── Speaker notes ──────────────────────────────────────────────
            try:
                notes_slide = slide.notes_slide
                notes_text = notes_slide.notes_text_frame.text.strip()
                if notes_text:
                    parts.append(f"[Notes]: {notes_text}")
            except Exception:
                pass  # No notes or notes not accessible

            combined = "\n\n".join(parts).strip()

            # Skip entirely blank slides
            if not combined:
                logger.debug(f"Slide {slide_num}: blank, skipping.")
                continue

            pages.append({
                "page_number": slide_num,
                "content": combined,
                "ocr_type": "digital",
                "confidence": 1.0,
            })

            logger.debug(f"Slide {slide_num}: {len(combined)} chars extracted.")

        if not pages:
            # Return one empty page rather than an empty list
            return [{
                "page_number": 1,
                "content": "",
                "ocr_type": "digital",
                "confidence": 1.0,
            }]

        logger.info(f"PowerPoint processed: {len(pages)} slide(s) extracted.")
        return pages

    except Exception as exc:
        logger.error(
            f"PowerPoint processing error for {file_path}: {exc}", exc_info=True
        )
        raise