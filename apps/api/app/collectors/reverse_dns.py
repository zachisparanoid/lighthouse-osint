"""Reverse DNS (PTR) collector — public reverse DNS lookups for an IP.

Public source: the DNS system via a recursive resolver. Maps an IP to its PTR hostname(s).
This collector uses dnspython (not httpx); tests monkeypatch ``dns.asyncresolver.resolve``.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef


class ReverseDNSCollector(Collector):
    name = "reverse_dns"
    title = "Reverse DNS (PTR)"
    description = "Resolve the PTR (reverse DNS) hostname(s) for an IP via public DNS."
    accepts = {EntityType.IP}
    produces = {EntityType.DOMAIN, EntityType.SUBDOMAIN}
    cost = CollectorCost.FREE
    rate_limit = "60/m"
    cache_ttl = 3600
    base_reliability = 75
    source_note = "Public reverse DNS (PTR) lookups."

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        import dns.asyncresolver
        import dns.exception
        import dns.resolver
        import dns.reversename

        ip = target.value.strip()
        result = CollectorResult()
        src = f"dns://{ip}/PTR"
        await ctx.report(20, "Reverse DNS lookup")

        try:
            rev = dns.reversename.from_address(ip)
            answers = await dns.asyncresolver.resolve(rev, "PTR")
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.resolver.NoNameservers,
            dns.exception.Timeout,
        ):
            await ctx.report(100)
            return CollectorResult(message=f"No PTR record for {ip}.")
        except Exception:  # noqa: BLE001 — any resolver hiccup: empty success
            await ctx.report(100)
            return CollectorResult(message=f"No PTR record for {ip}.")

        for rdata in answers:
            hostname = str(getattr(rdata, "target", rdata)).rstrip(".")
            if not hostname:
                continue
            # The normalizer reclassifies subdomains automatically; emit as DOMAIN.
            result.add_entity(EntityType.DOMAIN, hostname, attributes={"role": "ptr"}, source_url=src)
            result.add_edge(
                (EntityType.DOMAIN, hostname), (EntityType.IP, ip), RelationshipType.RESOLVES_TO,
                attributes={"record": "PTR"}, source_url=src,
            )

        await ctx.report(100)
        result.summary = {"ptr_count": len([e for e in result.entities if e.type == EntityType.DOMAIN])}
        if not result.entities:
            result.message = f"No PTR record for {ip}."
        return result
