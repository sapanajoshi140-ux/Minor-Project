from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime

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

# ---------- APP ----------
app = FastAPI(title="Auth Backend")

# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
async def signup(data: Signup, db: Session = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

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
        db.commit()
        db.refresh(user)

        # Send verification email (backend link)
        token = create_email_token(user.email)
        link = f"http://localhost:8000/verify-email?token={token}"

        await send_email(
            user.email,
            "Verify your email",
            verify_email_html(user.full_name, link)
        )

        return {"message": "Signup successful. Please check your email to verify."}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")

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

    # Redirect to frontend login page after verification
    return RedirectResponse("http://localhost:3000/login")



# ---------- RESEND VERIFICATION ----------
@app.post("/resend-verification")
async def resend_verification(data: ResendVerificationRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not registered")
    if user.is_verified:
        return {"message": "Email already verified"}

    token = create_email_token(user.email)
    link = f"http://localhost:8000/verify-email?token={token}"

    await send_email(
        user.email,
        "Verify your email",
        verify_email_html(user.full_name, link)
    )

    return {"message": "Verification email resent"}

# ---------- LOGIN ----------
@app.post("/login")
def login(data: Login, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

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
def refresh(data: RefreshToken):
    payload = decode_token(data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return {"access_token": create_access_token(payload["sub"])}

# ---------- FORGOT PASSWORD ----------
@app.post("/forgot-password")
async def forgot_password(data: ForgotPassword, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        raise HTTPException(status_code=404, detail="Email not registered")

    token = create_reset_token(user.email)
    link = f"http://localhost:8000/reset-password?token={token}"

    await send_email(
        user.email,
        "Reset your password",
        reset_email_html(user.full_name, link)
    )

    return {"message": "Reset password link sent to your email"}



# ---------- RESET PASSWORD ----------
@app.get("/reset-password")
def reset_password_get(token: str, db: Session = Depends(get_db)):
    """Redirect user to frontend reset password page with token"""
    payload = decode_token(token)
    user = db.query(User).filter(User.email == payload["sub"]).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return RedirectResponse(f"http://localhost:3000/reset-password?token={token}")

@app.post("/reset-password")
def reset_password(data: ResetPassword, db: Session = Depends(get_db)):
    """Update password and redirect to login"""
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    payload = decode_token(data.token)
    user = db.query(User).filter(User.email == payload["sub"]).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    db.commit()

    # Redirect to frontend login page after password reset
    return RedirectResponse("http://localhost:3000/login")

# ---------- GOOGLE LOGIN ----------
@app.post("/google-login")
async def google_login(data: GoogleLogin, db: Session = Depends(get_db)):
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
