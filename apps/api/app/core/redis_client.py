"""Async Redis clients.

Named ``redis_client`` (not ``redis``) so it doesn't shadow the ``redis`` package.
The API uses one long-lived client bound to its event loop; Celery tasks create a
fresh client per ``asyncio.run`` body (see ``make_redis``) to avoid cross-loop reuse.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

_app_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Long-lived client for the FastAPI app (and a FastAPI dependency)."""
    global _app_redis
    if _app_redis is None:
        _app_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _app_redis


def make_redis() -> aioredis.Redis:
    """A fresh client — use inside Celery task bodies (current event loop)."""
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    global _app_redis
    if _app_redis is not None:
        await _app_redis.aclose()
        _app_redis = None
