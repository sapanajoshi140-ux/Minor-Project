from datetime import datetime, timedelta, timezone
import uuid
import bcrypt
import jwt
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

# ---------- CONFIG ----------
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET not found in environment variables. Check your .env file")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


# ---------- CUSTOM EXCEPTIONS ----------
class TokenExpiredError(Exception):
    """Raised when a JWT has passed its expiry time."""

class TokenInvalidError(Exception):
    """Raised when a JWT has an invalid signature or is malformed."""


# ---------- PASSWORD FUNCTIONS ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ---------- TOKEN FUNCTIONS ----------
def create_token(data: dict, expires: timedelta) -> str:
    """
    Create a JWT that includes:
      jti — a unique UUID so the token can be individually revoked.
      exp — standard expiry timestamp (timezone-aware UTC).
    """
    payload = data.copy()
    payload["jti"] = str(uuid.uuid4())   # unique token ID — used for blacklisting
    payload["exp"] = datetime.now(timezone.utc) + expires
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(email: str) -> str:
    return create_token({"sub": email, "type": "access"}, timedelta(hours=2))

def create_refresh_token(email: str) -> str:
    return create_token({"sub": email, "type": "refresh"}, timedelta(days=7))

def create_email_token(email: str) -> str:
    return create_token({"sub": email, "type": "email"}, timedelta(hours=1))

def create_reset_token(email: str) -> str:
    return create_token({"sub": email, "type": "reset"}, timedelta(minutes=30))

def decode_token(token: str) -> dict:
    """
    Decode and return the JWT payload.

    Raises:
        TokenExpiredError  — token is well-formed but past its expiry.
        TokenInvalidError  — signature mismatch, malformed token, etc.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError("Invalid token") from exc


# ---------- GOOGLE LOGIN ----------
async def get_google_user(google_access_token: str) -> dict:
    url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {google_access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise Exception("Invalid Google token")
        return resp.json()