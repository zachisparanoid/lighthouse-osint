from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.cert_transparency import CertTransparencyCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType

_ROWS = [
    {
        "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
        "common_name": "www.example.com",
        "name_value": "www.example.com\nexample.com\n*.example.com",
        "id": 111,
        "not_before": "2023-01-01T00:00:00",
        "not_after": "2023-04-01T00:00:00",
        "serial_number": "AAAA1111",
    },
    {
        "issuer_name": "C=US, O=Let's Encrypt, CN=R3",
        "common_name": "mail.example.com",
        "name_value": "mail.example.com\nwww.example.com",
        "id": 222,
        "not_before": "2023-02-01T00:00:00",
        "not_after": "2023-05-01T00:00:00",
        "serial_number": "BBBB2222",
    },
]


@respx.mock
async def test_cert_transparency_enumerates_subdomains_and_certs(ctx_factory):
    respx.get(url__startswith="https://crt.sh/").mock(return_value=httpx.Response(200, json=_ROWS))

    ctx = ctx_factory()
    res = await CertTransparencyCollector().run(EntityRef(EntityType.DOMAIN, "example.com"), ctx)

    subs = {e.value for e in res.entities if e.type == EntityType.SUBDOMAIN}
    assert "www.example.com" in subs
    assert "mail.example.com" in subs
    # wildcard stripped to bare domain (no "*." entries)
    assert not any(s.startswith("*.") for s in subs)
    assert "*.example.com" not in subs

    # dedup: www appears in two rows -> a single subdomain entity
    www_entities = [e for e in res.entities if e.type == EntityType.SUBDOMAIN and e.value == "www.example.com"]
    assert len(www_entities) == 1

    # subdomain_of edges exist for the subdomains
    sub_edges = [e for e in res.edges if e.relationship == RelationshipType.SUBDOMAIN_OF]
    assert any(e.src == (EntityType.SUBDOMAIN, "www.example.com") for e in sub_edges)
    assert all(e.dst == (EntityType.DOMAIN, "example.com") for e in sub_edges)

    # at least one certificate entity + a uses_certificate edge
    certs = [e for e in res.entities if e.type == EntityType.CERTIFICATE]
    assert len(certs) >= 1
    uses = [e for e in res.edges if e.relationship == RelationshipType.USES_CERTIFICATE]
    assert uses and all(e.src == (EntityType.DOMAIN, "example.com") for e in uses)

    # every emitted entity/edge carries provenance
    assert all(e.provenance.source_url for e in res.entities)
    assert all(e.provenance.source_url for e in res.edges)

    # seed enriched
    seed = [
        e for e in res.entities
        if e.type == EntityType.DOMAIN and e.value == "example.com" and "subdomains_found" in e.attributes
    ]
    assert seed and seed[0].attributes["subdomains_found"] >= 2


@respx.mock
async def test_cert_transparency_empty_is_success(ctx_factory):
    respx.get(url__startswith="https://crt.sh/").mock(return_value=httpx.Response(200, json=[]))

    ctx = ctx_factory()
    res = await CertTransparencyCollector().run(EntityRef(EntityType.DOMAIN, "nothing.invalid"), ctx)

    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
