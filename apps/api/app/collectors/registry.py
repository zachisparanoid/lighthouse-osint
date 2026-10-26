"""Collector auto-discovery + capability metadata.

Walks the ``app.collectors`` package, instantiates every concrete ``Collector`` subclass,
and indexes it by ``name``. The API exposes ``capabilities()`` so the frontend renders the
available modules (and "add key to enable" states) dynamically — no hard-coded UI list.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any

from app.collectors.base import Collector

_registry: dict[str, Collector] = {}
_discovered = False
_SKIP = {"base", "registry"}


def _discover(force: bool = False) -> None:
    global _discovered
    if _discovered and not force:
        return
    _registry.clear()
    import app.collectors as pkg

    for modinfo in pkgutil.iter_modules(pkg.__path__):
        if modinfo.name in _SKIP or modinfo.name.startswith("_"):
            continue
        module = importlib.import_module(f"app.collectors.{modinfo.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, Collector) or obj is Collector:
                continue
            if inspect.isabstract(obj) or obj.__module__ != module.__name__:
                continue
            try:
                instance = obj()
            except Exception:  # noqa: BLE001 — a broken collector must not break discovery
                continue
            if instance.name:
                _registry[instance.name] = instance
    _discovered = True


def all_collectors() -> list[Collector]:
    _discover()
    return sorted(_registry.values(), key=lambda c: c.name)


def get_collector(name: str) -> Collector | None:
    _discover()
    return _registry.get(name)


def collectors_for(entity_type: Any) -> list[Collector]:
    """Collectors whose ``accepts`` includes this entity type."""
    _discover()
    return [c for c in all_collectors() if entity_type in c.accepts]


def free_collectors_for(entity_type: Any) -> list[Collector]:
    return [c for c in collectors_for(entity_type) if c.requires_key is None]


def capabilities(key_presence: dict[str, bool], disabled: set[str]) -> list[dict[str, Any]]:
    """Build the CollectorInfo list for the UI.

    ``key_presence`` maps a service value ("shodan") -> whether a usable key exists.
    A collector is ``enabled`` when it's not disabled AND (free OR its key is present).
    """
    _discover()
    out: list[dict[str, Any]] = []
    for c in all_collectors():
        key_present = True if c.requires_key is None else bool(key_presence.get(c.requires_key.value, False))
        enabled = (c.name not in disabled) and key_present
        out.append(c.info(key_present=key_present, enabled=enabled))
    return out
