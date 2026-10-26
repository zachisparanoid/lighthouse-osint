"""Declarative base, naming convention, reusable mixins, and column helpers.

A deterministic naming convention is set on the metadata so Alembic produces stable,
predictable constraint/index names across machines (critical for clean migrations).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Stable names for indexes/constraints -> reproducible migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


class UUIDMixin:
    """UUID primary key, generated DB-side via Postgres ``gen_random_uuid()`` (PG13+)."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    # Python-side default/onupdate keep the in-memory object populated (so freshly
    # created/updated rows serialize without a lazy DB load -> avoids async MissingGreenlet);
    # server_default keeps DB-level safety for raw SQL inserts and migrations.
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), default=_utcnow, server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=sa.func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True, index=True
    )


def enum_col(enum_cls: type[enum.Enum], *, type_name: str | None = None, **kwargs: Any):
    """A VARCHAR-backed enum column with a DB CHECK constraint (no native PG enum type).

    We avoid native Postgres enum types deliberately: they make schema evolution
    (adding a value) painful. ``native_enum=False`` stores the value as VARCHAR and
    creates a named CHECK constraint enforcing the allowed set — DB-level integrity
    without the ``ALTER TYPE`` headache.
    """
    name = type_name or enum_cls.__name__.lower()
    return mapped_column(
        sa.Enum(
            enum_cls,
            name=name,
            native_enum=False,
            length=64,
            create_constraint=True,
            validate_strings=True,
            # Store/check the enum *values* ("domain"), not the member NAMES ("DOMAIN"),
            # so the DB matches the lowercase contract used everywhere else in the stack.
            values_callable=lambda e: [member.value for member in e],
        ),
        **kwargs,
    )
