from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.username_search import PLATFORMS, UsernameSearchCollector
from lighthouse_shared import EntityType, RelationshipType


def test_platforms_has_about_30_public_templates():
    # Sanity: ~30 platforms, every template is a public profile URL with the {u} slot.
    assert len(PLATFORMS) >= 25
    for name, template in PLATFORMS.items():
        assert "{u}" in template, name
        assert template.startswith("https://"), name


@respx.mock
async def test_username_search_only_200_counts(ctx_factory):
    # respx 0.23 matches routes in registration order (first match wins), so register the
    # specific "exists" overrides BEFORE the catch-all "not found" default.
    respx.get("https://github.com/jdoe").mock(return_value=httpx.Response(200))
    respx.get("https://t.me/jdoe").mock(return_value=httpx.Response(200))
    respx.route().mock(return_value=httpx.Response(404))

    ctx = ctx_factory()
    res = await UsernameSearchCollector().run(EntityRef(EntityType.USERNAME, "jdoe"), ctx)

    profiles = {e.value for e in res.entities if e.type == EntityType.SOCIAL_PROFILE}
    assert profiles == {"https://github.com/jdoe", "https://t.me/jdoe"}

    # Each found profile gets a SAME_AS edge from the username.
    same_as = [e for e in res.edges if e.relationship == RelationshipType.SAME_AS]
    assert {e.dst for e in same_as} == {
        (EntityType.SOCIAL_PROFILE, "https://github.com/jdoe"),
        (EntityType.SOCIAL_PROFILE, "https://t.me/jdoe"),
    }
    assert all(e.src == (EntityType.USERNAME, "jdoe") for e in same_as)

    # A 404 platform (e.g. gitlab) must NOT appear.
    assert "https://gitlab.com/jdoe" not in profiles

    assert res.summary == {"checked": len(PLATFORMS), "found": 2}


@respx.mock
async def test_username_search_strips_at_prefix(ctx_factory):
    respx.get("https://github.com/jdoe").mock(return_value=httpx.Response(200))
    respx.route().mock(return_value=httpx.Response(404))

    ctx = ctx_factory()
    res = await UsernameSearchCollector().run(EntityRef(EntityType.USERNAME, "@jdoe"), ctx)

    profiles = [e for e in res.entities if e.type == EntityType.SOCIAL_PROFILE]
    assert len(profiles) == 1
    assert profiles[0].value == "https://github.com/jdoe"
    assert profiles[0].attributes == {"platform": "github", "status": 200}


@respx.mock
async def test_username_search_none_found_is_empty_success(ctx_factory):
    respx.route().mock(return_value=httpx.Response(404))
    ctx = ctx_factory()
    res = await UsernameSearchCollector().run(EntityRef(EntityType.USERNAME, "ghost"), ctx)
    assert res.entities == []
    assert res.summary["found"] == 0
    assert "No public profiles" in res.message
