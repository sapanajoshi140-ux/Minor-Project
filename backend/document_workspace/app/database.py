"""
database.py — SQLAlchemy models and DB session factory.

Schema changes
--------------
documents table:
  - `user_id` (FK → users.id, NOT NULL) — every document belongs to one user.
  - `file_size_bytes` — stored so we can maintain the user's storage quota
    without hitting the filesystem on every request.

users table:
  - `used_storage_bytes` — running total of bytes consumed by the user's
    uploaded files.  Incremented on upload, decremented on delete.
    Max allowed: USER_STORAGE_LIMIT_BYTES (500 MB).

document_pages table:
  - Unchanged structurally; cascade-deleted when the parent Document is deleted.
"""

import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

load_dotenv()

# ── Storage quota ─────────────────────────────────────────────────────────────
USER_STORAGE_LIMIT_BYTES = int(
    os.getenv("USER_STORAGE_LIMIT_BYTES")  
)

# ── Connection ────────────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL not found in environment variables. Check your .env file."
    )

engine       = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()


# ── User table (mirrors Login_signup — must stay in sync) ─────────────────────

class User(Base):
    """
    Shared users table.  The document_workspace service reads this table to
    authenticate requests and enforce per-user storage quotas.

    used_storage_bytes  — running total of all uploaded file sizes for this
                          user.  Must not exceed USER_STORAGE_LIMIT_BYTES.
    """

    __tablename__ = "users"

    id                 = Column(Integer,     primary_key=True)
    email              = Column(String(255), unique=True, nullable=False)
    full_name          = Column(String(255), nullable=False)
    hashed_password    = Column(String(255))
    is_verified        = Column(Boolean,     default=False)
    is_google_user     = Column(Boolean,     default=False)
    used_storage_bytes = Column(BigInteger,  default=0, nullable=False)
    created_at         = Column(DateTime,    default=datetime.utcnow)

    documents = relationship(
        "Document",
        back_populates="owner",
        cascade="all, delete-orphan",
    )



# ── RevokedToken table (mirrors Login_signup) ─────────────────────────────────

class RevokedToken(Base):
    """
    Blacklist of revoked JWTs — shared with the Login_signup service via the
    same database.  Queried by get_current_user to reject logged-out tokens.
    """
    __tablename__ = "revoked_tokens"

    id         = Column(Integer,    primary_key=True, autoincrement=True)
    jti        = Column(String(36), unique=True, nullable=False, index=True)
    token_type = Column(String(20), nullable=False)
    expires_at = Column(DateTime,   nullable=False)
    revoked_at = Column(DateTime,   default=datetime.utcnow)


# ── Document table ────────────────────────────────────────────────────────────

class Document(Base):
    """
    One row per uploaded document — ALL types (text and scanned).

    user_id             : FK → users.id.  Every document is owned by exactly
                          one authenticated user.  Documents are never visible
                          to other users.

    file_size_bytes     : size of the original uploaded file in bytes.
                          Used to update users.used_storage_bytes on upload
                          and on delete without extra filesystem calls.

    document_category   : "text"    → pure text document
                          "scanned" → image-based document

    generated_pdf_path  : viewer-ready PDF written to disk.
    """

    __tablename__ = "documents"

    id                 = Column(String(36),  primary_key=True)          # UUID
    user_id            = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename           = Column(String(255), nullable=False)
    file_type          = Column(String(50))
    file_path          = Column(String(500))
    file_size_bytes    = Column(BigInteger,  default=0)                 # original upload size
    document_category  = Column(String(20))                             # text | scanned
    total_pages        = Column(Integer)
    processing_status  = Column(String(20), default="pending")
    average_confidence = Column(Float)
    generated_pdf_path = Column(String(500))
    created_at         = Column(DateTime, default=datetime.utcnow)
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="documents")
    pages = relationship(
        "DocumentPage",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentPage.page_number",
    )


# ── DocumentPage table ────────────────────────────────────────────────────────

class DocumentPage(Base):
    """
    One row per page — SCANNED DOCUMENTS ONLY.
    """

    __tablename__ = "document_pages"

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    document_id      = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"))
    page_number      = Column(Integer,    nullable=False)
    extracted_text   = Column(LONGTEXT)
    ocr_type         = Column(String(20))
    confidence_score = Column(Float)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="pages")


# ── Bootstrap ─────────────────────────────────────────────────────────────────

Base.metadata.create_all(bind=engine)


# ── FastAPI dependency ────────────────────────────────────────────────────────

def get_db():
    """Yield a DB session; always closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()