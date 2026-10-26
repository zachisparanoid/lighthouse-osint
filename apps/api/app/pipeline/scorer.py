"""Confidence scoring (0-100).

Three forces, exactly as specified:
  * a per-collector base reliability (how much we trust this source),
  * a corroboration boost when independent sources agree (more provenance => higher),
  * a decay with graph distance from the seed (things found 2 hops out are softer).
"""
from __future__ import annotations

CORROBORATION_STEP = 8       # points per *additional* independent source
CORROBORATION_CAP = 25       # max corroboration bonus
MIN_DECAY = 0.4              # never decay below 40% of base


def clamp(value: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(value))))


def distance_decay(depth: int) -> float:
    """1.0 at the seed, falling 15% per hop, floored at MIN_DECAY."""
    return max(MIN_DECAY, 1.0 - 0.15 * max(0, depth))


def _corroboration(source_count: int) -> float:
    return min(CORROBORATION_CAP, CORROBORATION_STEP * max(0, source_count - 1))


def score_entity(base_reliability: int, source_count: int, depth: int) -> int:
    return clamp(base_reliability * distance_decay(depth) + _corroboration(source_count))


def score_edge(base_reliability: int, source_count: int, depth: int) -> int:
    # Edges (asserted relationships) are slightly more conservative than entities.
    return clamp((base_reliability - 5) * distance_decay(depth) + _corroboration(source_count))
