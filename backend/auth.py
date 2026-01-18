from datetime import datetime, timedelta
import bcrypt
import jwt
import httpx  # for Google API requests

# ---------- CONFIG ----------
SECRET_KEY = "your_secret_key_here"  # replace with a secure key
ALGORITHM = "HS256"

# ---------- PASSWORD FUNCTIONS ----------
def hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a hash."""
    if not hashed:
        return False
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ---------- TOKEN FUNCTIONS ----------
def create_token(data: dict, expires: timedelta) -> str:
    """Generic JWT token creator."""
    payload = data.copy()
    payload['exp'] = datetime.utcnow() + expires
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_access_token(email: str) -> str:
    return create_token({"sub": email, "type": "access"}, timedelta(minutes=15))

def create_refresh_token(email: str) -> str:
    return create_token({"sub": email, "type": "refresh"}, timedelta(days=7))

def create_email_token(email: str) -> str:
    return create_token({"sub": email, "type": "email"}, timedelta(hours=1))

def create_reset_token(email: str) -> str:
    return create_token({"sub": email, "type": "reset"}, timedelta(minutes=30))

def decode_token(token: str) -> dict:
    """Decode a JWT token and return the payload."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")

# ---------- GOOGLE LOGIN FUNCTION ----------
async def get_google_user(google_access_token: str) -> dict:
    """Fetch user info from Google API using access token."""
    url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {google_access_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code != 200:
            raise Exception("Invalid Google token")
        return resp.json()
