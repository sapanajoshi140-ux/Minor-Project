import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from dotenv import load_dotenv

load_dotenv()

# ---------- DATABASE CONFIGURATION ----------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not found in environment variables. Check your .env file")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ---------- DOCUMENTS TABLE ----------
class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True)  # UUID
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50))
    file_path = Column(String(500))
    total_pages = Column(Integer)
    processing_status = Column(String(50))
    average_confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    pages = relationship("DocumentPage", back_populates="document", cascade="all, delete-orphan")

# ---------- DOCUMENT PAGES TABLE ----------
class DocumentPage(Base):
    __tablename__ = "document_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"))
    page_number = Column(Integer)
    # LONGTEXT supports up to 4 GB per page — no silent truncation on large OCR output
    content = Column(LONGTEXT)
    ocr_type = Column(String(20))  # digital / printed / handwritten
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="pages")

# ---------- CREATE TABLES ----------
Base.metadata.create_all(bind=engine)

# ---------- FASTAPI DEPENDENCY ----------
def get_db():
    """Provides a DB session per request for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()