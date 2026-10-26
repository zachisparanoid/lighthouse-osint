"""Celery application — Redis broker/result backend, JSON serialization, beat schedule."""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery_app = Celery(
    "lighthouse",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.run_collector", "app.tasks.schedule_rescan"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
)

# Periodic re-scans: every 5 minutes the beat scheduler asks the worker to check
# which cases are due for a re-scan (schedules are stored in Redis).
celery_app.conf.beat_schedule = {
    "rescan-due-cases": {
        "task": "app.tasks.schedule_rescan.scan_due",
        "schedule": 300.0,
    },
}
