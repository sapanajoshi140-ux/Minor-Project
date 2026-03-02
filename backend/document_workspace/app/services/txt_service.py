"""
TXT Service — reads plain-text files and splits them into logical pages.

Pagination strategy:
  1. Split the file on blank lines (paragraph groups).
  2. Accumulate paragraphs until the character limit is reached.
  3. Start a new page when the limit would be exceeded.
"""

import logging
from typing import List

import os
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


def process_txt_file(file_path: str) -> List[dict]:
    """
    Read a .txt file and paginate by paragraph grouping / character limit.
    Returns a list of page dicts compatible with parser_service output format.
    """
    logger.info(f"Processing TXT file: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()

        # Split on blank lines → paragraph list
        paragraphs = [p.strip() for p in raw.split("\n\n") if p.strip()]

        if not paragraphs:
            return [{
                "page_number": 1,
                "content": "",
                "ocr_type": "digital",
                "confidence": 1.0,
            }]

        char_limit = int(os.getenv("TXT_PAGE_CHAR_LIMIT", "3000"))
        pages_data: List[dict] = []
        current: List[str] = []
        current_len = 0
        page_num = 1

        for para in paragraphs:
            if current and current_len + len(para) > char_limit:
                # Flush current page
                pages_data.append({
                    "page_number": page_num,
                    "content": "\n\n".join(current),
                    "ocr_type": "digital",
                    "confidence": 1.0,
                })
                page_num += 1
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += len(para)

        # Flush remaining content
        if current:
            pages_data.append({
                "page_number": page_num,
                "content": "\n\n".join(current),
                "ocr_type": "digital",
                "confidence": 1.0,
            })

        return pages_data

    except Exception as exc:
        logger.error(f"TXT processing error for {file_path}: {exc}", exc_info=True)
        raise