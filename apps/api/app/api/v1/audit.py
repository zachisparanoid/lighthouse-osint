"""Audit log browsing + CSV export (admin only).

The append-only audit trail is filterable and exportable so admins can review who did
what, when, and from where.
"""
from __future__ import annotations

import csv
import io
import json
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_admin
from app.db.models import AuditLog, User
from app.db.session import get_db
from app.schemas.audit import AuditOut
from app.schemas.common import Page

router = APIRouter()

_EXPORT_CAP = 10_000


def _apply_filters(
    stmt,
    *,
    action: str | None,
    actor_id: uuid.UUID | None,
    case_id: uuid.UUID | None,
    q: str | None,
):
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if case_id is not None:
        stmt = stmt.where(AuditLog.case_id == case_id)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(AuditLog.target_id.ilike(pattern), AuditLog.action.ilike(pattern))
        )
    return stmt


@router.get("/audit", response_model=Page[AuditOut])
async def list_audit(
    action: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    case_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Page[AuditOut]:
    """Paginated, filterable audit entries, newest first."""
    base = _apply_filters(
        select(AuditLog), action=action, actor_id=actor_id, case_id=case_id, q=q
    )

    total = (
        await db.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    return Page[AuditOut](
        items=[AuditOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/export")
async def export_audit(
    action: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    case_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None),
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream filtered audit entries as CSV (capped at 10k rows)."""
    base = _apply_filters(
        select(AuditLog), action=action, actor_id=actor_id, case_id=case_id, q=q
    )
    rows = (
        await db.execute(
            base.order_by(AuditLog.created_at.desc()).limit(_EXPORT_CAP)
        )
    ).scalars().all()

    columns = [
        "created_at",
        "actor_id",
        "action",
        "target_type",
        "target_id",
        "case_id",
        "ip",
        "user_agent",
        "meta",
    ]

    def _generate():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(columns)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for r in rows:
            writer.writerow(
                [
                    r.created_at.isoformat() if r.created_at else "",
                    str(r.actor_id) if r.actor_id else "",
                    r.action,
                    r.target_type or "",
                    r.target_id or "",
                    str(r.case_id) if r.case_id else "",
                    r.ip or "",
                    r.user_agent or "",
                    json.dumps(r.meta or {}),
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-export.csv"},
    )
