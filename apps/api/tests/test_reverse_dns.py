from __future__ import annotations

import types

import dns.resolver

from app.collectors.base import EntityRef
from app.collectors.reverse_dns import ReverseDNSCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType


async def test_reverse_dns_resolves_ptr(ctx_factory, monkeypatch):
    async def fake_resolve(name, rtype):
        assert rtype == "PTR"
        return [types.SimpleNamespace(target="host.example.com.")]

    monkeypatch.setattr("dns.asyncresolver.resolve", fake_resolve)

    ctx = ctx_factory()
    res = await ReverseDNSCollector().run(EntityRef(EntityType.IP, "93.184.216.34"), ctx)

    domains = [e for e in res.entities if e.type == EntityType.DOMAIN]
    assert [e.value for e in domains] == ["host.example.com"]

    ptr_edges = [e for e in res.edges if e.relationship == RelationshipType.RESOLVES_TO]
    assert ptr_edges
    assert ptr_edges[0].src == (EntityType.DOMAIN, "host.example.com")
    assert ptr_edges[0].dst == (EntityType.IP, "93.184.216.34")
    assert ptr_edges[0].attributes.get("record") == "PTR"

    # Provenance present.
    assert all(e.provenance.source_url for e in res.entities)
    assert all(e.provenance.source_url for e in res.edges)


async def test_reverse_dns_nxdomain_is_empty_success(ctx_factory, monkeypatch):
    async def fake_resolve(name, rtype):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr("dns.asyncresolver.resolve", fake_resolve)
    ctx = ctx_factory()
    res = await ReverseDNSCollector().run(EntityRef(EntityType.IP, "192.0.2.123"), ctx)

    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
