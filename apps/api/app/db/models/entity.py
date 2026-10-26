from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lighthouse_shared import EntityType

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, enum_col

# Full-text vector built DB-side from the most search-relevant fields.
# NOTE: tags are intentionally excluded here — array_to_string() is only STABLE
# (not IMMUTABLE), so Postgres rejects it in a STORED generated column. Tags get
# their own GIN index (ix_entities_tags) for exact membership queries instead.
_ENTITY_TSV = (
    "to_tsvector('english', "
    "coalesce(value,'') || ' ' || coalesce(label,'') || ' ' || "
    "coalesce(attributes::text, ''))"
)


class Entity(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "entities"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[EntityType] = enum_col(
        EntityType, type_name="entity_type", nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    label: Mapped[str] = mapped_column(sa.Text, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    first_seen: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    confidence: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=50, server_default="50")
    source_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, server_default="0")
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, default=list, server_default=sa.text("'{}'::text[]")
    )
    # Flagged when independent sources disagree about this entity's attributes.
    conflicting: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    pinned: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, sa.Computed(_ENTITY_TSV, persisted=True), nullable=True
    )

    provenances: Mapped[list["Provenance"]] = relationship(  # noqa: F821
        back_populates="entity",
        cascade="all, delete-orphan",
        foreign_keys="Provenance.entity_id",
    )

    __table_args__ = (
        sa.UniqueConstraint("case_id", "type", "value", name="entities_case_type_value"),
        sa.Index("ix_entities_tsv", "tsv", postgresql_using="gin"),
        sa.Index("ix_entities_tags", "tags", postgresql_using="gin"),
        sa.Index("ix_entities_case_type", "case_id", "type"),
    )
