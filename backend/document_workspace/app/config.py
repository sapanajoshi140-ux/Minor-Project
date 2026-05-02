import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── App ───────────────────────────────────────────────────────
APP_ENV  = os.getenv("APP_ENV", "development")
API_KEY  = os.getenv("API_KEY", "").strip()

# ── CORS ──────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# ── File storage ──────────────────────────────────────────────
UPLOAD_DIR          = os.getenv("UPLOAD_DIR", "uploads")
GENERATED_PDF_DIR   = os.getenv("GENERATED_PDF_DIR", "generated_pdfs")
MAX_FILE_SIZE_MB    = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS  = set(os.getenv(
    "ALLOWED_EXTENSIONS",
    "pdf,doc,docx,ppt,pptx,txt,png,jpg,jpeg"   # ← ppt, pptx added
).split(","))

# ── Rate limiting ─────────────────────────────────────────────
UPLOAD_RATE_LIMIT = os.getenv("UPLOAD_RATE_LIMIT", "10/minute")
GET_RATE_LIMIT    = os.getenv("GET_RATE_LIMIT",    "30/minute")
UPDATE_RATE_LIMIT = os.getenv("UPDATE_RATE_LIMIT", "20/minute")
DELETE_RATE_LIMIT = os.getenv("DELETE_RATE_LIMIT", "10/minute")

# ── OCR ───────────────────────────────────────────────────────
TESSERACT_CMD            = os.getenv("TESSERACT_CMD", "tesseract").strip().strip('"').strip("'")
OCR_CONFIDENCE_THRESHOLD = float(os.getenv("OCR_CONFIDENCE_THRESHOLD", "0.80"))

# ── TXT pagination ────────────────────────────────────────────
TXT_PAGE_CHAR_LIMIT = int(os.getenv("TXT_PAGE_CHAR_LIMIT", "3000"))

# ── Dashboard / Reading session tuneables ─────────────────────
DEFAULT_DAILY_GOAL_MIN      = int(os.getenv("DEFAULT_DAILY_GOAL_MIN",      "60"))
MIN_SESSION_DURATION_SECS   = int(os.getenv("MIN_SESSION_DURATION_SECS",    "5"))
DASHBOARD_CHART_DAYS        = int(os.getenv("DASHBOARD_CHART_DAYS",        "14"))
DASHBOARD_RECENT_DOCS_LIMIT = int(os.getenv("DASHBOARD_RECENT_DOCS_LIMIT",  "5"))
DASHBOARD_VOCAB_LIMIT       = int(os.getenv("DASHBOARD_VOCAB_LIMIT",        "7"))

# ── Ensure upload dir exists ──────────────────────────────────
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
# ── Logging ───────────────────────────────────────────────────
import logging
import sys

def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure root logger. Call once at application startup."""
    fmt      = "%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
    datefmt  = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    handlers: list[logging.Handler] = [_stream_handler(formatter)]
    if log_file:
        from pathlib import Path as _Path
        _Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        handlers.append(fh)

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
        force=True,
    )
    for name in ("urllib3", "PIL", "easyocr", "fitz", "multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)

def _stream_handler(formatter: logging.Formatter) -> logging.StreamHandler:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(formatter)
    return h