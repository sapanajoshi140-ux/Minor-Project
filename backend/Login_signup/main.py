from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import os
from dotenv import load_dotenv

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import SessionLocal, User
from schemas import (
    Signup, Login, RefreshToken,

    GoogleLogin, ForgotPassword, ResetPassword, ResendVerificationRequest

)
from auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    create_email_token, create_reset_token,
    decode_token, get_google_user
)
from email_config import send_email, verify_email_html, reset_email_html

load_dotenv()

# Get environment variables
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# ---------- APP ----------
app = FastAPI(title="Auth Backend")

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------- CORS (SECURE) ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # Whitelisted origins only!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DATABASE ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- CURRENT USER ----------
def get_current_user(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    try:
        token = authorization.split(" ")[1]
        payload = decode_token(token)

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")

        user = db.query(User).filter(User.email == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ---------- SIGNUP ----------
@app.post("/signup")
@limiter.limit("5/minute")  # Rate limiting: 5 signups per minute
async def signup(request: Request, data: Signup, db: Session = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    # Password validation
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    try:
        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            is_verified=False,
            is_google_user=False,
            created_at=datetime.utcnow()
        )
        db.add(user)
        
        # Send verification email BEFORE committing
        token = create_email_token(user.email)
        link = f"{BACKEND_URL}/verify-email?token={token}"
        await send_email(
            user.email,
            "Verify your email",
            verify_email_html(user.full_name, link)
        )
        
        # Only commit if email sent successfully
        db.commit()
        db.refresh(user)

        return {"message": "Signup successful. Please check your email to verify."}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Signup failed. Please try again.")

# ---------- VERIFY EMAIL ----------
@app.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    payload = decode_token(token)

    if payload.get("type") != "email":
        raise HTTPException(status_code=400, detail="Invalid token")

    user = db.query(User).filter(User.email == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_verified:
        user.is_verified = True
        db.commit()

    # Return JSON instead of redirect
    return {"message": "Email verified successfully!", "redirect": f"{FRONTEND_URL}/login"}

# ---------- RESEND VERIFICATION ----------
@app.post("/resend-verification")
@limiter.limit("3/minute")  # Rate limiting: 3 resends per minute
async def resend_verification(request: Request, data: ResendVerificationRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    # Don't reveal if email exists (security)
    if not user:
        return {"message": "If this email is registered, a verification link has been sent."}
    if user.is_verified:
        return {"message": "Email already verified"}

    token = create_email_token(user.email)
    link = f"{BACKEND_URL}/verify-email?token={token}"

    await send_email(
        user.email,
        "Verify your email",
        verify_email_html(user.full_name, link)
    )

    return {"message": "Verification email sent"}

# ---------- LOGIN ----------
@app.post("/login")
@limiter.limit("5/minute")  # Rate limiting: 5 login attempts per minute (prevents brute force)
async def login(request: Request, data: Login, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    # Generic error message (don't reveal if email exists)
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.is_google_user:
        raise HTTPException(status_code=400, detail="Use Google login")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Verify email first")

    return {
        "access_token": create_access_token(user.email),
        "refresh_token": create_refresh_token(user.email)
    }

# ---------- REFRESH ----------
@app.post("/refresh")
@limiter.limit("10/minute")
async def refresh(request: Request, data: RefreshToken):
    payload = decode_token(data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return {"access_token": create_access_token(payload["sub"])}

# ---------- FORGOT PASSWORD ----------
@app.post("/forgot-password")
@limiter.limit("3/hour")  # Rate limiting: 3 requests per hour
async def forgot_password(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    # Don't reveal if email exists (security)
    if not user:
        return {"message": "If this email is registered, a password reset link has been sent."}

    token = create_reset_token(user.email)
    link = f"{FRONTEND_URL}/reset-password?token={token}"

    await send_email(
        user.email,
        "Reset your password",
        reset_email_html(user.full_name, link)
    )

    return {"message": "Reset password link sent to your email"}

# ---------- RESET PASSWORD ----------
@app.post("/reset-password")
@limiter.limit("5/hour")
async def reset_password(request: Request, data: ResetPassword, db: Session = Depends(get_db)):
    """Update password"""
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    # Password validation
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    payload = decode_token(data.token)
    
    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Invalid reset token")
    
    user = db.query(User).filter(User.email == payload["sub"]).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    db.commit()

    return {"message": "Password reset successful"}

# ---------- GOOGLE LOGIN ----------
@app.post("/google-login")
@limiter.limit("10/minute")
async def google_login(request: Request, data: GoogleLogin, db: Session = Depends(get_db)):
    g_user = await get_google_user(data.google_access_token)
    email = g_user.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Invalid Google token")

    user = db.query(User).filter(User.email == email).first()

    if not user:
        user = User(
            email=email,
            full_name=g_user.get("name"),
            is_verified=True,
            is_google_user=True,
            created_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return {
        "access_token": create_access_token(email),
        "refresh_token": create_refresh_token(email)
    }

# ---------- ME ----------
@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "full_name": user.full_name}