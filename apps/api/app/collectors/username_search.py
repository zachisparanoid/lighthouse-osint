"""Username search collector — checks for a public profile page across ~30 platforms.

Ethics: requests ONLY public profile URLs (plain GET); never login-gated content, never
authenticates, never scrapes private data. A profile is considered to EXIST only when the
public URL returns HTTP 200. Every outbound request is gated through ``ctx.scope`` so the
denylist (e.g. ``*.gov`` / ``*.mil``) and non-HTTP(S) schemes are honoured.
"""
from __future__ import annotations

import asyncio

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import (
    CollectionContext,
    Collector,
    CollectorResult,
    EntityRef,
    ScopeViolation,
)

# platform name -> public-profile URL template ("{u}" = username). Public pages only.
PLATFORMS: dict[str, str] = {
    "github": "https://github.com/{u}",
    "gitlab": "https://gitlab.com/{u}",
    "twitter": "https://twitter.com/{u}",
    "instagram": "https://www.instagram.com/{u}/",
    "reddit": "https://www.reddit.com/user/{u}",
    "tiktok": "https://www.tiktok.com/@{u}",
    "medium": "https://medium.com/@{u}",
    "keybase": "https://keybase.io/{u}",
    "pinterest": "https://www.pinterest.com/{u}/",
    "soundcloud": "https://soundcloud.com/{u}",
    "twitch": "https://www.twitch.tv/{u}",
    "devto": "https://dev.to/{u}",
    "dockerhub": "https://hub.docker.com/u/{u}",
    "hackernews": "https://news.ycombinator.com/user?id={u}",
    "aboutme": "https://about.me/{u}",
    "patreon": "https://www.patreon.com/{u}",
    "telegram": "https://t.me/{u}",
    "youtube": "https://www.youtube.com/@{u}",
    "vimeo": "https://vimeo.com/{u}",
    "flickr": "https://www.flickr.com/people/{u}",
    "lastfm": "https://www.last.fm/user/{u}",
    "steam": "https://steamcommunity.com/id/{u}",
    "goodreads": "https://www.goodreads.com/{u}",
    "replit": "https://replit.com/@{u}",
    "codepen": "https://codepen.io/{u}",
    "bitbucket": "https://bitbucket.org/{u}/",
    "lobsters": "https://lobste.rs/u/{u}",
    "mastodon": "https://mastodon.social/@{u}",
    "gravatar": "https://gravatar.com/{u}",
    "producthunt": "https://www.producthunt.com/@{u}",
}

_CONCURRENCY = 8


class UsernameSearchCollector(Collector):
    name = "username_search"
    title = "Username Search"
    description = "Check whether a username has a public profile page across ~30 platforms."
    accepts = {EntityType.USERNAME}
    produces = {EntityType.SOCIAL_PROFILE}
    cost = CollectorCost.FREE
    rate_limit = "30/m"
    cache_ttl = 3600
    base_reliability = 55
    source_note = (
        "Checks for a public profile page across ~30 platforms. Requests only public "
        "profile URLs (GET); never login-gated content."
    )

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        username = target.value.strip().lstrip("@")
        result = CollectorResult()
        sem = asyncio.Semaphore(_CONCURRENCY)
        done = 0
        total = len(PLATFORMS)

        async def check(platform: str, template: str) -> tuple[str, str] | None:
            nonlocal done
            url = template.format(u=username)
            hit: tuple[str, str] | None = None
            async with sem:
                try:
                    ctx.scope.assert_url_allowed(url)
                except ScopeViolation:
                    pass
                else:
                    try:
                        resp = await ctx.http.get(url)
                        if resp.status_code == 200:
                            hit = (platform, url)
                    except Exception:  # noqa: BLE001 — timeouts/conn errors == not found
                        hit = None
            done += 1
            # Report progress periodically without spamming.
            if done % _CONCURRENCY == 0 or done == total:
                await ctx.report(int((done / total) * 100), f"Checked {done}/{total} platforms")
            return hit

        await ctx.report(0, f"Checking {total} platforms")
        results = await asyncio.gather(*(check(p, t) for p, t in PLATFORMS.items()))

        found = 0
        for hit in results:
            if hit is None:
                continue
            platform, url = hit
            found += 1
            result.add_entity(
                EntityType.SOCIAL_PROFILE,
                url,
                label=f"{platform}: {username}",
                attributes={"platform": platform, "status": 200},
                base_confidence=55,
                source_url=url,
            )
            result.add_edge(
                (EntityType.USERNAME, username),
                (EntityType.SOCIAL_PROFILE, url),
                RelationshipType.SAME_AS,
                source_url=url,
            )

        result.summary = {"checked": total, "found": found}
        if found == 0:
            result.message = f"No public profiles found for '{username}'."
        return result
