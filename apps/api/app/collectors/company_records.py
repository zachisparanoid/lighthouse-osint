"""Company records collector — OpenCorporates public company-filings API (BYOK).

Keyed source: https://api.opencorporates.com/v0.4 (requires the analyst's own API token).
Public company-registry data only: it searches the registry for matching companies, surfaces
their jurisdiction / number / status / registered address, and — for the top match — the
officers (directors, etc.) on file. All of this is public filing data.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, KeyService, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_API = "https://api.opencorporates.com/v0.4"


class CompanyRecordsCollector(Collector):
    name = "company_records"
    title = "Company Records (OpenCorporates)"
    description = "Search public company registries (OpenCorporates) for matching companies and officers."
    accepts = {EntityType.ORGANIZATION}
    produces = {EntityType.ORGANIZATION, EntityType.PERSON, EntityType.LOCATION}
    cost = CollectorCost.KEYED
    requires_key = KeyService.OPENCORPORATES
    rate_limit = "20/m"
    cache_ttl = 86400
    base_reliability = 75
    source_note = (
        "OpenCorporates public company-filings API (requires your API token). Public registry "
        "data only."
    )

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        key = await ctx.get_key("opencorporates")
        if not key:
            return CollectorResult.skipped(
                "Add a OpenCorporates API key in Settings → Keys to enable this module."
            )

        org_name = target.value.strip()
        result = CollectorResult()
        await ctx.report(15, "Searching OpenCorporates")

        resp = await ctx.http.get(
            f"{_API}/companies/search",
            params={"q": org_name, "api_token": key, "per_page": 5},
        )
        if resp.status_code in (401, 403):
            return CollectorResult.failed("Invalid OpenCorporates token")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            try:
                retry_after = int(retry) if retry is not None else 60
            except (TypeError, ValueError):
                retry_after = 60
            return CollectorResult.failed("rate limited by OpenCorporates", retry_after=retry_after)
        resp.raise_for_status()
        data = resp.json() or {}

        companies = ((data.get("results") or {}).get("companies")) or []
        if not companies:
            return CollectorResult(message=f"No company records found for '{org_name}'.")

        await ctx.report(55, "Parsing company records")
        for idx, wrapper in enumerate(companies[:5]):
            company = (wrapper or {}).get("company") or {}
            name = company.get("name")
            if not name:
                continue
            oc_url = company.get("opencorporates_url")
            jurisdiction = company.get("jurisdiction_code")
            number = company.get("company_number")

            result.add_entity(
                EntityType.ORGANIZATION, name,
                attributes={
                    "company_number": number,
                    "jurisdiction": jurisdiction,
                    "incorporation_date": company.get("incorporation_date"),
                    "status": company.get("current_status"),
                    "type": company.get("company_type"),
                    "opencorporates_url": oc_url,
                },
                source_url=oc_url,
            )
            if name != target.value:
                result.add_edge((EntityType.ORGANIZATION, target.value), (EntityType.ORGANIZATION, name),
                                RelationshipType.SAME_AS, source_url=oc_url)

            address = company.get("registered_address_in_full")
            if address:
                result.add_entity(EntityType.LOCATION, address, source_url=oc_url)
                result.add_edge((EntityType.ORGANIZATION, name), (EntityType.LOCATION, address),
                                RelationshipType.LOCATED_IN, source_url=oc_url)

            # For the top match only, fetch officers (directors, etc.).
            if idx == 0 and jurisdiction and number:
                await self._collect_officers(ctx, key, jurisdiction, number, name, oc_url, result)

        await ctx.report(100)
        result.summary = {"matches": len(companies)}
        return result

    async def _collect_officers(
        self, ctx: CollectionContext, key: str, jurisdiction: str, number: str,
        company_name: str, oc_url: str | None, result: CollectorResult,
    ) -> None:
        try:
            resp = await ctx.http.get(
                f"{_API}/companies/{jurisdiction}/{number}",
                params={"api_token": key},
            )
            if resp.status_code != 200:
                return
            company = ((resp.json() or {}).get("results") or {}).get("company") or {}
        except Exception:  # noqa: BLE001 — officers are a nice-to-have; never fail the whole job
            return

        for wrapper in (company.get("officers") or [])[:10]:
            officer = (wrapper or {}).get("officer") or {}
            name = officer.get("name")
            if not name:
                continue
            result.add_entity(
                EntityType.PERSON, name,
                attributes={"position": officer.get("position")},
                source_url=oc_url,
            )
            result.add_edge((EntityType.PERSON, name), (EntityType.ORGANIZATION, company_name),
                            RelationshipType.MEMBER_OF, source_url=oc_url)
