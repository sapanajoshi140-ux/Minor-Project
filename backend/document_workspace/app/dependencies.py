"""
dependencies.py — Shared FastAPI dependency for document_workspace.

get_current_user validates the Bearer JWT and additionally checks the
revoked_tokens blacklist so that logged-out tokens are rejected here too.
"""

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import User, RevokedToken, get_db

import os
import jwt
from dotenv import load_dotenv

load_dotenv()

_SECRET_KEY = os.getenv("JWT_SECRET")
if not _SECRET_KEY:
    raise ValueError("JWT_SECRET not found in environment variables.")

_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def get_current_user(
    authorization: str = Header(..., description="Bearer <access_token>"),
    db: Session = Depends(get_db),
) -> User:
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be: Bearer <token>",
        )

    payload = _decode_token(parts[1])

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    # Blacklist check — reject tokens revoked at logout
    jti = payload.get("jti", "")
    if jti and db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked. Please log in again.",
        )

    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Email not verified.")

    return user