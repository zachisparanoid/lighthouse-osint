"""Email breach collector — Have I Been Pwned breached-account API (BYOK).

Keyed source: https://haveibeenpwned.com/api/v3 (requires the analyst's own HIBP key).
ETHICS: this collector requests ``truncateResponse=true`` so HIBP returns breach NAMES
ONLY — never passwords, hashes, or any breached content. It surfaces *which* breaches an
email address appeared in so an analyst can assess exposure, nothing more.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, KeyService, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_API = "https://haveibeenpwned.com/api/v3"


class EmailBreachCollector(Collector):
    name = "email_breach"
    title = "Email Breaches (HIBP)"
    description = "Check an email against Have I Been Pwned — returns the names of breaches it appeared in."
    accepts = {EntityType.EMAIL}
    produces = {EntityType.BREACH}
    cost = CollectorCost.KEYED
    requires_key = KeyService.HIBP
    rate_limit = "10/m"
    cache_ttl = 21600
    base_reliability = 85
    source_note = (
        "Have I Been Pwned breached-account API (requires your HIBP key). Returns breach "
        "NAMES ONLY — never passwords or breached content."
    )

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        key = await ctx.get_key("hibp")
        if not key:
            return CollectorResult.skipped(
                "Add a HIBP API key in Settings → Keys to enable this module."
            )

        email = target.value.strip()
        result = CollectorResult()
        await ctx.report(20, "Querying Have I Been Pwned")

        resp = await ctx.http.get(
            f"{_API}/breachedaccount/{email}",
            params={"truncateResponse": "true"},  # ethics: names only — no breached content
            headers={"hibp-api-key": key},
        )
        if resp.status_code == 404:
            return CollectorResult(message="No known breaches for this email.")
        if resp.status_code in (401, 403):
            return CollectorResult.failed("Invalid HIBP API key")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            try:
                retry_after = int(retry) if retry is not None else 60
            except (TypeError, ValueError):
                retry_after = 60
            return CollectorResult.failed("rate limited by HIBP", retry_after=retry_after)
        resp.raise_for_status()
        breaches = resp.json() or []

        await ctx.report(70, "Parsing breaches")
        seed = (EntityType.EMAIL, email)
        for item in breaches:
            name = (item or {}).get("Name")
            if not name:
                continue
            breach_url = "https://haveibeenpwned.com/PwnedWebsites#" + name
            result.add_entity(EntityType.BREACH, name, label=name, source_url=breach_url)
            result.add_edge(seed, (EntityType.BREACH, name),
                            RelationshipType.BREACHED_IN, source_url=breach_url)

        # Enrich the seed email with the breach count.
        result.add_entity(
            EntityType.EMAIL, email,
            attributes={"breach_count": len(breaches)},
        )

        await ctx.report(100)
        result.summary = {"breach_count": len(breaches)}
        return result
