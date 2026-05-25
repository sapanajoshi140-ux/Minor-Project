"""
image_service.py — Preprocess and OCR standalone image files (PNG/JPG/JPEG).

OCR routing
-----------
ocr_mode == "printed"     → tesseract_ocr_page():
    Full-page Tesseract OCR.  TrOCR is used as a fallback only when Tesseract
    confidence falls below OCR_HANDWRITTEN_FALLBACK_THRESHOLD (default 0.60).
    No PaddleOCR/EasyOCR detection is performed.

ocr_mode == "handwritten" → hybrid_ocr_page() (PaddleOCR/EasyOCR detection +
    TrOCR recognition per crop).  If detection yields nothing → Tesseract with
    TrOCR fallback.

Output
------
process_image_file() returns a list with a single page dict.  ocr_metadata is
populated (with per-line bboxes, texts, and confidence scores) only for the
handwritten / hybrid path; it is None for the printed / Tesseract path.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from PIL import Image

from services.ocr_service import (
    OCRResult,
    HybridOCRResult,
    DetectedLine,
    tesseract_ocr_page,
    hybrid_ocr_page,
    ocr_handwritten,
)

logger = logging.getLogger(__name__)


# ── Preprocessing ─────────────────────────────────────────────────────────────

def _deskew(img_bgr: np.ndarray) -> np.ndarray:
    gray  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=100,
        minLineLength=100, maxLineGap=10,
    )
    if lines is None:
        return img_bgr
    angles = [
        math.degrees(math.atan2(y2 - y1, x2 - x1))
        for line in lines
        for x1, y1, x2, y2 in [line[0]]
        if x2 != x1
    ]
    if not angles:
        return img_bgr
    median = float(np.median(angles))
    if abs(median) < 0.5:
        return img_bgr
    h, w = img_bgr.shape[:2]
    M    = cv2.getRotationMatrix2D((w // 2, h // 2), median, 1.0)
    return cv2.warpAffine(img_bgr, M, (w, h),
                          flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def _upscale(gray: np.ndarray, min_width: int = 2000) -> np.ndarray:
    h, w = gray.shape[:2]
    if w < min_width:
        scale = min_width / w
        gray  = cv2.resize(gray, (int(w * scale), int(h * scale)),
                           interpolation=cv2.INTER_CUBIC)
    return gray


def preprocess_for_printed(image: Image.Image) -> Image.Image:
    bgr      = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    bgr      = _deskew(bgr)
    gray     = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
    thresh   = cv2.adaptiveThreshold(denoised, 255,
                                     cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, blockSize=11, C=2)
    # Return as 3-channel RGB so detection backends receive a colour image.
    # Some line detectors (PaddleOCR, EasyOCR) work better with RGB input.
    return Image.fromarray(thresh).convert("RGB")


def preprocess_for_handwriting(image: Image.Image) -> Image.Image:
    bgr      = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    bgr      = _deskew(bgr)
    gray     = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray     = _upscale(gray, min_width=2000)
    clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.fastNlMeansDenoising(enhanced, h=7, templateWindowSize=7, searchWindowSize=21)
    return Image.fromarray(denoised)


# Alias kept for pdf_service compatibility.
preprocess_image = preprocess_for_printed


# ── Serialisation helper (mirrors pdf_service) ────────────────────────────────

def _serialise_lines(lines: List[DetectedLine]) -> List[Dict[str, Any]]:
    return [
        {
            "bbox":       list(line.bbox),
            "text":       line.text,
            "confidence": line.confidence,
        }
        for line in lines
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def process_image_file(
    file_path: str,
    ocr_mode: str = "printed",
) -> List[dict]:
    """
    Process a standalone image file and return a single-element list of page dicts.

    ocr_mode "printed"     → tesseract_ocr_page() — full-page Tesseract with TrOCR
                             fallback on low confidence.  No detection stage;
                             ocr_metadata is always None for this path.
    ocr_mode "handwritten" → hybrid_ocr_page() (PaddleOCR/EasyOCR detection +
                             TrOCR recognition).  ocr_metadata carries per-line
                             bboxes, texts, and confidence scores.

    Page dict schema:
        page_number     : int (always 1 for standalone images)
        extracted_text  : str
        ocr_type        : "printed" | "handwritten"
        confidence_score: float (0–1)
        ocr_metadata    : dict | None
            {
              "lines"   : list of {bbox, text, confidence}  (hybrid path only)
              "fallback": bool
            }
    """
    logger.info(f"Processing image '{file_path}' — ocr_mode='{ocr_mode}'.")
    try:
        image = Image.open(file_path).convert("RGB")

        if ocr_mode == "handwritten":
            preprocessed = preprocess_for_handwriting(image)
            hybrid: HybridOCRResult = hybrid_ocr_page(preprocessed, ocr_type="handwritten")
            ocr_metadata: Optional[Dict[str, Any]] = {
                "lines":    _serialise_lines(hybrid.lines),
                "fallback": hybrid.fallback,
            }
            return [{
                "page_number":      1,
                "extracted_text":   hybrid.text,
                "ocr_type":         hybrid.ocr_type,
                "confidence_score": round(hybrid.confidence, 4),
                "ocr_metadata":     ocr_metadata,
            }]

        else:
            # Printed — Tesseract only (no PaddleOCR/EasyOCR detection).
            preprocessed = preprocess_for_printed(image)
            result: HybridOCRResult = tesseract_ocr_page(preprocessed)
            return [{
                "page_number":      1,
                "extracted_text":   result.text,
                "ocr_type":         result.ocr_type,
                "confidence_score": round(result.confidence, 4),
                "ocr_metadata":     None,
            }]

    except Exception as exc:
        logger.error(f"Image processing error for '{file_path}': {exc}", exc_info=True)
        raise