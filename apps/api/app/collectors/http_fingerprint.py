"""HTTP fingerprint collector — a polite, single HTTP(S) fetch of a public page.

Public source: the target's own web server. Captures the page title, ``Server`` /
``X-Powered-By`` headers, and lightweight technology hints. It identifies itself via the
configured User-Agent, honors robots.txt, enforces the scope/SSRF guard, and never
attempts to bypass authentication.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import (
    CollectionContext,
    Collector,
    CollectorResult,
    EntityRef,
    ScopeViolation,
)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TECH_HINTS = [
    "wordpress", "drupal", "nginx", "apache", "cloudflare", "react",
    "next.js", "django", "express", "shopify", "wix",
]


class HTTPFingerprintCollector(Collector):
    name = "http_fingerprint"
    title = "HTTP Fingerprint"
    description = "Polite HTTP(S) fetch of a public page: title, Server header, and technology hints."
    accepts = {EntityType.DOMAIN, EntityType.SUBDOMAIN, EntityType.URL, EntityType.IP}
    produces = {EntityType.URL}
    cost = CollectorCost.FREE
    rate_limit = "30/m"
    base_reliability = 70
    source_note = (
        "Polite HTTP(S) fetch: title, Server header, tech hints. "
        "Honors robots.txt, identifies via User-Agent, never bypasses auth."
    )

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        result = CollectorResult()

        if target.type == EntityType.URL:
            candidate = target.value.strip()
        else:
            candidate = f"https://{target.value.strip()}"

        # --- Scope / SSRF guard ---
        try:
            ctx.scope.assert_url_allowed(candidate)
        except ScopeViolation as e:
            return CollectorResult.skipped(str(e))

        await ctx.report(20, "Checking robots.txt")

        # --- robots.txt ---
        parsed = urlparse(candidate)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        user_agent = ctx.settings.http_user_agent
        try:
            robots_resp = await ctx.http.get(robots_url)
            if robots_resp.status_code == 200:
                rp = RobotFileParser()
                rp.parse(robots_resp.text.splitlines())
                if not rp.can_fetch(user_agent, candidate):
                    return CollectorResult.skipped("robots.txt disallows fetching this path")
        except Exception:  # noqa: BLE001 — no/unreachable robots.txt means fetching is allowed
            pass

        await ctx.report(50, "Fetching page")

        # --- Fetch the page ---
        try:
            resp = await ctx.http.get(candidate)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TransportError):
            return CollectorResult(message=f"Site unreachable: {candidate}")

        status = resp.status_code
        final_url = str(resp.url)
        server = resp.headers.get("Server")
        xpb = resp.headers.get("X-Powered-By")
        ctype = resp.headers.get("Content-Type")

        body = resp.text
        title = None
        m = _TITLE_RE.search(body)
        if m:
            title = m.group(1).strip()[:300]

        # --- Tech hints from headers + body (lowercased) ---
        haystack = " ".join(
            [
                (server or ""),
                (xpb or ""),
                (ctype or ""),
                body,
            ]
        ).lower()
        tech_list = [hint for hint in _TECH_HINTS if hint in haystack]

        result.add_entity(
            EntityType.URL,
            final_url,
            label=title or final_url,
            attributes={
                "status": status,
                "server": server,
                "powered_by": xpb,
                "title": title,
                "content_type": ctype,
                "tech": tech_list,
            },
            source_url=final_url,
        )
        result.add_edge(
            (target.type, target.value),
            (EntityType.URL, final_url),
            RelationshipType.REFERENCES,
            source_url=final_url,
        )

        result.summary = {"status": status, "tech": tech_list}
        await ctx.report(100)
        return result
