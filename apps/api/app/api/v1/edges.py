"""Manual edge management within a case.

Edges are cited like everything else in the graph: a manually asserted edge gets a
``manual`` Provenance row so the >=1-provenance invariant holds.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.rbac import (
    CaseContext,
    case_access,
    client_ip,
    user_agent,
)
from app.db.models import Edge, Entity, Provenance
from app.db.session import get_db
from app.schemas.common import MessageResponse
from app.schemas.entity import EdgeCreate, EdgeOut
from lighthouse_shared import Role

router = APIRouter()


@router.get("/cases/{case_id}/edges", response_model=list[EdgeOut])
async def list_edges(
    ctx: CaseContext = Depends(case_access(Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> list[Edge]:
    """List all live (non-deleted) edges for a case."""
    stmt = (
        select(Edge)
        .where(Edge.case_id == ctx.case.id, Edge.deleted_at.is_(None))
        .order_by(Edge.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.post("/cases/{case_id}/edges", response_model=EdgeOut, status_code=201)
async def create_edge(
    payload: EdgeCreate,
    request: Request,
    ctx: CaseContext = Depends(case_access(Role.ANALYST)),
    db: AsyncSession = Depends(get_db),
) -> Edge:
    """Manually create a cited edge between two existing entities in this case."""
    stmt = select(Entity).where(
        Entity.id.in_([payload.source_entity_id, payload.target_entity_id]),
        Entity.case_id == ctx.case.id,
        Entity.deleted_at.is_(None),
    )
    found = {e.id: e for e in (await db.execute(stmt)).scalars().all()}
    if payload.source_entity_id not in found:
        raise HTTPException(400, "Source entity not found in this case")
    if payload.target_entity_id not in found:
        raise HTTPException(400, "Target entity not found in this case")

    edge = Edge(
        case_id=ctx.case.id,
        source_entity_id=payload.source_entity_id,
        target_entity_id=payload.target_entity_id,
        relationship=payload.relationship,
        attributes=payload.attributes,
    )
    db.add(edge)
    await db.flush()

    # Every edge needs >= 1 provenance; a manual assertion records the analyst.
    db.add(
        Provenance(
            edge_id=edge.id,
            collector_name="manual",
            source_url=None,
            license_note="Manually asserted by analyst",
        )
    )

    await write_audit(
        db,
        action="edge.create",
        actor_id=ctx.user.id,
        target_type="edge",
        target_id=edge.id,
        case_id=ctx.case.id,
        ip=client_ip(request),
        user_agent=user_agent(request),
        meta={
            "relationship": payload.relationship.value,
            "source_entity_id": str(payload.source_entity_id),
            "target_entity_id": str(payload.target_entity_id),
        },
    )
    await db.commit()
    await db.refresh(edge)
    return edge


@router.delete("/cases/{case_id}/edges/{edge_id}", response_model=MessageResponse)
async def delete_edge(
    edge_id: uuid.UUID,
    request: Request,
    ctx: CaseContext = Depends(case_access(Role.ANALYST)),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Soft-delete an edge (sets deleted_at)."""
    edge = await db.get(Edge, edge_id)
    if edge is None or edge.deleted_at is not None or edge.case_id != ctx.case.id:
        raise HTTPException(404, "Edge not found")

    edge.deleted_at = datetime.now(timezone.utc)
    await write_audit(
        db,
        action="edge.delete",
        actor_id=ctx.user.id,
        target_type="edge",
        target_id=edge.id,
        case_id=ctx.case.id,
        ip=client_ip(request),
        user_agent=user_agent(request),
        meta={},
    )
    await db.commit()
    return MessageResponse(message="Edge deleted")
