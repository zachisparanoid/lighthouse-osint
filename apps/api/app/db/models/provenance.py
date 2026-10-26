from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDMixin, _utcnow


class Provenance(UUIDMixin, Base):
    """A citation. Every entity and edge links to >= 1 of these.

    Exactly which parent is set is enforced by a CHECK: at least one of
    ``entity_id`` / ``edge_id`` must be non-null. Nothing in the graph exists
    without a recorded source.
    """

    __tablename__ = "provenance"

    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    edge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("edges.id", ondelete="CASCADE"), nullable=True, index=True
    )
    collector_name: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    raw_excerpt: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=_utcnow, server_default=sa.func.now(), nullable=False
    )
    license_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=_utcnow, server_default=sa.func.now(), nullable=False
    )

    entity = relationship("Entity", back_populates="provenances", foreign_keys=[entity_id])
    edge = relationship("Edge", back_populates="provenances", foreign_keys=[edge_id])

    __table_args__ = (
        sa.CheckConstraint(
            "(entity_id IS NOT NULL) OR (edge_id IS NOT NULL)",
            name="entity_or_edge_present",
        ),
    )
