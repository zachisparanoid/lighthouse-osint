from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.email_breach import EmailBreachCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType


@respx.mock
async def test_email_breach_lists_breach_names(ctx_factory):
    route = respx.get(
        url__startswith="https://haveibeenpwned.com/api/v3/breachedaccount/test@example.com"
    ).mock(return_value=httpx.Response(200, json=[{"Name": "Adobe"}, {"Name": "LinkedIn"}]))

    ctx = ctx_factory(keys={"hibp": "K"})
    res = await EmailBreachCollector().run(EntityRef(EntityType.EMAIL, "test@example.com"), ctx)

    assert res.status == JobStatus.SUCCEEDED

    # Two BREACH entities by name.
    breaches = [e for e in res.entities if e.type == EntityType.BREACH]
    assert {e.value for e in breaches} == {"Adobe", "LinkedIn"}

    # breached_in edges from the email to each breach.
    breached = [e for e in res.edges if e.relationship == RelationshipType.BREACHED_IN]
    assert {e.dst for e in breached} == {
        (EntityType.BREACH, "Adobe"),
        (EntityType.BREACH, "LinkedIn"),
    }
    assert all(e.src == (EntityType.EMAIL, "test@example.com") for e in breached)

    # Seed email enriched with breach_count.
    seed = [e for e in res.entities if e.type == EntityType.EMAIL]
    assert any(e.attributes.get("breach_count") == 2 for e in seed)

    # Ethics: truncateResponse=true was sent (names only).
    sent = route.calls.last.request
    assert b"truncateResponse=true" in sent.url.query

    # Provenance on everything.
    assert all(e.provenance.source_url for e in breaches)


async def test_email_breach_no_key_is_skipped(ctx_factory):
    ctx = ctx_factory()
    res = await EmailBreachCollector().run(EntityRef(EntityType.EMAIL, "test@example.com"), ctx)
    assert res.status == JobStatus.SKIPPED
    assert res.entities == []


@respx.mock
async def test_email_breach_404_is_empty_success(ctx_factory):
    respx.get(
        url__startswith="https://haveibeenpwned.com/api/v3/breachedaccount/clean@example.com"
    ).mock(return_value=httpx.Response(404))
    ctx = ctx_factory(keys={"hibp": "K"})
    res = await EmailBreachCollector().run(EntityRef(EntityType.EMAIL, "clean@example.com"), ctx)
    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
    assert "No known breaches" in res.message
