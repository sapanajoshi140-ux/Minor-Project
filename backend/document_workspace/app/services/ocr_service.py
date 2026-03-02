"""
OCR Service — Tesseract primary, EasyOCR fallback.

Strategy:
  1. Run Tesseract on the preprocessed image.
  2. If confidence >= OCR_CONFIDENCE_THRESHOLD and text was found → return result.
  3. Otherwise fall back to EasyOCR (handles handwriting and low-quality scans).
  4. Return whichever result has the higher confidence score.

Install:
  pip install pytesseract easyocr
  # Also install the Tesseract binary: https://github.com/UB-Mannheim/tesseract/wiki
"""

import os
import logging
from dataclasses import dataclass, field

import pytesseract
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Read directly from .env — strip accidental quotes/whitespace
TESSERACT_CMD            = os.getenv("TESSERACT_CMD", "tesseract").strip().strip('"').strip("'")
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.80"))

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger.info(f"Tesseract path set to: {TESSERACT_CMD}")
logger.info(f"OCR confidence threshold: {OCR_CONFIDENCE_THRESHOLD}")


@dataclass
class OCRResult:
    text: str
    confidence: float
    ocr_type: str           # "digital" | "printed" | "handwritten"
    word_details: list = field(default_factory=list)


def _run_tesseract(image: Image.Image) -> tuple[str, float]:
    """
    Run Tesseract OCR on a PIL image.
    Returns (text, mean_confidence) where confidence is in [0.0, 1.0].
    """
    try:
        data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT,
            lang="eng",
        )
        confidences = [
            int(c)
            for c in data["conf"]
            if str(c).lstrip("-").isdigit() and int(c) >= 0
        ]
        text = pytesseract.image_to_string(image, lang="eng").strip()
        mean_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        return text, round(mean_conf, 4)
    except Exception as exc:
        logger.error(f"Tesseract error: {exc}")
        return "", 0.0


def ocr_image(image: Image.Image) -> OCRResult:
    """
    Run Tesseract first. If confidence < threshold → fall back to EasyOCR.
    Returns the result with the higher confidence score.
    """
    printed_text, printed_conf = _run_tesseract(image)

    if printed_conf >= OCR_CONFIDENCE_THRESHOLD and printed_text:
        logger.info(f"Tesseract accepted — confidence: {printed_conf:.2f}")
        return OCRResult(text=printed_text, confidence=printed_conf, ocr_type="printed")

    logger.info(
        f"Tesseract confidence {printed_conf:.2f} < threshold "
        f"{OCR_CONFIDENCE_THRESHOLD:.2f} — falling back to EasyOCR."
    )

    from services.handwritten_service import run_easyocr
    hw_result = run_easyocr(image)

    if hw_result.confidence >= printed_conf:
        logger.info(f"EasyOCR selected — confidence: {hw_result.confidence:.2f}")
        return hw_result

    # Tesseract text was better despite low confidence (e.g. mostly-empty page)
    logger.info(
        f"Tesseract kept (higher confidence) — "
        f"tesseract: {printed_conf:.2f}, easyocr: {hw_result.confidence:.2f}"
    )
    return OCRResult(
        text=printed_text or hw_result.text,
        confidence=max(printed_conf, hw_result.confidence),
        ocr_type="printed",
    )