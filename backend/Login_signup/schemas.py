# -------- Pydantic schemas for validation --------

from pydantic import BaseModel, EmailStr, Field


class Signup(BaseModel):
    full_name:        str = Field(..., min_length=1, max_length=255)
    email:            EmailStr
    password:         str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class Login(BaseModel):
    email:    EmailStr
    password: str = Field(..., max_length=128)


class RefreshToken(BaseModel):
    refresh_token: str = Field(..., max_length=2048)


class GoogleLogin(BaseModel):
    google_access_token: str = Field(..., max_length=2048)


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token:            str = Field(..., max_length=2048)
    new_password:     str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ChangePassword(BaseModel):
    current_password:   str = Field(..., max_length=128)
    new_password:       str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str = Field(..., min_length=8, max_length=128)


class CreatePassword(BaseModel):
    """
    Used by OAuth-only users who have never set a local password.
    No current_password field — the Bearer token is the identity proof.
    """
    new_password:       str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str = Field(..., min_length=8, max_length=128)