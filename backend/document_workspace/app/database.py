"""
database.py — SQLAlchemy models and DB session factory.

Schema changes (notes update)
------------------------------
New table:
  - `page_notes` : stores one note per (user, document, page_number).
                   Created/updated via PUT /documents/{id}/pages/{n}/note.
                   Fetched in bulk via GET /documents/{id}/notes.

Previous tables (unchanged):
  - `reading_sessions`, `reading_goals`, `user_vocabulary`,
    `users`, `documents`, `document_pages`, `revoked_tokens`
"""

from datetime import datetime

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
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import DATABASE_URL, USER_STORAGE_LIMIT_BYTES

engine       = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base         = declarative_base()


# ── User table ────────────────────────────────────────────────────────────────

class User(Base):
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
    page_notes        = relationship("PageNote",        back_populates="user",        cascade="all, delete-orphan")


# ── RevokedToken table ────────────────────────────────────────────────────────

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id         = Column(Integer,    primary_key=True, autoincrement=True)
    jti        = Column(String(36), unique=True, nullable=False, index=True)
    token_type = Column(String(20), nullable=False)
    expires_at = Column(DateTime,   nullable=False)
    revoked_at = Column(DateTime,   default=datetime.utcnow)


# ── Document table ────────────────────────────────────────────────────────────

class Document(Base):
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
    page_notes       = relationship("PageNote",       back_populates="document", cascade="all, delete-orphan")


# ── DocumentPage table ────────────────────────────────────────────────────────

class DocumentPage(Base):
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
    __tablename__ = "reading_sessions"

    id               = Column(Integer,    primary_key=True, autoincrement=True)
    user_id          = Column(Integer,    ForeignKey("users.id",     ondelete="CASCADE"), nullable=False)
    document_id      = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    started_at       = Column(DateTime,   nullable=False, default=datetime.utcnow)
    ended_at         = Column(DateTime,   nullable=True)
    duration_seconds = Column(Integer,    nullable=True)

    user     = relationship("User",     back_populates="reading_sessions")
    document = relationship("Document", back_populates="reading_sessions")

    __table_args__ = (
        Index("idx_rs_user_started", "user_id", "started_at"),
        Index("idx_rs_user_doc",     "user_id", "document_id"),
    )


# ── ReadingGoal table ─────────────────────────────────────────────────────────

class ReadingGoal(Base):
    __tablename__ = "reading_goals"

    user_id        = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    daily_goal_min = Column(Integer, nullable=False, default=60)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="reading_goal")


# ── UserVocabulary table ──────────────────────────────────────────────────────

class UserVocabulary(Base):
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


# ── PageNote table ────────────────────────────────────────────────────────────

class PageNote(Base):
    """
    One row per (user, document, page_number).
    Uses an upsert pattern — each user gets exactly one note slot per page.

    Powers:
      - The per-page note textarea rendered below each page in the viewer.
      - Notes are fetched in bulk when the document is opened and pre-populated
        into the correct textarea for each page.
    """
    __tablename__ = "page_notes"

    id          = Column(Integer,    primary_key=True, autoincrement=True)
    user_id     = Column(Integer,    ForeignKey("users.id",     ondelete="CASCADE"), nullable=False)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number = Column(Integer,    nullable=False)
    note_text   = Column(LONGTEXT,   nullable=False, default="")
    created_at  = Column(DateTime,   default=datetime.utcnow)
    updated_at  = Column(DateTime,   default=datetime.utcnow, onupdate=datetime.utcnow)

    user     = relationship("User",     back_populates="page_notes")
    document = relationship("Document", back_populates="page_notes")

    __table_args__ = (
        # One note per (user × document × page) — the upsert target key.
        UniqueConstraint("user_id", "document_id", "page_number", name="uq_page_note"),
        Index("idx_pn_user_doc", "user_id", "document_id"),
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