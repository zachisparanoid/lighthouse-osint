from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.wayback import WaybackCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType

_CDX_ROWS = [
    ["original", "timestamp", "statuscode", "mimetype"],
    ["http://example.com/", "20200101000000", "200", "text/html"],
    ["http://example.com/about", "20210101000000", "200", "text/html"],
]


@respx.mock
async def test_wayback_parses_snapshots(ctx_factory):
    respx.get(url__startswith="https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=_CDX_ROWS)
    )

    ctx = ctx_factory()
    res = await WaybackCollector().run(EntityRef(EntityType.DOMAIN, "example.com"), ctx)

    urls = [e for e in res.entities if e.type == EntityType.URL]
    # header row skipped -> exactly 2 archived URLs
    assert {e.value for e in urls} == {"http://example.com/", "http://example.com/about"}
    assert all(e.attributes.get("wayback_url") for e in urls)
    assert urls[0].attributes["wayback_url"].startswith("https://web.archive.org/web/")

    refs = [e for e in res.edges if e.relationship == RelationshipType.REFERENCES]
    assert refs and all(e.attributes.get("archived") is True for e in refs)
    assert all(e.provenance.source_url for e in res.entities)

    # seed enriched with snapshot count
    seed = [
        e for e in res.entities
        if e.type == EntityType.DOMAIN and e.value == "example.com" and "snapshot_count" in e.attributes
    ]
    assert seed and seed[0].attributes["snapshot_count"] == 2


@respx.mock
async def test_wayback_header_only_is_empty_success(ctx_factory):
    respx.get(url__startswith="https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(200, json=[["original", "timestamp", "statuscode", "mimetype"]])
    )

    ctx = ctx_factory()
    res = await WaybackCollector().run(EntityRef(EntityType.DOMAIN, "empty.invalid"), ctx)

    assert res.status == JobStatus.SUCCEEDED
    assert res.entities == []
