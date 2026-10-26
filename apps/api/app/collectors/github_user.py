"""GitHub user collector — public GitHub REST API (no auth required).

Public source: https://api.github.com (public profile + public repos only). Links the
username to its profile, public email (if the user published it), company, blog, location,
and linked Twitter/X handle — the canonical "email↔username from a public profile" case.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_API = "https://api.github.com"
_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
_USER_FIELDS = (
    "name", "company", "blog", "location", "bio", "public_repos",
    "public_gists", "followers", "following", "created_at", "twitter_username",
)


class GitHubUserCollector(Collector):
    name = "github_user"
    title = "GitHub User"
    description = "Resolve a username against the public GitHub API: profile, repos, linked identities."
    accepts = {EntityType.USERNAME}
    produces = {
        EntityType.SOCIAL_PROFILE, EntityType.EMAIL, EntityType.ORGANIZATION,
        EntityType.URL, EntityType.LOCATION, EntityType.USERNAME,
    }
    cost = CollectorCost.FREE
    rate_limit = "50/h"  # unauthenticated GitHub API is ~60 req/h per IP; stay well under.
    cache_ttl = 21600
    base_reliability = 80
    source_note = "Public GitHub REST API — public profile/repos only, no authentication."

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        login = target.value.strip().lstrip("@")
        result = CollectorResult()
        await ctx.report(10, "Fetching profile")

        resp = await ctx.http.get(f"{_API}/users/{login}", headers=_HEADERS)
        if resp.status_code == 404:
            return CollectorResult(message=f"No public GitHub user '{login}'.")
        resp.raise_for_status()
        u = resp.json()
        profile_url = u.get("html_url")
        excerpt = {k: u.get(k) for k in _USER_FIELDS if u.get(k) is not None}

        # Enrich the username node.
        result.add_entity(
            EntityType.USERNAME, login, label=u.get("name") or login,
            attributes=excerpt, source_url=profile_url, raw_excerpt=excerpt,
        )

        if profile_url:
            result.add_entity(
                EntityType.SOCIAL_PROFILE, profile_url, label=f"GitHub: {login}",
                attributes={"platform": "github", "avatar": u.get("avatar_url")}, source_url=profile_url,
            )
            result.add_edge((EntityType.USERNAME, login), (EntityType.SOCIAL_PROFILE, profile_url),
                            RelationshipType.SAME_AS, source_url=profile_url)

        if u.get("email"):
            result.add_entity(EntityType.EMAIL, u["email"], source_url=profile_url)
            result.add_edge((EntityType.USERNAME, login), (EntityType.EMAIL, u["email"]),
                            RelationshipType.SAME_AS, attributes={"via": "github_profile"}, source_url=profile_url)

        if u.get("company"):
            org = u["company"].lstrip("@").strip()
            result.add_entity(EntityType.ORGANIZATION, org, source_url=profile_url)
            result.add_edge((EntityType.USERNAME, login), (EntityType.ORGANIZATION, org),
                            RelationshipType.MEMBER_OF, source_url=profile_url)

        blog = (u.get("blog") or "").strip()
        if blog:
            url = blog if "://" in blog else f"https://{blog}"
            result.add_entity(EntityType.URL, url, source_url=profile_url)
            result.add_edge((EntityType.USERNAME, login), (EntityType.URL, url),
                            RelationshipType.REFERENCES, source_url=profile_url)

        if u.get("location"):
            result.add_entity(EntityType.LOCATION, u["location"], source_url=profile_url)
            result.add_edge((EntityType.USERNAME, login), (EntityType.LOCATION, u["location"]),
                            RelationshipType.LOCATED_IN, source_url=profile_url)

        if u.get("twitter_username"):
            turl = f"https://twitter.com/{u['twitter_username']}"
            result.add_entity(EntityType.SOCIAL_PROFILE, turl, label=f"Twitter/X: {u['twitter_username']}",
                              attributes={"platform": "twitter"}, source_url=profile_url)
            result.add_edge((EntityType.USERNAME, login), (EntityType.SOCIAL_PROFILE, turl),
                            RelationshipType.SAME_AS, source_url=profile_url)

        await ctx.report(60, "Fetching repositories")
        await self._collect_repos(ctx, login, result)

        await ctx.report(100)
        result.summary = {
            "name": u.get("name"), "public_repos": u.get("public_repos"), "followers": u.get("followers"),
        }
        return result

    async def _collect_repos(self, ctx: CollectionContext, login: str, result: CollectorResult) -> None:
        try:
            resp = await ctx.http.get(
                f"{_API}/users/{login}/repos",
                params={"per_page": 100, "sort": "pushed"},
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                return
            repos = resp.json()
        except Exception:  # noqa: BLE001 — repos are a nice-to-have; never fail the whole job
            return

        languages: dict[str, int] = {}
        for repo in repos:
            lang = repo.get("language")
            if lang:
                languages[lang] = languages.get(lang, 0) + 1

        top = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)[:3]
        for repo in top:
            url = repo.get("html_url")
            if not url:
                continue
            result.add_entity(
                EntityType.URL, url, label=repo.get("full_name"),
                attributes={"stars": repo.get("stargazers_count"), "language": repo.get("language")},
                source_url=url,
            )
            result.add_edge((EntityType.USERNAME, login), (EntityType.URL, url),
                            RelationshipType.REFERENCES, attributes={"kind": "repository"}, source_url=url)

        if languages:
            top_langs = sorted(languages, key=languages.get, reverse=True)[:5]
            result.add_entity(EntityType.USERNAME, login, attributes={"top_languages": top_langs})
