import os
from dotenv import load_dotenv

# Load .env FIRST — before any other imports that may read env variables
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
import uuid
import logging
from pathlib import Path

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import SessionLocal, Document, DocumentPage
from schemas import (
    UploadResponse,
    DocumentResponse,
    PaginatedPagesResponse,
    PageResponse,
    PageUpdateRequest,
    PageUpdateResponse,
    DeleteResponse,
)
from services.parser_service import FileType, detect_file_type, stream_document

# ---------- LOGGING ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("multipart").setLevel(logging.WARNING)

# ---------- ENV ----------
APP_ENV             = os.getenv("APP_ENV", "development")
API_KEY             = os.getenv("API_KEY", "").strip()
CORS_ORIGINS        = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
UPLOAD_DIR          = os.getenv("UPLOAD_DIR", "uploads")
MAX_FILE_SIZE_MB    = int(os.getenv("MAX_FILE_SIZE_MB", 50))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS  = set(os.getenv("ALLOWED_EXTENSIONS", "pdf,doc,docx,ppt,pptx,txt,png,jpg,jpeg").split(","))
UPLOAD_RATE_LIMIT   = os.getenv("UPLOAD_RATE_LIMIT", "10/minute")
GET_RATE_LIMIT      = os.getenv("GET_RATE_LIMIT", "30/minute")
UPDATE_RATE_LIMIT   = os.getenv("UPDATE_RATE_LIMIT", "20/minute")
DELETE_RATE_LIMIT   = os.getenv("DELETE_RATE_LIMIT", "10/minute")

# How many pages to accumulate before flushing to DB.
# Lower = more durability (partial saves survive crashes), higher = faster.
PAGE_COMMIT_BATCH_SIZE = int(os.getenv("PAGE_COMMIT_BATCH_SIZE", "10"))

if APP_ENV == "production" and not API_KEY:
    raise RuntimeError("API_KEY must be set in .env when APP_ENV=production")

Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# ---------- APP ----------
app = FastAPI(
    title="Document OCR API",
    docs_url    = "/docs"         if APP_ENV != "production" else None,
    redoc_url   = "/redoc"        if APP_ENV != "production" else None,
    openapi_url = "/openapi.json" if APP_ENV != "production" else None,
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title=app.title, version="1.0.0", routes=app.routes)
    schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
    }
    for path in schema.get("paths", {}).values():
        for method in path.values():
            method.setdefault("security", [{"APIKeyHeader": []}])
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# ---------- RATE LIMITER ----------
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# ---------- TRUSTED HOST ----------
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if APP_ENV != "production" else [
        h.replace("https://", "").replace("http://", "").split("/")[0]
        for h in CORS_ORIGINS
    ],
)

# ---------- DATABASE ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- API KEY ----------
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(key: str = Security(api_key_header)):
    if not API_KEY:
        logger.debug("API_KEY not set in .env — skipping auth (development mode)")
        return
    received = (key or "").strip()
    if not received:
        logger.warning("Request rejected — X-API-Key header is missing")
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    if received != API_KEY:
        logger.warning("Request rejected — wrong API key received")
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")
    logger.debug("API key validated OK")

# ---------- GLOBAL EXCEPTION HANDLER ----------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception [{request.method} {request.url}]: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "An internal server error occurred."})

# ---------- HEALTH ----------
@app.get("/health")
def health_check():
    return {"status": "ok"}

# ---------- UPLOAD ----------
@app.post("/upload", response_model=UploadResponse, status_code=201)
@limiter.limit(UPLOAD_RATE_LIMIT)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = Path(file.filename).suffix.lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Extension '.{ext}' not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    try:
        file_type: FileType = detect_file_type(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    doc_id = str(uuid.uuid4())
    stored_filename = f"{doc_id}.{ext}"
    file_path = Path(UPLOAD_DIR) / stored_filename

    # ── Save file to disk ─────────────────────────────────────────────────────
    try:
        total_bytes = 0
        with open(file_path, "wb") as fh:
            while chunk := await file.read(65_536):
                total_bytes += len(chunk)
                if total_bytes > MAX_FILE_SIZE_BYTES:
                    fh.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB} MB."
                    )
                fh.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File save error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # ── Create pending DB record ──────────────────────────────────────────────
    document = Document(
        id=doc_id,
        filename=file.filename,
        file_type=file_type.value,
        file_path=str(file_path),
        processing_status="processing"
    )
    db.add(document)
    db.commit()

    # ── Process and persist pages ─────────────────────────────────────────────
    # Pages are batched: a DB commit is issued every PAGE_COMMIT_BATCH_SIZE pages
    # rather than once per page, reducing round-trips while still giving partial
    # durability (a crash loses at most PAGE_COMMIT_BATCH_SIZE pages, not all).
    confidences = []
    total_pages = 0
    try:
        for page in stream_document(str(file_path), file_type):
            db.add(DocumentPage(
                document_id=doc_id,
                page_number=page["page_number"],
                content=page.get("content"),
                ocr_type=page.get("ocr_type"),
                confidence=page.get("confidence"),
            ))
            if page.get("confidence") is not None:
                confidences.append(page["confidence"])
            total_pages += 1

            # Flush to DB every N pages instead of every single page
            if total_pages % PAGE_COMMIT_BATCH_SIZE == 0:
                db.commit()
                logger.info(f"Document {doc_id} — committed batch up to page {total_pages}.")

        # Final flush for any remaining pages not caught by the batch boundary
        db.commit()
        logger.info(f"Document {doc_id} — final page batch committed ({total_pages} total).")

    except Exception as e:
        logger.error(f"Processing failed for {doc_id}: {e}", exc_info=True)
        document.processing_status = "failed"
        db.commit()
        # FIX: delete the uploaded file so it doesn't orphan on disk
        file_path.unlink(missing_ok=True)
        logger.info(f"Cleaned up orphaned file after processing failure: {file_path}")
        raise HTTPException(status_code=422, detail="Document processing failed.")

    # ── Finalise document record ──────────────────────────────────────────────
    document.total_pages = total_pages
    document.average_confidence = (
        round(sum(confidences) / len(confidences), 4) if confidences else None
    )
    document.processing_status = "completed"
    db.commit()

    logger.info(f"Document {doc_id} completed — {total_pages} page(s).")

    return UploadResponse(
        document_id=doc_id,
        message="Document uploaded and processed successfully.",
        total_pages=total_pages,
        processing_status="completed"
    )

# ---------- GET DOCUMENT METADATA ----------
@app.get("/document/{document_id}", response_model=DocumentResponse)
@limiter.limit(GET_RATE_LIMIT)
def get_document(
    request: Request,
    document_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Returns document metadata only (no page content).
    Use /document/{id}/pages or /document/{id}/page/{n} to fetch content.
    """
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


# ---------- GET SINGLE PAGE ----------
@app.get("/document/{document_id}/page/{page_number}", response_model=PageResponse)
@limiter.limit(GET_RATE_LIMIT)
def get_page(
    request: Request,
    document_id: str,
    page_number: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Returns the content of a single page by its page number (1-based).
    Ideal for rendering one page at a time in the frontend.
    """
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format.")

    if page_number < 1:
        raise HTTPException(status_code=400, detail="Page number must be 1 or greater.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    page = db.query(DocumentPage).filter(
        DocumentPage.document_id == document_id,
        DocumentPage.page_number == page_number,
    ).first()
    if not page:
        raise HTTPException(
            status_code=404,
            detail=f"Page {page_number} not found. Document has {document.total_pages} page(s)."
        )
    return page


# ---------- GET PAGES (PAGINATED) ----------
@app.get("/document/{document_id}/pages", response_model=PaginatedPagesResponse)
@limiter.limit(GET_RATE_LIMIT)
def get_pages(
    request: Request,
    document_id: str,
    page: int = 1,
    limit: int = 10,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Returns a paginated slice of pages for a document.

    Query params:
      page  — which batch to return (1-based, default: 1)
      limit — how many pages per batch (default: 10, max: 50)

    Example: GET /document/{id}/pages?page=2&limit=5
      Returns pages 6–10 of the document.
    """
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format.")

    if page < 1:
        raise HTTPException(status_code=400, detail="page must be 1 or greater.")
    if not (1 <= limit <= 50):
        raise HTTPException(status_code=400, detail="limit must be between 1 and 50.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    offset = (page - 1) * limit
    pages = (
        db.query(DocumentPage)
        .filter(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
        .offset(offset)
        .limit(limit)
        .all()
    )

    return PaginatedPagesResponse(
        document_id=document_id,
        total_pages=document.total_pages,
        page=page,
        limit=limit,
        pages=pages,
    )

# ---------- UPDATE PAGE ----------
@app.put("/document/{document_id}/page/{page_number}", response_model=PageUpdateResponse)
@limiter.limit(UPDATE_RATE_LIMIT)
def update_page(
    request: Request,
    document_id: str,
    page_number: int,
    data: PageUpdateRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format.")

    if page_number < 1:
        raise HTTPException(status_code=400, detail="Page number must be 1 or greater.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    page = db.query(DocumentPage).filter(
        DocumentPage.document_id == document_id,
        DocumentPage.page_number == page_number
    ).first()
    if not page:
        raise HTTPException(status_code=404, detail=f"Page {page_number} not found.")

    page.content = data.content
    db.commit()
    logger.info(f"Page {page_number} of document {document_id} updated.")

    return PageUpdateResponse(
        document_id=document_id,
        page_number=page_number,
        content=page.content,
        message="Page updated successfully."
    )

# ---------- DELETE DOCUMENT ----------
@app.delete("/document/{document_id}", response_model=DeleteResponse)
@limiter.limit(DELETE_RATE_LIMIT)
def delete_document(
    request: Request,
    document_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID format.")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    file_path = Path(document.file_path)
    if file_path.exists():
        file_path.unlink()
        logger.info(f"Deleted file: {file_path}")
    else:
        logger.warning(f"File not found on disk: {file_path}")

    db.delete(document)
    db.commit()
    logger.info(f"Document {document_id} deleted.")

    return DeleteResponse(message=f"Document '{document_id}' deleted successfully.")