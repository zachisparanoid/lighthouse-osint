"""Idempotent persistence with merge semantics.

Re-running a collector must NOT duplicate anything: entities/edges are upserted on their
natural keys, provenance is updated-in-place per (target, collector, source_url), and
``source_count`` reflects the number of *distinct* collectors that have cited a thing —
which is what the scorer turns into a corroboration boost.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import ProvenanceDraft
from app.db.models import Edge, Entity, Provenance
from app.pipeline.enricher import merge_attributes
from app.pipeline.normalizer import Normalized
from app.pipeline.scorer import score_edge, score_entity


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _distinct_source_count(
    db: AsyncSession, *, entity_id: uuid.UUID | None = None, edge_id: uuid.UUID | None = None
) -> int:
    col = Provenance.entity_id == entity_id if entity_id else Provenance.edge_id == edge_id
    count = (
        await db.execute(select(func.count(distinct(Provenance.collector_name))).where(col))
    ).scalar()
    return int(count or 1)


async def _upsert_provenance(
    db: AsyncSession,
    *,
    collector_name: str,
    prov: ProvenanceDraft,
    entity_id: uuid.UUID | None = None,
    edge_id: uuid.UUID | None = None,
) -> bool:
    """Add or refresh provenance. Returns True if this collector is a NEW source."""
    target_col = Provenance.entity_id == entity_id if entity_id else Provenance.edge_id == edge_id
    rows = (
        await db.execute(
            select(Provenance).where(target_col, Provenance.collector_name == collector_name)
        )
    ).scalars().all()
    is_new_source = len(rows) == 0

    match = next((p for p in rows if p.source_url == prov.source_url), None)
    if match is not None:
        match.retrieved_at = _now()
        if prov.raw_excerpt is not None:
            match.raw_excerpt = prov.raw_excerpt
        if prov.license_note:
            match.license_note = prov.license_note
    else:
        db.add(
            Provenance(
                entity_id=entity_id,
                edge_id=edge_id,
                collector_name=collector_name,
                source_url=prov.source_url,
                raw_excerpt=prov.raw_excerpt,
                retrieved_at=_now(),
                license_note=prov.license_note,
            )
        )
        await db.flush()
    return is_new_source


async def upsert_entity(
    db: AsyncSession,
    case_id: uuid.UUID,
    norm: Normalized,
    *,
    attributes: dict | None = None,
    tags: list[str] | None = None,
    first_seen: datetime | None = None,
    last_seen: datetime | None = None,
    base_confidence: int | None = None,
    base_reliability: int = 60,
    collector_name: str = "",
    depth: int = 0,
    provenance: ProvenanceDraft | None = None,
) -> tuple[Entity, bool]:
    existing = (
        await db.execute(
            select(Entity).where(
                Entity.case_id == case_id,
                Entity.type == norm.type,
                Entity.value == norm.value,
                Entity.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    created = existing is None
    seen = last_seen or _now()

    if created:
        entity = Entity(
            case_id=case_id,
            type=norm.type,
            value=norm.value,
            label=norm.label or norm.value,
            attributes={},
            tags=[],
            confidence=base_confidence or 0,
            source_count=0,
            first_seen=first_seen or seen,
            last_seen=seen,
        )
        db.add(entity)
        await db.flush()
    else:
        entity = existing
        if first_seen and (entity.first_seen is None or first_seen < entity.first_seen):
            entity.first_seen = first_seen
        if entity.last_seen is None or seen > entity.last_seen:
            entity.last_seen = seen

    merged, conflict = merge_attributes(entity.attributes or {}, attributes or {}, source=collector_name)
    entity.attributes = merged
    if conflict:
        entity.conflicting = True
    if tags:
        entity.tags = sorted(set(entity.tags or []) | set(tags))
    if norm.label and entity.label in (None, "", entity.value) and norm.label != entity.value:
        entity.label = norm.label

    if provenance is not None:
        await _upsert_provenance(db, collector_name=collector_name, prov=provenance, entity_id=entity.id)
        entity.source_count = await _distinct_source_count(db, entity_id=entity.id)
    entity.source_count = entity.source_count or 1

    fresh = score_entity(base_reliability, entity.source_count, depth)
    entity.confidence = fresh if created else max(entity.confidence or 0, fresh)
    return entity, created


async def upsert_edge(
    db: AsyncSession,
    case_id: uuid.UUID,
    source: Entity,
    target: Entity,
    relationship,
    *,
    attributes: dict | None = None,
    base_confidence: int | None = None,
    base_reliability: int = 60,
    collector_name: str = "",
    depth: int = 0,
    provenance: ProvenanceDraft | None = None,
) -> tuple[Edge, bool]:
    existing = (
        await db.execute(
            select(Edge).where(
                Edge.case_id == case_id,
                Edge.source_entity_id == source.id,
                Edge.target_entity_id == target.id,
                Edge.relationship == relationship,
                Edge.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    created = existing is None

    if created:
        edge = Edge(
            case_id=case_id,
            source_entity_id=source.id,
            target_entity_id=target.id,
            relationship=relationship,
            attributes=attributes or {},
            confidence=base_confidence or 0,
        )
        db.add(edge)
        await db.flush()
    else:
        edge = existing
        merged, _ = merge_attributes(edge.attributes or {}, attributes or {}, source=collector_name)
        edge.attributes = merged

    if provenance is not None:
        await _upsert_provenance(db, collector_name=collector_name, prov=provenance, edge_id=edge.id)

    source_count = await _distinct_source_count(db, edge_id=edge.id)
    fresh = score_edge(base_reliability, source_count, depth)
    edge.confidence = fresh if created else max(edge.confidence or 0, fresh)
    return edge, created
