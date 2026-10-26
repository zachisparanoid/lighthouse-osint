"""DNS records collector — public recursive DNS lookups (A/AAAA/MX/NS/CNAME/TXT/SOA).

Public source: the DNS system via a recursive resolver. No private zones, no AXFR.
This collector uses dnspython (not httpx); tests monkeypatch ``dns.asyncresolver.resolve``.
"""
from __future__ import annotations

from lighthouse_shared import CollectorCost, EntityType, JobStatus, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_RECORD_TYPES = ["A", "AAAA", "MX", "NS", "CNAME", "TXT", "SOA"]


class DNSRecordsCollector(Collector):
    name = "dns_records"
    title = "DNS Records"
    description = "Resolve A/AAAA/MX/NS/CNAME/TXT/SOA records for a domain via public DNS."
    accepts = {EntityType.DOMAIN, EntityType.SUBDOMAIN}
    produces = {EntityType.IP, EntityType.DOMAIN, EntityType.SUBDOMAIN}
    cost = CollectorCost.FREE
    rate_limit = "60/m"
    cache_ttl = 3600
    base_reliability = 85
    source_note = "Authoritative public DNS via a recursive resolver. No zone transfers."

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        import dns.asyncresolver
        import dns.exception
        import dns.resolver

        name = target.value.strip().rstrip(".")
        result = CollectorResult()
        txt_records: list[str] = []
        found_any = False

        for i, rtype in enumerate(_RECORD_TYPES):
            await ctx.report(int((i / len(_RECORD_TYPES)) * 90), f"DNS {rtype}")
            src = f"dns://{name}/{rtype}"
            try:
                answers = await dns.asyncresolver.resolve(name, rtype)
            except (
                dns.resolver.NXDOMAIN,
                dns.resolver.NoAnswer,
                dns.resolver.NoNameservers,
                dns.exception.Timeout,
            ):
                continue
            except Exception:  # noqa: BLE001 — any resolver hiccup: skip this record type
                continue

            found_any = True
            for rdata in answers:
                self._handle(result, target, name, rtype, rdata, src, txt_records)

        # Fold scalar findings (TXT/SOA) back onto the seed entity as attributes.
        if txt_records:
            has_spf = any(t.lower().startswith("v=spf1") for t in txt_records)
            has_dmarc = any("dmarc" in t.lower() for t in txt_records)
            result.add_entity(
                target.type,
                name,
                attributes={"txt_records": txt_records, "has_spf": has_spf, "has_dmarc": has_dmarc},
                source_url=f"dns://{name}/TXT",
            )

        result.summary = {
            "records_found": len(result.entities) + len(result.edges),
            "txt_count": len(txt_records),
        }
        if not found_any:
            result.status = JobStatus.SUCCEEDED
            result.message = f"No DNS records resolved for {name}."
        await ctx.report(100)
        return result

    def _handle(self, result, target, name, rtype, rdata, src, txt_records) -> None:
        seed = (target.type, name)
        if rtype in ("A", "AAAA"):
            ip = str(getattr(rdata, "address", rdata))
            result.add_entity(EntityType.IP, ip, source_url=src, raw_excerpt={"record": rtype})
            result.add_edge(seed, (EntityType.IP, ip), RelationshipType.RESOLVES_TO,
                            attributes={"record": rtype}, source_url=src)
        elif rtype == "MX":
            host = str(rdata.exchange).rstrip(".")
            pref = getattr(rdata, "preference", None)
            result.add_entity(EntityType.DOMAIN, host, attributes={"role": "mail_server"}, source_url=src)
            result.add_edge(seed, (EntityType.DOMAIN, host), RelationshipType.REFERENCES,
                            attributes={"record": "MX", "priority": pref}, source_url=src)
        elif rtype == "NS":
            host = str(rdata.target).rstrip(".")
            result.add_entity(EntityType.DOMAIN, host, attributes={"role": "name_server"}, source_url=src)
            result.add_edge(seed, (EntityType.DOMAIN, host), RelationshipType.REFERENCES,
                            attributes={"record": "NS"}, source_url=src)
        elif rtype == "CNAME":
            host = str(rdata.target).rstrip(".")
            result.add_entity(EntityType.DOMAIN, host, source_url=src)
            result.add_edge(seed, (EntityType.DOMAIN, host), RelationshipType.RESOLVES_TO,
                            attributes={"record": "CNAME"}, source_url=src)
        elif rtype == "TXT":
            try:
                parts = b"".join(rdata.strings).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                parts = str(rdata)
            txt_records.append(parts)
        elif rtype == "SOA":
            result.add_entity(
                target.type, name,
                attributes={
                    "soa_mname": str(getattr(rdata, "mname", "")).rstrip("."),
                    "soa_rname": str(getattr(rdata, "rname", "")).rstrip("."),
                    "soa_serial": getattr(rdata, "serial", None),
                },
                source_url=src,
            )
