from __future__ import annotations

import types

import dns.resolver

from app.collectors.base import EntityRef
from app.collectors.dns_records import DNSRecordsCollector
from lighthouse_shared import EntityType, RelationshipType


def _fake_answers():
    return {
        "A": [types.SimpleNamespace(address="93.184.216.34")],
        "MX": [types.SimpleNamespace(exchange="mail.example.com.", preference=10)],
        "NS": [types.SimpleNamespace(target="ns1.example.com.")],
        "TXT": [types.SimpleNamespace(strings=[b"v=spf1 include:_spf.example.com ~all"])],
    }


async def test_dns_records_parses_all_types(ctx_factory, monkeypatch):
    answers = _fake_answers()

    async def fake_resolve(name, rtype):
        if rtype in answers:
            return answers[rtype]
        raise dns.resolver.NoAnswer(qnames=[name], responses={})

    monkeypatch.setattr("dns.asyncresolver.resolve", fake_resolve)

    ctx = ctx_factory()
    res = await DNSRecordsCollector().run(EntityRef(EntityType.DOMAIN, "example.com"), ctx)

    ips = [e for e in res.entities if e.type == EntityType.IP]
    assert [e.value for e in ips] == ["93.184.216.34"]

    mx = [e for e in res.entities if e.type == EntityType.DOMAIN and e.value == "mail.example.com"]
    assert mx and mx[0].attributes.get("role") == "mail_server"

    # SPF folded onto the seed entity
    seed = [e for e in res.entities if e.type == EntityType.DOMAIN and e.value == "example.com"]
    assert any(e.attributes.get("has_spf") for e in seed)

    assert any(e.relationship == RelationshipType.RESOLVES_TO for e in res.edges)
    # every emitted entity/edge carries a provenance source
    assert all(e.provenance.source_url for e in res.entities)


async def test_dns_records_empty_is_success(ctx_factory, monkeypatch):
    async def fake_resolve(name, rtype):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr("dns.asyncresolver.resolve", fake_resolve)
    ctx = ctx_factory()
    res = await DNSRecordsCollector().run(EntityRef(EntityType.DOMAIN, "nope.invalid"), ctx)
    from lighthouse_shared import JobStatus

    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
