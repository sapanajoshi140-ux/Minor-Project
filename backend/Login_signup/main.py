import re
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from fastapi.openapi.utils import get_openapi
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import os
from dotenv import load_dotenv

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import SessionLocal, User, RevokedToken
from schemas import (
    Signup, Login, RefreshToken,
    GoogleLogin, ForgotPassword, ResetPassword, ResendVerificationRequest,
    ChangePassword, CreatePassword,
)
from auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    create_email_token, create_reset_token,
    decode_token, get_google_user,
    TokenExpiredError, TokenInvalidError,
)
from email_config import send_email, verify_email_html, reset_email_html

load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL", "")
BACKEND_URL  = os.getenv("BACKEND_URL", "")


_raw_origins = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
if not CORS_ORIGINS:
    raise ValueError("CORS_ORIGINS is not set. Check your .env file.")

# ---------- SCHEDULER / LIFESPAN ----------
_scheduler = AsyncIOScheduler()

def _cleanup_revoked_tokens() -> None:
    """Purge expired blacklist rows — runs daily."""
    db = SessionLocal()
    try:
        db.query(RevokedToken) \
          .filter(RevokedToken.expires_at < datetime.now(timezone.utc)) \
          .delete()
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    _scheduler.add_job(_cleanup_revoked_tokens, "interval", hours=24, id="cleanup_revoked")
    _scheduler.start()
    yield
    _scheduler.shutdown(wait=False)

# ---------- APP ----------
security = HTTPBearer()

app = FastAPI(
    title="Auth Backend",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title="Auth Backend",
        version="0.1.0",
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your access_token from POST /login here.",
        }
    }
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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

# ---------- BLACKLIST HELPERS ----------
def _is_revoked(jti: str, db: Session) -> bool:
    """Return True if the token's jti exists in the revoked_tokens table."""
    return db.query(RevokedToken).filter(RevokedToken.jti == jti).first() is not None

def _revoke(payload: dict, db: Session) -> None:
    """Insert a jti into the blacklist. Ignores duplicates silently."""
    jti = payload.get("jti")
    if not jti:
        return  # old token without jti — nothing to store
    if db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
        return  # already revoked
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    db.add(RevokedToken(
        jti        = jti,
        token_type = payload.get("type", "unknown"),
        expires_at = exp,
    ))
    db.commit()

# ---------- CURRENT USER ----------
def get_current_user(
    authorization: str = Header(..., include_in_schema=False),
    db: Session = Depends(get_db),
) -> User:
    """Validate Bearer token and return the authenticated User."""
    try:
        token   = authorization.split(" ")[1]
        payload = decode_token(token)

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        if _is_revoked(payload.get("jti", ""), db):
            raise HTTPException(status_code=401, detail="Token has been revoked. Please log in again.")

        user = db.query(User).filter(User.email == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    except HTTPException:
        raise
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token has expired. Please log in again.")
    except TokenInvalidError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

# ---------- PASSWORD STRENGTH ----------
# Fix #9 — import re at module level, not inside the function on every call
def _check_password_strength(password: str) -> None:
    """
    Enforce a baseline password policy.  Raises HTTPException 400 on failure.
    Rules: ≥8 chars, at least one uppercase, one lowercase, one digit.
    """
    errors = []
    if len(password) < 8:
        errors.append("at least 8 characters")
    if not re.search(r"[A-Z]", password):
        errors.append("at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        errors.append("at least one lowercase letter")
    if not re.search(r"\d", password):
        errors.append("at least one number")
    if errors:
        raise HTTPException(
            status_code=400,
            detail="Password must contain " + ", ".join(errors) + ".",
        )


# ---------- SIGNUP ----------
@app.post("/signup")
@limiter.limit("5/minute")
async def signup(request: Request, data: Signup, db: Session = Depends(get_db)):
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    _check_password_strength(data.password)

    try:
        user = User(
            email           = data.email,
            full_name       = data.full_name,
            hashed_password = hash_password(data.password),
            is_verified     = False,
            is_google_user  = False,
            has_password    = True,
            created_at      = datetime.now(timezone.utc),
        )
        db.add(user)


        db.commit()
        db.refresh(user)

        token = create_email_token(user.email)
        link  = f"{FRONTEND_URL}/verify-email?token={token}"
        await send_email(user.email, "Verify your email", verify_email_html(user.full_name, link))

        return {"message": "Signup successful. Please check your email to verify."}

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Signup failed. Please try again.")


# ---------- VERIFY EMAIL ----------
@app.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):

    try:
        payload = decode_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=400, detail="Verification link has expired. Please request a new one.")
    except TokenInvalidError:
        raise HTTPException(status_code=400, detail="Invalid verification link.")

    if payload.get("type") != "email":
        raise HTTPException(status_code=400, detail="Invalid token")

    user = db.query(User).filter(User.email == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_verified:
        user.is_verified = True
        db.commit()

    return {"message": "Email verified successfully!", "redirect": f"{FRONTEND_URL}/login"}


# ---------- RESEND VERIFICATION ----------
@app.post("/resend-verification")
@limiter.limit("3/minute")
async def resend_verification(request: Request, data: ResendVerificationRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        return {"message": "If this email is registered, a verification link has been sent."}
    if user.is_verified:
        return {"message": "Email already verified"}

    token = create_email_token(user.email)
    link  = f"{FRONTEND_URL}/verify-email?token={token}"
    await send_email(user.email, "Verify your email", verify_email_html(user.full_name, link))
    return {"message": "Verification email sent"}


# ---------- LOGIN ----------
@app.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, data: Login, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password or ""):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Block OAuth-only accounts (no password set) from using this endpoint
    if user.is_google_user and not user.has_password:
        raise HTTPException(status_code=400, detail="This account uses Google login. Use Google sign-in or create a password first.")
    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Verify email first")

    return {
        "access_token":  create_access_token(user.email),
        "refresh_token": create_refresh_token(user.email),
    }


# ---------- LOGOUT ----------
@app.post("/logout")
@limiter.limit("10/minute")
async def logout(
    request: Request,
    data: RefreshToken,
    authorization: str = Header(..., include_in_schema=False),
    db: Session = Depends(get_db),
):
    """
    Revoke both the access token (from Authorization header) and the
    refresh token (from the request body).  After this call:
      - The access token is blacklisted immediately (not just on expiry).
      - The refresh token cannot be used to mint new access tokens.
    """
    errors = []

    # 1. Revoke the access token
    try:
        raw_access = authorization.split(" ")[1]
        access_payload = decode_token(raw_access)
        _revoke(access_payload, db)
    except Exception as e:
        errors.append(f"Access token: {e}")

    # 2. Revoke the refresh token
    try:
        refresh_payload = decode_token(data.refresh_token)
        if refresh_payload.get("type") != "refresh":
            errors.append("Refresh token: wrong token type")
        else:
            _revoke(refresh_payload, db)
    except Exception as e:
        errors.append(f"Refresh token: {e}")


    if errors:
        return {"message": "Logged out (with warnings)", "warnings": errors}
    return {"message": "Logged out successfully"}


# ---------- REFRESH ----------
@app.post("/refresh")
@limiter.limit("10/minute")
async def refresh(request: Request, data: RefreshToken, db: Session = Depends(get_db)):
    try:
        payload = decode_token(data.refresh_token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Refresh token has expired. Please log in again.")
    except TokenInvalidError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if _is_revoked(payload.get("jti", ""), db):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked. Please log in again.")

    return {"access_token": create_access_token(payload["sub"])}


# ---------- FORGOT PASSWORD ----------
@app.post("/forgot-password")
@limiter.limit("3/hour")
async def forgot_password(request: Request, data: ForgotPassword, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user:
        return {"message": "If this email is registered, a password reset link has been sent."}

    token = create_reset_token(user.email)
    link  = f"{FRONTEND_URL}/reset-password?token={token}"
    await send_email(user.email, "Reset your password", reset_email_html(user.full_name, link))
    return {"message": "Reset password link sent to your email"}


# ---------- RESET PASSWORD ----------
@app.post("/reset-password")
@limiter.limit("5/hour")
async def reset_password(request: Request, data: ResetPassword, db: Session = Depends(get_db)):
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    _check_password_strength(data.new_password)


    try:
        payload = decode_token(data.token)
    except TokenExpiredError:
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")
    except TokenInvalidError:
        raise HTTPException(status_code=400, detail="Invalid reset token.")

    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Invalid reset token")

    user = db.query(User).filter(User.email == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(data.new_password)
    db.commit()


    _revoke(payload, db)

    return {"message": "Password reset successful"}


# ---------- GOOGLE LOGIN ----------
@app.post("/google-login")
@limiter.limit("10/minute")
async def google_login(request: Request, data: GoogleLogin, db: Session = Depends(get_db)):
    g_user = await get_google_user(data.google_access_token)
    email  = g_user.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Invalid Google token")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        # New user — create an OAuth-only account
        user = User(
            email          = email,
            full_name      = g_user.get("name"),
            is_verified    = True,
            is_google_user = True,
            created_at     = datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:

        if not user.is_google_user:
            user.is_google_user = True
            db.commit()

    return {
        "access_token":  create_access_token(email),
        "refresh_token": create_refresh_token(email),
    }


# ---------- CHANGE PASSWORD ----------
@app.post("/change-password")
@limiter.limit("5/hour")
async def change_password(
    request: Request,
    data: ChangePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    For email/password users: verify the current password, then update to a new one.
    OAuth-only users (has_password=False) must use POST /create-password instead.
    Identity is established via the Bearer token — no email field needed in the body.
    """
    if not current_user.has_password:
        raise HTTPException(
            status_code=400,
            detail="Your account has no password yet. Use POST /create-password to set one.",
        )
    if not current_user.is_verified:
        raise HTTPException(status_code=403, detail="Verify your email before changing your password")
    if data.new_password != data.confirm_new_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")
    _check_password_strength(data.new_password)
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from current password")
    if not verify_password(data.current_password, current_user.hashed_password or ""):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    user = db.query(User).filter(User.id == current_user.id).first()
    user.hashed_password = hash_password(data.new_password)
    user.has_password    = True   # already True, but be explicit
    db.commit()
    return {"message": "Password changed successfully"}


# ---------- CREATE PASSWORD (OAuth users) ----------
@app.post("/create-password")
@limiter.limit("5/hour")
async def create_password(
    request: Request,
    data: CreatePassword,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lets OAuth-only users (Google, GitHub, …) add a local password to their account.

    After this call the user can log in with EITHER their OAuth provider
    OR their email + the newly created password.

    - Requires a valid Bearer access token (i.e. the user must already be
      signed in via OAuth).
    - Rejected if the account already has a password — use /change-password instead.
    """
    if current_user.has_password:
        raise HTTPException(
            status_code=400,
            detail="Your account already has a password. Use POST /change-password to update it.",
        )
    if data.new_password != data.confirm_new_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")


    _check_password_strength(data.new_password)

    user = db.query(User).filter(User.id == current_user.id).first()
    user.hashed_password = hash_password(data.new_password)
    user.has_password    = True
    db.commit()
    return {
        "message": "Password created successfully. You can now log in with your email and password.",
    }


# ---------- ME ----------
@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "email":          user.email,
        "full_name":      user.full_name,
        "is_google_user": user.is_google_user,
        # Frontend uses this to decide: True → "Change Password", False → "Create Password"
        "has_password":   user.has_password,
    }


@app.delete("/admin/revoked-tokens/cleanup", include_in_schema=False)
def cleanup_revoked_tokens(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_user),   # any valid token is sufficient;
                                                  # extend to an is_admin check if needed
):
    """
    Delete blacklist rows whose natural expiry has already passed.
    These tokens are harmless — they can never be decoded as valid — so
    keeping them only wastes storage.  Also runs automatically via the
    daily APScheduler job.
    """
    deleted = (
        db.query(RevokedToken)
        .filter(RevokedToken.expires_at < datetime.now(timezone.utc))
        .delete()
    )
    db.commit()
    return {"deleted_rows": deleted}