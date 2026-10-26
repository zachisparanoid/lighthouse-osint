"""IP geolocation collector — coarse city/country/ASN for an IP.

Public source: https://ipwho.is — a free, keyless, HTTPS IP-geolocation API. Returns only
coarse location (city/region/country), the hosting ASN, and the network operator. No
login-gated or private data.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_API = "https://ipwho.is"


class IPGeoCollector(Collector):
    name = "ip_geo"
    title = "IP Geolocation"
    description = "Resolve coarse geolocation (city/country), ASN, and network operator for an IP."
    accepts = {EntityType.IP}
    produces = {EntityType.LOCATION, EntityType.ORGANIZATION, EntityType.ASN}
    cost = CollectorCost.FREE
    rate_limit = "40/m"
    cache_ttl = 3600
    base_reliability = 65
    source_note = "Free IP geolocation API (ipwho.is). Coarse city/country/ASN only."

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        ip = target.value.strip()
        url = f"{_API}/{ip}"
        result = CollectorResult()
        await ctx.report(20, "Querying geolocation")

        resp = await ctx.http.get(url)
        if resp.status_code == 404:
            return CollectorResult(message=f"No geolocation for {ip}.")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            try:
                retry_after = int(retry) if retry is not None else 60
            except (TypeError, ValueError):
                retry_after = 60
            return CollectorResult.failed("rate limited by ipwho.is", retry_after=retry_after)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success"):
            msg = data.get("message", "lookup failed")
            return CollectorResult(message=f"No geolocation for {ip}: {msg}")

        await ctx.report(60, "Parsing geolocation")
        seed = (EntityType.IP, ip)
        connection = data.get("connection") or {}
        timezone = data.get("timezone") or {}

        city = data.get("city")
        region = data.get("region")
        country = data.get("country")
        loc_value = ", ".join(filter(None, [city, region, country]))
        if loc_value:
            result.add_entity(
                EntityType.LOCATION, loc_value,
                attributes={
                    "country_code": data.get("country_code"),
                    "latitude": data.get("latitude"),
                    "longitude": data.get("longitude"),
                    "timezone": timezone.get("id"),
                },
                source_url=url,
            )
            result.add_edge(seed, (EntityType.LOCATION, loc_value),
                            RelationshipType.LOCATED_IN, source_url=url)

        asn = connection.get("asn")
        if asn:
            asn_value = f"AS{asn}"
            result.add_entity(EntityType.ASN, asn_value,
                              attributes={"org": connection.get("org")}, source_url=url)
            result.add_edge(seed, (EntityType.ASN, asn_value),
                            RelationshipType.MEMBER_OF, source_url=url)

        org = connection.get("org") or connection.get("isp")
        if org:
            result.add_entity(EntityType.ORGANIZATION, org, source_url=url)
            result.add_edge(seed, (EntityType.ORGANIZATION, org),
                            RelationshipType.REFERENCES, source_url=url)

        await ctx.report(100)
        result.summary = {"country": country, "asn": connection.get("asn")}
        return result
