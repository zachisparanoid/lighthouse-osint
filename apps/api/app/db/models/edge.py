from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
# Aliased: this model has a column literally named ``relationship`` which would
# otherwise shadow the ORM ``relationship()`` helper inside the class body.
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from lighthouse_shared import RelationshipType

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, enum_col


class Edge(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "edges"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship: Mapped[RelationshipType] = enum_col(
        RelationshipType, type_name="relationship_type", nullable=False, index=True
    )
    confidence: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=50, server_default="50")
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )

    provenances = orm_relationship(
        "Provenance", back_populates="edge", cascade="all, delete-orphan",
        foreign_keys="Provenance.edge_id",
    )
    source_entity = orm_relationship("Entity", foreign_keys=[source_entity_id])
    target_entity = orm_relationship("Entity", foreign_keys=[target_entity_id])

    __table_args__ = (
        sa.UniqueConstraint(
            "case_id", "source_entity_id", "target_entity_id", "relationship",
            name="edges_unique_relationship",
        ),
    )
