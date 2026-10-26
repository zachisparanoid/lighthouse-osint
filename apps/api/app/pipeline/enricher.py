"""Attribute merging + conflict detection.

When two sources report the same attribute key with different values we keep BOTH —
the first value stays primary, the alternates are recorded under ``_conflicts`` with
their source, and the entity is flagged ``conflicting`` so the UI can surface it.
"""
from __future__ import annotations

from typing import Any

# Keys that are expected to differ across runs and should never be treated as conflicts.
_VOLATILE_KEYS = {"retrieved_at", "checked_at", "last_seen", "ttl", "response_time_ms"}


def merge_attributes(
    existing: dict[str, Any], incoming: dict[str, Any], *, source: str
) -> tuple[dict[str, Any], bool]:
    """Return (merged_attributes, has_conflict)."""
    merged = dict(existing or {})
    conflicts: dict[str, list[dict[str, Any]]] = dict(merged.get("_conflicts", {}))
    has_conflict = False

    for key, value in (incoming or {}).items():
        if key == "_conflicts" or value is None:
            continue
        if key not in merged:
            merged[key] = value
        elif merged[key] == value or key in _VOLATILE_KEYS:
            continue
        else:
            has_conflict = True
            entries = conflicts.setdefault(key, [])
            if not any(e.get("value") == value for e in entries):
                entries.append({"source": source, "value": value})

    if conflicts:
        merged["_conflicts"] = conflicts
    return merged, has_conflict
