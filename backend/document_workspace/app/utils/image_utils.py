"""
Image utility helpers — loading, conversion, resizing, blank-page detection.
Shared across image_service and pdf_service.
"""

import logging
from typing import Tuple

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


def load_image(file_path: str) -> Image.Image:
    """
    Load an image from disk as a PIL Image (RGB).
    Raises ValueError for corrupt or unrecognised files.
    """
    try:
        img = Image.open(file_path)
        img.verify()                   # detect corruption
        img = Image.open(file_path)    # re-open (verify() closes the file)
        return img.convert("RGB")
    except UnidentifiedImageError:
        raise ValueError(f"Not a valid image file: {file_path}")
    except Exception as exc:
        raise ValueError(f"Could not load image {file_path}: {exc}") from exc


def pil_to_cv2(image: Image.Image) -> np.ndarray:
    """Convert PIL Image (RGB) → OpenCV array (BGR)."""
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def cv2_to_pil(array: np.ndarray) -> Image.Image:
    """Convert OpenCV array (BGR or grayscale) → PIL Image."""
    if len(array.shape) == 2:
        return Image.fromarray(array)
    return Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))


def get_dimensions(file_path: str) -> Tuple[int, int]:
    """Return (width, height) for an image file."""
    with Image.open(file_path) as img:
        return img.size


def upscale_for_ocr(image: Image.Image, min_width: int = 1000) -> Image.Image:
    """
    Upscale small images to improve OCR quality.
    Never downscales.
    """
    w, h = image.size
    if w < min_width:
        scale = min_width / w
        new_size = (int(w * scale), int(h * scale))
        logger.debug(f"Upscaling {w}×{h} → {new_size[0]}×{new_size[1]} for OCR.")
        return image.resize(new_size, Image.LANCZOS)
    return image


def is_blank_page(image: Image.Image, threshold: float = 0.98) -> bool:
    """
    Return True if the image is mostly white / blank.
    threshold: fraction of pixels that must be near-white (value > 240).
    """
    gray = np.array(image.convert("L"))
    white_ratio = np.sum(gray > 240) / gray.size
    return white_ratio >= threshold