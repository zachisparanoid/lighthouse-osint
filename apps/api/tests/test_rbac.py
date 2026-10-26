"""RBAC: role ordering + the ``case_access`` dependency's effective-role resolution.

We call the *inner* dependency function returned by ``case_access(min_role)`` directly
with concrete ``(case_id, user, db)`` — bypassing FastAPI's injection — so we can assert
on the returned ``CaseContext`` or the raised ``HTTPException``.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.core.rbac import ROLE_ORDER, CaseContext, case_access
from app.core.security import hash_password
from app.db.models import Case, CaseMember, User
from lighthouse_shared import Role


def _user(email: str, role: Role) -> User:
    return User(email=email, password_hash=hash_password("pw"), role=role)


@pytest_asyncio.fixture
async def world(db_session):
    """Owner A, outsider B, sysadmin C, viewer-member V, and a case owned by A."""
    a = _user("owner-a@example.com", Role.ANALYST)
    b = _user("outsider-b@example.com", Role.ANALYST)
    c = _user("sysadmin-c@example.com", Role.ADMIN)
    v = _user("viewer-v@example.com", Role.ANALYST)  # system role analyst, but viewer *within* the case
    db_session.add_all([a, b, c, v])
    await db_session.flush()

    case = Case(
        name="RBAC Case",
        slug=f"rbac-{uuid.uuid4().hex[:8]}",
        owner_id=a.id,
        created_by=a.id,
        legal_basis="Authorized investigation for RBAC tests.",
        aup_accepted=True,
    )
    db_session.add(case)
    await db_session.flush()

    db_session.add(CaseMember(case_id=case.id, user_id=v.id, case_role=Role.VIEWER))
    await db_session.flush()
    await db_session.commit()
    return {"a": a, "b": b, "c": c, "v": v, "case": case}


def test_role_order() -> None:
    assert ROLE_ORDER[Role.VIEWER] < ROLE_ORDER[Role.ANALYST] < ROLE_ORDER[Role.ADMIN]


async def test_owner_gets_admin(db_session, world):
    dep = case_access(Role.ANALYST)
    ctx = await dep(case_id=world["case"].id, user=world["a"], db=db_session)
    assert isinstance(ctx, CaseContext)
    assert ctx.role == Role.ADMIN


async def test_non_member_forbidden(db_session, world):
    dep = case_access(Role.ANALYST)
    with pytest.raises(HTTPException) as exc:
        await dep(case_id=world["case"].id, user=world["b"], db=db_session)
    assert exc.value.status_code == 403


async def test_system_admin_gets_admin(db_session, world):
    dep = case_access(Role.ANALYST)
    ctx = await dep(case_id=world["case"].id, user=world["c"], db=db_session)
    assert ctx.role == Role.ADMIN


async def test_viewer_member_insufficient_for_analyst(db_session, world):
    dep = case_access(Role.ANALYST)
    with pytest.raises(HTTPException) as exc:
        await dep(case_id=world["case"].id, user=world["v"], db=db_session)
    assert exc.value.status_code == 403


async def test_viewer_member_ok_for_viewer(db_session, world):
    dep = case_access(Role.VIEWER)
    ctx = await dep(case_id=world["case"].id, user=world["v"], db=db_session)
    assert ctx.role == Role.VIEWER
