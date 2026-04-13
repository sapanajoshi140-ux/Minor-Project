"""
dependencies.py — Shared FastAPI dependency for document_workspace.

get_current_user validates the Bearer JWT and additionally checks the
revoked_tokens blacklist so that logged-out tokens are rejected here too.

get_current_user_flexible also accepts a `token` query parameter — used
for endpoints loaded in iframes/embeds where custom headers can't be sent.
"""

from fastapi import Depends, Header, HTTPException, Query
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


def _get_user_from_token(raw_token: str, db: Session) -> User:
    """Shared logic: decode token, check blacklist, return User."""
    payload = _decode_token(raw_token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type.")

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
    return _get_user_from_token(parts[1], db)


def get_current_user_flexible(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Like get_current_user but also accepts a `token` query parameter.
    Use ONLY for endpoints loaded in iframes or <embed> tags where
    browsers cannot send custom Authorization headers.
    """
    raw_token = None

    if authorization:
        parts = authorization.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Authorization header must be: Bearer <token>",
            )
        raw_token = parts[1]
    elif token:
        raw_token = token

    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Provide Authorization header or token query param.",
        )

    return _get_user_from_token(raw_token, db)