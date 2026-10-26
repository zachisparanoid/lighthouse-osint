from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class AuditLog(UUIDMixin, Base):
    """Append-only audit trail. No updates, no soft-delete — write once, read forever."""

    __tablename__ = "audit_log"

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(sa.String(80), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    target_id: Mapped[str | None] = mapped_column(sa.String(120), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ip: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(sa.String(400), nullable=True)
    # Attribute is ``meta`` because ``metadata`` is reserved on the Declarative base;
    # the underlying DB column is still named ``metadata`` per the spec.
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
