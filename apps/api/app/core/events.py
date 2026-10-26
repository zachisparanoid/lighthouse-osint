"""WebSocket fan-out over Redis pub/sub.

Workers publish job/graph events to a per-case channel; the API's WebSocket endpoint
subscribes and relays them to connected analysts. This decouples the worker process
(where collection runs) from the API process (where sockets live).
"""
from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis


def case_channel(case_id: Any) -> str:
    return f"ws:case:{case_id}"


async def publish_event(redis: aioredis.Redis, case_id: Any, event: dict[str, Any]) -> None:
    # Delivery is best-effort: a dropped live update must never fail a collection job.
    try:
        await redis.publish(case_channel(case_id), json.dumps(event, default=str))
    except Exception:  # noqa: BLE001
        pass
