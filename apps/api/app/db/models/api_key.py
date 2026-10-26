from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from lighthouse_shared import KeyService

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, enum_col


class KeyScope(str, enum.Enum):
    """Whether a BYOK key belongs to a single user or is shared within a case."""

    USER = "user"
    CASE = "case"


class APIKey(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A bring-your-own-key credential, stored Fernet-encrypted at rest.

    ``encrypted_value`` is never decrypted toward the client; the API only ever
    returns a masked hint (e.g. ``••••1234``).
    """

    __tablename__ = "api_keys"

    scope: Mapped[KeyScope] = enum_col(
        KeyScope, type_name="key_scope", nullable=False,
        default=KeyScope.USER, server_default=KeyScope.USER.value,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    owner_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    service: Mapped[KeyService] = enum_col(
        KeyService, type_name="key_service", nullable=False, index=True
    )
    encrypted_value: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # Last 4 chars of the plaintext, stored so the UI can show ••••1234 without decrypting.
    hint: Mapped[str | None] = mapped_column(sa.String(8), nullable=True)
    label: Mapped[str] = mapped_column(sa.String(120), nullable=False, default="")
    last_used_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # None = never tested; True/False = last validity check result.
    is_valid: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
