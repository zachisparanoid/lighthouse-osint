"""BYOK API key manager.

Plaintext key material is NEVER returned to the client — endpoints surface only
``KeyOut`` (masked hint). Secrets are stored Fernet-encrypted at rest; a lightweight
``/test`` endpoint verifies a key against its upstream service.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import crypto
from app.core.audit import write_audit
from app.core.rbac import (
    client_ip,
    get_current_user,
    require_analyst,
    user_agent,
)
from app.db.models import APIKey, Case, KeyScope, User
from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.schemas.key import KeyCreate, KeyOut, KeyTestResult
from lighthouse_shared import KeyService, Role

router = APIRouter()


async def _owned_case_ids(db: AsyncSession, user: User) -> list[uuid.UUID]:
    """Case ids the user owns (admins see all cases)."""
    stmt = select(Case.id).where(Case.deleted_at.is_(None))
    if user.role != Role.ADMIN:
        stmt = stmt.where(Case.owner_id == user.id)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def _user_may_manage_key(db: AsyncSession, key: APIKey, user: User) -> bool:
    """True if the user owns the key (user-scope) or owns/admins its case (case-scope)."""
    if user.role == Role.ADMIN:
        return True
    if key.scope == KeyScope.USER:
        return key.owner_user_id == user.id
    if key.scope == KeyScope.CASE and key.owner_case_id is not None:
        case = await db.get(Case, key.owner_case_id)
        return case is not None and case.owner_id == user.id
    return False


@router.get("/keys", response_model=list[KeyOut])
async def list_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[APIKey]:
    """List the user's own user-keys plus case-keys for cases they own (admins: all)."""
    owned_cases = await _owned_case_ids(db, current_user)
    stmt = select(APIKey).where(APIKey.deleted_at.is_(None))
    if current_user.role != Role.ADMIN:
        conditions = [
            (APIKey.scope == KeyScope.USER) & (APIKey.owner_user_id == current_user.id)
        ]
        if owned_cases:
            conditions.append(
                (APIKey.scope == KeyScope.CASE) & (APIKey.owner_case_id.in_(owned_cases))
            )
        # Combine the OR-conditions.
        combined = conditions[0]
        for cond in conditions[1:]:
            combined = combined | cond
        stmt = stmt.where(combined)
    stmt = stmt.order_by(APIKey.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.post("/keys", response_model=KeyOut, status_code=201)
async def create_key(
    payload: KeyCreate,
    request: Request,
    current_user: User = Depends(require_analyst),
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    """Create a BYOK key. Encrypts the value; only a hint is ever stored alongside."""
    if payload.scope == "case":
        if payload.case_id is None:
            raise HTTPException(400, "case_id is required for a case-scoped key")
        case = await db.get(Case, payload.case_id)
        if case is None or case.deleted_at is not None:
            raise HTTPException(404, "Case not found")
        if current_user.role != Role.ADMIN and case.owner_id != current_user.id:
            raise HTTPException(403, "Only the case owner or an admin may add a case key")
        owner_user_id = None
        owner_case_id = payload.case_id
    else:  # user scope
        owner_user_id = current_user.id
        owner_case_id = None

    key = APIKey(
        scope=KeyScope(payload.scope),
        owner_user_id=owner_user_id,
        owner_case_id=owner_case_id,
        service=payload.service,
        encrypted_value=crypto.encrypt(payload.value),
        hint=crypto.hint_of(payload.value),
        label=payload.label,
        is_valid=None,
        created_by=current_user.id,
    )
    db.add(key)
    await db.flush()

    await write_audit(
        db,
        action="key.create",
        actor_id=current_user.id,
        target_type="api_key",
        target_id=key.id,
        case_id=owner_case_id,
        ip=client_ip(request),
        user_agent=user_agent(request),
        meta={"service": payload.service.value, "scope": payload.scope},
    )
    await db.commit()
    await db.refresh(key)
    return key


async def _check_service_key(service: KeyService, plaintext: str) -> tuple[bool | None, str]:
    """Lightweight upstream validity check. Returns (is_valid, message).

    Network/transport errors leave is_valid as None ("could not verify").
    """
    headers = {"User-Agent": settings.http_user_agent}
    timeout = httpx.Timeout(10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as http:
            if service == KeyService.SHODAN:
                resp = await http.get(
                    "https://api.shodan.io/api-info", params={"key": plaintext}
                )
                if resp.status_code == 200:
                    return True, "Key is valid."
                return False, f"Shodan rejected the key (HTTP {resp.status_code})."
            if service == KeyService.HIBP:
                resp = await http.get(
                    "https://haveibeenpwned.com/api/v3/subscription/status",
                    headers={"hibp-api-key": plaintext},
                )
                if resp.status_code == 200:
                    return True, "Key is valid."
                if resp.status_code == 401:
                    return False, "HIBP rejected the key (unauthorized)."
                return False, f"HIBP returned HTTP {resp.status_code}."
            if service == KeyService.OPENCORPORATES:
                resp = await http.get(
                    "https://api.opencorporates.com/v0.4/account_status",
                    params={"api_token": plaintext},
                )
                if resp.status_code == 200:
                    return True, "Key is valid."
                return False, f"OpenCorporates rejected the key (HTTP {resp.status_code})."
    except (httpx.HTTPError, httpx.TimeoutException):
        return None, "Could not verify (network error)."
    return None, "Could not verify."


@router.post("/keys/{key_id}/test", response_model=KeyTestResult)
async def test_key(
    key_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyTestResult:
    """Decrypt and verify a key against its upstream service; records is_valid."""
    key = await db.get(APIKey, key_id)
    if key is None or key.deleted_at is not None:
        raise HTTPException(404, "Key not found")
    if not await _user_may_manage_key(db, key, current_user):
        raise HTTPException(403, "You may not test this key")

    plaintext = crypto.try_decrypt(key.encrypted_value)
    if plaintext is None:
        # Stored ciphertext is unreadable (e.g. rotated FERNET_KEY).
        key.is_valid = False
        await write_audit(
            db,
            action="key.test",
            actor_id=current_user.id,
            target_type="api_key",
            target_id=key.id,
            case_id=key.owner_case_id,
            ip=client_ip(request),
            user_agent=user_agent(request),
            meta={"service": key.service.value, "result": "undecryptable"},
        )
        await db.commit()
        raise HTTPException(400, "Stored key could not be decrypted")

    is_valid, message = await _check_service_key(key.service, plaintext)
    key.is_valid = is_valid
    key.last_used_at = datetime.now(timezone.utc)

    await write_audit(
        db,
        action="key.test",
        actor_id=current_user.id,
        target_type="api_key",
        target_id=key.id,
        case_id=key.owner_case_id,
        ip=client_ip(request),
        user_agent=user_agent(request),
        meta={"service": key.service.value, "is_valid": is_valid},
    )
    await db.commit()

    return KeyTestResult(
        id=key.id,
        service=key.service,
        is_valid=bool(is_valid),
        message=message,
    )


@router.delete("/keys/{key_id}", response_model=MessageResponse)
async def delete_key(
    key_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Soft-delete a key (sets deleted_at). Owner / case-owner / admin only."""
    key = await db.get(APIKey, key_id)
    if key is None or key.deleted_at is not None:
        raise HTTPException(404, "Key not found")
    if not await _user_may_manage_key(db, key, current_user):
        raise HTTPException(403, "You may not delete this key")

    key.deleted_at = datetime.now(timezone.utc)
    await write_audit(
        db,
        action="key.delete",
        actor_id=current_user.id,
        target_type="api_key",
        target_id=key.id,
        case_id=key.owner_case_id,
        ip=client_ip(request),
        user_agent=user_agent(request),
        meta={"service": key.service.value, "scope": key.scope.value},
    )
    await db.commit()
    return MessageResponse(message="Key deleted")
