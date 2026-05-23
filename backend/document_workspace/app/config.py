import os
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _require(key: str) -> str:
    """
    Return the value of a required environment variable.
    Raises a clear RuntimeError at startup (not a cryptic AttributeError later)
    if the key is missing or blank.
    """
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(
            f"Required environment variable '{key}' is missing or empty. "
            f"Check your .env file."
        )
    return val


def _int(key: str, default: int | None = None) -> int:
    raw = os.getenv(key, "").strip()
    if not raw:
        if default is not None:
            return default
        raise RuntimeError(f"Required integer env var '{key}' is missing.")
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"Env var '{key}' must be an integer, got: '{raw}'")


def _float(key: str, default: float | None = None) -> float:
    raw = os.getenv(key, "").strip()
    if not raw:
        if default is not None:
            return default
        raise RuntimeError(f"Required float env var '{key}' is missing.")
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"Env var '{key}' must be a float, got: '{raw}'")


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).strip().lower() == "true"


# ── App ───────────────────────────────────────────────────────────────────────
APP_ENV  = os.getenv("APP_ENV", "production")
API_KEY  = os.getenv("API_KEY")

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = _require("DATABASE_URL")

# ── Auth ──────────────────────────────────────────────────────────────────────
JWT_SECRET    = _require("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ORIGINS = _require("CORS_ORIGINS").split(",")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
BACKEND_URL  = os.getenv("BACKEND_URL", "")

# ── File storage ──────────────────────────────────────────────────────────────
UPLOAD_DIR               = os.getenv("UPLOAD_DIR", "./uploads")
GENERATED_PDF_DIR        = os.getenv("GENERATED_PDF_DIR", "./generated_pdfs")
MAX_FILE_SIZE_MB         = _int("MAX_FILE_SIZE_MB", 50)
MAX_FILE_SIZE_BYTES      = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS       = set(
    os.getenv("ALLOWED_EXTENSIONS", "pdf,doc,docx,ppt,pptx,txt,png,jpg,jpeg").split(",")
)
USER_STORAGE_LIMIT_BYTES = _int("USER_STORAGE_LIMIT_BYTES", 524_288_000)  # 500 MB

# ── Rate limiting ─────────────────────────────────────────────────────────────
UPLOAD_RATE_LIMIT = os.getenv("UPLOAD_RATE_LIMIT", "10/minute")
GET_RATE_LIMIT    = os.getenv("GET_RATE_LIMIT",    "60/minute")
UPDATE_RATE_LIMIT = os.getenv("UPDATE_RATE_LIMIT", "20/minute")
DELETE_RATE_LIMIT = os.getenv("DELETE_RATE_LIMIT", "10/minute")

# ── OCR ───────────────────────────────────────────────────────────────────────
_raw_tesseract = os.getenv("TESSERACT_CMD", "tesseract").strip().strip('"').strip("'")
TESSERACT_CMD                      = _raw_tesseract or "tesseract"
OCR_CONFIDENCE_THRESHOLD           = _float("OCR_CONFIDENCE_THRESHOLD", 0.5)
OCR_HANDWRITTEN_FALLBACK_THRESHOLD = _float("OCR_HANDWRITTEN_FALLBACK_THRESHOLD", 0.3)
TROCR_PRINTED_PATH                 = os.getenv("TROCR_PRINTED_PATH")
TROCR_HANDWRITTEN_PATH             = os.getenv("TROCR_HANDWRITTEN_PATH")
LIBREOFFICE_PATH                   = os.getenv("LIBREOFFICE_PATH", "libreoffice")

# ── TXT pagination ────────────────────────────────────────────────────────────
TXT_PAGE_CHAR_LIMIT    = _int("TXT_PAGE_CHAR_LIMIT",    3000)
PAGE_COMMIT_BATCH_SIZE = _int("PAGE_COMMIT_BATCH_SIZE", 10)

# ── Dashboard / Reading session tuneables ─────────────────────────────────────
DEFAULT_DAILY_GOAL_MIN      = _int("DEFAULT_DAILY_GOAL_MIN",      60)
MIN_SESSION_DURATION_SECS   = _int("MIN_SESSION_DURATION_SECS",   60)
DASHBOARD_CHART_DAYS        = _int("DASHBOARD_CHART_DAYS",        14)
DASHBOARD_RECENT_DOCS_LIMIT = _int("DASHBOARD_RECENT_DOCS_LIMIT", 5)
DASHBOARD_VOCAB_LIMIT       = _int("DASHBOARD_VOCAB_LIMIT",       7)

# ── RAG / Ollama ──────────────────────────────────────────────────────────────
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL          = os.getenv("LLM_MODEL",       "llama3")
CONTEXT_WINDOW     = _int("CONTEXT_WINDOW",     4096)
LLM_TIMEOUT        = _int("LLM_TIMEOUT",        120)
RAG_SERVICE_URL    = os.getenv("RAG_SERVICE_URL", "")
RAG_INGEST_TIMEOUT = _int("RAG_INGEST_TIMEOUT", 60)

# ── ChromaDB ──────────────────────────────────────────────────────────────────
CHROMA_DIR        = os.getenv("CHROMA_DIR",        "./chroma")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "documents")

# ── Embeddings ────────────────────────────────────────────────────────────────
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL",  "nomic-embed-text")
EMBEDDING_DIM    = _int("EMBEDDING_DIM",    768)
EMBED_BATCH_SIZE = _int("EMBED_BATCH_SIZE", 32)
EMBED_TIMEOUT    = _int("EMBED_TIMEOUT",    30)
CHUNK_SIZE       = _int("CHUNK_SIZE",       512)
CHUNK_OVERLAP    = _int("CHUNK_OVERLAP",    64)

# ── Retrieval ─────────────────────────────────────────────────────────────────
TOP_K      = _int("TOP_K", 5)
USE_HYBRID = _bool("USE_HYBRID", True)
RRF_K      = _int("RRF_K", 60)
BM25_K1    = _float("BM25_K1", 1.5)
BM25_B     = _float("BM25_B",  0.75)

# ── OCR Formatting (Ollama post-processing) ───────────────────────────────────
OCR_FORMAT_CHUNK_CHARS = _int("OCR_FORMAT_CHUNK_CHARS", 3000)
OCR_FORMAT_MAX_RETRIES = _int("OCR_FORMAT_MAX_RETRIES", 2)
FORMAT_CONCURRENCY     = _int("FORMAT_CONCURRENCY",     2)
FORMAT_QUEUE_SIZE      = _int("FORMAT_QUEUE_SIZE",      500)
FORMAT_MAX_RETRIES     = _int("FORMAT_MAX_RETRIES",     2)

# ── Ensure upload dir exists ──────────────────────────────────────────────────
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging(log_file: str | None = None) -> None:
    """Configure root logger. Call once at application startup."""
    raw_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level     = getattr(logging, raw_level, None)
    if not isinstance(level, int):
        level = logging.INFO
        print(
            f"WARNING: Unknown LOG_LEVEL '{raw_level}'; defaulting to INFO.",
            file=sys.stderr,
        )

    fmt       = "%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
    datefmt   = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    handlers: list[logging.Handler] = [_stream_handler(formatter)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        handlers.append(fh)

    logging.basicConfig(level=level, handlers=handlers, force=True)

    for name in ("urllib3", "PIL", "easyocr", "fitz", "multipart"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _stream_handler(formatter: logging.Formatter) -> logging.StreamHandler:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(formatter)
    return h