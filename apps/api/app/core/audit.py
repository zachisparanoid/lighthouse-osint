"""Append-only audit trail writer + a per-service circuit breaker.

The circuit breaker lives in Redis: after N consecutive failures a service is marked
'open' for a cooldown window, during which collectors short-circuit instead of
hammering a struggling/blocking source.
"""
from __future__ import annotations

import uuid
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: Any | None = None,
    case_id: uuid.UUID | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        case_id=case_id,
        ip=ip,
        user_agent=(user_agent or "")[:400] or None,
        meta=meta or {},
    )
    db.add(entry)
    await db.flush()
    return entry


# --------------------------------------------------------- circuit breaker ---
def _fail_key(service: str) -> str:
    return f"cb:fails:{service}"


def _open_key(service: str) -> str:
    return f"cb:open:{service}"


async def cb_is_open(redis: aioredis.Redis, service: str) -> bool:
    return bool(await redis.exists(_open_key(service)))


async def cb_record_failure(redis: aioredis.Redis, service: str) -> bool:
    """Increment failure count; trip the breaker if threshold reached. Returns is_open."""
    fails = await redis.incr(_fail_key(service))
    await redis.expire(_fail_key(service), settings.circuit_breaker_cooldown_seconds)
    if fails >= settings.circuit_breaker_threshold:
        await redis.set(_open_key(service), "1", ex=settings.circuit_breaker_cooldown_seconds)
        await redis.delete(_fail_key(service))
        return True
    return False


async def cb_record_success(redis: aioredis.Redis, service: str) -> None:
    await redis.delete(_fail_key(service))
