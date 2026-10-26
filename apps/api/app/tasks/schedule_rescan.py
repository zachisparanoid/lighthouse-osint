"""Scheduled re-scans.

Schedules live in a Redis hash ``rescan:schedules`` (case_id -> JSON) set via the
Modules settings API — no dedicated table needed. Celery beat calls ``scan_due`` every
5 minutes; due cases get a fresh auto-expand enqueued from their seed entity.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from app.core.redis_client import make_redis
from app.db.models import Job
from app.db.session import task_session
from app.tasks.celery_app import celery_app
from lighthouse_shared import JobStatus

RESCAN_HASH = "rescan:schedules"


@celery_app.task(name="app.tasks.schedule_rescan.scan_due")
def scan_due() -> None:
    asyncio.run(_scan_due())


async def _scan_due() -> None:
    from app.tasks.run_collector import run_autoexpand

    redis = make_redis()
    try:
        schedules = await redis.hgetall(RESCAN_HASH)
        now = time.time()
        for case_id, raw in schedules.items():
            try:
                cfg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            interval = float(cfg.get("interval_hours", 24)) * 3600
            if now - float(cfg.get("last_run", 0)) < interval:
                continue
            seed_entity_id = cfg.get("seed_entity_id")
            if not seed_entity_id:
                continue

            async with task_session() as db:
                root = Job(
                    case_id=uuid.UUID(case_id),
                    collector_name="auto_expand",
                    target_entity_id=uuid.UUID(seed_entity_id),
                    status=JobStatus.QUEUED,
                    params={
                        "depth": cfg.get("depth", 2),
                        "budget": cfg.get("budget", 250),
                        "rescan": True,
                    },
                    requested_by=None,
                )
                db.add(root)
                await db.commit()
                run_autoexpand.delay(str(root.id))

            cfg["last_run"] = now
            await redis.hset(RESCAN_HASH, case_id, json.dumps(cfg))
    finally:
        await redis.aclose()
