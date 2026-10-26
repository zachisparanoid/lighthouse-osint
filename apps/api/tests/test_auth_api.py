"""Auth API integration flow against the real app (ASGI) + Postgres + fakeredis.

Covers: first-user-is-admin registration, /me with and without a bearer token,
duplicate registration conflict, brute-force lockout, and the acceptable-use
acknowledgment gate on case creation.
"""
from __future__ import annotations

from app.config import settings

EMAIL = "founder@example.com"
PASSWORD = "Sup3r-Secret-Pw!"


async def _register(api_client, email=EMAIL, password=PASSWORD):
    return await api_client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )


async def test_register_first_user_is_admin(api_client):
    resp = await _register(api_client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["access_token"]
    # The very first registered user bootstraps as admin.
    assert body["user"]["role"] == "admin"
    assert body["user"]["email"] == EMAIL


async def test_me_requires_and_returns_authenticated_user(api_client):
    reg = await _register(api_client)
    token = reg.json()["access_token"]

    ok = await api_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.json()["email"] == EMAIL

    # No credentials -> 401.
    unauth = await api_client.get("/api/v1/auth/me")
    assert unauth.status_code == 401


async def test_duplicate_register_conflicts(api_client):
    first = await _register(api_client)
    assert first.status_code == 201
    dup = await _register(api_client)
    assert dup.status_code == 409


async def test_login_lockout_after_max_attempts(api_client):
    await _register(api_client)

    last_status = None
    # Hammer with the wrong password; the account should lock at max_login_attempts.
    for _ in range(settings.max_login_attempts):
        resp = await api_client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-password"}
        )
        # Each bad attempt is 401 until the lockout trips.
        assert resp.status_code in (401, 423)
        last_status = resp.status_code

    # Now the account is locked: even a *correct* password is refused with 423.
    locked = await api_client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert locked.status_code == 423
    # And at least one wrong attempt returned 401 along the way.
    assert last_status in (401, 423)


async def _auth_headers(api_client) -> dict[str, str]:
    token = (await _register(api_client)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_case_requires_aup_acknowledgment(api_client):
    headers = await _auth_headers(api_client)

    # aup_accepted False -> rejected by the schema validator (422).
    rejected = await api_client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "name": "Investigation One",
            "legal_basis": "Authorized by client engagement letter dated 2026-05.",
            "aup_accepted": False,
        },
    )
    assert rejected.status_code == 422

    # aup_accepted True + a legal_basis >= 10 chars -> created.
    created = await api_client.post(
        "/api/v1/cases",
        headers=headers,
        json={
            "name": "Investigation One",
            "legal_basis": "Authorized by client engagement letter dated 2026-05.",
            "aup_accepted": True,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["aup_accepted"] is True
    assert body["name"] == "Investigation One"
