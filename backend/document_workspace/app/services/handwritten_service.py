"""
Handwritten OCR Service — powered by EasyOCR.

EasyOCR uses a deep learning backend (CRAFT text detector + CRNN recogniser)
and works well for both printed and handwritten text without complex
system-level dependencies.

Install:
  pip install easyocr

GPU acceleration (optional — significantly faster):
  pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
  Then set gpu=True in _get_easy_ocr() below.
"""

import logging
from typing import List

import numpy as np
from PIL import Image

from services.ocr_service import OCRResult

logger = logging.getLogger(__name__)

_easy_ocr_reader = None  # module-level singleton — loaded once on first use


# ── EasyOCR loader ────────────────────────────────────────────────────────────

def _get_easy_ocr():
    """
    Lazily initialise and cache the EasyOCR Reader instance.
    Loading the model (~200 MB) only happens once per process.
    """
    global _easy_ocr_reader
    if _easy_ocr_reader is None:
        try:
            import easyocr
            logger.info("Loading EasyOCR model (first use — may take a moment)…")

            # gpu=False → CPU-only inference; set True if CUDA is available
            _easy_ocr_reader = easyocr.Reader(["en"], gpu=False)

            logger.info("EasyOCR model loaded successfully.")
        except ImportError:
            raise RuntimeError(
                "EasyOCR is not installed. Run: pip install easyocr"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to load EasyOCR model: {exc}") from exc
    return _easy_ocr_reader


# ── Core OCR function ─────────────────────────────────────────────────────────

def run_easyocr(image: Image.Image) -> OCRResult:
    """
    Run EasyOCR on a PIL image and return a structured OCRResult.

    EasyOCR's readtext() returns a list of tuples:
        (bbox, text, confidence)
    where:
        bbox       — four corner points [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        text       — recognised string
        confidence — float in [0.0, 1.0]
    """
    try:
        reader = _get_easy_ocr()
        # EasyOCR accepts numpy arrays (RGB) directly
        img_array = np.array(image.convert("RGB"))

        # detail=1  → full output (bbox, text, conf)
        # paragraph=False → line-by-line results (more granular confidence)
        raw_results = reader.readtext(img_array, detail=1, paragraph=False)

        texts: List[str] = []
        confidences: List[float] = []
        word_details: List[dict] = []

        for bbox, text, conf in raw_results:
            text = str(text).strip()
            if not text:
                continue
            texts.append(text)
            confidences.append(float(conf))
            word_details.append({
                "text": text,
                "confidence": round(float(conf), 4),
                "bbox": [[int(p[0]), int(p[1])] for p in bbox],
            })

        combined_text = "\n".join(texts)
        mean_conf = (
            round(sum(confidences) / len(confidences), 4)
            if confidences else 0.0
        )

        logger.info(
            f"EasyOCR: {len(texts)} line(s) extracted, "
            f"mean confidence: {mean_conf:.2f}"
        )

        return OCRResult(
            text=combined_text,
            confidence=mean_conf,
            ocr_type="handwritten",
            word_details=word_details,
        )

    except Exception as exc:
        logger.error(f"EasyOCR error: {exc}", exc_info=True)
        return OCRResult(text="", confidence=0.0, ocr_type="handwritten")


# ── Public API ────────────────────────────────────────────────────────────────

def process_handwritten_image(file_path: str) -> List[dict]:
    """
    Process a single image file known to contain handwritten content.
    Uses EasyOCR directly, bypassing Tesseract entirely.
    """
    logger.info(f"Processing handwritten image: {file_path}")
    try:
        image = Image.open(file_path)
        result = run_easyocr(image)
        return [{
            "page_number": 1,
            "content": result.text,
            "ocr_type": "handwritten",
            "confidence": result.confidence,
        }]
    except Exception as exc:
        logger.error(f"Failed to process handwritten image {file_path}: {exc}")
        raise