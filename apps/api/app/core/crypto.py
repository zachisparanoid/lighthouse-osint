"""Symmetric encryption for secrets at rest (BYOK API keys, TOTP secrets).

Uses Fernet (AES-128-CBC + HMAC) with the key from ``FERNET_KEY``. Plaintext is
never logged and never returned to the client — callers surface only ``mask_secret``.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet = Fernet(settings.fernet_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()


def try_decrypt(token: str) -> str | None:
    try:
        return decrypt(token)
    except (InvalidToken, ValueError):
        return None


def hint_of(plaintext: str) -> str:
    """Last 4 chars — stored alongside the ciphertext so the UI can show ••••1234."""
    return plaintext[-4:] if len(plaintext) >= 4 else plaintext


def mask_secret(hint: str | None) -> str:
    return "••••" + (hint or "")
