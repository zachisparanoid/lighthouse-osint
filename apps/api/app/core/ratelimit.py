"""Distributed token-bucket rate limiting backed by Redis.

The check-and-decrement happens inside a single Lua script so it is atomic across
every API process and Celery worker — we never accidentally over-spend a source's
budget because two workers raced on the same counter.
"""
from __future__ import annotations

import re
import time

import redis.asyncio as aioredis

# tokens: current fill; ts: last refill time. Refills continuously at `rate`/sec.
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then tokens = capacity; ts = now end
local delta = math.max(0, now - ts)
tokens = math.min(capacity, tokens + (delta * rate))
local allowed = 0
local retry = 0.0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
else
  retry = (requested - tokens) / rate
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, math.ceil((capacity / rate) * 1000) + 2000)
return {allowed, tostring(retry)}
"""

_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*/\s*(\d+)?\s*([smh])\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}


def parse_rate(spec: str) -> tuple[float, float]:
    """Parse '10/m', '5/s', '1/2s' -> (tokens_per_second, burst_capacity).

    Burst capacity defaults to the numerator (e.g. '10/m' allows a burst of 10 then
    refills at 10/60 per second).
    """
    m = _RATE_RE.match(spec or "")
    if not m:
        return 1.0, 1.0
    count = float(m.group(1))
    mult = int(m.group(2)) if m.group(2) else 1
    seconds = _UNIT_SECONDS[m.group(3).lower()] * mult
    rate = count / seconds
    capacity = max(count, 1.0)
    return rate, capacity


async def consume(
    redis: aioredis.Redis, bucket: str, *, rate: float, capacity: float, tokens: int = 1
) -> tuple[bool, float]:
    """Try to take ``tokens`` from ``bucket``. Returns (allowed, retry_after_seconds)."""
    now = time.time()
    res = await redis.eval(
        _TOKEN_BUCKET_LUA, 1, f"ratelimit:{bucket}", rate, capacity, now, tokens
    )
    allowed = bool(int(res[0]))
    retry_after = float(res[1])
    return allowed, retry_after


async def consume_spec(
    redis: aioredis.Redis, bucket: str, spec: str, *, tokens: int = 1
) -> tuple[bool, float]:
    rate, capacity = parse_rate(spec)
    return await consume(redis, bucket, rate=rate, capacity=capacity, tokens=tokens)
