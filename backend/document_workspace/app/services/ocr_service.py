"""
ocr_service.py — OCR routing: Tesseract for printed, TrOCR for handwritten,
                 with confidence-based fallback.

Routing rules (fixed)
---------------------
Printed documents  → Tesseract first.
    If Tesseract confidence >= OCR_HANDWRITTEN_FALLBACK_THRESHOLD (default 0.60)
        → accept Tesseract result.
    If confidence < threshold
        → re-run with TrOCR (handwritten model).
        → keep whichever result has the higher confidence score.

Handwritten documents → TrOCR directly; Tesseract is never called.

Why the threshold matters
-------------------------
Tesseract works well on clean, printed scans.  When it returns a confidence
score below 0.60 it usually means the page is handwritten or mixed, the scan
quality is very poor, or the content is non-latin / decorative.  In all these
cases TrOCR often produces a significantly better result.

Configuration
-------------
OCR_HANDWRITTEN_FALLBACK_THRESHOLD — confidence floor; default 0.60.
    Set in .env to tune without code changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import pytesseract
from PIL import Image

from config import TESSERACT_CMD, OCR_CONFIDENCE_THRESHOLD, OCR_HANDWRITTEN_FALLBACK_THRESHOLD

logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger.info(f"Tesseract path                : {TESSERACT_CMD}")
logger.info(f"Handwritten fallback threshold: {OCR_HANDWRITTEN_FALLBACK_THRESHOLD}")


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class OCRResult:
    text:       str
    confidence: float
    ocr_type:   str    # "printed" | "handwritten"


# ── Tesseract ─────────────────────────────────────────────────────────────────

def _run_tesseract(image: Image.Image) -> tuple[str, float]:
    try:
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            lang="eng",
        )

        valid_confs: List[float] = []
        for txt, conf_raw in zip(data["text"], data["conf"]):
            if not (txt or "").strip():
                continue
            try:
                conf_int = int(conf_raw)
            except (ValueError, TypeError):
                continue
            if conf_int < 0:
                continue
            valid_confs.append(conf_int / 100.0)

        full_text = pytesseract.image_to_string(image, lang="eng").strip()
        mean_conf = (sum(valid_confs) / len(valid_confs)) if valid_confs else 0.0
        return full_text, round(mean_conf, 4)

    except Exception as exc:
        logger.error(f"Tesseract error: {exc}", exc_info=True)
        return "", 0.0


# ── Public OCR entry points ───────────────────────────────────────────────────

def ocr_printed(image: Image.Image) -> OCRResult:
    """Run Tesseract only — no fallback. Use ocr_with_fallback() for smart routing."""
    text, conf = _run_tesseract(image)
    logger.info(f"Tesseract: confidence={conf:.3f}, chars={len(text)}")
    return OCRResult(text=text, confidence=conf, ocr_type="printed")


def ocr_handwritten(image: Image.Image) -> OCRResult:
    """Run TrOCR only — for documents classified as handwritten."""
    from services.handwritten_service import run_trocr, TrOCRResult
    result: TrOCRResult = run_trocr(image, mode="handwritten")
    logger.info(f"TrOCR (handwritten): confidence={result.confidence:.3f}")
    return OCRResult(text=result.text, confidence=result.confidence, ocr_type="handwritten")


def ocr_with_fallback(image: Image.Image) -> OCRResult:
    """
    Smart OCR for scanned (printed) documents.

    1. Run Tesseract.
    2. confidence >= OCR_HANDWRITTEN_FALLBACK_THRESHOLD (0.60)  → return.
    3. confidence <  threshold  → also run TrOCR, keep the better result.
    """
    tess_text, tess_conf = _run_tesseract(image)
    logger.info(f"Tesseract: confidence={tess_conf:.3f}, chars={len(tess_text)}")

    if tess_conf >= OCR_HANDWRITTEN_FALLBACK_THRESHOLD:
        logger.info(f"Tesseract accepted (conf={tess_conf:.3f}).")
        return OCRResult(text=tess_text, confidence=tess_conf, ocr_type="printed")

    logger.info(
        f"Tesseract confidence {tess_conf:.3f} < threshold "
        f"{OCR_HANDWRITTEN_FALLBACK_THRESHOLD} — falling back to TrOCR."
    )
    try:
        from services.handwritten_service import run_trocr, TrOCRResult
        hw_result: TrOCRResult = run_trocr(image, mode="handwritten")
        logger.info(f"TrOCR: confidence={hw_result.confidence:.3f}")

        if hw_result.confidence >= tess_conf:
            logger.info(f"TrOCR selected (trocr={hw_result.confidence:.3f}).")
            return OCRResult(
                text=hw_result.text, confidence=hw_result.confidence, ocr_type="handwritten"
            )
        else:
            logger.info(f"Tesseract kept despite low confidence (better than TrOCR).")
            return OCRResult(
                text=tess_text or hw_result.text,
                confidence=max(tess_conf, hw_result.confidence),
                ocr_type="printed",
            )

    except Exception as exc:
        logger.warning(f"TrOCR fallback failed ({exc}); keeping Tesseract result.")
        return OCRResult(text=tess_text, confidence=tess_conf, ocr_type="printed")


# ── Legacy alias ──────────────────────────────────────────────────────────────

def ocr_image(image: Image.Image) -> OCRResult:
    """Deprecated — routes to ocr_with_fallback()."""
    logger.warning("ocr_image() is deprecated. Use ocr_with_fallback() explicitly.")
    return ocr_with_fallback(image)