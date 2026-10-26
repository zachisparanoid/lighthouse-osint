"""Pipeline persistence against a real Postgres: normalize -> dedupe -> score.

Drives ``ingest.ingest_result`` directly with a ``CollectionContext`` bound to the
``db_session`` fixture (truncated per test). Verifies the three scoring forces and,
critically, idempotency: re-running a collector must not duplicate the graph, and a
second *independent* collector must corroborate (raise confidence + source_count).
"""
from __future__ import annotations

import uuid

import fakeredis.aioredis
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.collectors.base import (
    CollectionContext,
    CollectorResult,
    EntityRef,
    ScopeGuard,
)
from app.core.security import hash_password
from app.db.models import Case, Edge, Entity, Provenance, User
from app.pipeline import ingest
from lighthouse_shared import EntityType, RelationshipType, Role

SEED_IP = "8.8.8.8"
SEED_DOMAIN = "example.com"


@pytest_asyncio.fixture
async def seed(db_session):
    """A User + Case + seed DOMAIN entity, committed. Returns (user, case, seed_entity)."""
    user = User(email="analyst@example.com", password_hash=hash_password("pw-not-used-here"), role=Role.ANALYST)
    db_session.add(user)
    await db_session.flush()

    case = Case(
        name="Pipeline Case",
        slug=f"pipeline-{uuid.uuid4().hex[:8]}",
        owner_id=user.id,
        created_by=user.id,
        legal_basis="Authorized investigation for automated pipeline tests.",
        aup_accepted=True,
    )
    db_session.add(case)
    await db_session.flush()

    seed_entity = Entity(
        case_id=case.id,
        type=EntityType.DOMAIN,
        value=SEED_DOMAIN,
        label=SEED_DOMAIN,
        confidence=90,
        source_count=1,
    )
    db_session.add(seed_entity)
    await db_session.flush()
    await db_session.commit()
    return user, case, seed_entity


@pytest.fixture
def ctx_for(db_session):
    """Build a CollectionContext for a given case bound to db_session + fakeredis."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    def _make(case_id) -> CollectionContext:
        async def get_key(service: str):
            return None

        async def progress(pct: int, message: str = "") -> None:
            return None

        from app.config import settings

        return CollectionContext(
            db=db_session,
            redis=fake,
            http=None,
            case_id=case_id,
            settings=settings,
            scope=ScopeGuard([]),
            get_key=get_key,
            progress=progress,
        )

    return _make


def _dns_result() -> CollectorResult:
    """A DNS-style result: one IP entity + a resolves_to edge from the seed domain."""
    res = CollectorResult()
    res.add_entity(
        EntityType.IP,
        SEED_IP,
        source_url="https://dns.example/lookup",
        raw_excerpt={"record": "A"},
    )
    res.add_edge(
        (EntityType.DOMAIN, SEED_DOMAIN),
        (EntityType.IP, SEED_IP),
        RelationshipType.RESOLVES_TO,
        source_url="https://dns.example/lookup",
    )
    return res


def _shodan_result() -> CollectorResult:
    """A second, independent sighting of the same IP (different source)."""
    res = CollectorResult()
    res.add_entity(
        EntityType.IP,
        SEED_IP,
        source_url="https://shodan.example/host",
        raw_excerpt={"ports": [443]},
    )
    return res


async def _count(db, model, **filters) -> int:
    stmt = select(func.count()).select_from(model)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    return int((await db.execute(stmt)).scalar() or 0)


async def test_ingest_persists_entity_edge_and_provenance(db_session, seed, ctx_for):
    _user, case, seed_entity = seed
    ctx = ctx_for(case.id)
    target = EntityRef(EntityType.DOMAIN, SEED_DOMAIN, id=seed_entity.id)

    delta = await ingest.ingest_result(
        ctx, "dns_records", base_reliability=85, target=target, result=_dns_result(), depth=1
    )
    await db_session.commit()

    ip = (
        await db_session.execute(
            select(Entity).where(Entity.case_id == case.id, Entity.type == EntityType.IP)
        )
    ).scalar_one()
    assert ip.value == SEED_IP
    # 85 * distance_decay(1)=0.85 -> 72; no corroboration yet (single source).
    assert ip.confidence == 72
    assert ip.source_count == 1

    edges = (await db_session.execute(select(Edge).where(Edge.case_id == case.id))).scalars().all()
    assert len(edges) == 1
    assert edges[0].relationship == RelationshipType.RESOLVES_TO

    prov = await _count(db_session, Provenance, entity_id=ip.id)
    assert prov == 1

    assert delta["counts"]["new_entities"] == 1
    assert delta["counts"]["edges"] == 1


async def test_reingest_same_result_is_idempotent(db_session, seed, ctx_for):
    _user, case, seed_entity = seed
    ctx = ctx_for(case.id)
    target = EntityRef(EntityType.DOMAIN, SEED_DOMAIN, id=seed_entity.id)

    await ingest.ingest_result(
        ctx, "dns_records", base_reliability=85, target=target, result=_dns_result(), depth=1
    )
    await db_session.commit()
    # Re-run the identical collector result.
    await ingest.ingest_result(
        ctx, "dns_records", base_reliability=85, target=target, result=_dns_result(), depth=1
    )
    await db_session.commit()

    # Still exactly one IP entity (dedupe on natural key).
    assert await _count(db_session, Entity, case_id=case.id, type=EntityType.IP) == 1
    ip = (
        await db_session.execute(
            select(Entity).where(Entity.case_id == case.id, Entity.type == EntityType.IP)
        )
    ).scalar_one()
    # Provenance updated-in-place, not appended; one distinct source.
    assert await _count(db_session, Provenance, entity_id=ip.id) == 1
    assert ip.source_count == 1
    # One edge only.
    assert await _count(db_session, Edge, case_id=case.id) == 1


async def test_second_collector_corroborates(db_session, seed, ctx_for):
    _user, case, seed_entity = seed
    ctx = ctx_for(case.id)
    target = EntityRef(EntityType.DOMAIN, SEED_DOMAIN, id=seed_entity.id)

    await ingest.ingest_result(
        ctx, "dns_records", base_reliability=85, target=target, result=_dns_result(), depth=1
    )
    await db_session.commit()

    # A second, independent collector reports the same IP.
    await ingest.ingest_result(
        ctx, "shodan", base_reliability=80, target=target, result=_shodan_result(), depth=1
    )
    await db_session.commit()

    ip = (
        await db_session.execute(
            select(Entity).where(Entity.case_id == case.id, Entity.type == EntityType.IP)
        )
    ).scalar_one()
    assert ip.source_count == 2
    # 80 * 0.85 = 68, + corroboration step (8 for one extra source) = 76.
    assert ip.confidence == 76
    # Two provenance rows now (one per distinct collector source_url).
    assert await _count(db_session, Provenance, entity_id=ip.id) == 2
    # Still a single IP entity.
    assert await _count(db_session, Entity, case_id=case.id, type=EntityType.IP) == 1
