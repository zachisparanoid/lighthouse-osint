"""Cases (investigations): the acknowledgment gate on creation, membership, saved graph
layout, re-scan schedule, and case/entity notes.
"""
from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.rbac import CaseContext, case_access, client_ip, get_current_user, user_agent
from app.core.redis_client import get_redis
from app.db.models import Case, CaseMember, Edge, Entity, Note, User
from app.db.session import get_db
from app.schemas.case import (
    CaseCreate,
    CaseMemberAdd,
    CaseMemberOut,
    CaseOut,
    CaseSummary,
    CaseUpdate,
    GraphLayoutUpdate,
    RescanConfig,
)
from app.schemas.common import MessageResponse
from app.schemas.entity import NoteCreate, NoteOut, NoteUpdate
from lighthouse_shared import CaseStatus, JobStatus, Role

router = APIRouter()
RESCAN_HASH = "rescan:schedules"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "case"
    return f"{base}-{secrets.token_hex(3)}"


async def _summary(db: AsyncSession, case: Case, role: Role | None) -> CaseSummary:
    from app.db.models import Job

    ec = await db.scalar(select(func.count()).select_from(Entity).where(
        Entity.case_id == case.id, Entity.deleted_at.is_(None)))
    gc = await db.scalar(select(func.count()).select_from(Edge).where(
        Edge.case_id == case.id, Edge.deleted_at.is_(None)))
    rj = await db.scalar(select(func.count()).select_from(Job).where(
        Job.case_id == case.id, Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING])))
    out = CaseSummary.model_validate(case)
    out.entity_count = int(ec or 0)
    out.edge_count = int(gc or 0)
    out.running_jobs = int(rj or 0)
    out.role = role
    return out


@router.get("/cases", response_model=list[CaseSummary])
async def list_cases(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)) -> list[CaseSummary]:
    if user.role == Role.ADMIN:
        cases = (await db.execute(
            select(Case).where(Case.deleted_at.is_(None)).order_by(Case.updated_at.desc())
        )).scalars().all()
        return [await _summary(db, c, Role.ADMIN) for c in cases]

    member_case_ids = (await db.execute(
        select(CaseMember.case_id).where(CaseMember.user_id == user.id)
    )).scalars().all()
    cases = (await db.execute(
        select(Case).where(
            Case.deleted_at.is_(None),
            (Case.owner_id == user.id) | (Case.id.in_(member_case_ids)),
        ).order_by(Case.updated_at.desc())
    )).scalars().all()
    out = []
    for c in cases:
        role = Role.ADMIN if c.owner_id == user.id else None
        if role is None:
            m = await db.get(CaseMember, {"case_id": c.id, "user_id": user.id})
            role = m.case_role if m else Role.VIEWER
        out.append(await _summary(db, c, role))
    return out


@router.post("/cases", response_model=CaseOut, status_code=201)
async def create_case(
    payload: CaseCreate, request: Request, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CaseOut:
    if user.role == Role.VIEWER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Viewers cannot create cases.")
    case = Case(
        name=payload.name,
        slug=_slugify(payload.name),
        description=payload.description,
        owner_id=user.id,
        created_by=user.id,
        legal_basis=payload.legal_basis,
        aup_accepted=True,
        aup_accepted_at=_now(),
        aup_version=payload.aup_version,
        status=CaseStatus.ACTIVE,
    )
    db.add(case)
    await db.flush()
    # The acknowledgment is recorded in the immutable audit log (DoD requirement).
    await write_audit(
        db, action="case.create", actor_id=user.id, target_type="case", target_id=case.id, case_id=case.id,
        ip=client_ip(request), user_agent=user_agent(request),
        meta={"aup_accepted": True, "aup_version": payload.aup_version, "legal_basis": payload.legal_basis},
    )
    await db.commit()
    return CaseOut.model_validate(case)


@router.get("/cases/{case_id}", response_model=CaseSummary)
async def get_case(ctx: CaseContext = Depends(case_access(Role.VIEWER)), db: AsyncSession = Depends(get_db)) -> CaseSummary:
    return await _summary(db, ctx.case, ctx.role)


@router.patch("/cases/{case_id}", response_model=CaseOut)
async def update_case(
    payload: CaseUpdate, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> CaseOut:
    case = ctx.case
    if payload.name is not None:
        case.name = payload.name
    if payload.description is not None:
        case.description = payload.description
    if payload.status is not None:
        case.status = payload.status
    if payload.legal_basis is not None:
        case.legal_basis = payload.legal_basis
    await write_audit(db, action="case.update", actor_id=ctx.user.id, target_type="case", target_id=case.id, case_id=case.id)
    await db.commit()
    return CaseOut.model_validate(case)


@router.delete("/cases/{case_id}", response_model=MessageResponse)
async def delete_case(
    ctx: CaseContext = Depends(case_access(Role.ADMIN)), db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    ctx.case.deleted_at = _now()
    await write_audit(db, action="case.delete", actor_id=ctx.user.id, target_type="case",
                      target_id=ctx.case.id, case_id=ctx.case.id)
    await db.commit()
    return MessageResponse(message="Case archived/deleted.")


# ------------------------------------------------------------------ members ---
@router.get("/cases/{case_id}/members", response_model=list[CaseMemberOut])
async def list_members(
    ctx: CaseContext = Depends(case_access(Role.VIEWER)), db: AsyncSession = Depends(get_db)
) -> list[CaseMemberOut]:
    rows = (await db.execute(
        select(CaseMember, User).join(User, User.id == CaseMember.user_id).where(CaseMember.case_id == ctx.case.id)
    )).all()
    out = [CaseMemberOut(user_id=m.user_id, email=u.email, case_role=m.case_role) for m, u in rows]
    owner = await db.get(User, ctx.case.owner_id)
    if owner is not None:
        out.insert(0, CaseMemberOut(user_id=owner.id, email=owner.email, case_role=Role.ADMIN))
    return out


@router.post("/cases/{case_id}/members", response_model=CaseMemberOut, status_code=201)
async def add_member(
    payload: CaseMemberAdd, ctx: CaseContext = Depends(case_access(Role.ADMIN)), db: AsyncSession = Depends(get_db)
) -> CaseMemberOut:
    target = await db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No user with that email.")
    if target.id == ctx.case.owner_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That user owns this case.")
    member = await db.get(CaseMember, {"case_id": ctx.case.id, "user_id": target.id})
    if member is None:
        member = CaseMember(case_id=ctx.case.id, user_id=target.id, case_role=payload.case_role)
        db.add(member)
    else:
        member.case_role = payload.case_role
    await write_audit(db, action="case.member_add", actor_id=ctx.user.id, target_type="user",
                      target_id=target.id, case_id=ctx.case.id, meta={"role": payload.case_role.value})
    await db.commit()
    return CaseMemberOut(user_id=target.id, email=target.email, case_role=payload.case_role)


@router.delete("/cases/{case_id}/members/{user_id}", response_model=MessageResponse)
async def remove_member(
    user_id: uuid.UUID, ctx: CaseContext = Depends(case_access(Role.ADMIN)), db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    member = await db.get(CaseMember, {"case_id": ctx.case.id, "user_id": user_id})
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not a member.")
    await db.delete(member)
    await write_audit(db, action="case.member_remove", actor_id=ctx.user.id, target_type="user",
                      target_id=user_id, case_id=ctx.case.id)
    await db.commit()
    return MessageResponse(message="Member removed.")


# ------------------------------------------------------------- graph layout ---
@router.put("/cases/{case_id}/graph-layout", response_model=MessageResponse)
async def save_layout(
    payload: GraphLayoutUpdate, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    ctx.case.graph_layout = payload.layout
    await db.commit()
    return MessageResponse(message="Layout saved.")


# ----------------------------------------------------------------- re-scan ---
@router.get("/cases/{case_id}/rescan", response_model=RescanConfig)
async def get_rescan(ctx: CaseContext = Depends(case_access(Role.VIEWER))) -> RescanConfig:
    raw = await get_redis().hget(RESCAN_HASH, str(ctx.case.id))
    if not raw:
        return RescanConfig(enabled=False)
    data = json.loads(raw)
    return RescanConfig(
        enabled=True, interval_hours=data.get("interval_hours", 24),
        seed_entity_id=data.get("seed_entity_id"), depth=data.get("depth", 2), budget=data.get("budget", 250),
    )


@router.put("/cases/{case_id}/rescan", response_model=RescanConfig)
async def set_rescan(
    payload: RescanConfig, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> RescanConfig:
    redis = get_redis()
    if payload.enabled and payload.seed_entity_id:
        await redis.hset(RESCAN_HASH, str(ctx.case.id), json.dumps({
            "interval_hours": payload.interval_hours, "seed_entity_id": str(payload.seed_entity_id),
            "depth": payload.depth, "budget": payload.budget, "last_run": 0,
        }))
    else:
        await redis.hdel(RESCAN_HASH, str(ctx.case.id))
    await write_audit(db, action="case.rescan_config", actor_id=ctx.user.id, case_id=ctx.case.id,
                      meta={"enabled": payload.enabled, "interval_hours": payload.interval_hours})
    await db.commit()
    return payload


# ------------------------------------------------------------------- notes ---
@router.get("/cases/{case_id}/notes", response_model=list[NoteOut])
async def list_notes(
    entity_id: uuid.UUID | None = None, ctx: CaseContext = Depends(case_access(Role.VIEWER)),
    db: AsyncSession = Depends(get_db),
) -> list[NoteOut]:
    stmt = select(Note).where(Note.case_id == ctx.case.id, Note.deleted_at.is_(None))
    if entity_id is not None:
        stmt = stmt.where(Note.entity_id == entity_id)
    stmt = stmt.order_by(Note.pinned.desc(), Note.created_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [NoteOut.model_validate(n) for n in rows]


@router.post("/cases/{case_id}/notes", response_model=NoteOut, status_code=201)
async def create_note(
    payload: NoteCreate, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> NoteOut:
    note = Note(case_id=ctx.case.id, entity_id=payload.entity_id, author_id=ctx.user.id,
                body=payload.body, pinned=payload.pinned)
    db.add(note)
    await db.flush()
    await write_audit(db, action="note.create", actor_id=ctx.user.id, target_type="note", target_id=note.id, case_id=ctx.case.id)
    await db.commit()
    return NoteOut.model_validate(note)


@router.patch("/cases/{case_id}/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: uuid.UUID, payload: NoteUpdate, ctx: CaseContext = Depends(case_access(Role.ANALYST)),
    db: AsyncSession = Depends(get_db),
) -> NoteOut:
    note = await db.get(Note, note_id)
    if note is None or note.case_id != ctx.case.id or note.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found.")
    if note.author_id != ctx.user.id and ctx.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own notes.")
    if payload.body is not None:
        note.body = payload.body
    if payload.pinned is not None:
        note.pinned = payload.pinned
    await db.commit()
    return NoteOut.model_validate(note)


@router.delete("/cases/{case_id}/notes/{note_id}", response_model=MessageResponse)
async def delete_note(
    note_id: uuid.UUID, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    note = await db.get(Note, note_id)
    if note is None or note.case_id != ctx.case.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note not found.")
    if note.author_id != ctx.user.id and ctx.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own notes.")
    note.deleted_at = _now()
    await db.commit()
    return MessageResponse(message="Note deleted.")
