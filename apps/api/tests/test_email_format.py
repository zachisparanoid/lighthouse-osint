from __future__ import annotations

from types import SimpleNamespace

import dns.resolver

from app.collectors.base import EntityRef
from app.collectors.email_format import EmailFormatCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType


async def test_email_format_with_mx(ctx_factory, monkeypatch):
    async def fake_resolve(domain, rtype):
        assert rtype == "MX"
        return [SimpleNamespace(exchange="mail.example.com.", preference=10)]

    monkeypatch.setattr("dns.asyncresolver.resolve", fake_resolve)

    ctx = ctx_factory()
    res = await EmailFormatCollector().run(EntityRef(EntityType.EMAIL, "alice@example.com"), ctx)

    assert res.status == JobStatus.SUCCEEDED

    # DOMAIN entity emitted.
    domains = [e for e in res.entities if e.type == EntityType.DOMAIN]
    assert [e.value for e in domains] == ["example.com"]

    # Seed email enriched with MX info.
    emails = [e for e in res.entities if e.type == EntityType.EMAIL]
    assert emails
    attrs = emails[0].attributes
    assert attrs["has_mx"] is True
    assert "mail.example.com" in attrs["mx_hosts"]
    assert attrs["syntax_valid"] is True
    assert attrs["deliverable_heuristic"] is True

    # references edge email -> domain.
    refs = [e for e in res.edges if e.relationship == RelationshipType.REFERENCES]
    assert any(
        e.src == (EntityType.EMAIL, "alice@example.com")
        and e.dst == (EntityType.DOMAIN, "example.com")
        for e in refs
    )

    assert res.summary == {"has_mx": True, "deliverable": True}


async def test_email_format_no_mx_still_success(ctx_factory, monkeypatch):
    async def fake_resolve(domain, rtype):
        raise dns.resolver.NoAnswer(qnames=[domain], responses={})

    monkeypatch.setattr("dns.asyncresolver.resolve", fake_resolve)

    ctx = ctx_factory()
    res = await EmailFormatCollector().run(EntityRef(EntityType.EMAIL, "bob@example.org"), ctx)

    assert res.status == JobStatus.SUCCEEDED
    emails = [e for e in res.entities if e.type == EntityType.EMAIL]
    assert emails
    attrs = emails[0].attributes
    assert attrs["has_mx"] is False
    assert attrs["mx_hosts"] == []
    assert attrs["deliverable_heuristic"] is False
    # Domain still surfaced even with no MX.
    assert any(e.type == EntityType.DOMAIN and e.value == "example.org" for e in res.entities)
