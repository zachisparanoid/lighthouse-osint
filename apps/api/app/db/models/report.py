from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin, enum_col


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class Report(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "reports"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    # Which sections/entities to include, etc.
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    format: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="pdf")
    status: Mapped[ReportStatus] = enum_col(
        ReportStatus, type_name="report_status", nullable=False,
        default=ReportStatus.PENDING, server_default=ReportStatus.PENDING.value,
    )
    file_path: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # {pdf: path, json: path, csv: path}
    artifacts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
