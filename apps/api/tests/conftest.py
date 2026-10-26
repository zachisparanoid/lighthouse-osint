"""Shared pytest fixtures.

Collectors are DB-free (they only use ctx.http / get_key / scope / progress), so they can
be exercised with just an httpx client + respx — no Postgres required. DB-touching tests
(pipeline, RBAC) use the ``db_session`` fixture which skips if TEST_DATABASE_URL is unset.
"""
from __future__ import annotations

import os
import uuid

# Must be set before importing app.config.
os.environ.setdefault("SECRET_KEY", "test-secret-key-please-only-for-tests-0123456789")
os.environ.setdefault("FERNET_KEY", "Yp3s8mJ4kQpV2nF7rL0wXc1bN9aD6eH5tU8iO2yR4gM=")
os.environ.setdefault("LIGHTHOUSE_ENV", "test")

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.collectors.base import CollectionContext, ScopeGuard  # noqa: E402
from app.config import settings  # noqa: E402


@pytest_asyncio.fixture
async def ctx_factory():
    """Returns a builder for a CollectionContext wired to a real httpx client
    (intercepted by respx in tests). Closes all created clients on teardown.
    """
    clients: list[httpx.AsyncClient] = []

    def _make(*, keys: dict | None = None, scope: ScopeGuard | None = None) -> CollectionContext:
        client = httpx.AsyncClient(
            headers={"User-Agent": "LighthouseTest/1.0"}, timeout=10.0, follow_redirects=True
        )
        clients.append(client)

        async def get_key(service: str) -> str | None:
            return (keys or {}).get(service)

        async def progress(pct: int, message: str = "") -> None:
            return None

        return CollectionContext(
            db=None,  # collectors never touch the DB
            redis=None,
            http=client,
            case_id=uuid.uuid4(),
            settings=settings,
            scope=scope or ScopeGuard([]),
            get_key=get_key,
            progress=progress,
        )

    yield _make
    for c in clients:
        await c.aclose()


@pytest.fixture
def scope_open() -> ScopeGuard:
    return ScopeGuard([])


# --------------------------------------------------------------------------- #
# DB / API integration fixtures (appended).
#
# Collector tests above are DB-free. The fixtures below give DB-touching tests
# (pipeline, RBAC) and the auth API integration flow a real Postgres session
# (truncated per-test) plus a FastAPI app wired to fakeredis so the auth refresh
# token store works without a live Redis.
# --------------------------------------------------------------------------- #
import os as _os

_os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://lighthouse:lighthouse@localhost:5432/lighthouse"
)

import pytest_asyncio  # noqa: E402
from sqlalchemy import text as _sql_text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

_TABLES = "users, cases, case_members, entities, edges, provenance, jobs, api_keys, notes, audit_log, reports"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(_os.environ["DATABASE_URL"], poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(_sql_text(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE"))
    Session = async_sessionmaker(engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def api_client(db_session):
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient

    import app.core.redis_client as rc
    from app.db.session import get_db
    from app.main import app

    # Use fakeredis so auth (refresh jti store) works without touching real redis.
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    rc._app_redis = fake

    async def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    rc._app_redis = None
