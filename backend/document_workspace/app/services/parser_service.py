"""
parser_service.py — file-type detection and routing to the correct sub-service.

This is the single entry point for document processing.

All sub-services now emit page dicts with DB-aligned field names:
    page_number      int
    extracted_text   str
    ocr_type         "digital" | "printed" | "handwritten"
    confidence_score float  (0.0 – 1.0)
    ocr_json         dict | None   (structured OCR output; None for digital)
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Generator, List

logger = logging.getLogger(__name__)


class FileType(str, Enum):
    PDF  = "pdf"
    DOCX = "docx"
    DOC  = "doc"
    PPT  = "ppt"
    PPTX = "pptx"
    TXT  = "txt"
    PNG  = "png"
    JPG  = "jpg"
    JPEG = "jpeg"


ALLOWED_EXTENSIONS: set[str] = {ft.value for ft in FileType}


def detect_file_type(filename: str) -> FileType:
    """
    Detect file type from extension.
    Raises ValueError for unsupported types.
    """
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '.{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return FileType(ext)


def process_document(file_path: str, file_type: FileType) -> List[dict]:
    """
    Route to the appropriate service and return a list of page dicts.
    Each dict has the shape described in the module docstring.
    """
    logger.info(f"Routing '{file_path}' → {file_type.value} processor")
    return list(stream_document(file_path, file_type))


def stream_document(
    file_path: str, file_type: FileType
) -> Generator[dict, None, None]:
    """
    Generator version of process_document.
    Yields one page dict at a time so the caller can persist pages
    incrementally without holding all pages in memory.
    """
    logger.info(f"Streaming '{file_path}' → {file_type.value} processor")

    match file_type:
        case FileType.PDF:
            from services.pdf_service import process_pdf_file
            yield from process_pdf_file(file_path)

        case FileType.DOC | FileType.DOCX:
            from services.doc_service import process_doc_file
            yield from process_doc_file(file_path)

        case FileType.PPT | FileType.PPTX:
            from services.ppt_service import process_ppt_file
            yield from process_ppt_file(file_path)

        case FileType.TXT:
            from services.txt_service import process_txt_file
            yield from process_txt_file(file_path)

        case FileType.PNG | FileType.JPG | FileType.JPEG:
            from services.image_service import process_image_file
            yield from process_image_file(file_path)

        case _:
            raise ValueError(f"No processor registered for file type: {file_type}")