from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.shodan import ShodanCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType

_HOST = {
    "ip_str": "8.8.8.8",
    "ports": [53, 443],
    "org": "Google LLC",
    "isp": "Google LLC",
    "asn": "AS15169",
    "country_name": "United States",
    "city": "Mountain View",
    "hostnames": ["dns.google"],
    "domains": ["google.com"],
    "os": None,
    "data": [{"port": 53, "transport": "udp", "product": "Google DNS"}],
}


@respx.mock
async def test_shodan_parses_host_intel(ctx_factory):
    respx.get(url__startswith="https://api.shodan.io/shodan/host/8.8.8.8").mock(
        return_value=httpx.Response(200, json=_HOST)
    )

    ctx = ctx_factory(keys={"shodan": "K"})
    res = await ShodanCollector().run(EntityRef(EntityType.IP, "8.8.8.8"), ctx)

    assert res.status == JobStatus.SUCCEEDED

    # ORGANIZATION + references edge.
    orgs = [e for e in res.entities if e.type == EntityType.ORGANIZATION]
    assert any(e.value == "Google LLC" for e in orgs)
    assert any(
        e.relationship == RelationshipType.REFERENCES and e.dst == (EntityType.ORGANIZATION, "Google LLC")
        for e in res.edges
    )

    # ASN "AS15169" + member_of edge.
    asns = [e for e in res.entities if e.type == EntityType.ASN]
    assert asns and asns[0].value == "AS15169"
    assert any(
        e.relationship == RelationshipType.MEMBER_OF and e.dst == (EntityType.ASN, "AS15169")
        for e in res.edges
    )

    # LOCATION "Mountain View, United States" + located_in edge.
    locs = [e for e in res.entities if e.type == EntityType.LOCATION]
    assert locs and locs[0].value == "Mountain View, United States"
    assert any(e.relationship == RelationshipType.LOCATED_IN for e in res.edges)

    # DOMAIN "dns.google" with a resolves_to edge -> the IP.
    domains = [e for e in res.entities if e.type == EntityType.DOMAIN]
    assert any(e.value == "dns.google" for e in domains)
    assert any(
        e.relationship == RelationshipType.RESOLVES_TO
        and e.src == (EntityType.DOMAIN, "dns.google")
        and e.dst == (EntityType.IP, "8.8.8.8")
        for e in res.edges
    )

    # Seed IP enriched with open_ports.
    seed = [e for e in res.entities if e.type == EntityType.IP and e.value == "8.8.8.8"]
    assert seed and seed[0].attributes.get("open_ports") == [53, 443]

    # Provenance on everything.
    assert all(e.provenance.source_url for e in res.entities)


async def test_shodan_no_key_is_skipped(ctx_factory):
    ctx = ctx_factory()
    res = await ShodanCollector().run(EntityRef(EntityType.IP, "8.8.8.8"), ctx)
    assert res.status == JobStatus.SKIPPED
    assert res.entities == []


@respx.mock
async def test_shodan_404_is_empty_success(ctx_factory):
    respx.get(url__startswith="https://api.shodan.io/shodan/host/198.51.100.1").mock(
        return_value=httpx.Response(404)
    )
    ctx = ctx_factory(keys={"shodan": "K"})
    res = await ShodanCollector().run(EntityRef(EntityType.IP, "198.51.100.1"), ctx)
    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
    assert "No Shodan data" in res.message
