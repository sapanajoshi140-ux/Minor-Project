"""
ocr_service.py — OCR routing: Tesseract for printed, TrOCR for handwritten,
                 with confidence-based fallback, AND a hybrid detection+recognition
                 pipeline (PaddleOCR/EasyOCR line detection → TrOCR recognition).

Routing rules
-------------
Printed / scanned documents → Tesseract only via tesseract_ocr_page().
    Returns a HybridOCRResult with fallback=True and empty lines list.
    No PaddleOCR/EasyOCR detection is performed.
    If Tesseract confidence < OCR_HANDWRITTEN_FALLBACK_THRESHOLD (default 0.60)
        → also run TrOCR, keep the better result (ocr_with_fallback behaviour).

Handwritten documents → hybrid_ocr_page() (detection + TrOCR):
    1. Detect text line bounding boxes via PaddleOCR (primary) or EasyOCR
       (fallback).  Their *recognition* output is discarded; only bounding
       boxes are used.
    2. Crop each detected line from the original image.
    3. Resize/normalise cropped lines for TrOCR input.
    4. Batch-infer with TrOCR (GPU when available).
    5. Filter low-confidence lines (< HYBRID_MIN_LINE_CONF).
    6. Reconstruct page text in reading order (top→bottom, left→right).
    7. If no lines were detected, fall back to full-page ocr_with_fallback().

Configuration
-------------
OCR_HANDWRITTEN_FALLBACK_THRESHOLD — confidence floor for Tesseract; default 0.60.
HYBRID_DETECTION_BACKEND          — "paddle" | "easy" | "auto" (default "auto").
HYBRID_MIN_LINE_CONF              — per-line confidence gate; default 0.20.
HYBRID_TROCR_BATCH_SIZE           — lines per TrOCR batch; default 8.
TROCR_MAX_NEW_TOKENS              — max tokens per line; default 128.

All config values are read from config.py / .env — never hard-coded here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import pytesseract
from PIL import Image

from config import (
    TESSERACT_CMD,
    OCR_HANDWRITTEN_FALLBACK_THRESHOLD,
    HYBRID_DETECTION_BACKEND,
    HYBRID_MIN_LINE_CONF,
    HYBRID_TROCR_BATCH_SIZE,
    TROCR_MAX_NEW_TOKENS,
)

logger = logging.getLogger(__name__)

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
logger.info(f"Tesseract path                : {TESSERACT_CMD}")
logger.info(f"Handwritten fallback threshold: {OCR_HANDWRITTEN_FALLBACK_THRESHOLD}")
logger.info(f"Hybrid detection backend      : {HYBRID_DETECTION_BACKEND}")


# ── Shared result dataclasses ─────────────────────────────────────────────────

@dataclass
class OCRResult:
    text:       str
    confidence: float
    ocr_type:   str    # "printed" | "handwritten"


@dataclass
class DetectedLine:
    """
    A single text line produced by the detection stage.

    bbox  : (x_min, y_min, x_max, y_max) in absolute pixel coordinates.
    order : sort key for reading-order reconstruction (y_band * 1e6 + x_min).
    image : cropped, normalised PIL.Image ready for TrOCR (set by line_cropper).
    text  : recognised text (set by trocr_recognition stage).
    confidence : TrOCR per-token geometric-mean confidence (set by recognition).
    """
    bbox:       Tuple[int, int, int, int]  # x0, y0, x1, y1
    order:      float = 0.0
    image:      Optional[Image.Image] = field(default=None, repr=False)
    text:       str   = ""
    confidence: float = 0.0


@dataclass
class HybridOCRResult:
    """
    Full result from hybrid_ocr_page().

    text       : full page text, lines joined by '\n'.
    confidence : mean confidence across accepted lines (0–1).
    ocr_type   : always "printed" (detection+TrOCR path) or "handwritten".
    lines      : individual DetectedLine objects (for bbox/confidence storage).
    fallback   : True when the result came from Tesseract, not the hybrid pipeline.
    """
    text:       str
    confidence: float
    ocr_type:   str
    lines:      List[DetectedLine] = field(default_factory=list)
    fallback:   bool = False


# ── Tesseract ─────────────────────────────────────────────────────────────────

def _run_tesseract(image: Image.Image) -> Tuple[str, float]:
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


# ── Public OCR entry points (unchanged API) ───────────────────────────────────

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
            logger.info("Tesseract kept despite low confidence (better than TrOCR).")
            return OCRResult(
                text=tess_text or hw_result.text,
                confidence=max(tess_conf, hw_result.confidence),
                ocr_type="printed",
            )

    except Exception as exc:
        logger.warning(f"TrOCR fallback failed ({exc}); keeping Tesseract result.")
        return OCRResult(text=tess_text, confidence=tess_conf, ocr_type="printed")


def tesseract_ocr_page(image: Image.Image) -> HybridOCRResult:
    """
    Tesseract-only OCR for printed / scanned pages.

    No PaddleOCR or EasyOCR detection is performed — Tesseract processes the
    full page image directly.  If Tesseract confidence falls below
    OCR_HANDWRITTEN_FALLBACK_THRESHOLD the result is compared against a TrOCR
    pass and the better result is kept (ocr_with_fallback behaviour).

    Returns a HybridOCRResult so callers share the same return type as
    hybrid_ocr_page().  lines is always empty and fallback is always True
    because no line-detection stage is run.

    Use this for all printed / scanned documents.
    Use hybrid_ocr_page() for handwritten documents only.
    """
    result = ocr_with_fallback(image)
    return HybridOCRResult(
        text=result.text,
        confidence=result.confidence,
        ocr_type=result.ocr_type,
        lines=[],
        fallback=True,
    )


# ── Legacy alias ──────────────────────────────────────────────────────────────

def ocr_image(image: Image.Image) -> OCRResult:
    """Deprecated — routes to ocr_with_fallback()."""
    logger.warning("ocr_image() is deprecated. Use ocr_with_fallback() explicitly.")
    return ocr_with_fallback(image)


# ══════════════════════════════════════════════════════════════════════════════
# ── Hybrid pipeline: detection (PaddleOCR / EasyOCR) + TrOCR recognition ────
# ══════════════════════════════════════════════════════════════════════════════

# ── Detection backends ────────────────────────────────────────────────────────

def _detect_with_paddle(image: Image.Image) -> List[DetectedLine]:
    """
    Use PaddleOCR to detect text line bounding boxes.

    Only bounding-box coordinates are kept — PaddleOCR's own text recognition
    output is intentionally discarded so TrOCR can do the recognition.

    PaddleOCR returns results as:
        [ [ [[x0,y0],[x1,y0],[x1,y1],[x0,y1]], (text, score) ], … ]
    We convert each quad to an axis-aligned bounding box.
    """
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except ImportError:
        raise ImportError(
            "paddleocr not installed. Run: pip install paddleocr paddlepaddle"
        )

    import numpy as np

    # rec=False → detection only, no recognition pass (faster, no text output).
    # use_angle_cls=True detects rotated text lines.
    # lang="en" can be extended via config if multilingual support is needed.
    ocr_engine = PaddleOCR(use_angle_cls=True, lang="en", rec=False, show_log=False)
    result = ocr_engine.ocr(np.array(image.convert("RGB")), cls=True)

    lines: List[DetectedLine] = []
    if not result or not result[0]:
        logger.debug("PaddleOCR: no detections.")
        return lines

    for detection in result[0]:
        # Each detection: [quad_points, (text, score)] — we ignore text/score.
        quad = detection[0]  # [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]
        xs = [int(p[0]) for p in quad]
        ys = [int(p[1]) for p in quad]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        lines.append(DetectedLine(bbox=bbox))

    logger.debug(f"PaddleOCR: detected {len(lines)} line(s).")
    return lines


def _detect_with_easyocr(image: Image.Image) -> List[DetectedLine]:
    """
    Use EasyOCR to detect text line bounding boxes.

    EasyOCR returns:
        [ ([[x0,y0],[x1,y0],[x1,y1],[x0,y1]], text, confidence), … ]
    Again only bbox coordinates are used.
    """
    try:
        import easyocr  # type: ignore
    except ImportError:
        raise ImportError(
            "easyocr not installed. Run: pip install easyocr"
        )

    import numpy as np

    # detail=1 returns bboxes; we don't use the text/confidence fields.
    reader = easyocr.Reader(["en"], gpu=_gpu_available(), verbose=False)
    result = reader.readtext(np.array(image.convert("RGB")), detail=1)

    lines: List[DetectedLine] = []
    for (quad, _text, _conf) in result:
        xs = [int(p[0]) for p in quad]
        ys = [int(p[1]) for p in quad]
        bbox = (min(xs), min(ys), max(xs), max(ys))
        lines.append(DetectedLine(bbox=bbox))

    logger.debug(f"EasyOCR: detected {len(lines)} line(s).")
    return lines


def _gpu_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


# ── Text line detection (public) ──────────────────────────────────────────────

def detect_text_lines(image: Image.Image) -> List[DetectedLine]:
    """
    Detect text line bounding boxes using the configured backend.

    Backend selection (HYBRID_DETECTION_BACKEND in .env):
        "paddle" → PaddleOCR only (raises if unavailable).
        "easy"   → EasyOCR only (raises if unavailable).
        "auto"   → try PaddleOCR first, fall back to EasyOCR, then raise.

    After detection, lines are sorted into reading order:
        primary   sort key: y-band (line's top coordinate // LINE_BAND_PX)
        secondary sort key: x_min (left-to-right within the same band)

    LINE_BAND_PX is set to 10 pixels — lines whose tops differ by ≤10px
    are treated as part of the same text row (handles slight baseline skew).

    Returns an empty list (NOT an exception) when the backend found nothing —
    callers should fall back to Tesseract in that case.
    """
    backend = (HYBRID_DETECTION_BACKEND or "auto").lower().strip()
    lines: List[DetectedLine] = []

    if backend == "paddle":
        lines = _detect_with_paddle(image)
    elif backend == "easy":
        lines = _detect_with_easyocr(image)
    else:  # "auto"
        try:
            lines = _detect_with_paddle(image)
            logger.debug("Hybrid detection: using PaddleOCR.")
        except Exception as paddle_err:
            logger.warning(
                f"PaddleOCR unavailable ({paddle_err}); trying EasyOCR."
            )
            try:
                lines = _detect_with_easyocr(image)
                logger.debug("Hybrid detection: using EasyOCR.")
            except Exception as easy_err:
                logger.warning(
                    f"EasyOCR also unavailable ({easy_err}). "
                    f"Hybrid detection will return 0 lines → Tesseract fallback."
                )
                return []

    # ── Reading-order sort ────────────────────────────────────────────────────
    # Group by y-band (10px buckets) then sort left-to-right within each band.
    LINE_BAND_PX = 10
    for line in lines:
        x0, y0, x1, y1 = line.bbox
        band = y0 // LINE_BAND_PX
        # order key: band (major) + normalised x_min (minor, 0–1 range)
        img_w = max(image.width, 1)
        line.order = band * 1_000_000.0 + (x0 / img_w) * 1_000.0

    lines.sort(key=lambda l: l.order)
    return lines


# ── Line cropping & normalisation ─────────────────────────────────────────────

# TrOCR was fine-tuned on images of roughly this height.
# Maintaining aspect ratio avoids distorting character proportions.
_TROCR_TARGET_HEIGHT = 64


def _normalise_line_crop(crop: Image.Image) -> Image.Image:
    """
    Resize a cropped text-line image to TrOCR's expected input size.

    Strategy
    --------
    - Convert to grayscale then back to RGB (TrOCR processor expects 3 channels).
    - Scale so height == _TROCR_TARGET_HEIGHT, width proportional (aspect preserved).
    - If the resulting width is narrower than the target height (very short word),
      pad with white on the right so the image is at least square.
    - Apply mild sharpening to compensate for LANCZOS interpolation softness.
    """
    import cv2
    import numpy as np

    # Grayscale → RGB
    gray = crop.convert("L")
    rgb  = gray.convert("RGB")

    # Proportional resize to target height
    orig_w, orig_h = rgb.size
    if orig_h == 0:
        return rgb
    scale     = _TROCR_TARGET_HEIGHT / orig_h
    new_w     = max(1, int(orig_w * scale))
    resized   = rgb.resize((new_w, _TROCR_TARGET_HEIGHT), Image.LANCZOS)

    # Pad to at least square if very narrow
    if new_w < _TROCR_TARGET_HEIGHT:
        padded = Image.new("RGB", (_TROCR_TARGET_HEIGHT, _TROCR_TARGET_HEIGHT), (255, 255, 255))
        padded.paste(resized, (0, 0))
        resized = padded

    # Mild unsharp-mask sharpening (sigma=1, amount=0.5)
    arr = np.array(resized).astype(np.float32)
    blur = cv2.GaussianBlur(arr, (0, 0), sigmaX=1.0)
    sharpened = np.clip(arr + 0.5 * (arr - blur), 0, 255).astype(np.uint8)

    return Image.fromarray(sharpened)


def crop_and_normalise_lines(
    image: Image.Image,
    lines: List[DetectedLine],
    padding_px: int = 4,
) -> List[DetectedLine]:
    """
    Crop each detected line from *image*, normalise, and attach to DetectedLine.image.

    padding_px — extra pixels added around each bbox to avoid clipping
                 ascenders/descenders (clamped to image boundaries).

    Lines whose crop is empty (zero width or height) are dropped.
    Returns the input list with .image populated (in-place mutation + filter).
    """
    img_w, img_h = image.size
    valid: List[DetectedLine] = []

    for line in lines:
        x0, y0, x1, y1 = line.bbox

        # Apply padding, clamp to image bounds
        x0_p = max(0, x0 - padding_px)
        y0_p = max(0, y0 - padding_px)
        x1_p = min(img_w, x1 + padding_px)
        y1_p = min(img_h, y1 + padding_px)

        if x1_p <= x0_p or y1_p <= y0_p:
            logger.debug(f"Dropping degenerate bbox {line.bbox} after padding.")
            continue

        crop = image.crop((x0_p, y0_p, x1_p, y1_p))
        line.image = _normalise_line_crop(crop)
        valid.append(line)

    logger.debug(f"Cropped {len(valid)}/{len(lines)} line(s) successfully.")
    return valid


# ── TrOCR batch recognition ───────────────────────────────────────────────────

def batch_trocr_lines(lines: List[DetectedLine]) -> List[DetectedLine]:
    """
    Run TrOCR inference on all lines in batches of HYBRID_TROCR_BATCH_SIZE.

    Each DetectedLine must have .image already set (call crop_and_normalise_lines
    first).  Results are written back to .text and .confidence in-place.

    Batching strategy
    -----------------
    TrOCR's VisionEncoderDecoderModel.generate() accepts a batch of pixel_values
    tensors stacked on dim-0.  We group lines into fixed-size batches, process
    each batch with a single forward pass, then decode token sequences.

    Confidence per line
    -------------------
    Computed as the arithmetic mean of per-token softmax probabilities
    (geometric-mean approximation via mean of log-probs would be slightly more
    principled, but arithmetic mean is faster and sufficient for filtering).

    Error handling
    --------------
    If TrOCR raises on a batch, each line in the batch is retried individually.
    If individual retry also fails, text="" and confidence=0.0 are set and the
    caller's confidence gate will discard the line.
    """
    import torch
    import torch.nn.functional as F
    from services.handwritten_service import _get_trocr

    if not lines:
        return lines

    try:
        processor, model, device = _get_trocr("handwritten")
    except RuntimeError as exc:
        logger.error(f"TrOCR unavailable for hybrid pipeline: {exc}")
        for line in lines:
            line.text, line.confidence = "", 0.0
        return lines

    batch_size = max(1, HYBRID_TROCR_BATCH_SIZE)

    for batch_start in range(0, len(lines), batch_size):
        batch = lines[batch_start : batch_start + batch_size]
        try:
            _run_trocr_batch(batch, processor, model, device)
        except Exception as exc:
            logger.warning(
                f"TrOCR batch [{batch_start}:{batch_start+len(batch)}] failed: {exc}. "
                f"Retrying lines individually."
            )
            for line in batch:
                try:
                    _run_trocr_single(line, processor, model, device)
                except Exception as single_exc:
                    logger.debug(
                        f"TrOCR single-line retry failed for bbox {line.bbox}: {single_exc}"
                    )
                    line.text, line.confidence = "", 0.0

    return lines


def _run_trocr_batch(
    batch: List[DetectedLine],
    processor,
    model,
    device,
) -> None:
    """
    Forward a batch of line images through TrOCR.
    Mutates each line's .text and .confidence in-place.
    """
    import torch
    import torch.nn.functional as F

    images = [line.image.convert("RGB") for line in batch]

    # Stack pixel values into a single batch tensor [B, C, H, W].
    pixel_values = processor(images=images, return_tensors="pt").pixel_values.to(device)

    with torch.inference_mode():
        outputs = model.generate(
            pixel_values,
            output_scores=True,
            return_dict_in_generate=True,
            max_new_tokens=TROCR_MAX_NEW_TOKENS,
        )

    # Decode text for each sequence in the batch.
    texts = processor.batch_decode(outputs.sequences, skip_special_tokens=True)

    # Compute per-item confidence from scores.
    # outputs.scores: tuple of [vocab_size] tensors, one per generated token step.
    # outputs.sequences: [B, seq_len] token IDs.
    batch_size = len(batch)
    per_item_confs: List[float] = [0.0] * batch_size

    if outputs.scores:
        n_steps = len(outputs.scores)
        # Accumulate confidence per item
        item_conf_sums  = [0.0] * batch_size
        item_conf_counts = [0]  * batch_size

        for step_idx, step_logits in enumerate(outputs.scores):
            # step_logits: [B, vocab_size]
            probs = F.softmax(step_logits, dim=-1)  # [B, vocab_size]
            # Token ids at this step for each item: sequences[:, 1+step_idx]
            tok_ids = outputs.sequences[:, 1 + step_idx]  # [B]
            for item_idx in range(batch_size):
                tok_id = tok_ids[item_idx].item()
                conf   = probs[item_idx, tok_id].item()
                item_conf_sums[item_idx]   += conf
                item_conf_counts[item_idx] += 1

        for item_idx in range(batch_size):
            count = item_conf_counts[item_idx]
            per_item_confs[item_idx] = (
                round(item_conf_sums[item_idx] / count, 4) if count else 0.0
            )

    for line, text, conf in zip(batch, texts, per_item_confs):
        line.text       = text.strip()
        line.confidence = conf


def _run_trocr_single(line: DetectedLine, processor, model, device) -> None:
    """Single-line TrOCR inference — used as retry fallback."""
    import torch
    import torch.nn.functional as F

    pixel_values = processor(
        images=line.image.convert("RGB"), return_tensors="pt"
    ).pixel_values.to(device)

    with torch.inference_mode():
        outputs = model.generate(
            pixel_values,
            output_scores=True,
            return_dict_in_generate=True,
            max_new_tokens=TROCR_MAX_NEW_TOKENS,
        )

    line.text = processor.batch_decode(
        outputs.sequences, skip_special_tokens=True
    )[0].strip()

    if outputs.scores:
        token_confs = [
            torch.nn.functional.softmax(score[0], dim=-1)[tok_id].item()
            for score, tok_id in zip(outputs.scores, outputs.sequences[0][1:])
        ]
        line.confidence = round(sum(token_confs) / len(token_confs), 4) if token_confs else 0.0
    else:
        line.confidence = 0.0


# ── Text reconstruction ───────────────────────────────────────────────────────

def reconstruct_page_text(lines: List[DetectedLine]) -> str:
    """
    Merge recognised lines into a single page string in reading order.

    Lines are already sorted by (y_band, x_min) from detect_text_lines().
    This function groups nearby lines into paragraphs: if the vertical gap
    between consecutive lines exceeds PARAGRAPH_GAP_FACTOR × mean_line_height,
    a blank line is inserted to signal a paragraph break.

    PARAGRAPH_GAP_FACTOR = 1.8  (empirically good for typical documents)
    """
    accepted = [l for l in lines if l.text.strip()]
    if not accepted:
        return ""

    if len(accepted) == 1:
        return accepted[0].text

    # Compute mean line height for paragraph-gap detection
    heights = [l.bbox[3] - l.bbox[1] for l in accepted]
    mean_h  = sum(heights) / len(heights) if heights else 20.0
    GAP_THRESHOLD = mean_h * 1.8

    output: List[str] = [accepted[0].text]
    for prev, curr in zip(accepted, accepted[1:]):
        prev_bottom = prev.bbox[3]
        curr_top    = curr.bbox[1]
        gap         = curr_top - prev_bottom

        if gap > GAP_THRESHOLD:
            # Significant vertical gap → paragraph break
            output.append("")

        output.append(curr.text)

    return "\n".join(output)


# ── Main hybrid pipeline entry point ─────────────────────────────────────────

def hybrid_ocr_page(
    image: Image.Image,
    ocr_type: str = "handwritten",
) -> HybridOCRResult:
    """
    Hybrid OCR pipeline for handwritten pages (detection + TrOCR recognition).

    Use tesseract_ocr_page() for printed / scanned documents — it is faster
    and avoids loading PaddleOCR/EasyOCR unnecessarily.

    Steps
    -----
    1. Detect text line bounding boxes (PaddleOCR / EasyOCR).
    2. Crop and normalise each detected line.
    3. Batch-infer with TrOCR.
    4. Filter lines below HYBRID_MIN_LINE_CONF confidence.
    5. Reconstruct page text in reading order.
    6. If no lines detected OR no text survived the confidence gate
       → fall back to ocr_with_fallback() (Tesseract + TrOCR).

    Parameters
    ----------
    image    : preprocessed PIL.Image (grayscale or RGB, deskewed, denoised).
    ocr_type : stored in HybridOCRResult.ocr_type — should always be
               "handwritten" for this pipeline.

    Returns
    -------
    HybridOCRResult — never raises (falls back gracefully on any error).
    """
    logger.info("hybrid_ocr_page: starting detection+recognition pipeline.")

    try:
        # Step 1 — detect lines
        raw_lines = detect_text_lines(image)

        if not raw_lines:
            logger.info(
                "hybrid_ocr_page: no lines detected — "
                "falling back to Tesseract/TrOCR."
            )
            return _hybrid_tesseract_fallback(image, ocr_type)

        logger.info(f"hybrid_ocr_page: {len(raw_lines)} line(s) detected.")

        # Step 2 — crop & normalise
        lines_with_crops = crop_and_normalise_lines(image, raw_lines)

        if not lines_with_crops:
            logger.warning("hybrid_ocr_page: all crops degenerate — falling back.")
            return _hybrid_tesseract_fallback(image, ocr_type)

        # Step 3 — batch TrOCR recognition
        recognised = batch_trocr_lines(lines_with_crops)

        # Step 4 — confidence gate
        min_conf = HYBRID_MIN_LINE_CONF
        accepted = [
            l for l in recognised
            if l.confidence >= min_conf and len(l.text.strip()) >= 1
        ]
        dropped = len(recognised) - len(accepted)
        if dropped:
            logger.debug(
                f"hybrid_ocr_page: dropped {dropped} line(s) "
                f"with confidence < {min_conf}."
            )

        if not accepted:
            logger.info(
                "hybrid_ocr_page: no lines passed confidence gate — falling back."
            )
            return _hybrid_tesseract_fallback(image, ocr_type)

        # Step 5 — reconstruct text
        page_text = reconstruct_page_text(accepted)
        mean_conf = round(
            sum(l.confidence for l in accepted) / len(accepted), 4
        )

        logger.info(
            f"hybrid_ocr_page: {len(accepted)} accepted line(s), "
            f"mean_conf={mean_conf:.3f}, chars={len(page_text)}."
        )

        return HybridOCRResult(
            text=page_text,
            confidence=mean_conf,
            ocr_type=ocr_type,
            lines=accepted,
            fallback=False,
        )

    except Exception as exc:
        logger.error(
            f"hybrid_ocr_page unexpected error: {exc}. Falling back to Tesseract.",
            exc_info=True,
        )
        return _hybrid_tesseract_fallback(image, ocr_type)


def _hybrid_tesseract_fallback(
    image: Image.Image,
    ocr_type: str,
) -> HybridOCRResult:
    """
    Tesseract (+ TrOCR if needed) fallback used when line detection yields nothing.
    Wraps the existing ocr_with_fallback() result into a HybridOCRResult.
    """
    result = ocr_with_fallback(image)
    return HybridOCRResult(
        text=result.text,
        confidence=result.confidence,
        ocr_type=result.ocr_type,
        lines=[],
        fallback=True,
    )