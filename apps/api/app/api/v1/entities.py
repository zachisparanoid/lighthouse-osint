"""Entities + the graph endpoint + global full-text search.

Search uses the Postgres ``tsv`` generated column (websearch_to_tsquery + ts_rank), with
an ILIKE fallback for short/partial queries.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import ProvenanceDraft
from app.collectors.registry import free_collectors_for, get_collector
from app.config import settings
from app.core.audit import write_audit
from app.core.rbac import CaseContext, case_access
from app.api.v1.jobs import enqueue_autoexpand, enqueue_collector
from app.db.models import Edge, Entity, Provenance
from app.db.session import get_db
from app.pipeline import deduper
from app.pipeline.normalizer import normalize
from app.schemas.common import Page
from app.schemas.entity import (
    BulkAction,
    EdgeOut,
    EntityCreate,
    EntityDetail,
    EntityOut,
    EntityUpdate,
    GraphResponse,
    ProvenanceOut,
)
from lighthouse_shared import EntityType, Role

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/cases/{case_id}/entities", response_model=Page[EntityOut])
async def list_entities(
    q: str | None = None,
    type: EntityType | None = None,
    tag: str | None = None,
    min_confidence: int = Query(default=0, ge=0, le=100),
    conflicting: bool | None = None,
    sort: str = "confidence",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: CaseContext = Depends(case_access(Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> Page[EntityOut]:
    base = select(Entity).where(Entity.case_id == ctx.case.id, Entity.deleted_at.is_(None))
    if type is not None:
        base = base.where(Entity.type == type)
    if tag:
        base = base.where(Entity.tags.any(tag))
    if min_confidence:
        base = base.where(Entity.confidence >= min_confidence)
    if conflicting is not None:
        base = base.where(Entity.conflicting == conflicting)

    if q and q.strip():
        tsq = func.websearch_to_tsquery("english", q)
        base = base.where(Entity.tsv.op("@@")(tsq))
        order = func.ts_rank(Entity.tsv, tsq).desc()
    else:
        order = {
            "confidence": Entity.confidence.desc(),
            "recent": Entity.last_seen.desc().nullslast(),
            "value": Entity.value.asc(),
        }.get(sort, Entity.confidence.desc())

    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(order).limit(limit).offset(offset))).scalars().all()
    return Page(items=[EntityOut.model_validate(e) for e in rows], total=int(total or 0), limit=limit, offset=offset)


@router.get("/cases/{case_id}/search", response_model=list[EntityOut])
async def search(
    q: str, limit: int = Query(default=20, ge=1, le=100),
    ctx: CaseContext = Depends(case_access(Role.VIEWER)), db: AsyncSession = Depends(get_db),
) -> list[EntityOut]:
    if not q.strip():
        return []
    tsq = func.websearch_to_tsquery("english", q)
    stmt = (select(Entity).where(
        Entity.case_id == ctx.case.id, Entity.deleted_at.is_(None), Entity.tsv.op("@@")(tsq))
        .order_by(func.ts_rank(Entity.tsv, tsq).desc()).limit(limit))
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:  # fallback for partial/short queries that FTS won't match
        like = f"%{q.strip()}%"
        rows = (await db.execute(
            select(Entity).where(
                Entity.case_id == ctx.case.id, Entity.deleted_at.is_(None),
                Entity.value.ilike(like) | Entity.label.ilike(like)).limit(limit)
        )).scalars().all()
    return [EntityOut.model_validate(e) for e in rows]


@router.get("/cases/{case_id}/graph", response_model=GraphResponse)
async def graph(
    min_confidence: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=1500, ge=1, le=5000),
    ctx: CaseContext = Depends(case_access(Role.VIEWER)), db: AsyncSession = Depends(get_db),
) -> GraphResponse:
    ent_rows = (await db.execute(
        select(Entity).where(
            Entity.case_id == ctx.case.id, Entity.deleted_at.is_(None), Entity.confidence >= min_confidence)
        .order_by(Entity.confidence.desc()).limit(limit)
    )).scalars().all()
    ids = {e.id for e in ent_rows}
    edge_rows = (await db.execute(
        select(Edge).where(Edge.case_id == ctx.case.id, Edge.deleted_at.is_(None))
    )).scalars().all()
    edges = [e for e in edge_rows if e.source_entity_id in ids and e.target_entity_id in ids]
    return GraphResponse(
        entities=[EntityOut.model_validate(e) for e in ent_rows],
        edges=[EdgeOut.model_validate(e) for e in edges],
        layout=ctx.case.graph_layout or {},
    )


@router.get("/cases/{case_id}/entities/{entity_id}", response_model=EntityDetail)
async def get_entity(
    entity_id: uuid.UUID, ctx: CaseContext = Depends(case_access(Role.VIEWER)), db: AsyncSession = Depends(get_db)
) -> EntityDetail:
    e = await db.get(Entity, entity_id)
    if e is None or e.case_id != ctx.case.id or e.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found.")
    provs = (await db.execute(
        select(Provenance).where(Provenance.entity_id == e.id).order_by(Provenance.retrieved_at.desc())
    )).scalars().all()
    detail = EntityDetail.model_validate(e)
    detail.provenances = [ProvenanceOut.model_validate(p) for p in provs]
    return detail


@router.post("/cases/{case_id}/entities", response_model=EntityOut, status_code=201)
async def create_seed(
    payload: EntityCreate, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> EntityOut:
    norm = normalize(payload.type, payload.value)
    if not norm.value:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Could not normalize that selector.")
    entity, _created = await deduper.upsert_entity(
        db, ctx.case.id, norm, attributes={}, tags=payload.tags, base_reliability=95,
        collector_name="manual", depth=0,
        provenance=ProvenanceDraft(source_url=None, license_note="Seed entered by analyst."),
    )
    if payload.label:
        entity.label = payload.label
    await db.flush()

    if payload.autoexpand:
        await enqueue_autoexpand(db, ctx.case.id, entity.id, ctx.user.id,
                                 depth=settings.default_autoexpand_depth, budget=settings.default_node_budget, disabled=[])
    elif payload.run_collectors:
        for collector in free_collectors_for(entity.type):
            await enqueue_collector(db, ctx.case.id, collector.name, entity.id, ctx.user.id)

    await write_audit(db, action="entity.create", actor_id=ctx.user.id, target_type="entity",
                      target_id=entity.id, case_id=ctx.case.id, meta={"type": norm.type.value, "value": norm.value})
    await db.commit()
    return EntityOut.model_validate(entity)


@router.patch("/cases/{case_id}/entities/{entity_id}", response_model=EntityOut)
async def update_entity(
    entity_id: uuid.UUID, payload: EntityUpdate,
    ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db),
) -> EntityOut:
    e = await db.get(Entity, entity_id)
    if e is None or e.case_id != ctx.case.id or e.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found.")
    if payload.label is not None:
        e.label = payload.label
    if payload.tags is not None:
        e.tags = sorted(set(payload.tags))
    if payload.pinned is not None:
        e.pinned = payload.pinned
    await db.commit()
    return EntityOut.model_validate(e)


@router.delete("/cases/{case_id}/entities/{entity_id}", response_model=dict)
async def delete_entity(
    entity_id: uuid.UUID, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> dict:
    e = await db.get(Entity, entity_id)
    if e is None or e.case_id != ctx.case.id or e.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found.")
    e.deleted_at = _now()
    # Soft-delete incident edges so the graph stays consistent.
    incident = (await db.execute(
        select(Edge).where(
            Edge.case_id == ctx.case.id, Edge.deleted_at.is_(None),
            (Edge.source_entity_id == e.id) | (Edge.target_entity_id == e.id))
    )).scalars().all()
    for edge in incident:
        edge.deleted_at = _now()
    await write_audit(db, action="entity.delete", actor_id=ctx.user.id, target_type="entity",
                      target_id=e.id, case_id=ctx.case.id)
    await db.commit()
    return {"deleted": True, "edges_removed": len(incident)}


@router.post("/cases/{case_id}/entities/bulk", response_model=dict)
async def bulk_action(
    payload: BulkAction, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> dict:
    rows = (await db.execute(
        select(Entity).where(
            Entity.case_id == ctx.case.id, Entity.id.in_(payload.entity_ids), Entity.deleted_at.is_(None))
    )).scalars().all()
    affected = 0
    jobs = 0
    if payload.action == "delete":
        for e in rows:
            e.deleted_at = _now()
            affected += 1
    elif payload.action in ("tag", "untag"):
        if not payload.tag:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A tag is required.")
        for e in rows:
            tags = set(e.tags or [])
            tags.add(payload.tag) if payload.action == "tag" else tags.discard(payload.tag)
            e.tags = sorted(tags)
            affected += 1
    elif payload.action in ("pin", "unpin"):
        for e in rows:
            e.pinned = payload.action == "pin"
            affected += 1
    elif payload.action == "run":
        collector = get_collector(payload.collector_name or "")
        if collector is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown collector.")
        for e in rows:
            if e.type in collector.accepts:
                await enqueue_collector(db, ctx.case.id, collector.name, e.id, ctx.user.id)
                jobs += 1
    await write_audit(db, action="entity.bulk", actor_id=ctx.user.id, case_id=ctx.case.id,
                      meta={"action": payload.action, "count": affected, "jobs": jobs})
    await db.commit()
    return {"affected": affected, "jobs_enqueued": jobs}
