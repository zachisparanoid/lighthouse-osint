"""Collection task bodies.

`execute_collection` is the heart: scope guard -> circuit breaker -> key check ->
token-bucket rate limit -> cache -> httpx+tenacity -> pipeline ingest -> WS deltas ->
audit. It is reused by both the single-collector task and the auto-expand BFS.

Celery tasks are synchronous; each wraps an async body via ``asyncio.run`` with a
fresh NullPool DB engine + Redis client bound to that loop (see db.session.task_session).
"""
from __future__ import annotations

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.collectors.base import (
    CollectionContext,
    Collector,
    CollectorResult,
    EntityRef,
    ScopeGuard,
    ScopeViolation,
)
from app.collectors.registry import free_collectors_for, get_collector
from app.config import settings
from app.core.audit import cb_is_open, cb_record_failure, cb_record_success, write_audit
from app.core.cache import cache_get, cache_key, cache_set
from app.core.events import publish_event
from app.core.keys import resolve_key
from app.core.ratelimit import consume_spec
from app.core.redis_client import make_redis
from app.db.models import Entity, Job
from app.db.session import task_session
from app.pipeline.ingest import ingest_result
from app.tasks.celery_app import celery_app
from lighthouse_shared import JobStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_http() -> httpx.AsyncClient:
    # Transport-level retries cover connection resets; tenacity (below) covers timeouts.
    transport = httpx.AsyncHTTPTransport(retries=2)
    return httpx.AsyncClient(
        headers={"User-Agent": settings.http_user_agent},
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
        transport=transport,
    )


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
)
async def _run_collector_fn(collector: Collector, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
    return await collector.run(target, ctx)


# --------------------------------------------------- cache (de)serialization ---
def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _serialize_result(r: CollectorResult) -> dict:
    def prov(p):
        return {"source_url": p.source_url, "raw_excerpt": p.raw_excerpt, "license_note": p.license_note}

    return {
        "status": r.status.value,
        "message": r.message,
        "summary": r.summary,
        "entities": [
            {
                "type": e.type.value, "value": e.value, "label": e.label, "attributes": e.attributes,
                "tags": e.tags, "first_seen": e.first_seen.isoformat() if e.first_seen else None,
                "last_seen": e.last_seen.isoformat() if e.last_seen else None,
                "base_confidence": e.base_confidence, "prov": prov(e.provenance),
            }
            for e in r.entities
        ],
        "edges": [
            {
                "src": [e.src[0].value, e.src[1]], "dst": [e.dst[0].value, e.dst[1]],
                "relationship": e.relationship.value, "attributes": e.attributes,
                "base_confidence": e.base_confidence, "prov": prov(e.provenance),
            }
            for e in r.edges
        ],
    }


def _deserialize_result(d: dict) -> CollectorResult:
    from lighthouse_shared import EntityType, RelationshipType

    r = CollectorResult(status=JobStatus(d["status"]), message=d.get("message", ""), summary=d.get("summary", {}))
    for e in d.get("entities", []):
        p = e.get("prov", {})
        r.add_entity(
            EntityType(e["type"]), e["value"], label=e.get("label"), attributes=e.get("attributes") or {},
            tags=e.get("tags") or [], first_seen=_parse_dt(e.get("first_seen")), last_seen=_parse_dt(e.get("last_seen")),
            base_confidence=e.get("base_confidence"), source_url=p.get("source_url"),
            raw_excerpt=p.get("raw_excerpt"), license_note=p.get("license_note"),
        )
    for e in d.get("edges", []):
        p = e.get("prov", {})
        r.add_edge(
            (EntityType(e["src"][0]), e["src"][1]), (EntityType(e["dst"][0]), e["dst"][1]),
            RelationshipType(e["relationship"]), attributes=e.get("attributes") or {},
            base_confidence=e.get("base_confidence"), source_url=p.get("source_url"),
            raw_excerpt=p.get("raw_excerpt"), license_note=p.get("license_note"),
        )
    return r


# ------------------------------------------------------------ target loading ---
async def _load_target(db, job: Job) -> EntityRef:
    if job.target_entity_id is not None:
        ent = await db.get(Entity, job.target_entity_id)
        if ent is not None:
            return EntityRef(ent.type, ent.value, ent.attributes or {}, ent.id)
    params = job.params or {}
    from lighthouse_shared import EntityType

    return EntityRef(EntityType(params["seed_type"]), params["seed_value"], {}, job.target_entity_id)


async def _finish(db, redis, job: Job, status: JobStatus, *, error=None, summary=None) -> None:
    job.status = status
    job.finished_at = _now()
    if status == JobStatus.SUCCEEDED:
        job.progress = 100
    if error:
        job.error = error[:2000]
    if summary is not None:
        job.result_summary = summary
    await db.commit()
    await publish_event(redis, job.case_id, {
        "type": "job_completed", "job_id": str(job.id), "collector": job.collector_name,
        "status": status.value, "error": job.error, "summary": job.result_summary,
    })


# ------------------------------------------------------- the core executor ---
async def execute_collection(
    db, redis, http: httpx.AsyncClient, scope: ScopeGuard,
    collector: Collector, target: EntityRef, job: Job, depth: int, user_id,
) -> dict | None:
    """Run one collector against one target. Returns the graph delta on success, else None."""
    job.status = JobStatus.RUNNING
    job.started_at = _now()
    job.progress = 1
    await db.commit()
    await publish_event(redis, job.case_id, {
        "type": "job_progress", "job_id": str(job.id), "collector": collector.name, "progress": 1, "message": "starting",
    })

    async def progress(pct: int, message: str = "") -> None:
        job.progress = max(job.progress or 0, pct)
        await db.commit()
        await publish_event(redis, job.case_id, {
            "type": "job_progress", "job_id": str(job.id), "collector": collector.name,
            "progress": job.progress, "message": message,
        })

    ctx = CollectionContext(
        db=db, redis=redis, http=http, case_id=job.case_id, settings=settings, scope=scope,
        get_key=lambda service: resolve_key(db, job.case_id, service, user_id),
        progress=progress,
    )

    # 1) Scope guard — refuse out-of-scope targets.
    try:
        scope.check_target(target.type, target.value)
    except ScopeViolation as exc:
        await _audit(db, job, "skipped", str(exc), user_id)
        await _finish(db, redis, job, JobStatus.SKIPPED, error=str(exc), summary={"reason": "scope_violation"})
        return None

    # 2) Circuit breaker — don't hammer a struggling source.
    if await cb_is_open(redis, collector.name):
        msg = f"{collector.title} is temporarily unavailable (circuit breaker open). Try again shortly."
        await _finish(db, redis, job, JobStatus.FAILED, error=msg, summary={"reason": "circuit_open"})
        return None

    # 3) Keyed collector with no key -> graceful skip.
    if collector.requires_key is not None:
        if not await resolve_key(db, job.case_id, collector.requires_key.value, user_id):
            msg = f"No {collector.requires_key.value} API key configured. Add one in Settings → Keys."
            await _finish(db, redis, job, JobStatus.SKIPPED, error=msg, summary={"reason": "missing_key"})
            return None

    # 4) Rate limit (token bucket per service). Brief in-task wait, then back off.
    bucket = collector.requires_key.value if collector.requires_key else collector.name
    allowed, retry_after = await consume_spec(redis, bucket, collector.rate_limit)
    waits = 0
    while not allowed and waits < 3 and retry_after <= 5:
        await asyncio.sleep(max(0.2, min(retry_after, 5)))
        allowed, retry_after = await consume_spec(redis, bucket, collector.rate_limit)
        waits += 1
    if not allowed:
        await _finish(db, redis, job, JobStatus.FAILED,
                      error="Rate limited — please retry shortly.",
                      summary={"reason": "rate_limited", "retry_after": round(retry_after, 1)})
        return None

    # 5) Cache (TTL per source).
    ckey = cache_key(collector.name, target.type.value, target.value)
    cached = await cache_get(redis, ckey)
    if cached is not None:
        result = _deserialize_result(cached)
        await progress(80, "from cache")
    else:
        await progress(15, "querying source")
        try:
            result = await _run_collector_fn(collector, target, ctx)
        except httpx.HTTPStatusError as exc:
            await cb_record_failure(redis, collector.name)
            code = exc.response.status_code
            await _finish(db, redis, job, JobStatus.FAILED,
                          error=f"Source returned HTTP {code}.", summary={"reason": "http_error", "status": code})
            return None
        except Exception as exc:  # noqa: BLE001
            await cb_record_failure(redis, collector.name)
            await _finish(db, redis, job, JobStatus.FAILED, error=str(exc)[:500], summary={"reason": "exception"})
            return None
        if result.status == JobStatus.SUCCEEDED:
            await cache_set(redis, ckey, _serialize_result(result), collector.cache_ttl)

    # 6) Honor collector-reported skip/failure.
    if result.status == JobStatus.SKIPPED:
        await _finish(db, redis, job, JobStatus.SKIPPED, error=result.message, summary={"reason": "collector_skipped"})
        return None
    if result.status == JobStatus.FAILED:
        await cb_record_failure(redis, collector.name)
        await _finish(db, redis, job, JobStatus.FAILED, error=result.message,
                      summary={"retry_after": result.retry_after})
        return None

    # 7) Success -> ingest into the graph, push deltas, audit.
    await cb_record_success(redis, collector.name)
    await progress(85, "writing graph")
    delta = await ingest_result(ctx, collector.name, collector.base_reliability, target, result, depth=depth)
    await db.commit()

    if delta["counts"]["new_entities"] or delta["counts"]["updated_entities"] or delta["counts"]["edges"]:
        await publish_event(redis, job.case_id, {
            "type": "graph_delta", "job_id": str(job.id), "collector": collector.name,
            "new_entities": delta["new_entities"], "updated_entities": delta["updated_entities"],
            "edges": delta["edges"],
        })

    summary = {**(result.summary or {}), **delta["counts"]}
    await _audit(db, job, "succeeded", None, user_id, extra=delta["counts"])
    await _finish(db, redis, job, JobStatus.SUCCEEDED, summary=summary)
    return delta


async def _audit(db, job: Job, outcome: str, message, user_id, extra=None) -> None:
    await write_audit(
        db, action="collection.run", actor_id=user_id, target_type="job", target_id=job.id,
        case_id=job.case_id, meta={"collector": job.collector_name, "outcome": outcome,
                                   "message": message, **(extra or {})},
    )
    await db.commit()


# --------------------------------------------------------------- Celery tasks ---
@celery_app.task(bind=True, name="app.tasks.run_collector.run_collector")
def run_collector(self, job_id: str) -> None:
    asyncio.run(_run_collector_async(job_id))


async def _run_collector_async(job_id: str) -> None:
    async with task_session() as db:
        redis = make_redis()
        http = _make_http()
        try:
            job = await db.get(Job, uuid.UUID(job_id))
            if job is None:
                return
            collector = get_collector(job.collector_name)
            if collector is None:
                await _finish(db, redis, job, JobStatus.FAILED, error=f"Unknown collector '{job.collector_name}'.")
                return
            target = await _load_target(db, job)
            scope = ScopeGuard(settings.scope_denylist_list)
            await execute_collection(db, redis, http, scope, collector, target, job, job.depth or 0, job.requested_by)
        finally:
            await http.aclose()
            await redis.aclose()


@celery_app.task(bind=True, name="app.tasks.run_collector.run_autoexpand")
def run_autoexpand(self, job_id: str) -> None:
    asyncio.run(_run_autoexpand_async(job_id))


async def _run_autoexpand_async(root_job_id: str) -> None:
    """BFS from a seed: run every free collector that accepts each node, up to a depth
    and a node budget, pushing live deltas. A Redis stop flag halts it (the stop button).
    """
    async with task_session() as db:
        redis = make_redis()
        http = _make_http()
        try:
            root = await db.get(Job, uuid.UUID(root_job_id))
            if root is None:
                return
            params = root.params or {}
            max_depth = int(params.get("depth", settings.default_autoexpand_depth))
            budget = int(params.get("budget", settings.default_node_budget))
            disabled = set(params.get("disabled") or [])
            scope = ScopeGuard(settings.scope_denylist_list)
            stop_key = f"expand:{root.id}:stop"

            seed = await db.get(Entity, root.target_entity_id) if root.target_entity_id else None
            if seed is None:
                await _finish(db, redis, root, JobStatus.FAILED, error="Seed entity not found.")
                return

            root.status = JobStatus.RUNNING
            root.started_at = _now()
            root.progress = 1
            await db.commit()

            frontier: deque[tuple[Entity, int]] = deque([(seed, 0)])
            visited: set[uuid.UUID] = {seed.id}
            nodes_used = 1
            jobs_run = 0
            stopped = False

            while frontier:
                if await redis.exists(stop_key):
                    stopped = True
                    break
                if nodes_used >= budget:
                    break
                entity, depth = frontier.popleft()
                collectors = [c for c in free_collectors_for(entity.type) if c.name not in disabled]
                for collector in collectors:
                    if await redis.exists(stop_key):
                        stopped = True
                        break
                    try:
                        scope.check_target(entity.type, entity.value)
                    except ScopeViolation:
                        continue
                    child = Job(
                        case_id=root.case_id, collector_name=collector.name, target_entity_id=entity.id,
                        status=JobStatus.QUEUED, depth=depth, parent_job_id=root.id,
                        requested_by=root.requested_by, params={"autoexpand": True},
                    )
                    db.add(child)
                    await db.commit()
                    target = EntityRef(entity.type, entity.value, entity.attributes or {}, entity.id)
                    delta = await execute_collection(
                        db, redis, http, scope, collector, target, child, depth, root.requested_by
                    )
                    jobs_run += 1
                    root.progress = min(95, int((nodes_used / max(budget, 1)) * 100))
                    await db.commit()
                    await publish_event(redis, root.case_id, {
                        "type": "autoexpand_progress", "job_id": str(root.id),
                        "progress": root.progress, "nodes": nodes_used, "jobs": jobs_run,
                    })

                    if delta and depth + 1 <= max_depth:
                        for node in delta["new_entities"]:
                            nid = uuid.UUID(node["id"])
                            if nid in visited or nodes_used >= budget:
                                continue
                            visited.add(nid)
                            nodes_used += 1
                            child_entity = await db.get(Entity, nid)
                            if child_entity is not None:
                                frontier.append((child_entity, depth + 1))
                if stopped:
                    break

            final = JobStatus.SKIPPED if stopped else JobStatus.SUCCEEDED
            await redis.delete(stop_key)
            await write_audit(
                db, action="collection.autoexpand", actor_id=root.requested_by, target_type="case",
                target_id=root.case_id, case_id=root.case_id,
                meta={"nodes": nodes_used, "jobs": jobs_run, "stopped": stopped, "depth": max_depth},
            )
            await _finish(db, redis, root, final, summary={"nodes": nodes_used, "jobs": jobs_run, "stopped": stopped})
        finally:
            await http.aclose()
            await redis.aclose()
