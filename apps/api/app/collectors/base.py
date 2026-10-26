"""Collector contract: the ABC, the data drafts collectors emit, the runtime context
they receive, and the ScopeGuard that keeps collection lawful and public-only.

Design: a Collector is (close to) a pure function. It receives a target and a context,
makes outbound requests, and returns a ``CollectorResult`` of *drafts* expressed purely
as ``(type, value)`` tuples + attributes + provenance. It never persists, dedupes, or
scores — the pipeline does that. This is what makes collectors testable with only
``respx`` and plain assertions.
"""
from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from lighthouse_shared import (
    CollectorCost,
    EntityType,
    JobStatus,
    KeyService,
    RelationshipType,
)

if TYPE_CHECKING:  # avoid heavy imports at module load / in tests
    import uuid

    import httpx
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings


# --------------------------------------------------------------------- drafts ---
@dataclass
class ProvenanceDraft:
    source_url: str | None = None
    raw_excerpt: dict[str, Any] | None = None
    license_note: str | None = None


@dataclass
class EntityDraft:
    type: EntityType
    value: str
    label: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    # Collector's confidence in THIS specific finding (0-100); falls back to base_reliability.
    base_confidence: int | None = None
    provenance: ProvenanceDraft = field(default_factory=ProvenanceDraft)


@dataclass
class EdgeDraft:
    src: tuple[EntityType, str]
    dst: tuple[EntityType, str]
    relationship: RelationshipType
    attributes: dict[str, Any] = field(default_factory=dict)
    base_confidence: int | None = None
    provenance: ProvenanceDraft = field(default_factory=ProvenanceDraft)


@dataclass
class CollectorResult:
    status: JobStatus = JobStatus.SUCCEEDED
    message: str = ""
    entities: list[EntityDraft] = field(default_factory=list)
    edges: list[EdgeDraft] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    retry_after: float | None = None

    # ---- ergonomic builders so collectors read cleanly ----
    def add_entity(
        self,
        type: EntityType,
        value: str,
        *,
        label: str | None = None,
        attributes: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        first_seen: datetime | None = None,
        last_seen: datetime | None = None,
        base_confidence: int | None = None,
        source_url: str | None = None,
        raw_excerpt: dict[str, Any] | None = None,
        license_note: str | None = None,
    ) -> EntityDraft:
        draft = EntityDraft(
            type=type,
            value=value,
            label=label,
            attributes=attributes or {},
            tags=tags or [],
            first_seen=first_seen,
            last_seen=last_seen,
            base_confidence=base_confidence,
            provenance=ProvenanceDraft(source_url=source_url, raw_excerpt=raw_excerpt, license_note=license_note),
        )
        self.entities.append(draft)
        return draft

    def add_edge(
        self,
        src: tuple[EntityType, str],
        dst: tuple[EntityType, str],
        relationship: RelationshipType,
        *,
        attributes: dict[str, Any] | None = None,
        base_confidence: int | None = None,
        source_url: str | None = None,
        raw_excerpt: dict[str, Any] | None = None,
        license_note: str | None = None,
    ) -> EdgeDraft:
        draft = EdgeDraft(
            src=src,
            dst=dst,
            relationship=relationship,
            attributes=attributes or {},
            base_confidence=base_confidence,
            provenance=ProvenanceDraft(source_url=source_url, raw_excerpt=raw_excerpt, license_note=license_note),
        )
        self.edges.append(draft)
        return draft

    @classmethod
    def skipped(cls, message: str) -> CollectorResult:
        return cls(status=JobStatus.SKIPPED, message=message)

    @classmethod
    def failed(cls, message: str, *, retry_after: float | None = None) -> CollectorResult:
        return cls(status=JobStatus.FAILED, message=message, retry_after=retry_after)


# ------------------------------------------------------------------- context ---
@dataclass
class EntityRef:
    """The seed/target an enabled collector operates on."""

    type: EntityType
    value: str
    attributes: dict[str, Any] = field(default_factory=dict)
    id: "uuid.UUID | None" = None


@dataclass
class CollectionContext:
    db: "AsyncSession"
    redis: "aioredis.Redis"
    http: "httpx.AsyncClient"
    case_id: "uuid.UUID"
    settings: "Settings"
    scope: "ScopeGuard"
    # Resolve a BYOK key for a service (case key -> user key -> env fallback), or None.
    get_key: Callable[[str], Awaitable[str | None]]
    # Report incremental progress (0-100) for the live job view.
    progress: Callable[[int, str], Awaitable[None]]

    async def report(self, pct: int, message: str = "") -> None:
        await self.progress(pct, message)


# ----------------------------------------------------------------- ScopeGuard ---
class ScopeViolation(Exception):
    """Raised when a target/host is out of ethical/legal scope."""


class ScopeGuard:
    """Refuses non-public / disallowed targets.

    Rules:
      * Private, loopback, link-local, reserved, multicast IPs are always blocked
        (no internal-network scanning / SSRF).
      * Hosts matching the configured denylist (exact, ``*.suffix`` wildcards, or CIDR
        for IPs) are refused — defaults include ``*.gov`` / ``*.mil`` / localhost.
    """

    def __init__(self, denylist: list[str] | None = None) -> None:
        self.denylist = [d.strip().lower() for d in (denylist or []) if d.strip()]

    # ---- IPs ----
    def is_ip_allowed(self, value: str) -> bool:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return True  # not an IP literal; host rules apply instead
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
        for entry in self.denylist:
            if "/" in entry:
                try:
                    if ip in ipaddress.ip_network(entry, strict=False):
                        return False
                except ValueError:
                    continue
        return True

    # ---- hostnames ----
    def is_host_allowed(self, host: str) -> bool:
        host = (host or "").lower().strip().rstrip(".")
        if not host:
            return False
        if not self.is_ip_allowed(host):  # host may be an IP literal
            return False
        for pat in self.denylist:
            if "/" in pat:
                continue
            if pat == host:
                return False
            if pat.startswith("*.") and (host == pat[2:] or host.endswith(pat[1:])):
                return False
        return True

    @staticmethod
    def host_of(value: str) -> str:
        if "://" in value:
            return (urlparse(value).hostname or "").lower()
        return value.split("/")[0].split(":")[0].lower()

    def check_target(self, entity_type: EntityType, value: str) -> None:
        """Raise ScopeViolation if this target may not be collected on."""
        if entity_type == EntityType.IP:
            if not self.is_ip_allowed(value):
                raise ScopeViolation(f"IP {value} is private/reserved or denylisted — out of scope.")
            return
        if entity_type in {EntityType.DOMAIN, EntityType.SUBDOMAIN, EntityType.URL, EntityType.CERTIFICATE}:
            host = self.host_of(value)
            if host and not self.is_host_allowed(host):
                raise ScopeViolation(f"Host {host} is denylisted or non-public — out of scope.")
        # email/username/phone/person/org/etc.: host-based rules don't apply.

    def assert_url_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ScopeViolation(f"Refusing non-HTTP(S) scheme: {parsed.scheme!r}")
        host = (parsed.hostname or "").lower()
        if not self.is_host_allowed(host):
            raise ScopeViolation(f"Refusing request to out-of-scope host {host!r}")


# ------------------------------------------------------------------- ABC ---
class Collector(ABC):
    """Base class. Subclass and set the class attributes + implement ``run``."""

    name: str = ""
    title: str = ""
    description: str = ""
    accepts: set[EntityType] = set()
    produces: set[EntityType] = set()
    requires_key: KeyService | None = None
    cost: CollectorCost = CollectorCost.FREE
    rate_limit: str = "60/m"  # token-bucket spec, e.g. "10/m", "5/s"
    cache_ttl: int = 3600  # seconds
    base_reliability: int = 60  # 0-100, seeds the confidence scorer
    source_note: str = "Uses only publicly accessible data / official APIs."

    @abstractmethod
    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:  # pragma: no cover
        ...

    def info(self, *, key_present: bool, enabled: bool) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title or self.name,
            "description": self.description,
            "accepts": sorted(t.value for t in self.accepts),
            "produces": sorted(t.value for t in self.produces),
            "cost": self.cost.value,
            "requires_key": self.requires_key.value if self.requires_key else None,
            "key_present": key_present,
            "enabled": enabled,
            "rate_limit": self.rate_limit,
            "source_note": self.source_note,
        }
