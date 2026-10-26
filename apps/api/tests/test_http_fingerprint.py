from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.http_fingerprint import HTTPFingerprintCollector
from lighthouse_shared import EntityType, JobStatus, RelationshipType

_BODY = (
    "<html><head><title>Example Domain</title>"
    "<meta name=generator content=WordPress></head>"
    "<body>Hello</body></html>"
)


@respx.mock
async def test_http_fingerprint_extracts_title_server_tech(ctx_factory):
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nAllow: /")
    )
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(
            200, text=_BODY, headers={"Server": "nginx", "Content-Type": "text/html"}
        )
    )

    ctx = ctx_factory()
    res = await HTTPFingerprintCollector().run(EntityRef(EntityType.DOMAIN, "example.com"), ctx)

    urls = [e for e in res.entities if e.type == EntityType.URL]
    assert urls, "expected a URL entity"
    attrs = urls[0].attributes
    assert attrs["title"] == "Example Domain"
    assert attrs["server"] == "nginx"
    assert "wordpress" in attrs["tech"]

    # references edge from the seed domain to the discovered URL
    refs = [e for e in res.edges if e.relationship == RelationshipType.REFERENCES]
    assert any(e.src == (EntityType.DOMAIN, "example.com") for e in refs)
    assert all(e.provenance.source_url for e in res.entities)


@respx.mock
async def test_http_fingerprint_respects_robots_disallow(ctx_factory):
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /")
    )

    ctx = ctx_factory()
    res = await HTTPFingerprintCollector().run(EntityRef(EntityType.DOMAIN, "example.com"), ctx)

    assert res.status == JobStatus.SKIPPED
    assert res.entities == []
