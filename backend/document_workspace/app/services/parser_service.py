"""
Parser Service — file type detection and routing to the correct sub-service.

This is the single entry point for document processing.
It detects the file type from the extension and delegates to:
  PDF       → pdf_service
  DOC/DOCX  → doc_service
  PPT/PPTX  → ppt_service
  TXT       → txt_service
  PNG/JPG/JPEG → image_service
"""

import logging
from enum import Enum
from pathlib import Path
from typing import List

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
    Detect file type from the filename extension.
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

    Each page dict has the shape:
        {
            "page_number": int,
            "content": str,
            "ocr_type": "digital" | "printed" | "handwritten",
            "confidence": float,   # 0.0 – 1.0
        }
    """
    logger.info(f"Routing '{file_path}' → {file_type.value} processor")

    match file_type:
        case FileType.PDF:
            from services.pdf_service import process_pdf_file
            return process_pdf_file(file_path)

        case FileType.DOC | FileType.DOCX:
            from services.doc_service import process_doc_file
            return process_doc_file(file_path)

        case FileType.PPT | FileType.PPTX:
            from services.ppt_service import process_ppt_file
            return process_ppt_file(file_path)

        case FileType.TXT:
            from services.txt_service import process_txt_file
            return process_txt_file(file_path)

        case FileType.PNG | FileType.JPG | FileType.JPEG:
            from services.image_service import process_image_file
            return process_image_file(file_path)

        case _:
            raise ValueError(f"No processor registered for file type: {file_type}")

def stream_document(file_path: str, file_type: FileType):
    """
    Generator version of process_document.
    Yields one page dict at a time so the caller can save each page
    to the DB immediately — avoiding holding all pages in memory and
    allowing partial results to be visible as soon as processing starts.
    """
    logger.info(f"Routing '{file_path}' → {file_type.value} processor (streaming)")

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