from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from database import SessionLocal, User
from schemas import (
    Signup, Login, RefreshToken,
    GoogleLogin, ForgotPassword, ResetPassword
)
from auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    create_email_token, create_reset_token,
    decode_token, get_google_user
)

# ---------- APP ----------
app = FastAPI(title="Auth Backend")



# ---------- CORS ----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Replace with frontend URL 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ---------- DATABASE DEPENDENCY ----------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



# ---------- CURRENT USER DEPENDENCY ----------
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
# Register new user; returns email verification link

@app.post("/signup")
def signup(data: Signup, db: Session = Depends(get_db)):
    try:
        if data.password != data.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")

        hashed_pw = hash_password(data.password)

        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hashed_pw,
            is_verified=False,
            is_google_user=False,
            created_at=datetime.utcnow()
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        verify_token = create_email_token(user.email)

        return {
            "message": "Signup successful",
            "verify_link": f"http://localhost:8000/verify-email?token={verify_token}"
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")



# ---------- EMAIL VERIFICATION ----------
# Verify user email using token from signup link

@app.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    try:
        payload = decode_token(token)
        user = db.query(User).filter(User.email == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.is_verified = True
        db.commit()
        return {"message": "Email verified successfully"}

    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")



# ---------- LOGIN ----------
# Login with email/password; returns access & refresh tokens

@app.post("/login")
def login(data: Login, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == data.email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if user.is_google_user:
            raise HTTPException(status_code=400, detail="Use Google login for this account")

        if not user.hashed_password or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        if not user.is_verified:
            raise HTTPException(status_code=403, detail="Verify email first")

        access_token = create_access_token(user.email)
        refresh_token = create_refresh_token(user.email)
        return {"access_token": access_token, "refresh_token": refresh_token}

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")



# ---------- REFRESH TOKEN ----------
# Get new access token using refresh token

@app.post("/refresh")
def refresh(data: RefreshToken):
    try:
        payload = decode_token(data.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid refresh token")

        access_token = create_access_token(payload["sub"])
        return {"access_token": access_token}

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")



# ---------- FORGOT PASSWORD ----------
# Request password reset link; email may not exist

@app.post("/forgot-password")
def forgot_password(data: ForgotPassword, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        return {"message": "If email exists, reset link sent"}

    reset_token = create_reset_token(user.email)
    return {"reset_link": f"http://localhost:8000/reset-password?token={reset_token}"}



# ---------- RESET PASSWORD ----------
 # Reset password using token from reset link

@app.post("/reset-password")
def reset_password(data: ResetPassword, db: Session = Depends(get_db)):
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    try:
        payload = decode_token(data.token)
        user = db.query(User).filter(User.email == payload["sub"]).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user.hashed_password = hash_password(data.new_password)
        db.commit()
        return {"message": "Password reset successful"}

    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired token")



# ---------- GOOGLE LOGIN ----------
# Login/register using Google OAuth token; returns access & refresh tokens

@app.post("/google-login")
async def google_login(data: GoogleLogin, db: Session = Depends(get_db)):
    try:
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
                hashed_password=None,
                created_at=datetime.utcnow()
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        access_token = create_access_token(email)
        refresh_token = create_refresh_token(email)
        return {"access_token": access_token, "refresh_token": refresh_token}

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")



# ---------- PROTECTED ROUTE ----------
# Get current logged-in user's info (email & full name)

@app.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"email": user.email, "full_name": user.full_name}
