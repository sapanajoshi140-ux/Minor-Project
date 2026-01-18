from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime

# ---------- DATABASE CONFIGURATION ----------
DATABASE_URL="mysql+pymysql://root:password@localhost:3306/readwithease_db"

engine = create_engine(DATABASE_URL,pool_pre_ping=True,echo=True)
SessionLocal= sessionmaker(bind=engine)
Base= declarative_base()

class User(Base):
    #---------------Users table-------------

    __tablename__ = "users"

    id=  id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255))

    is_verified = Column(Boolean, default=False)
    is_google_user = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Create tables
Base.metadata.create_all(bind=engine)