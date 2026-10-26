"""Collection jobs: enqueue single modules, auto-expand, list, retry, cancel/stop.

The ``enqueue_*`` helpers are imported by entities.py too (seed -> run on create).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.registry import get_collector
from app.config import settings
from app.core.audit import write_audit
from app.core.rbac import CaseContext, case_access
from app.core.redis_client import get_redis
from app.db.models import Entity, Job
from app.db.session import get_db
from app.schemas.common import MessageResponse, Page
from app.schemas.job import AutoExpandRequest, JobOut, RunModuleRequest
from app.tasks.celery_app import celery_app
from app.tasks.run_collector import run_autoexpand, run_collector
from lighthouse_shared import JobStatus, Role

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def enqueue_collector(
    db: AsyncSession, case_id: uuid.UUID, collector_name: str, target_entity_id: uuid.UUID,
    user_id: uuid.UUID, *, depth: int = 0, params: dict | None = None,
) -> Job:
    job = Job(case_id=case_id, collector_name=collector_name, target_entity_id=target_entity_id,
              status=JobStatus.QUEUED, requested_by=user_id, depth=depth, params=params or {})
    db.add(job)
    await db.flush()
    res = run_collector.delay(str(job.id))
    job.celery_task_id = res.id
    return job


async def enqueue_autoexpand(
    db: AsyncSession, case_id: uuid.UUID, seed_entity_id: uuid.UUID, user_id: uuid.UUID,
    *, depth: int, budget: int, disabled: list[str],
) -> Job:
    job = Job(case_id=case_id, collector_name="auto_expand", target_entity_id=seed_entity_id,
              status=JobStatus.QUEUED, requested_by=user_id,
              params={"depth": depth, "budget": budget, "disabled": disabled})
    db.add(job)
    await db.flush()
    res = run_autoexpand.delay(str(job.id))
    job.celery_task_id = res.id
    return job


@router.get("/cases/{case_id}/jobs", response_model=Page[JobOut])
async def list_jobs(
    job_status: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
    ctx: CaseContext = Depends(case_access(Role.VIEWER)), db: AsyncSession = Depends(get_db),
) -> Page[JobOut]:
    base = select(Job).where(Job.case_id == ctx.case.id)
    if job_status is not None:
        base = base.where(Job.status == job_status)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(Job.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return Page(items=[JobOut.model_validate(j) for j in rows], total=int(total or 0), limit=limit, offset=offset)


@router.get("/cases/{case_id}/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID, ctx: CaseContext = Depends(case_access(Role.VIEWER)), db: AsyncSession = Depends(get_db)
) -> JobOut:
    job = await db.get(Job, job_id)
    if job is None or job.case_id != ctx.case.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return JobOut.model_validate(job)


@router.post("/cases/{case_id}/jobs/run", response_model=JobOut, status_code=202)
async def run_module(
    payload: RunModuleRequest, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> JobOut:
    collector = get_collector(payload.collector_name)
    if collector is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown collector '{payload.collector_name}'.")
    entity = await db.get(Entity, payload.target_entity_id)
    if entity is None or entity.case_id != ctx.case.id or entity.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Target entity not found in this case.")
    if entity.type not in collector.accepts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"{collector.title} does not accept {entity.type.value} entities.")
    job = await enqueue_collector(db, ctx.case.id, collector.name, entity.id, ctx.user.id)
    await write_audit(db, action="job.enqueue", actor_id=ctx.user.id, target_type="job", target_id=job.id,
                      case_id=ctx.case.id, meta={"collector": collector.name})
    await db.commit()
    return JobOut.model_validate(job)


@router.post("/cases/{case_id}/jobs/autoexpand", response_model=JobOut, status_code=202)
async def autoexpand(
    payload: AutoExpandRequest, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> JobOut:
    seed = await db.get(Entity, payload.seed_entity_id)
    if seed is None or seed.case_id != ctx.case.id or seed.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Seed entity not found in this case.")
    depth = payload.depth or settings.default_autoexpand_depth
    budget = payload.budget or settings.default_node_budget
    job = await enqueue_autoexpand(db, ctx.case.id, seed.id, ctx.user.id,
                                   depth=depth, budget=budget, disabled=payload.disabled)
    await write_audit(db, action="job.autoexpand", actor_id=ctx.user.id, target_type="job", target_id=job.id,
                      case_id=ctx.case.id, meta={"depth": depth, "budget": budget})
    await db.commit()
    return JobOut.model_validate(job)


@router.post("/cases/{case_id}/jobs/{job_id}/retry", response_model=JobOut, status_code=202)
async def retry_job(
    job_id: uuid.UUID, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> JobOut:
    job = await db.get(Job, job_id)
    if job is None or job.case_id != ctx.case.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(status.HTTP_409_CONFLICT, "Job is already active.")
    job.status = JobStatus.QUEUED
    job.progress = 0
    job.error = None
    job.result_summary = None
    job.started_at = None
    job.finished_at = None
    await db.flush()
    is_expand = job.collector_name == "auto_expand"
    res = (run_autoexpand if is_expand else run_collector).delay(str(job.id))
    job.celery_task_id = res.id
    await write_audit(db, action="job.retry", actor_id=ctx.user.id, target_type="job", target_id=job.id, case_id=ctx.case.id)
    await db.commit()
    return JobOut.model_validate(job)


@router.post("/cases/{case_id}/jobs/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: uuid.UUID, ctx: CaseContext = Depends(case_access(Role.ANALYST)), db: AsyncSession = Depends(get_db)
) -> JobOut:
    job = await db.get(Job, job_id)
    if job is None or job.case_id != ctx.case.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.SKIPPED):
        return JobOut.model_validate(job)

    if job.collector_name == "auto_expand":
        # Signal the BFS loop to stop at its next checkpoint.
        await get_redis().set(f"expand:{job.id}:stop", "1", ex=3600)
    if job.celery_task_id:
        try:
            celery_app.control.revoke(job.celery_task_id, terminate=False)
        except Exception:  # noqa: BLE001
            pass
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.SKIPPED
        job.error = "Cancelled by user."
        job.finished_at = _now()
    await write_audit(db, action="job.cancel", actor_id=ctx.user.id, target_type="job", target_id=job.id, case_id=ctx.case.id)
    await db.commit()
    return JobOut.model_validate(job)
