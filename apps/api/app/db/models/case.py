from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lighthouse_shared import CaseStatus, Role

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, enum_col


class Case(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "cases"

    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    slug: Mapped[str] = mapped_column(sa.String(220), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[CaseStatus] = enum_col(
        CaseStatus, type_name="case_status", nullable=False,
        default=CaseStatus.ACTIVE, server_default=CaseStatus.ACTIVE.value, index=True,
    )
    # The analyst MUST record their authorization/scope — enforced NOT NULL at the DB.
    legal_basis: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Acceptable-use acknowledgment gate.
    aup_accepted: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    aup_accepted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    aup_version: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    # Saved Cytoscape positions per case: {entity_id: {x, y}}.
    graph_layout: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )

    members: Mapped[list["CaseMember"]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class CaseMember(Base):
    __tablename__ = "case_members"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    case_role: Mapped[Role] = enum_col(
        Role, type_name="case_member_role", nullable=False,
        default=Role.VIEWER, server_default=Role.VIEWER.value,
    )
    added_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )

    case: Mapped["Case"] = relationship(back_populates="members")
    user = relationship("User")
