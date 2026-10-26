from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from lighthouse_shared import Role


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    # First registered user becomes admin; subsequent default to analyst (enforced server-side).


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    role: Role
    is_active: bool
    totp_enabled: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    # Set when the account has 2FA enabled but no code was supplied yet.
    totp_required: bool = False


class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TOTPVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=200)
