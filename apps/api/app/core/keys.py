"""BYOK key resolution.

Lookup order for a service's key: a case-scoped key, then the requesting user's key,
then an optional process-wide env fallback. Plaintext is only ever produced here for an
outbound request; it is never returned toward the client.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core import crypto
from app.db.models import APIKey, KeyScope
from lighthouse_shared import KeyService

_SERVICES = [s.value for s in KeyService]


async def _candidate_keys(
    db: AsyncSession, case_id: uuid.UUID, service: str, user_id: uuid.UUID | None
) -> APIKey | None:
    svc = KeyService(service)
    rows = (
        await db.execute(
            select(APIKey).where(APIKey.service == svc, APIKey.deleted_at.is_(None))
        )
    ).scalars().all()
    case_key = next((k for k in rows if k.scope == KeyScope.CASE and k.owner_case_id == case_id), None)
    user_key = next(
        (k for k in rows if k.scope == KeyScope.USER and user_id and k.owner_user_id == user_id), None
    )
    return case_key or user_key


async def resolve_key(
    db: AsyncSession, case_id: uuid.UUID, service: str, user_id: uuid.UUID | None = None
) -> str | None:
    """Return a usable plaintext key (and bump last_used_at), or None to force graceful skip."""
    chosen = await _candidate_keys(db, case_id, service, user_id)
    if chosen is not None:
        plaintext = crypto.try_decrypt(chosen.encrypted_value)
        if plaintext:
            chosen.last_used_at = datetime.now(timezone.utc)
            return plaintext
    return settings.global_key_for(service)


async def has_usable_key(
    db: AsyncSession, case_id: uuid.UUID, service: str, user_id: uuid.UUID | None = None
) -> bool:
    """Presence check with no side effects (used to render module availability)."""
    chosen = await _candidate_keys(db, case_id, service, user_id)
    if chosen is not None and crypto.try_decrypt(chosen.encrypted_value):
        return True
    return bool(settings.global_key_for(service))


async def key_presence(
    db: AsyncSession, case_id: uuid.UUID, user_id: uuid.UUID | None = None
) -> dict[str, bool]:
    return {svc: await has_usable_key(db, case_id, svc, user_id) for svc in _SERVICES}
