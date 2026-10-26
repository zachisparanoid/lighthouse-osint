from __future__ import annotations

import httpx
import respx

from app.collectors.base import EntityRef
from app.collectors.github_user import GitHubUserCollector
from lighthouse_shared import EntityType, RelationshipType

_USER = {
    "login": "octocat",
    "name": "The Octocat",
    "html_url": "https://github.com/octocat",
    "avatar_url": "https://avatars.example/octocat.png",
    "email": "octo@github.com",
    "company": "@GitHub",
    "blog": "https://octocat.example",
    "location": "San Francisco",
    "twitter_username": "octocat",
    "public_repos": 8,
    "followers": 1000,
    "created_at": "2011-01-25T18:44:36Z",
}
_REPOS = [
    {"full_name": "octocat/Hello-World", "html_url": "https://github.com/octocat/Hello-World",
     "stargazers_count": 2000, "language": "Python"},
    {"full_name": "octocat/spoon", "html_url": "https://github.com/octocat/spoon",
     "stargazers_count": 5, "language": "Go"},
]


@respx.mock
async def test_github_user_links_identities(ctx_factory):
    respx.get("https://api.github.com/users/octocat").mock(return_value=httpx.Response(200, json=_USER))
    respx.get(url__startswith="https://api.github.com/users/octocat/repos").mock(
        return_value=httpx.Response(200, json=_REPOS)
    )

    ctx = ctx_factory()
    res = await GitHubUserCollector().run(EntityRef(EntityType.USERNAME, "octocat"), ctx)

    types_seen = {e.type for e in res.entities}
    assert EntityType.SOCIAL_PROFILE in types_seen
    assert EntityType.EMAIL in types_seen
    assert EntityType.ORGANIZATION in types_seen
    assert EntityType.LOCATION in types_seen

    # email <-> username same_as edge (the canonical public-profile linkage)
    same_as = [e for e in res.edges if e.relationship == RelationshipType.SAME_AS]
    assert any(e.dst == (EntityType.EMAIL, "octo@github.com") for e in same_as)

    # top repo surfaced as a URL with a references edge
    assert any(e.type == EntityType.URL and "Hello-World" in (e.label or "") for e in res.entities)


@respx.mock
async def test_github_user_404_is_empty_success(ctx_factory):
    respx.get("https://api.github.com/users/ghost").mock(return_value=httpx.Response(404))
    ctx = ctx_factory()
    res = await GitHubUserCollector().run(EntityRef(EntityType.USERNAME, "ghost"), ctx)
    assert res.entities == []
    assert "No public GitHub user" in res.message
