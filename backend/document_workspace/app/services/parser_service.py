"""
parser_service.py — file-type detection and routing to the correct sub-service.

This is the single entry point for document processing.

All sub-services emit page dicts with DB-aligned field names:
    page_number      int
    extracted_text   str | None   (None for digital PDF pages)
    ocr_type         "digital" | "printed" | "handwritten"
    confidence_score float        (0.0 – 1.0; 1.0 for digital)
    ocr_metadata     dict | None  — populated by the hybrid OCR pipeline:
        {
          "lines"   : [ {"bbox": [x0,y0,x1,y1], "text": str, "confidence": float}, … ]
          "fallback": bool   (True when Tesseract was used instead of line detection)
        }

Streaming
---------
stream_document() is a generator that yields one page dict at a time.
Callers (e.g. upload.py) should iterate it and persist/stream each page
immediately — this keeps peak memory low for large PDFs and lets the
frontend receive pages as they are ready rather than waiting for the whole
document to finish.

    for page in stream_document(file_path, file_type):
        db_save(page)                   # persist raw OCR text
        sse_emit("ocr_ready", page)     # stream to frontend
        enqueue_page(page["db_id"])     # schedule Ollama formatting
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

    Materialises the full generator into a list — use stream_document()
    directly when you want to process pages incrementally (recommended for
    large PDFs to avoid holding all pages in memory).
    """
    logger.info(f"Routing '{file_path}' → {file_type.value} processor")
    return list(stream_document(file_path, file_type))


def stream_document(
    file_path: str, file_type: FileType
) -> Generator[dict, None, None]:
    """
    Generator that yields one page dict per page/slide as it is processed.

    Callers should consume this lazily:

        for page in stream_document(path, ftype):
            # persist page to DB
            # emit SSE "ocr_ready" event
            # enqueue page for Ollama formatting

    PDF pages are yielded one at a time (process_pdf_file is itself a
    generator).  All other file types materialise all pages first and then
    yield them; this is acceptable because DOCX/PPTX/TXT processing is
    fast and memory-bounded.
    """
    logger.info(f"Streaming '{file_path}' → {file_type.value} processor")

    match file_type:
        case FileType.PDF:
            from services.pdf_service import process_pdf_file
            # pdf_service.process_pdf_file is a generator — yield directly
            # so each page is available to the caller as soon as OCR finishes.
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