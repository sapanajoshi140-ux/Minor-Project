"""
handwritten_service.py — TrOCR loaded from LOCAL DISK (no HuggingFace at runtime).

Refactor changes
----------------
- `run_trocr()` return value no longer includes `word_details` / `ocr_json`.
  The OCRResult is now (text, confidence, ocr_type) only — word-level bbox
  data is not stored anywhere in this pipeline.
- `_get_trocr()` rewritten to fix:
    * Device placement: model is fully moved to CPU/CUDA before caching so
      that no tensor ever lives on the meta device at inference time.
    * `low_cpu_mem_usage=False` retained (prevents meta-device buffers).
    * Failure sentinel (_LOAD_FAILED) prevents repeated expensive retries.
    * Explicit `torch.inference_mode()` instead of `torch.no_grad()` —
      slightly lower overhead and disables autograd bookkeeping.
- `process_handwritten_image()` no longer emits `ocr_json` key.

Setup (one time only)
---------------------
1. Run:  python download_models.py
2. Add to .env:
       TROCR_PRINTED_PATH=./models/trocr-large-printed
       TROCR_HANDWRITTEN_PATH=./models/trocr-large-handwritten

Model variants
--------------
"printed"     → trocr-large-printed      (~1.1 GB)  best for scanned printed docs
"handwritten" → trocr-large-handwritten  (~2.2 GB)  best for cursive / mixed handwriting

Both are lazily loaded and cached for the lifetime of the server process.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Literal

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Local model paths (from .env) ─────────────────────────────────────────────

_LOCAL_PATHS: dict[str, str] = {
    "printed":     os.getenv("TROCR_PRINTED_PATH",     "microsoft/trocr-large-printed"),
    "handwritten": os.getenv("TROCR_HANDWRITTEN_PATH", "microsoft/trocr-large-handwritten"),
}

# In-process singleton cache: mode → (processor, model, device) | _LOAD_FAILED
_cache: dict = {}
_LOAD_FAILED  = "_failed"           # sentinel — avoids repeated costly retries


# ── Shared result dataclass ───────────────────────────────────────────────────

@dataclass
class TrOCRResult:
    text:       str
    confidence: float
    ocr_type:   str    # "printed" | "handwritten"


# ── Source resolution ─────────────────────────────────────────────────────────

def _resolve_source(raw: str) -> tuple[str, bool]:
    """
    Return (source_string, is_local).

    Rules
    -----
    - Paths starting with . / \\ or an absolute drive letter are treated as local.
    - If the resolved directory exists  → return absolute path, is_local=True.
    - If the directory does NOT exist   → derive a hub ID from the dir name and
      warn; is_local=False so the caller can fall back to the HuggingFace hub.
    - Plain hub IDs ("microsoft/trocr-…") are returned as-is, is_local=False.
    """
    looks_local = (
        raw.startswith((".", "/", "\\"))
        or (len(raw) > 1 and raw[1] == ":")
    )

    if not looks_local:
        return raw, False

    resolved = Path(raw).resolve()
    if resolved.is_dir():
        return str(resolved), True

    # Directory missing — fall back gracefully to the HuggingFace hub.
    stem   = resolved.name                    # e.g. "trocr-large-printed"
    hub_id = f"microsoft/{stem}"
    logger.warning(
        f"Local model directory not found: '{resolved}'. "
        f"Falling back to HuggingFace hub ID '{hub_id}'. "
        f"Run download_models.py and set the correct path in .env."
    )
    return hub_id, False


# ── Model loader / cache ──────────────────────────────────────────────────────

def _get_trocr(mode: Literal["printed", "handwritten"]):
    """
    Load and cache TrOCR processor + model for *mode*.

    Returns (processor, model, device) on success.
    Raises RuntimeError on failure; caches the failure so that subsequent
    calls in the same process do not re-attempt the expensive load.

    Fix notes
    ---------
    1. `low_cpu_mem_usage=False`  — disables the "meta device" lazy-init path
       that newer transformers uses by default.  Without this, non-parameter
       buffers (e.g. decoder.embed_positions._float_tensor) stay on the meta
       device and cause a crash at inference time even after model.to(device).

    2. Explicit `model.to(device).eval()` BEFORE caching — ensures every
       buffer/parameter is on the target device so inference never touches the
       meta device.

    3. Device is stored alongside (processor, model) so all call-sites use
       the same device consistently — no second `torch.cuda.is_available()`
       call scattered across the codebase.
    """
    cached = _cache.get(mode)

    # Fast-path: already loaded or already failed.
    if cached is _LOAD_FAILED:
        raise RuntimeError(
            f"TrOCR [{mode}] previously failed to load — skipping retry. "
            f"Ensure the model is downloaded and TROCR_*_PATH is set in .env."
        )
    if cached is not None:
        return cached   # (processor, model, device)

    raw_source       = _LOCAL_PATHS[mode]
    source, is_local = _resolve_source(raw_source)

    try:
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        # Determine target device once.
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"TrOCR [{mode}]: using device '{device}'.")

        load_kwargs = {
            # Keeps all tensors on real storage during load; prevents meta-device
            # buffers that cause "Tensor on device meta is not on expected device"
            # errors at inference time after model.to(device).
            "low_cpu_mem_usage": False,
        }

        if is_local:
            logger.info(f"Loading TrOCR [{mode}] from local disk: {source}")
            processor = TrOCRProcessor.from_pretrained(
                source, local_files_only=True
            )
            model = VisionEncoderDecoderModel.from_pretrained(
                source, local_files_only=True, **load_kwargs
            )
        else:
            logger.warning(
                f"Loading TrOCR [{mode}] from HuggingFace hub '{source}' "
                f"— requires internet access."
            )
            processor = TrOCRProcessor.from_pretrained(source)
            model     = VisionEncoderDecoderModel.from_pretrained(
                source, **load_kwargs
            )

        # Move to device and set eval mode BEFORE caching so that every
        # subsequent call gets a fully initialised, inference-ready model.
        model = model.to(device).eval()

        _cache[mode] = (processor, model, device)
        logger.info(f"TrOCR [{mode}] ready on '{device}'.")
        return _cache[mode]

    except ImportError:
        _cache[mode] = _LOAD_FAILED
        raise RuntimeError(
            "transformers / torch not installed. "
            "Run: pip install transformers torch torchvision"
        )
    except Exception as exc:
        _cache[mode] = _LOAD_FAILED
        raise RuntimeError(
            f"Failed to load TrOCR [{mode}] from '{source}': {exc}"
        ) from exc


# ── Line slicer ───────────────────────────────────────────────────────────────

def _split_into_line_strips(image, min_height: int = 20) -> list:
    """
    Slice a multi-line image into individual horizontal line strips using a
    horizontal projection profile.

    TrOCR is a line-level model; slicing a full-page image into line strips
    first gives significantly better recognition accuracy.
    """
    import numpy as np
    from PIL import Image

    arr      = np.array(image.convert("L"))
    h, w     = arr.shape
    row_ink  = (arr < 200).sum(axis=1)
    text_row = row_ink > (w * 0.01)

    bands: list[tuple[int, int]] = []
    in_band = False
    start   = 0

    for i, is_text in enumerate(text_row):
        if is_text and not in_band:
            start   = i
            in_band = True
        elif not is_text and in_band:
            in_band = False
            if (i - start) >= min_height:
                bands.append((start, i))

    if in_band and (h - start) >= min_height:
        bands.append((start, h))

    if not bands:
        return [image]

    pad = 4
    return [
        image.crop((0, max(0, t - pad), w, min(h, b + pad)))
        for t, b in bands
    ]


# ── Single-strip inference ────────────────────────────────────────────────────

def _run_strip(strip, processor, model, device) -> tuple[str, float]:
    """
    Run TrOCR on one line strip.

    Returns (text, confidence_0_to_1).

    Uses `torch.inference_mode()` (superset of no_grad — also disables
    autograd version tracking, lower overhead for pure inference).
    """
    import torch
    import torch.nn.functional as F

    pixel_values = processor(
        images=strip.convert("RGB"), return_tensors="pt"
    ).pixel_values.to(device)

    with torch.inference_mode():
        outputs = model.generate(
            pixel_values,
            output_scores=True,
            return_dict_in_generate=True,
            max_new_tokens=128,
        )

    text = processor.batch_decode(
        outputs.sequences, skip_special_tokens=True
    )[0].strip()

    # Per-token softmax confidence → geometric-mean approximation via
    # arithmetic mean of log-probs.
    confidence = 0.0
    if outputs.scores:
        token_confs = [
            F.softmax(score[0], dim=-1)[tok_id].item()
            for score, tok_id in zip(outputs.scores, outputs.sequences[0][1:])
        ]
        confidence = (
            round(sum(token_confs) / len(token_confs), 4)
            if token_confs else 0.0
        )

    return text, confidence


# ── Core public function ──────────────────────────────────────────────────────

def run_trocr(
    image,
    mode: Literal["printed", "handwritten"] = "printed",
) -> TrOCRResult:
    """
    Run TrOCR on a PIL image.

    Parameters
    ----------
    image : PIL.Image — preprocessed input image.
    mode  : "printed" (default) or "handwritten".

    Returns
    -------
    TrOCRResult with text, confidence (0–1), and ocr_type.
    word_details / ocr_json are NOT produced — they are not stored in
    the refactored schema.
    """
    try:
        processor, model, device = _get_trocr(mode)

        strips = _split_into_line_strips(image)
        logger.info(f"TrOCR [{mode}]: processing {len(strips)} line strip(s).")

        lines:       list[str]   = []
        confidences: list[float] = []

        for idx, strip in enumerate(strips):
            text, conf = _run_strip(strip, processor, model, device)
            if text:
                lines.append(text)
                confidences.append(conf)
                logger.debug(f"  strip {idx}: conf={conf:.3f} text='{text[:60]}'")

        mean_conf = (
            round(sum(confidences) / len(confidences), 4)
            if confidences else 0.0
        )
        logger.info(
            f"TrOCR [{mode}]: {len(lines)} line(s), mean confidence {mean_conf:.3f}."
        )

        ocr_type = "handwritten" if mode == "handwritten" else "printed"
        return TrOCRResult(
            text       = "\n".join(lines),
            confidence = mean_conf,
            ocr_type   = ocr_type,
        )

    except Exception as exc:
        logger.error(f"TrOCR [{mode}] inference error: {exc}", exc_info=True)
        return TrOCRResult(text="", confidence=0.0, ocr_type=mode)


# ── Convenience wrapper ───────────────────────────────────────────────────────

def process_handwritten_image(file_path: str) -> list[dict]:
    """
    Process a single handwritten image file (uses the handwritten TrOCR model).

    Returns a list containing one page dict — no ocr_json key.
    """
    from PIL import Image

    logger.info(f"Processing handwritten image: {file_path}")
    image  = Image.open(file_path).convert("RGB")
    result = run_trocr(image, mode="handwritten")

    return [{
        "page_number":      1,
        "extracted_text":   result.text,
        "ocr_type":         "handwritten",
        "confidence_score": result.confidence,
    }]