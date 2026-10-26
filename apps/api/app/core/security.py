"""Password hashing (Argon2), JWT access/refresh tokens, and TOTP 2FA.

Access tokens are short-lived stateless JWTs. Refresh tokens carry a ``jti`` that is
recorded in Redis so they can be rotated and revoked (logout / lockout) without a DB
table — see ``store_refresh_jti`` / ``is_refresh_valid`` / ``revoke_refresh_jti``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings
from app.core.redis_client import get_redis

_ph = PasswordHasher()
ALGORITHM = "HS256"


# ---------------------------------------------------------------- passwords ---
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _ph.check_needs_rehash(hashed)
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------- tokens ---
def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, user_id: uuid.UUID | str, role: str) -> str:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": _now(),
        "exp": _now() + timedelta(seconds=settings.access_token_ttl_seconds),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(*, user_id: uuid.UUID | str, role: str) -> tuple[str, str]:
    """Returns (token, jti). Caller stores the jti in Redis to make it usable."""
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "refresh",
        "jti": jti,
        "iat": _now(),
        "exp": _now() + timedelta(seconds=settings.refresh_token_ttl_seconds),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), jti


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any]:
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(f"expected {expected_type} token")
    return payload


# ----------------------------------------------- refresh rotation (Redis) ---
def _refresh_key(jti: str) -> str:
    return f"refresh:{jti}"


async def store_refresh_jti(user_id: uuid.UUID | str, jti: str) -> None:
    await get_redis().set(
        _refresh_key(jti), str(user_id), ex=settings.refresh_token_ttl_seconds
    )


async def is_refresh_valid(jti: str) -> bool:
    return bool(await get_redis().exists(_refresh_key(jti)))


async def revoke_refresh_jti(jti: str) -> None:
    await get_redis().delete(_refresh_key(jti))


# --------------------------------------------------------------------- TOTP ---
def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=settings.totp_issuer)


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    try:
        # valid_window=1 tolerates ~30s clock skew on either side.
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:  # noqa: BLE001
        return False
