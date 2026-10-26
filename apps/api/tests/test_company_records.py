from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.company_records import CompanyRecordsCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType

_SEARCH = {
    "results": {
        "companies": [
            {
                "company": {
                    "name": "Acme Inc",
                    "company_number": "123",
                    "jurisdiction_code": "us_de",
                    "incorporation_date": "2001-01-01",
                    "company_type": "Corporation",
                    "current_status": "Active",
                    "registered_address_in_full": "1 Main St, Dover, DE",
                    "opencorporates_url": "https://opencorporates.com/companies/us_de/123",
                }
            }
        ]
    }
}

_OFFICERS = {
    "results": {
        "company": {
            "officers": [
                {"officer": {"name": "Jane Roe", "position": "director"}},
            ]
        }
    }
}


@respx.mock
async def test_company_records_parses_company_and_officers(ctx_factory):
    respx.get(url__startswith="https://api.opencorporates.com/v0.4/companies/search").mock(
        return_value=httpx.Response(200, json=_SEARCH)
    )
    respx.get(url__startswith="https://api.opencorporates.com/v0.4/companies/us_de/123").mock(
        return_value=httpx.Response(200, json=_OFFICERS)
    )

    ctx = ctx_factory(keys={"opencorporates": "K"})
    res = await CompanyRecordsCollector().run(EntityRef(EntityType.ORGANIZATION, "Acme"), ctx)

    assert res.status == JobStatus.SUCCEEDED

    # ORGANIZATION "Acme Inc" with registry attributes + same_as edge from the seed.
    orgs = [e for e in res.entities if e.type == EntityType.ORGANIZATION]
    acme = next((e for e in orgs if e.value == "Acme Inc"), None)
    assert acme is not None
    assert acme.attributes.get("company_number") == "123"
    assert acme.attributes.get("jurisdiction") == "us_de"
    assert any(
        e.relationship == RelationshipType.SAME_AS and e.dst == (EntityType.ORGANIZATION, "Acme Inc")
        for e in res.edges
    )

    # LOCATION for the registered address + located_in edge.
    locs = [e for e in res.entities if e.type == EntityType.LOCATION]
    assert any(e.value == "1 Main St, Dover, DE" for e in locs)
    assert any(e.relationship == RelationshipType.LOCATED_IN for e in res.edges)

    # PERSON "Jane Roe" with member_of edge into the company.
    people = [e for e in res.entities if e.type == EntityType.PERSON]
    jane = next((e for e in people if e.value == "Jane Roe"), None)
    assert jane is not None
    assert jane.attributes.get("position") == "director"
    assert any(
        e.relationship == RelationshipType.MEMBER_OF
        and e.src == (EntityType.PERSON, "Jane Roe")
        and e.dst == (EntityType.ORGANIZATION, "Acme Inc")
        for e in res.edges
    )

    # Provenance on everything.
    assert all(e.provenance.source_url for e in res.entities)


async def test_company_records_no_key_is_skipped(ctx_factory):
    ctx = ctx_factory()
    res = await CompanyRecordsCollector().run(EntityRef(EntityType.ORGANIZATION, "Acme"), ctx)
    assert res.status == JobStatus.SKIPPED
    assert res.entities == []


@respx.mock
async def test_company_records_empty_results_is_empty_success(ctx_factory):
    respx.get(url__startswith="https://api.opencorporates.com/v0.4/companies/search").mock(
        return_value=httpx.Response(200, json={"results": {"companies": []}})
    )
    ctx = ctx_factory(keys={"opencorporates": "K"})
    res = await CompanyRecordsCollector().run(EntityRef(EntityType.ORGANIZATION, "Nope"), ctx)
    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
    assert "No company records" in res.message
