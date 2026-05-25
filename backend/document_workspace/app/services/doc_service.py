"""
doc_service.py — extracts text from Word documents via python-docx.

Features
--------
- Headings   → Markdown-style #, ##, ### prefixes
- List items → • prefix
- Logical pagination by grouping _PARAGRAPHS_PER_PAGE non-empty paragraphs

Output dict keys use DB-aligned names:
    extracted_text   (was "content")
    confidence_score (was "confidence")
"""

from __future__ import annotations

import logging
import re
from typing import List

from docx import Document

logger = logging.getLogger(__name__)

_PARAGRAPHS_PER_PAGE = 15


def _heading_level(style_name: str) -> int:
    """
    Extract the numeric heading level from a paragraph style name.

    FIX: the previous implementation collected ALL digits from the style name
    with `filter(str.isdigit, style)` then took only `digits[0]`, which
    broke for two-digit levels (e.g. "Heading 10" → digits="10" → level=1)
    and for localised names that contain digits elsewhere in the string.

    This version uses a regex to find the trailing integer explicitly, and
    falls back to level 1 if none is found.
    """
    m = re.search(r"(\d+)\s*$", style_name)
    return int(m.group(1)) if m else 1


def _format_paragraph(para) -> str:
    text = para.text.strip()
    if not text:
        return ""
    style = (para.style.name or "").lower()
    if "heading" in style:
        level = _heading_level(para.style.name)
        return f"{'#' * min(level, 6)} {text}"
    if "list" in style:
        return f"• {text}"
    return text


def process_doc_file(file_path: str) -> List[dict]:
    """
    Parse a .doc / .docx file and return logically paginated page dicts.
    Each dict uses DB-aligned field names.
    """
    logger.info(f"Processing Word document: {file_path}")

    try:
        doc       = Document(file_path)
        formatted = [_format_paragraph(p) for p in doc.paragraphs]
        non_empty = [p for p in formatted if p]

        if not non_empty:
            return [{
                "page_number":      1,
                "extracted_text":   "",
                "ocr_type":         "digital",
                "confidence_score": 1.0,
                "ocr_metadata":     None,
            }]

        chunks = [
            non_empty[i: i + _PARAGRAPHS_PER_PAGE]
            for i in range(0, len(non_empty), _PARAGRAPHS_PER_PAGE)
        ]

        return [
            {
                "page_number":      page_num,
                "extracted_text":   "\n".join(chunk),
                "ocr_type":         "digital",
                "confidence_score": 1.0,
                "ocr_metadata":     None,
            }
            for page_num, chunk in enumerate(chunks, start=1)
        ]

    except Exception as exc:
        logger.error(f"Word document processing error for {file_path}: {exc}", exc_info=True)
        raise