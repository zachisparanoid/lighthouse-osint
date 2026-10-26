"""Report generation + download.

Reports are rendered server-side and persisted to ``settings.reports_dir`` as
file artifacts (PDF via WeasyPrint, JSON, CSV; ``bundle`` produces all three).
Generation runs synchronously inside the POST request — acceptable for the
current scale — and is wrapped so a missing PDF engine (WeasyPrint absent) never
crashes the endpoint: json/csv are still written and the PDF is marked
unavailable in ``error``.

Every claim in a report cites its open-source provenance (collector, source URL,
retrieval timestamp); the renderer pulls Provenance rows for each included
entity/edge and renders a provenance appendix. This is a hard product
requirement, so the router always loads provenance, even for json/csv exports.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit import write_audit
from app.core.rbac import CaseContext, case_access, client_ip, user_agent
from app.db.models import Edge, Entity, Provenance, Report, ReportStatus
from app.db.session import get_db
from app.reports import renderer
from app.schemas.report import ReportCreate, ReportOut
from lighthouse_shared import Role

router = APIRouter()

# Download format -> (artifact key, media type).
_DOWNLOAD_MEDIA: dict[str, tuple[str, str]] = {
    "pdf": ("pdf", "application/pdf"),
    "json": ("json", "application/json"),
    "csv": ("csv", "text/csv"),
}


def _entity_to_dict(e: Entity) -> dict:
    """Plain-dict view of an Entity row (keeps the renderer DB-free)."""
    return {
        "id": str(e.id),
        "type": e.type,
        "value": e.value,
        "label": e.label,
        "attributes": e.attributes or {},
        "first_seen": e.first_seen,
        "last_seen": e.last_seen,
        "confidence": e.confidence,
        "source_count": e.source_count,
        "tags": list(e.tags or []),
        "conflicting": e.conflicting,
        "pinned": e.pinned,
    }


def _edge_to_dict(ed: Edge) -> dict:
    return {
        "id": str(ed.id),
        "source_entity_id": str(ed.source_entity_id),
        "target_entity_id": str(ed.target_entity_id),
        "relationship": ed.relationship,
        "confidence": ed.confidence,
        "attributes": ed.attributes or {},
    }


def _prov_to_dict(p: Provenance) -> dict:
    return {
        "id": str(p.id),
        "collector_name": p.collector_name,
        "source_url": p.source_url,
        "retrieved_at": p.retrieved_at,
        "license_note": p.license_note,
    }


async def _load_report_data(
    db: AsyncSession, case_id: uuid.UUID, payload: ReportCreate
) -> tuple[list[dict], list[dict], dict[str, list[dict]], dict[str, list[dict]]]:
    """Load entities (scoped/filtered), the edges among them, and provenance.

    Returns (entities, edges, provenance_by_entity, provenance_by_edge) — all as
    plain dicts keyed by string ids.
    """
    # ---- entities ----
    ent_stmt = (
        select(Entity)
        .where(Entity.case_id == case_id, Entity.deleted_at.is_(None))
        .where(Entity.confidence >= payload.min_confidence)
    )
    if payload.entity_ids:
        ent_stmt = ent_stmt.where(Entity.id.in_(payload.entity_ids))
    ent_stmt = ent_stmt.order_by(Entity.type, Entity.confidence.desc())
    entities = list((await db.execute(ent_stmt)).scalars().all())
    entity_ids = [e.id for e in entities]

    # ---- edges among the included entities (both endpoints in scope) ----
    edges: list[Edge] = []
    if entity_ids:
        edge_stmt = (
            select(Edge)
            .where(Edge.case_id == case_id, Edge.deleted_at.is_(None))
            .where(Edge.source_entity_id.in_(entity_ids))
            .where(Edge.target_entity_id.in_(entity_ids))
        )
        edges = list((await db.execute(edge_stmt)).scalars().all())
    edge_ids = [ed.id for ed in edges]

    # ---- provenance for those entities + edges ----
    prov_by_entity: dict[str, list[dict]] = {}
    prov_by_edge: dict[str, list[dict]] = {}
    if entity_ids:
        rows = (
            await db.execute(
                select(Provenance)
                .where(Provenance.entity_id.in_(entity_ids))
                .order_by(Provenance.retrieved_at.desc())
            )
        ).scalars().all()
        for p in rows:
            prov_by_entity.setdefault(str(p.entity_id), []).append(_prov_to_dict(p))
    if edge_ids:
        rows = (
            await db.execute(
                select(Provenance)
                .where(Provenance.edge_id.in_(edge_ids))
                .order_by(Provenance.retrieved_at.desc())
            )
        ).scalars().all()
        for p in rows:
            prov_by_edge.setdefault(str(p.edge_id), []).append(_prov_to_dict(p))

    return (
        [_entity_to_dict(e) for e in entities],
        [_edge_to_dict(ed) for ed in edges],
        prov_by_entity,
        prov_by_edge,
    )


@router.get("/cases/{case_id}/reports", response_model=list[ReportOut])
async def list_reports(
    ctx: CaseContext = Depends(case_access(Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> list[Report]:
    """All reports for the case, most recent first."""
    stmt = (
        select(Report)
        .where(Report.case_id == ctx.case.id)
        .order_by(Report.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.post("/cases/{case_id}/reports", response_model=ReportOut, status_code=201)
async def create_report(
    payload: ReportCreate,
    request: Request,
    ctx: CaseContext = Depends(case_access(Role.ANALYST)),
    db: AsyncSession = Depends(get_db),
) -> Report:
    """Generate a report synchronously and persist its artifacts.

    The Report row is created as ``pending`` and committed first so it is always
    persisted, then flipped to ``ready``/``failed`` after rendering.
    """
    report = Report(
        case_id=ctx.case.id,
        title=payload.title,
        config=payload.model_dump(mode="json"),
        format=payload.format,
        status=ReportStatus.PENDING,
    )
    db.add(report)
    await db.flush()

    # Load the graph slice + provenance, then render.
    entities, edges, prov_by_entity, prov_by_edge = await _load_report_data(
        db, ctx.case.id, payload
    )

    error: str | None = None
    artifacts: dict[str, str] = {}
    try:
        artifacts = renderer.write_artifacts(
            report_id=str(report.id),
            fmt=payload.format,
            case=ctx.case,
            entities=entities,
            edges=edges,
            provenance_by_entity=prov_by_entity,
            provenance_by_edge=prov_by_edge,
            sections=payload.sections,
            graph_snapshot_png=payload.graph_snapshot_png,
            out_dir=settings.reports_dir,
        )
        # A bundle may legitimately come back without a PDF if WeasyPrint is
        # absent — record that without failing the whole report.
        if payload.format in ("pdf", "bundle") and "pdf" not in artifacts:
            error = "PDF rendering unavailable (WeasyPrint not installed); other formats produced."
    except ImportError as exc:
        # pdf-only request with no PDF engine.
        error = f"PDF rendering unavailable: {exc}"
    except Exception as exc:  # noqa: BLE001 — any render failure marks the report failed.
        error = str(exc)

    if artifacts:
        report.status = ReportStatus.READY
        report.artifacts = artifacts
        # Primary artifact: prefer the PDF, else whichever was produced first.
        report.file_path = artifacts.get("pdf") or next(iter(artifacts.values()))
        report.generated_at = datetime.now(timezone.utc)
        report.generated_by = ctx.user.id
        if error:
            report.error = error
    else:
        report.status = ReportStatus.FAILED
        report.error = error or "Report generation produced no artifacts."

    await write_audit(
        db,
        action="report.generate",
        actor_id=ctx.user.id,
        target_type="report",
        target_id=report.id,
        case_id=ctx.case.id,
        ip=client_ip(request),
        user_agent=user_agent(request),
        meta={
            "format": payload.format,
            "status": report.status.value,
            "sections": list(payload.sections),
            "entity_count": len(entities),
            "edge_count": len(edges),
            "artifacts": list(artifacts.keys()),
        },
    )
    await db.commit()
    await db.refresh(report)
    return report


async def _get_case_report(db: AsyncSession, case_id: uuid.UUID, report_id: uuid.UUID) -> Report:
    report = await db.get(Report, report_id)
    if report is None or report.case_id != case_id:
        raise HTTPException(404, "Report not found")
    return report


@router.get("/cases/{case_id}/reports/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: uuid.UUID,
    ctx: CaseContext = Depends(case_access(Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> Report:
    """Fetch one report's metadata (404 if it is not in this case)."""
    return await _get_case_report(db, ctx.case.id, report_id)


@router.get("/cases/{case_id}/reports/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    format: str = Query("pdf", pattern="^(pdf|json|csv)$"),
    ctx: CaseContext = Depends(case_access(Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Stream a generated artifact for the requested format."""
    report = await _get_case_report(db, ctx.case.id, report_id)

    ext, media_type = _DOWNLOAD_MEDIA[format]
    path = (report.artifacts or {}).get(ext)
    if not path:
        raise HTTPException(404, f"No {format} artifact for this report")

    if not os.path.exists(path):
        raise HTTPException(404, f"{format} artifact file is missing on disk")

    filename = f"{ctx.case.slug}-report.{ext}"
    return FileResponse(path, media_type=media_type, filename=filename)
