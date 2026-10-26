from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from lighthouse_shared import JobStatus

from app.db.base import Base, TimestampMixin, UUIDMixin, enum_col


class Job(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "jobs"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collector_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    status: Mapped[JobStatus] = enum_col(
        JobStatus, type_name="job_status", nullable=False,
        default=JobStatus.QUEUED, server_default=JobStatus.QUEUED.value, index=True,
    )
    progress: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Auto-expand lineage / budget tracking.
    depth: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(sa.String(155), nullable=True, index=True)
