"""Shodan host collector — passive host intel from Shodan's existing scan data (BYOK).

Keyed source: https://api.shodan.io (requires the analyst's own API key). Uses scan data
Shodan has *already* collected from public hosts — this collector never initiates a scan.
Surfaces the host's network operator, ASN, coarse location, and any hostnames Shodan
observed resolving to the IP, plus open ports / OS as attributes on the seed.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, KeyService, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_API = "https://api.shodan.io"


class ShodanCollector(Collector):
    name = "shodan"
    title = "Shodan"
    description = "Look up a host on Shodan: network operator, ASN, location, hostnames, open ports."
    accepts = {EntityType.IP}
    produces = {
        EntityType.URL, EntityType.ORGANIZATION, EntityType.LOCATION,
        EntityType.ASN, EntityType.DOMAIN,
    }
    cost = CollectorCost.KEYED
    requires_key = KeyService.SHODAN
    rate_limit = "60/m"
    cache_ttl = 21600
    base_reliability = 80
    source_note = (
        "Shodan host API (requires your API key). Uses scan data Shodan already collected "
        "from public hosts."
    )

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        key = await ctx.get_key("shodan")
        if not key:
            return CollectorResult.skipped(
                "Add a Shodan API key in Settings → Keys to enable this module."
            )

        ip = target.value.strip()
        result = CollectorResult()
        await ctx.report(15, "Querying Shodan")

        resp = await ctx.http.get(f"{_API}/shodan/host/{ip}", params={"key": key})
        if resp.status_code == 404:
            return CollectorResult(message=f"No Shodan data for {ip}.")
        if resp.status_code in (401, 403):
            return CollectorResult.failed("Invalid Shodan API key")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            try:
                retry_after = int(retry) if retry is not None else 60
            except (TypeError, ValueError):
                retry_after = 60
            return CollectorResult.failed("rate limited by Shodan", retry_after=retry_after)
        resp.raise_for_status()
        data = resp.json()

        await ctx.report(60, "Parsing host data")
        source_url = f"https://www.shodan.io/host/{ip}"
        seed = (EntityType.IP, ip)

        ports = data.get("ports") or []
        os_name = data.get("os")
        # Enrich the seed IP with the passive scan summary.
        result.add_entity(
            EntityType.IP, ip,
            attributes={"open_ports": ports, "os": os_name},
            source_url=source_url,
        )

        org = data.get("org") or data.get("isp")
        if org:
            result.add_entity(EntityType.ORGANIZATION, org, source_url=source_url)
            result.add_edge(seed, (EntityType.ORGANIZATION, org),
                            RelationshipType.REFERENCES, source_url=source_url)

        asn = data.get("asn")
        if asn:
            asn_value = asn if str(asn).upper().startswith("AS") else f"AS{asn}"
            result.add_entity(EntityType.ASN, asn_value, source_url=source_url)
            result.add_edge(seed, (EntityType.ASN, asn_value),
                            RelationshipType.MEMBER_OF, source_url=source_url)

        city = data.get("city")
        country = data.get("country_name")
        loc_value = ", ".join(filter(None, [city, country]))
        if loc_value:
            result.add_entity(EntityType.LOCATION, loc_value, source_url=source_url)
            result.add_edge(seed, (EntityType.LOCATION, loc_value),
                            RelationshipType.LOCATED_IN, source_url=source_url)

        for host in data.get("hostnames") or []:
            host = (host or "").strip().rstrip(".")
            if not host:
                continue
            result.add_entity(EntityType.DOMAIN, host, source_url=source_url)
            result.add_edge((EntityType.DOMAIN, host), seed,
                            RelationshipType.RESOLVES_TO, source_url=source_url)

        await ctx.report(100)
        result.summary = {
            "open_ports": ports,
            "org": org,
            "hostnames": data.get("hostnames") or [],
        }
        return result
