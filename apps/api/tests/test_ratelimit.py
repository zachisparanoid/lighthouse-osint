"""Token-bucket rate limiting: rate-spec parsing + atomic consume.

The bucket logic runs as a single Redis Lua script (EVAL) so the check-and-decrement is
atomic across processes. fakeredis cannot execute Lua without the optional ``lupa``
backend, so the consume test runs against the real localhost Redis with a unique,
self-cleaned bucket key. ``parse_rate`` is a pure function and needs no Redis.
"""
from __future__ import annotations

import uuid

import pytest
import redis.asyncio as aioredis

from app.core.ratelimit import consume_spec, parse_rate

REDIS_URL = "redis://localhost:6379/0"


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("10/m", (10 / 60, 10)),
        ("5/s", (5, 5)),
        ("1/2s", (0.5, 1)),
    ],
)
def test_parse_rate(spec: str, expected: tuple[float, float]) -> None:
    rate, capacity = parse_rate(spec)
    assert rate == pytest.approx(expected[0])
    assert capacity == pytest.approx(expected[1])


async def test_consume_spec_capacity_two() -> None:
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    bucket = f"svc-{uuid.uuid4().hex}"
    try:
        # "2/s" -> burst capacity of 2: first two requests succeed immediately.
        allowed1, _ = await consume_spec(r, bucket, "2/s")
        allowed2, _ = await consume_spec(r, bucket, "2/s")
        assert allowed1 is True
        assert allowed2 is True

        # Third request within the same instant exceeds capacity -> denied, with a wait.
        allowed3, retry_after = await consume_spec(r, bucket, "2/s")
        assert allowed3 is False
        assert retry_after > 0
    finally:
        await r.delete(f"ratelimit:{bucket}")
        await r.aclose()
