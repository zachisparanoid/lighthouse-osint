"""Authentication + role-based access control, expressed as FastAPI dependencies.

Role hierarchy (system-wide and per-case): viewer < analyst < admin. A system admin or
a case's owner is implicitly admin *within* that case; otherwise the effective case role
comes from ``case_members``. Every protected endpoint depends on one of these, and the
WebSocket path reuses ``authenticate_token``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from lighthouse_shared import Role

from app.core import security
from app.db.models import Case, CaseMember, User
from app.db.session import get_db

ROLE_ORDER: dict[Role, int] = {Role.VIEWER: 0, Role.ANALYST: 1, Role.ADMIN: 2}

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


async def _load_active_user(db: AsyncSession, user_id: str) -> User:
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError, AttributeError):
        raise _CREDENTIALS_EXC from None
    user = await db.get(User, uid)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise _CREDENTIALS_EXC
    return user


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = _bearer_token(request)
    if not token:
        raise _CREDENTIALS_EXC
    try:
        payload = security.decode_token(token, expected_type="access")
    except jwt.PyJWTError:
        raise _CREDENTIALS_EXC from None
    return await _load_active_user(db, payload.get("sub", ""))


async def authenticate_token(db: AsyncSession, token: str) -> User | None:
    """Validate an access-token string (used by the WebSocket handshake)."""
    try:
        payload = security.decode_token(token, expected_type="access")
        return await _load_active_user(db, payload.get("sub", ""))
    except (jwt.PyJWTError, HTTPException):
        return None


def require_role(min_role: Role):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if ROLE_ORDER[user.role] < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail="Insufficient role for this action")
        return user

    return dependency


require_analyst = require_role(Role.ANALYST)
require_admin = require_role(Role.ADMIN)


@dataclass
class CaseContext:
    """Resolved case + the requesting user's effective role within it."""

    case: Case
    user: User
    role: Role


def case_access(min_role: Role = Role.VIEWER):
    """Dependency factory: ensures the user can access ``{case_id}`` at >= ``min_role``."""

    async def dependency(
        case_id: uuid.UUID,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> CaseContext:
        case = await db.get(Case, case_id)
        if case is None or case.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Case not found")

        if user.role == Role.ADMIN or case.owner_id == user.id:
            effective = Role.ADMIN
        else:
            member = await db.get(CaseMember, {"case_id": case_id, "user_id": user.id})
            if member is None:
                raise HTTPException(status_code=403, detail="You are not a member of this case")
            effective = member.case_role

        if ROLE_ORDER[effective] < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail="Insufficient role within this case")
        return CaseContext(case=case, user=user, role=effective)

    return dependency


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")
