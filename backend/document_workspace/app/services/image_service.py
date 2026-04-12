"""
image_service.py — Preprocess and OCR standalone image files (PNG/JPG/JPEG).

OCR routing (fixed)
-------------------
ocr_mode == "printed"     → ocr_with_fallback():
    Tesseract confidence >= 0.60  → Tesseract result.
    Tesseract confidence <  0.60  → TrOCR also runs; best result kept.
ocr_mode == "handwritten" → ocr_handwritten() (TrOCR only).
"""

from __future__ import annotations

import logging
import math
from typing import List

import cv2
import numpy as np
from PIL import Image

from services.ocr_service import OCRResult, ocr_with_fallback, ocr_handwritten

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
    return Image.fromarray(thresh)


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


# ── Public API ────────────────────────────────────────────────────────────────

def process_image_file(
    file_path: str,
    ocr_mode: str = "printed",
) -> List[dict]:
    """
    Process a standalone image file.

    ocr_mode "printed"     → Tesseract with TrOCR fallback when conf < 0.60.
    ocr_mode "handwritten" → TrOCR only.
    """
    logger.info(f"Processing image '{file_path}' — ocr_mode='{ocr_mode}'.")
    try:
        image = Image.open(file_path).convert("RGB")

        if ocr_mode == "handwritten":
            preprocessed = preprocess_for_handwriting(image)
            result       = ocr_handwritten(preprocessed)
        else:
            preprocessed = preprocess_for_printed(image)
            result       = ocr_with_fallback(preprocessed)

        return [_page_dict(1, result)]

    except Exception as exc:
        logger.error(f"Image processing error for '{file_path}': {exc}", exc_info=True)
        raise


def _page_dict(page_number: int, result: OCRResult) -> dict:
    return {
        "page_number":      page_number,
        "extracted_text":   result.text,
        "ocr_type":         result.ocr_type,
        "confidence_score": round(result.confidence, 4),
    }