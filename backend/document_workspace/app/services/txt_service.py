"""
txt_service.py — reads plain-text files and splits them into logical pages.

Pagination strategy
-------------------
1. Split on blank lines (paragraph groups).
2. Accumulate paragraphs until the character limit (TXT_PAGE_CHAR_LIMIT) is reached.
3. Start a new page when the limit would be exceeded.

Output dict keys use DB-aligned names:
    extracted_text   (was "content")
    confidence_score (was "confidence")
"""

from __future__ import annotations

import logging
from typing import List

from config import TXT_PAGE_CHAR_LIMIT

logger = logging.getLogger(__name__)


def process_txt_file(file_path: str) -> List[dict]:
    """
    Read a .txt file and paginate by paragraph grouping / character limit.
    Returns a list of page dicts with DB-aligned field names.
    """
    logger.info(f"Processing TXT file: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()

        paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]

        if not paragraphs:
            return [{
                "page_number":      1,
                "extracted_text":   "",
                "ocr_type":         "digital",
                "confidence_score": 1.0,
            }]

        char_limit  = TXT_PAGE_CHAR_LIMIT
        pages_data  : List[dict] = []
        current     : List[str]  = []
        current_len = 0
        page_num    = 1

        for para in paragraphs:
            if current and current_len + len(para) > char_limit:
                pages_data.append(_make_page(page_num, current))
                page_num    += 1
                current      = [para]
                current_len  = len(para)
            else:
                current.append(para)
                current_len += len(para)

        if current:
            pages_data.append(_make_page(page_num, current))

        return pages_data

    except Exception as exc:
        logger.error(f"TXT processing error for {file_path}: {exc}", exc_info=True)
        raise


def _make_page(page_num: int, paragraphs: List[str]) -> dict:
    return {
        "page_number":      page_num,
        "extracted_text":   "\n\n".join(paragraphs),
        "ocr_type":         "digital",
        "confidence_score": 1.0,
    }