import os
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── App ───────────────────────────────────────────────────────
APP_ENV  = os.getenv("APP_ENV")
API_KEY  = os.getenv("API_KEY")

# ── Database ──────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# ── Auth ──────────────────────────────────────────────────────
JWT_SECRET    = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM")

# ── CORS ──────────────────────────────────────────────────────
CORS_ORIGINS = os.getenv("CORS_ORIGINS").split(",")
FRONTEND_URL = os.getenv("FRONTEND_URL")
BACKEND_URL  = os.getenv("BACKEND_URL")

# ── File storage ──────────────────────────────────────────────
UPLOAD_DIR               = os.getenv("UPLOAD_DIR")
GENERATED_PDF_DIR        = os.getenv("GENERATED_PDF_DIR")
MAX_FILE_SIZE_MB         = int(os.getenv("MAX_FILE_SIZE_MB"))
MAX_FILE_SIZE_BYTES      = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS       = set(os.getenv("ALLOWED_EXTENSIONS").split(","))
USER_STORAGE_LIMIT_BYTES = int(os.getenv("USER_STORAGE_LIMIT_BYTES"))

# ── Rate limiting ─────────────────────────────────────────────
UPLOAD_RATE_LIMIT = os.getenv("UPLOAD_RATE_LIMIT")
GET_RATE_LIMIT    = os.getenv("GET_RATE_LIMIT")
UPDATE_RATE_LIMIT = os.getenv("UPDATE_RATE_LIMIT")
DELETE_RATE_LIMIT = os.getenv("DELETE_RATE_LIMIT")

# ── OCR ───────────────────────────────────────────────────────
TESSERACT_CMD                      = os.getenv("TESSERACT_CMD").strip().strip('"').strip("'")
OCR_CONFIDENCE_THRESHOLD           = float(os.getenv("OCR_CONFIDENCE_THRESHOLD"))
OCR_HANDWRITTEN_FALLBACK_THRESHOLD = float(os.getenv("OCR_HANDWRITTEN_FALLBACK_THRESHOLD"))
TROCR_PRINTED_PATH                 = os.getenv("TROCR_PRINTED_PATH")
TROCR_HANDWRITTEN_PATH             = os.getenv("TROCR_HANDWRITTEN_PATH")
LIBREOFFICE_PATH                   = os.getenv("LIBREOFFICE_PATH")

# ── TXT pagination ────────────────────────────────────────────
TXT_PAGE_CHAR_LIMIT    = int(os.getenv("TXT_PAGE_CHAR_LIMIT"))
PAGE_COMMIT_BATCH_SIZE = int(os.getenv("PAGE_COMMIT_BATCH_SIZE"))

# ── Dashboard / Reading session tuneables ─────────────────────
DEFAULT_DAILY_GOAL_MIN      = int(os.getenv("DEFAULT_DAILY_GOAL_MIN"))
MIN_SESSION_DURATION_SECS   = int(os.getenv("MIN_SESSION_DURATION_SECS"))
DASHBOARD_CHART_DAYS        = int(os.getenv("DASHBOARD_CHART_DAYS"))
DASHBOARD_RECENT_DOCS_LIMIT = int(os.getenv("DASHBOARD_RECENT_DOCS_LIMIT"))
DASHBOARD_VOCAB_LIMIT       = int(os.getenv("DASHBOARD_VOCAB_LIMIT"))

# ── RAG / Ollama ──────────────────────────────────────────────
OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL")
LLM_MODEL          = os.getenv("LLM_MODEL")
CONTEXT_WINDOW     = int(os.getenv("CONTEXT_WINDOW"))
LLM_TIMEOUT        = int(os.getenv("LLM_TIMEOUT"))
RAG_SERVICE_URL    = os.getenv("RAG_SERVICE_URL")
RAG_INGEST_TIMEOUT = int(os.getenv("RAG_INGEST_TIMEOUT"))

# ── ChromaDB ──────────────────────────────────────────────────
CHROMA_DIR        = os.getenv("CHROMA_DIR")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION")

# ── Embeddings ────────────────────────────────────────────────
EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL")
EMBEDDING_DIM    = int(os.getenv("EMBEDDING_DIM"))
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE"))
EMBED_TIMEOUT    = int(os.getenv("EMBED_TIMEOUT"))
CHUNK_SIZE       = int(os.getenv("CHUNK_SIZE"))
CHUNK_OVERLAP    = int(os.getenv("CHUNK_OVERLAP"))

# ── Retrieval ─────────────────────────────────────────────────
TOP_K      = int(os.getenv("TOP_K"))
USE_HYBRID = os.getenv("USE_HYBRID").lower() == "true"
RRF_K      = int(os.getenv("RRF_K"))
BM25_K1    = float(os.getenv("BM25_K1"))
BM25_B     = float(os.getenv("BM25_B"))

# ── OCR Formatting (Ollama post-processing) ───────────────────
# Maximum characters per page chunk sent to Ollama in one request.
# A page above this limit is split into sequential sub-chunks and
# the formatted pieces are joined back before saving.
OCR_FORMAT_CHUNK_CHARS = int(os.getenv("OCR_FORMAT_CHUNK_CHARS", "3000"))

# Per-chunk retry attempts when Ollama returns an error or times out.
OCR_FORMAT_MAX_RETRIES = int(os.getenv("OCR_FORMAT_MAX_RETRIES", "2"))

# Number of pages formatted in parallel by the background worker.
# Keep at 1–2 unless your Ollama server explicitly supports concurrency.
FORMAT_CONCURRENCY = int(os.getenv("FORMAT_CONCURRENCY", "2"))

# Maximum in-process queue depth.  Excess pages are dropped with a warning
# and their formatting_status is left as "pending" for retry on restart.
FORMAT_QUEUE_SIZE = int(os.getenv("FORMAT_QUEUE_SIZE", "500"))

# Maximum per-page retry attempts before the page is marked "failed".
FORMAT_MAX_RETRIES = int(os.getenv("FORMAT_MAX_RETRIES", "2"))

# ── Ensure upload dir exists ──────────────────────────────────
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────
def setup_logging(log_file: str | None = None) -> None:
    """Configure root logger. Call once at application startup."""
    level     = os.getenv("LOG_LEVEL")
    fmt       = "%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
    datefmt   = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    handlers: list[logging.Handler] = [_stream_handler(formatter)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
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