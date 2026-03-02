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

# ── Ensure upload dir exists ──────────────────────────────────
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)