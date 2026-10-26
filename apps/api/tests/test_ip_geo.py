from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.ip_geo import IPGeoCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType

_GEO = {
    "success": True,
    "ip": "8.8.8.8",
    "type": "IPv4",
    "country": "United States",
    "country_code": "US",
    "region": "California",
    "city": "Mountain View",
    "latitude": 37.3860517,
    "longitude": -122.0838511,
    "timezone": {"id": "America/Los_Angeles"},
    "connection": {
        "asn": 15169,
        "org": "Google LLC",
        "isp": "Google LLC",
        "domain": "google.com",
    },
}


@respx.mock
async def test_ip_geo_parses_location_asn_org(ctx_factory):
    respx.get("https://ipwho.is/8.8.8.8").mock(return_value=httpx.Response(200, json=_GEO))

    ctx = ctx_factory()
    res = await IPGeoCollector().run(EntityRef(EntityType.IP, "8.8.8.8"), ctx)

    # LOCATION entity + located_in edge.
    locs = [e for e in res.entities if e.type == EntityType.LOCATION]
    assert locs and locs[0].value == "Mountain View, California, United States"
    assert locs[0].attributes.get("country_code") == "US"
    assert any(e.relationship == RelationshipType.LOCATED_IN for e in res.edges)

    # ASN entity "AS15169" + member_of edge.
    asns = [e for e in res.entities if e.type == EntityType.ASN]
    assert asns and asns[0].value == "AS15169"
    assert asns[0].attributes.get("org") == "Google LLC"
    assert any(
        e.relationship == RelationshipType.MEMBER_OF and e.dst == (EntityType.ASN, "AS15169")
        for e in res.edges
    )

    # ORGANIZATION entity + references edge.
    orgs = [e for e in res.entities if e.type == EntityType.ORGANIZATION]
    assert any(e.value == "Google LLC" for e in orgs)
    assert any(
        e.relationship == RelationshipType.REFERENCES and e.dst == (EntityType.ORGANIZATION, "Google LLC")
        for e in res.edges
    )

    # Provenance on everything.
    assert all(e.provenance.source_url == "https://ipwho.is/8.8.8.8" for e in res.entities)


@respx.mock
async def test_ip_geo_failure_is_empty_success(ctx_factory):
    respx.get("https://ipwho.is/192.0.2.1").mock(
        return_value=httpx.Response(200, json={"success": False, "message": "Reserved range"})
    )
    ctx = ctx_factory()
    res = await IPGeoCollector().run(EntityRef(EntityType.IP, "192.0.2.1"), ctx)

    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
    assert "No geolocation" in res.message
