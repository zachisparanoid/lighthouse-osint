"""Authentication: register, login (with lockout + optional TOTP), rotating refresh
tokens in an httpOnly cookie, logout, /me, and TOTP management.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import crypto
from app.core.audit import write_audit
from app.core.rbac import client_ip, get_current_user, user_agent
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_totp_secret,
    hash_password,
    is_refresh_valid,
    needs_rehash,
    revoke_refresh_jti,
    store_refresh_jti,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    UserOut,
)
from app.schemas.common import MessageResponse
from lighthouse_shared import Role

router = APIRouter()

REFRESH_COOKIE = "lh_refresh"
COOKIE_PATH = "/api/v1/auth"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=COOKIE_PATH,
    )


async def _issue_tokens(user: User, response: Response) -> TokenResponse:
    access = create_access_token(user_id=user.id, role=user.role.value)
    refresh, jti = create_refresh_token(user_id=user.id, role=user.role.value)
    await store_refresh_jti(user.id, jti)
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=access,
        expires_in=settings.access_token_ttl_seconds,
        user=UserOut.model_validate(user),
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    email = payload.email.lower()
    existing = await db.scalar(select(User).where(func.lower(User.email) == email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists.")
    # The very first user bootstraps as admin; everyone else starts as analyst.
    user_count = await db.scalar(select(func.count()).select_from(User))
    role = Role.ADMIN if user_count == 0 else Role.ANALYST
    user = User(email=email, password_hash=hash_password(payload.password), role=role)
    db.add(user)
    await db.flush()
    await write_audit(db, action="auth.register", actor_id=user.id, target_type="user", target_id=user.id,
                      ip=client_ip(request), user_agent=user_agent(request), meta={"role": role.value})
    await db.commit()
    return await _issue_tokens(user, response)


@router.post("/auth/login", response_model=None)
async def login(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
    if user is None or user.deleted_at is not None:
        raise invalid
    if user.locked_until is not None and user.locked_until > _now():
        raise HTTPException(status.HTTP_423_LOCKED, "Account temporarily locked after repeated failures.")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        action = "auth.login_failed"
        if user.failed_login_count >= settings.max_login_attempts:
            user.locked_until = _now() + timedelta(seconds=settings.login_lockout_seconds)
            user.failed_login_count = 0
            action = "auth.lockout"
        await write_audit(db, action=action, actor_id=user.id, ip=client_ip(request), user_agent=user_agent(request))
        await db.commit()
        raise invalid

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled.")

    if user.totp_enabled:
        if not payload.totp_code:
            return JSONResponse({"totp_required": True}, status_code=200)
        secret = crypto.try_decrypt(user.totp_secret or "")
        if not secret or not verify_totp(secret, payload.totp_code):
            user.failed_login_count += 1
            await write_audit(db, action="auth.totp_failed", actor_id=user.id,
                              ip=client_ip(request), user_agent=user_agent(request))
            await db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid 2FA code.")

    # Success: reset counters, opportunistically upgrade the password hash.
    user.failed_login_count = 0
    user.locked_until = None
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
    await write_audit(db, action="auth.login", actor_id=user.id, ip=client_ip(request), user_agent=user_agent(request))
    await db.commit()
    return await _issue_tokens(user, response)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session.")
    if not token:
        raise invalid
    try:
        payload = decode_token(token, expected_type="refresh")
    except Exception:  # noqa: BLE001
        raise invalid from None
    jti = payload.get("jti")
    if not jti or not await is_refresh_valid(jti):
        raise invalid
    import uuid

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active or user.deleted_at is not None:
        raise invalid
    await revoke_refresh_jti(jti)  # rotate: the old refresh token is now dead
    return await _issue_tokens(user, response)


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        try:
            jti = decode_token(token).get("jti")
            if jti:
                await revoke_refresh_jti(jti)
        except Exception:  # noqa: BLE001
            pass
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    await write_audit(db, action="auth.logout", actor_id=user.id, ip=client_ip(request), user_agent=user_agent(request))
    await db.commit()
    return MessageResponse(message="Logged out.")


@router.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/auth/password", response_model=MessageResponse)
async def change_password(
    payload: PasswordChangeRequest, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    user.password_hash = hash_password(payload.new_password)
    await write_audit(db, action="auth.password_change", actor_id=user.id)
    await db.commit()
    return MessageResponse(message="Password updated.")


# --------------------------------------------------------------------- TOTP ---
@router.post("/auth/totp/setup", response_model=TOTPSetupResponse)
async def totp_setup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> TOTPSetupResponse:
    secret = generate_totp_secret()
    user.totp_secret = crypto.encrypt(secret)  # stored encrypted; not enabled until verified
    await db.commit()
    return TOTPSetupResponse(secret=secret, provisioning_uri=totp_provisioning_uri(secret, user.email))


@router.post("/auth/totp/enable", response_model=MessageResponse)
async def totp_enable(
    payload: TOTPVerifyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> MessageResponse:
    secret = crypto.try_decrypt(user.totp_secret or "")
    if not secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Run TOTP setup first.")
    if not verify_totp(secret, payload.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid 2FA code.")
    user.totp_enabled = True
    await write_audit(db, action="auth.totp_enabled", actor_id=user.id)
    await db.commit()
    return MessageResponse(message="Two-factor authentication enabled.")


@router.post("/auth/totp/disable", response_model=MessageResponse)
async def totp_disable(
    payload: TOTPVerifyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> MessageResponse:
    secret = crypto.try_decrypt(user.totp_secret or "")
    if user.totp_enabled and (not secret or not verify_totp(secret, payload.code)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid 2FA code.")
    user.totp_enabled = False
    user.totp_secret = None
    await write_audit(db, action="auth.totp_disabled", actor_id=user.id)
    await db.commit()
    return MessageResponse(message="Two-factor authentication disabled.")
