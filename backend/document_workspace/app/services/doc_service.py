"""
DOC / DOCX Service — extracts text from Word documents via python-docx.

Features:
  - Preserves headings (converted to Markdown-style #, ##, ###)
  - Preserves bullet / list paragraphs (• prefix)
  - Simulates page breaks by grouping N paragraphs per logical page
"""

import logging
from typing import List

from docx import Document

logger = logging.getLogger(__name__)

# Number of non-empty paragraphs to group into one logical "page"
_PARAGRAPHS_PER_PAGE = 15


def _format_paragraph(para) -> str:
    """Return a styled string for a single paragraph, or '' if empty."""
    text = para.text.strip()
    if not text:
        return ""

    style_name = (para.style.name or "").lower()

    if "heading" in style_name:
        # Extract heading level digit, default to 1
        digits = "".join(filter(str.isdigit, style_name))
        level = int(digits[0]) if digits else 1
        return f"{'#' * min(level, 6)} {text}"

    if "list" in style_name:
        return f"• {text}"

    return text


def process_doc_file(file_path: str) -> List[dict]:
    """
    Parse a .doc / .docx file and return logically paginated content.
    Returns a list of page dicts compatible with parser_service output format.
    """
    logger.info(f"Processing Word document: {file_path}")

    try:
        doc = Document(file_path)

        formatted = [_format_paragraph(p) for p in doc.paragraphs]
        non_empty = [p for p in formatted if p]

        if not non_empty:
            return [{
                "page_number": 1,
                "content": "",
                "ocr_type": "digital",
                "confidence": 1.0,
            }]

        # Split into page-sized chunks
        chunks = [
            non_empty[i: i + _PARAGRAPHS_PER_PAGE]
            for i in range(0, len(non_empty), _PARAGRAPHS_PER_PAGE)
        ]

        return [
            {
                "page_number": page_num,
                "content": "\n".join(chunk),
                "ocr_type": "digital",
                "confidence": 1.0,
            }
            for page_num, chunk in enumerate(chunks, start=1)
        ]

    except Exception as exc:
        logger.error(f"Word document processing error for {file_path}: {exc}", exc_info=True)
        raise