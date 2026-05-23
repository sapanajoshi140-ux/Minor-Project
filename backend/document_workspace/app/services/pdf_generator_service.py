"""
pdf_generator_service.py — Generate clean, faithful PDFs from processed documents.

Conversion strategy
-------------------
PDF input       → passthrough (byte copy, no re-encoding).
DOCX / DOC      → LibreOffice headless (pixel-perfect, raises if unavailable).
PPTX / PPT      → LibreOffice headless (pixel-perfect, raises if unavailable).
TXT             → ReportLab plain paginated text.
Scanned / Image → ReportLab OCR-text PDF.

LibreOffice path
----------------
On Linux/Mac, soffice / libreoffice must be on PATH.
On Windows, set LIBREOFFICE_PATH in .env, e.g.:
    LIBREOFFICE_PATH=C:\\Program Files\\LibreOffice\\program\\soffice.exe

Output
------
Written to:  <GENERATED_PDF_DIR>/<document_id>_output.pdf
Returns the absolute path string.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from config import GENERATED_PDF_DIR as _GENERATED_PDF_DIR, LIBREOFFICE_PATH

logger = logging.getLogger(__name__)

GENERATED_PDF_DIR = Path(_GENERATED_PDF_DIR)
GENERATED_PDF_DIR.mkdir(parents=True, exist_ok=True)

# ── ReportLab geometry (A4) — used only for TXT and scanned ──────────────────
PAGE_WIDTH  = 595.28
PAGE_HEIGHT = 841.89
MARGIN      = 60.0
CONTENT_W   = PAGE_WIDTH - 2 * MARGIN

# ── Fonts & sizes ─────────────────────────────────────────────────────────────
FONT_NORMAL   = "Helvetica"
FONT_BOLD     = "Helvetica-Bold"
FONT_SIZE     = 11
HEADING_SIZES = {1: 20, 2: 16, 3: 13, 4: 12, 5: 11, 6: 11}

_PDF_EXT           = {"pdf"}
_TEXT_DOC_EXTS     = {"doc", "docx"}
_PRESENTATION_EXTS = {"ppt", "pptx"}
_PLAIN_TEXT_EXTS   = {"txt"}
_IMAGE_EXTS        = {"png", "jpg", "jpeg"}


# ══════════════════════════════════════════════════════════════════════════════
# Public entry point
# ══════════════════════════════════════════════════════════════════════════════

def generate_searchable_pdf(
    document_id: str,
    document_category: str,
    original_file_path: str,
    pages: List[dict],
    original_filename: Optional[str] = None,
) -> str:
    out_path = GENERATED_PDF_DIR / f"{document_id}_output.pdf"
    ext      = Path(original_file_path).suffix.lstrip(".").lower()
    filename = Path(original_filename or original_file_path).stem

    if ext in _PDF_EXT:
        shutil.copy2(original_file_path, out_path)
        logger.info(f"PDF passthrough: {out_path}")
        return str(out_path)

    if ext in _TEXT_DOC_EXTS:
        _libreoffice_convert(original_file_path, out_path)
        logger.info(f"DOCX → PDF via LibreOffice: {out_path}")
        return str(out_path)

    if ext in _PRESENTATION_EXTS:
        _libreoffice_convert(original_file_path, out_path)
        logger.info(f"PPTX → PDF via LibreOffice: {out_path}")
        return str(out_path)

    if ext in _PLAIN_TEXT_EXTS:
        _build_text_pdf(pages, out_path, filename)
        logger.info(f"TXT → PDF: {out_path}")
        return str(out_path)

    if ext in _IMAGE_EXTS or document_category == "scanned":
        _build_ocr_text_pdf(pages, out_path, filename)
        logger.info(f"Scanned → OCR text PDF: {out_path}")
        return str(out_path)

    logger.warning(f"Unknown extension '.{ext}' — falling back to plain text PDF.")
    _build_text_pdf(pages, out_path, filename)
    return str(out_path)


# ══════════════════════════════════════════════════════════════════════════════
# LibreOffice converter  (DOCX + PPTX)
# ══════════════════════════════════════════════════════════════════════════════

def _libreoffice_convert(source_path: str, out_path: Path) -> None:
    """
    Convert *source_path* to PDF using LibreOffice headless.

    Writes the result to *out_path*.
    Raises RuntimeError if LibreOffice is not found or conversion fails.

    Path resolution order
    ---------------------
    1. LIBREOFFICE_PATH env var — for Windows installs.
       Set in .env: LIBREOFFICE_PATH=C:\\Program Files\\LibreOffice\\program\\soffice.exe
    2. shutil.which("libreoffice") / shutil.which("soffice") — Linux / Mac.
    """
    lo_bin = (
        LIBREOFFICE_PATH
        or shutil.which("libreoffice")
        or shutil.which("soffice")
    )
    if not lo_bin:
        raise RuntimeError(
            "LibreOffice not found. "
            "Install it and ensure it is on PATH, or set LIBREOFFICE_PATH in .env.\n"
            "  Linux/Mac : sudo apt install libreoffice  /  brew install libreoffice\n"
            "  Windows   : https://www.libreoffice.org/download/libreoffice-fresh/"
        )

    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                lo_bin,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", tmp,
                source_path,
            ],
            capture_output=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"LibreOffice conversion failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')}"
            )

        tmp_pdfs = list(Path(tmp).glob("*.pdf"))
        if not tmp_pdfs:
            raise RuntimeError(
                f"LibreOffice produced no PDF output for '{source_path}'."
            )

        shutil.move(str(tmp_pdfs[0]), str(out_path))


# ══════════════════════════════════════════════════════════════════════════════
# Shared ReportLab helpers  (TXT + scanned only)
# ══════════════════════════════════════════════════════════════════════════════

def _require_reportlab() -> None:
    try:
        from reportlab.platypus import SimpleDocTemplate  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "reportlab is not installed. Run: pip install reportlab"
        ) from exc


def _xml_escape(text: str) -> str:
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _safe_text(text: str) -> str:
    """Replace characters that Helvetica cannot encode."""
    try:
        from unidecode import unidecode
        return unidecode(text)
    except ImportError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


def _make_simple_doc(out_path: Path):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate
    return SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
    )


def _doc_title_style():
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle
    return ParagraphStyle(
        "DocTitle",
        fontName=FONT_BOLD,
        fontSize=22,
        leading=28,
        spaceBefore=0,
        spaceAfter=16,
        textColor=colors.black,
        alignment=TA_LEFT,
    )


def _heading_style(level: int):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    size = HEADING_SIZES.get(level, FONT_SIZE)
    return ParagraphStyle(
        f"Heading{level}",
        fontName=FONT_BOLD,
        fontSize=size,
        leading=size * 1.35,
        spaceBefore=size * 0.7,
        spaceAfter=size * 0.3,
        textColor=colors.black,
    )


def _body_style():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    return ParagraphStyle(
        "Body",
        fontName=FONT_NORMAL,
        fontSize=FONT_SIZE,
        leading=FONT_SIZE * 1.6,
        spaceBefore=2,
        spaceAfter=4,
        textColor=colors.black,
    )


def _bullet_style(indent_level: int = 0):
    from reportlab.lib.styles import ParagraphStyle
    return ParagraphStyle(
        f"Bullet{indent_level}",
        fontName=FONT_NORMAL,
        fontSize=FONT_SIZE,
        leading=FONT_SIZE * 1.5,
        leftIndent=16 + indent_level * 14,
        spaceBefore=1,
        spaceAfter=2,
    )


# ══════════════════════════════════════════════════════════════════════════════
# TXT → PDF
# ══════════════════════════════════════════════════════════════════════════════

def _build_text_pdf(pages: List[dict], out_path: Path, filename: str = "") -> None:
    _require_reportlab()

    from reportlab.platypus import Paragraph, Spacer

    doc_title = filename or "Plain Text Document"
    rl_doc    = _make_simple_doc(out_path)
    body_sty  = _body_style()

    story: list = []
    story.append(Paragraph(_xml_escape(_safe_text(doc_title)), _doc_title_style()))

    for page in sorted(pages, key=lambda p: p["page_number"]):
        text = (page.get("extracted_text") or "").strip()
        if text:
            for block in text.split("\n\n"):
                safe = _xml_escape(_safe_text(block.strip())).replace("\n", "<br/>")
                if safe:
                    try:
                        story.append(Paragraph(safe, body_sty))
                        story.append(Spacer(1, 3))
                    except Exception:
                        pass

    if not story:
        story.append(Paragraph("(No content extracted)", body_sty))

    rl_doc.build(story)


# ══════════════════════════════════════════════════════════════════════════════
# Scanned / handwritten → clean OCR-text PDF
# ══════════════════════════════════════════════════════════════════════════════

def _build_ocr_text_pdf(pages: List[dict], out_path: Path, filename: str = "") -> None:
    _require_reportlab()

    from reportlab.platypus import Paragraph, Spacer

    doc_title  = filename or "Extracted Text"
    rl_doc     = _make_simple_doc(out_path)
    body_sty   = _body_style()
    bullet_sty = _bullet_style(0)

    def _render_line(line: str) -> None:
        stripped = line.rstrip()
        if not stripped:
            story.append(Spacer(1, 3))
            return
        safe = _xml_escape(_safe_text(stripped))
        # Match heading levels 1–6 (######...# prefix)
        import re as _re
        heading_match = _re.match(r"^(#{1,6}) (.+)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text  = _xml_escape(_safe_text(heading_match.group(2)))
            story.append(Paragraph(text, _heading_style(level)))
        elif stripped.startswith(("• ", "- ")):
            story.append(Paragraph(safe, bullet_sty))
        else:
            try:
                story.append(Paragraph(safe, body_sty))
            except Exception:
                story.append(Paragraph(_xml_escape(_safe_text(stripped)), body_sty))

    story: list = []
    story.append(Paragraph(_xml_escape(_safe_text(doc_title)), _doc_title_style()))

    for page in sorted(pages, key=lambda p: p["page_number"]):
        text = (page.get("extracted_text") or "").strip()
        if text:
            for line in text.split("\n"):
                _render_line(line)
        else:
            story.append(Paragraph("<i>[No text extracted from this page]</i>", body_sty))
        story.append(Spacer(1, 6))

    if not story:
        story.append(Paragraph("(No content extracted)", body_sty))

    rl_doc.build(story)