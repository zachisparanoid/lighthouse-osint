from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from lighthouse_shared import Role

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, enum_col


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[Role] = enum_col(
        Role, type_name="role", nullable=False, default=Role.ANALYST, server_default=Role.ANALYST.value
    )
    # Fernet-encrypted TOTP secret (never stored or returned in plaintext).
    totp_secret: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=sa.true()
    )
    # Brute-force protection.
    failed_login_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email} ({self.role})>"
