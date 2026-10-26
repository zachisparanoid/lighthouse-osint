from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.rdap_whois import RDAPWhoisCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType

_RDAP = {
    "objectClassName": "domain",
    "handle": "EXAMPLE-COM",
    "ldhName": "example.com",
    "status": ["client transfer prohibited"],
    "events": [
        {"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
        {"eventAction": "expiration", "eventDate": "2026-08-13T04:00:00Z"},
        {"eventAction": "last changed", "eventDate": "2024-08-14T07:01:44Z"},
    ],
    "entities": [
        {
            "roles": ["registrar"],
            "vcardArray": [
                "vcard",
                [
                    ["version", {}, "text", "4.0"],
                    ["fn", {}, "text", "Example Registrar, Inc."],
                    ["org", {}, "text", "Example Registrar, Inc."],
                    ["email", {}, "text", "abuse@registrar.test"],
                ],
            ],
        },
        {
            "roles": ["registrant"],
            "vcardArray": [
                "vcard",
                [
                    ["version", {}, "text", "4.0"],
                    ["fn", {}, "text", "REDACTED FOR PRIVACY"],
                    ["org", {}, "text", "REDACTED FOR PRIVACY"],
                    ["email", {}, "text", "Please query the RDAP server of the registrar"],
                ],
            ],
        },
    ],
    "nameservers": [
        {"ldhName": "ns1.example.com"},
        {"ldhName": "ns2.example.com"},
    ],
}


@respx.mock
async def test_rdap_whois_parses_registrar_and_dates(ctx_factory):
    respx.get("https://rdap.org/domain/example.com").mock(return_value=httpx.Response(200, json=_RDAP))

    ctx = ctx_factory()
    res = await RDAPWhoisCollector().run(EntityRef(EntityType.DOMAIN, "example.com"), ctx)

    # Registrar organization surfaced.
    orgs = [e for e in res.entities if e.type == EntityType.ORGANIZATION]
    assert any(e.value == "Example Registrar, Inc." for e in orgs)

    # A registered_by edge exists.
    assert any(e.relationship == RelationshipType.REGISTERED_BY for e in res.edges)

    # Seed carries registration + expiry dates.
    seed = [e for e in res.entities if e.type == EntityType.DOMAIN and e.value == "example.com"]
    assert seed and seed[0].attributes.get("registered_on") == "1995-08-14T04:00:00Z"
    assert seed[0].attributes.get("expires_on") == "2026-08-13T04:00:00Z"

    # Abuse email from the registrar surfaced.
    emails = [e for e in res.entities if e.type == EntityType.EMAIL]
    assert any(e.value == "abuse@registrar.test" for e in emails)

    # The REDACTED registrant is NOT created (neither person nor org nor its placeholder email).
    assert not any(e.type == EntityType.PERSON for e in res.entities)
    values = {e.value for e in res.entities}
    assert "REDACTED FOR PRIVACY" not in values
    assert not any("query the RDAP" in v for v in values)

    # Nameservers surfaced as DOMAIN entities with references edges.
    ns = [e for e in res.entities if e.type == EntityType.DOMAIN and e.value.startswith("ns")]
    assert {e.value for e in ns} == {"ns1.example.com", "ns2.example.com"}

    # Provenance on everything.
    assert all(e.provenance.source_url for e in res.entities)


@respx.mock
async def test_rdap_whois_404_is_empty_success(ctx_factory):
    respx.get("https://rdap.org/domain/nope.invalid").mock(return_value=httpx.Response(404))
    ctx = ctx_factory()
    res = await RDAPWhoisCollector().run(EntityRef(EntityType.DOMAIN, "nope.invalid"), ctx)
    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
    assert "No RDAP record" in res.message
