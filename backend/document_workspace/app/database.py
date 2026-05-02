"""
database.py — SQLAlchemy models and DB session factory.

Schema changes (dashboard update)
----------------------------------
New tables:
  - `reading_sessions`  : tracks when a user opens/closes a document and
                          for how long.  Powers total time, daily chart,
                          streak, and per-document time-spent.
  - `reading_goals`     : stores each user's daily reading goal in minutes.
                          One row per user (upsert pattern).
  - `user_vocabulary`   : records every dictionary lookup a user makes,
                          which document they were reading, and when.
                          Powers the "Your Vocabulary" panel.

Existing tables (unchanged):
  - `users`             : added `used_storage_bytes` in previous revision.
  - `documents`         : one row per uploaded file.
  - `document_pages`    : one row per OCR page (scanned docs only).
  - `revoked_tokens`    : JWT blacklist shared with Login_signup service.
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
    os.getenv("USER_STORAGE_LIMIT_BYTES", "524288000")   # 500 MB default
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


# ── User table ────────────────────────────────────────────────────────────────

class User(Base):
    """
    Shared users table.  The document_workspace service reads this table to
    authenticate requests and enforce per-user storage quotas.
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

    documents         = relationship("Document",        back_populates="owner",       cascade="all, delete-orphan")
    reading_sessions  = relationship("ReadingSession",  back_populates="user",        cascade="all, delete-orphan")
    reading_goal      = relationship("ReadingGoal",     back_populates="user",        uselist=False, cascade="all, delete-orphan")
    vocabulary        = relationship("UserVocabulary",  back_populates="user",        cascade="all, delete-orphan")


# ── RevokedToken table ────────────────────────────────────────────────────────

class RevokedToken(Base):
    """JWT blacklist — shared with the Login_signup service."""
    __tablename__ = "revoked_tokens"

    id         = Column(Integer,    primary_key=True, autoincrement=True)
    jti        = Column(String(36), unique=True, nullable=False, index=True)
    token_type = Column(String(20), nullable=False)
    expires_at = Column(DateTime,   nullable=False)
    revoked_at = Column(DateTime,   default=datetime.utcnow)


# ── Document table ────────────────────────────────────────────────────────────

class Document(Base):
    """One row per uploaded document — ALL types (text and scanned)."""
    __tablename__ = "documents"

    id                 = Column(String(36),  primary_key=True)
    user_id            = Column(Integer,     ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    filename           = Column(String(255), nullable=False)
    file_type          = Column(String(50))
    file_path          = Column(String(500))
    file_size_bytes    = Column(BigInteger,  default=0)
    document_category  = Column(String(20))
    total_pages        = Column(Integer)
    processing_status  = Column(String(20),  default="pending")
    average_confidence = Column(Float)
    generated_pdf_path = Column(String(500))
    created_at         = Column(DateTime,    default=datetime.utcnow)
    updated_at         = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    owner            = relationship("User",          back_populates="documents")
    pages            = relationship("DocumentPage",  back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number")
    reading_sessions = relationship("ReadingSession", back_populates="document", cascade="all, delete-orphan")
    vocabulary_refs  = relationship("UserVocabulary", back_populates="document")


# ── DocumentPage table ────────────────────────────────────────────────────────

class DocumentPage(Base):
    """One row per page — SCANNED DOCUMENTS ONLY."""
    __tablename__ = "document_pages"

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    document_id      = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"))
    page_number      = Column(Integer,    nullable=False)
    extracted_text   = Column(LONGTEXT)
    ocr_type         = Column(String(20))
    confidence_score = Column(Float)
    created_at       = Column(DateTime,   default=datetime.utcnow)
    updated_at       = Column(DateTime,   default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="pages")


# ── ReadingSession table ──────────────────────────────────────────────────────

class ReadingSession(Base):
    """
    One row per reading session — created when a user opens a document,
    closed (duration_seconds filled) when they leave.

    Powers:
      - Total time read (all-time)
      - Today's reading progress vs daily goal
      - Daily reading chart (last 14 days)
      - Per-document time-spent shown in Recent Documents list
      - Reading streak (consecutive days with ≥ 1 completed session)
    """
    __tablename__ = "reading_sessions"

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    user_id          = Column(Integer,    ForeignKey("users.id",     ondelete="CASCADE"), nullable=False)
    document_id      = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    started_at       = Column(DateTime,   nullable=False, default=datetime.utcnow)
    ended_at         = Column(DateTime,   nullable=True)           # NULL = session still open
    duration_seconds = Column(Integer,    nullable=True)           # filled on end

    user     = relationship("User",     back_populates="reading_sessions")
    document = relationship("Document", back_populates="reading_sessions")

    __table_args__ = (
        Index("idx_rs_user_started", "user_id", "started_at"),
        Index("idx_rs_user_doc",     "user_id", "document_id"),
    )


# ── ReadingGoal table ─────────────────────────────────────────────────────────

class ReadingGoal(Base):
    """
    One row per user — stores their daily reading goal in minutes.
    Default: 60 minutes.  Updated via PUT /me/reading-goal.
    """
    __tablename__ = "reading_goals"

    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    daily_goal_min = Column(Integer, nullable=False, default=60)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="reading_goal")


# ── UserVocabulary table ──────────────────────────────────────────────────────

class UserVocabulary(Base):
    """
    One row per word lookup per user.  Linked to the document the user was
    reading when they looked up the word (nullable — can be looked up
    outside a document context).

    Powers the "Your Vocabulary" panel on the dashboard.
    """
    __tablename__ = "user_vocabulary"

    id           = Column(Integer,    primary_key=True, autoincrement=True)
    user_id      = Column(Integer,    ForeignKey("users.id",     ondelete="CASCADE"), nullable=False)
    word         = Column(String(100), nullable=False)
    document_id  = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    looked_up_at = Column(DateTime,   nullable=False, default=datetime.utcnow)

    user     = relationship("User",     back_populates="vocabulary")
    document = relationship("Document", back_populates="vocabulary_refs")

    __table_args__ = (
        Index("idx_uv_user_word",    "user_id", "word"),
        Index("idx_uv_user_looked",  "user_id", "looked_up_at"),
    )


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