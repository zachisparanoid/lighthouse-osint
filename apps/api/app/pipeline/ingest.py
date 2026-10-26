"""Orchestrates a CollectorResult into the graph: normalize -> dedupe/persist -> score
-> enrich, then returns a compact delta (new/updated nodes + edges) for the live view.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.collectors.base import CollectionContext, CollectorResult, EntityRef, ProvenanceDraft
from app.db.models import Edge, Entity
from app.pipeline import deduper
from app.pipeline.normalizer import Normalized, normalize


def node_payload(e: Entity) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "type": e.type.value if hasattr(e.type, "value") else e.type,
        "value": e.value,
        "label": e.label,
        "confidence": e.confidence,
        "conflicting": e.conflicting,
        "tags": list(e.tags or []),
        "source_count": e.source_count,
    }


def edge_payload(e: Edge) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "source_entity_id": str(e.source_entity_id),
        "target_entity_id": str(e.target_entity_id),
        "relationship": e.relationship.value if hasattr(e.relationship, "value") else e.relationship,
        "confidence": e.confidence,
    }


async def _ensure_entity(
    ctx: CollectionContext,
    index: dict[tuple, Entity],
    norm: Normalized,
    collector_name: str,
    base_reliability: int,
    depth: int,
    provenance: ProvenanceDraft,
) -> Entity:
    key = (norm.type, norm.value)
    if key in index:
        return index[key]
    entity, _ = await deduper.upsert_entity(
        ctx.db,
        ctx.case_id,
        norm,
        collector_name=collector_name,
        base_reliability=base_reliability,
        depth=depth,
        provenance=provenance,
    )
    index[key] = entity
    return entity


async def ingest_result(
    ctx: CollectionContext,
    collector_name: str,
    base_reliability: int,
    target: EntityRef,
    result: CollectorResult,
    *,
    depth: int,
) -> dict[str, Any]:
    db = ctx.db
    index: dict[tuple, Entity] = {}

    # Index the seed/target so edges referencing it resolve to the existing node.
    if target.id is not None:
        target_entity = await db.get(Entity, target.id)
        if target_entity is not None:
            index[(target_entity.type, target_entity.value)] = target_entity

    new_entities: list[Entity] = []
    updated_entities: list[Entity] = []

    for draft in result.entities:
        norm = normalize(draft.type, draft.value)
        if not norm.value:
            continue
        entity, created = await deduper.upsert_entity(
            db,
            ctx.case_id,
            norm,
            attributes=draft.attributes,
            tags=draft.tags,
            first_seen=draft.first_seen,
            last_seen=draft.last_seen,
            base_confidence=draft.base_confidence,
            base_reliability=base_reliability,
            collector_name=collector_name,
            depth=depth,
            provenance=draft.provenance,
        )
        index[(norm.type, norm.value)] = entity
        (new_entities if created else updated_entities).append(entity)

    edges_changed: list[Edge] = []
    for ed in result.edges:
        s_norm = normalize(*ed.src)
        d_norm = normalize(*ed.dst)
        if not s_norm.value or not d_norm.value:
            continue
        s_ent = await _ensure_entity(ctx, index, s_norm, collector_name, base_reliability, depth, ed.provenance)
        d_ent = await _ensure_entity(ctx, index, d_norm, collector_name, base_reliability, depth, ed.provenance)
        if s_ent.id == d_ent.id:
            continue  # no self-loops
        edge, _created = await deduper.upsert_edge(
            db,
            ctx.case_id,
            s_ent,
            d_ent,
            ed.relationship,
            attributes=ed.attributes,
            base_confidence=ed.base_confidence,
            base_reliability=base_reliability,
            collector_name=collector_name,
            depth=depth,
            provenance=ed.provenance,
        )
        edges_changed.append(edge)

    await db.flush()

    return {
        "new_entities": [node_payload(e) for e in new_entities],
        "updated_entities": [node_payload(e) for e in updated_entities],
        "edges": [edge_payload(e) for e in edges_changed],
        "counts": {
            "new_entities": len(new_entities),
            "updated_entities": len(updated_entities),
            "edges": len(edges_changed),
        },
    }
