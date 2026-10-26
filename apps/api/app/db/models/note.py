from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Note(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "notes"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("entities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    pinned: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        sa.Computed("to_tsvector('english', coalesce(body,''))", persisted=True),
        nullable=True,
    )

    __table_args__ = (sa.Index("ix_notes_tsv", "tsv", postgresql_using="gin"),)
