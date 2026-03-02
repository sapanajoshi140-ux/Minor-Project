"""
Image Service — preprocesses images with OpenCV then routes to OCR.

Preprocessing pipelines:
  Printed text:
    deskew → grayscale → denoise → adaptive threshold

  Handwritten text:
    deskew → grayscale → upscale → CLAHE contrast enhance → gentle denoise
    (NO adaptive threshold — it fragments handwriting strokes)

OCR routing (via ocr_service):
  - Tesseract is tried first (fast, great for clean printed text).
  - If Tesseract confidence < threshold, EasyOCR is used as fallback
    (better for handwriting, skewed text, and low-quality scans).
"""

import logging
import math
from typing import List

import cv2
import numpy as np
from PIL import Image

from services.ocr_service import OCRResult, ocr_image

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _deskew(img_bgr: np.ndarray) -> np.ndarray:
    """Detect and correct image skew using the Hough line transform."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180, threshold=100,
        minLineLength=100, maxLineGap=10,
    )
    if lines is None:
        return img_bgr

    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        if x2 != x1:
            angles.append(math.degrees(math.atan2(y2 - y1, x2 - x1)))

    if not angles:
        return img_bgr

    median_angle = float(np.median(angles))
    if abs(median_angle) < 0.5:
        return img_bgr

    h, w = img_bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w // 2, h // 2), median_angle, 1.0)
    return cv2.warpAffine(
        img_bgr, M, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _upscale(gray: np.ndarray, min_width: int = 2000) -> np.ndarray:
    """Upscale small images — more pixels improves EasyOCR accuracy on handwriting."""
    h, w = gray.shape[:2]
    if w < min_width:
        scale = min_width / w
        new_w, new_h = int(w * scale), int(h * scale)
        gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
        logger.debug(f"Upscaled {w}×{h} → {new_w}×{new_h}")
    return gray


# ── Preprocessing pipelines ───────────────────────────────────────────────────

def preprocess_for_printed(image: Image.Image) -> Image.Image:
    """
    Pipeline for printed / typed text:
      deskew → grayscale → denoise → adaptive threshold
    Produces a clean binary image — optimal for Tesseract.
    """
    img_bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    img_bgr = _deskew(img_bgr)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=11, C=2,
    )
    return Image.fromarray(thresh)


def preprocess_for_handwriting(image: Image.Image) -> Image.Image:
    """
    Pipeline optimised for handwritten text:
      deskew → grayscale → upscale → CLAHE contrast → gentle denoise

    Key differences from the printed pipeline:
      - NO adaptive threshold (binarising fragments pen strokes)
      - CLAHE enhances local contrast without destroying stroke continuity
      - Higher upscale target (EasyOCR benefits from larger handwritten images)
      - Gentler denoise to preserve ink-stroke edges
    """
    img_bgr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)

    # 1. Deskew
    img_bgr = _deskew(img_bgr)

    # 2. Grayscale
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 3. Upscale — EasyOCR handles handwriting better at higher resolution
    gray = _upscale(gray, min_width=2000)

    # 4. CLAHE — local contrast enhancement without binarising
    #    clipLimit=2.0 avoids over-amplifying noise
    #    tileGridSize=(8,8) adapts to local lighting variations
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 5. Gentle denoise — remove background noise while preserving stroke edges
    denoised = cv2.fastNlMeansDenoising(
        enhanced, h=7,
        templateWindowSize=7,
        searchWindowSize=21,
    )

    return Image.fromarray(denoised)


def preprocess_image(image: Image.Image) -> Image.Image:
    """Default preprocessing — printed pipeline. Used by pdf_service."""
    return preprocess_for_printed(image)


# ── Public API ────────────────────────────────────────────────────────────────

def process_image_file(file_path: str) -> List[dict]:
    """
    Load an image, run both preprocessing pipelines, return the best result.

    Both pipelines feed into ocr_service.ocr_image(), which tries Tesseract
    first and falls back to EasyOCR automatically when confidence is low.
    """
    logger.info(f"Processing image: {file_path}")
    try:
        image = Image.open(file_path)

        # Try handwriting pipeline
        hw_result: OCRResult = ocr_image(preprocess_for_handwriting(image))
        logger.info(f"Handwriting pipeline confidence: {hw_result.confidence:.2f}")

        # Try printed pipeline
        printed_result: OCRResult = ocr_image(preprocess_for_printed(image))
        logger.info(f"Printed pipeline confidence: {printed_result.confidence:.2f}")

        # Pick the better result
        best = hw_result if hw_result.confidence >= printed_result.confidence else printed_result
        logger.info(f"Using {'handwriting' if best is hw_result else 'printed'} pipeline.")

        return [{
            "page_number": 1,
            "content": best.text,
            "ocr_type": best.ocr_type,
            "confidence": round(best.confidence, 4),
        }]
    except Exception as exc:
        logger.error(f"Image processing error for {file_path}: {exc}", exc_info=True)
        raise