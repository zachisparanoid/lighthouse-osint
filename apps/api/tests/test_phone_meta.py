from __future__ import annotations

from app.collectors.base import EntityRef
from app.collectors.phone_meta import PhoneMetaCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType


async def test_phone_meta_us_number(ctx_factory):
    ctx = ctx_factory()
    res = await PhoneMetaCollector().run(EntityRef(EntityType.PHONE, "+14155552671"), ctx)

    assert res.status == JobStatus.SUCCEEDED

    # Seed phone enriched with metadata.
    phones = [e for e in res.entities if e.type == EntityType.PHONE]
    assert phones
    attrs = phones[0].attributes
    assert attrs["region"] == "US"
    assert attrs["line_type"]  # some non-empty mapped string
    assert isinstance(attrs["timezones"], list)

    # LOCATION entity + LOCATED_IN edge.
    locations = [e for e in res.entities if e.type == EntityType.LOCATION]
    assert locations
    loc_value = locations[0].value
    located_in = [e for e in res.edges if e.relationship == RelationshipType.LOCATED_IN]
    assert any(
        e.src == (EntityType.PHONE, "+14155552671")
        and e.dst == (EntityType.LOCATION, loc_value)
        for e in located_in
    )

    # Library-derived provenance: license_note set, no source_url.
    assert phones[0].provenance.license_note
    assert phones[0].provenance.source_url is None


async def test_phone_meta_invalid_is_empty_success(ctx_factory):
    ctx = ctx_factory()
    res = await PhoneMetaCollector().run(EntityRef(EntityType.PHONE, "not-a-phone"), ctx)

    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
    assert res.edges == []
    assert "Unparseable" in res.message
