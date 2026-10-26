"""Redis TTL cache for collector responses — so we don't re-hit a source we just
queried (good citizenship + speed). Keys are namespaced by collector + target.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import redis.asyncio as aioredis


def cache_key(collector: str, target_type: str, target_value: str, **params: Any) -> str:
    base = f"{collector}:{target_type}:{target_value.lower()}"
    if params:
        digest = hashlib.sha256(
            json.dumps(params, sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        base = f"{base}:{digest}"
    return base


async def cache_get(redis: aioredis.Redis, key: str) -> Any | None:
    raw = await redis.get(f"cache:{key}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def cache_set(redis: aioredis.Redis, key: str, value: Any, ttl_seconds: int) -> None:
    await redis.set(f"cache:{key}", json.dumps(value, default=str), ex=ttl_seconds)
