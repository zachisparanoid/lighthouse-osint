"""Email deliverability collector — syntax validation + domain MX records.

Ethics: this NEVER sends mail and NEVER connects to an SMTP server / probes mailboxes.
"Deliverability" here is a heuristic: valid syntax AND the domain publishes MX records,
checked via public DNS only. It enriches the seed email and links it to its domain.
"""
from __future__ import annotations

import re

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

# Pragmatic email syntax check — not a full RFC 5322 parser, deliberately conservative.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailFormatCollector(Collector):
    name = "email_format"
    title = "Email Deliverability (MX)"
    description = "Validate email syntax and check the domain's MX records (no mail sent)."
    accepts = {EntityType.EMAIL}
    produces = {EntityType.DOMAIN}
    cost = CollectorCost.FREE
    rate_limit = "60/m"
    cache_ttl = 3600
    base_reliability = 60
    source_note = (
        "Validates email syntax and checks the domain's MX records (deliverability "
        "heuristic). Never sends mail or probes mailboxes."
    )

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        import dns.asyncresolver
        import dns.exception
        import dns.resolver

        result = CollectorResult()
        raw = target.value.strip()
        syntax_valid = bool(_EMAIL_RE.match(raw))

        local, _, domain = raw.partition("@")
        domain = domain.strip().lower().rstrip(".")

        await ctx.report(20, "Validating syntax")

        mx_hosts: list[str] = []
        if domain:
            await ctx.report(50, f"Resolving MX for {domain}")
            try:
                answers = await dns.asyncresolver.resolve(domain, "MX")
                ranked = sorted(answers, key=lambda r: getattr(r, "preference", 0))
                mx_hosts = [str(r.exchange).rstrip(".") for r in ranked]
            except (
                dns.resolver.NXDOMAIN,
                dns.resolver.NoAnswer,
                dns.resolver.NoNameservers,
                dns.exception.Timeout,
            ):
                mx_hosts = []
            except Exception:  # noqa: BLE001 — any resolver hiccup: treat as no MX
                mx_hosts = []

        has_mx = len(mx_hosts) > 0
        deliverable_heuristic = syntax_valid and has_mx

        # Enrich the seed email node with the deliverability heuristic.
        result.add_entity(
            EntityType.EMAIL,
            raw,
            attributes={
                "syntax_valid": syntax_valid,
                "has_mx": has_mx,
                "mx_hosts": mx_hosts,
                "deliverable_heuristic": deliverable_heuristic,
            },
            source_url=f"dns://{domain}/MX" if domain else None,
        )

        if domain:
            result.add_entity(EntityType.DOMAIN, domain, source_url=f"dns://{domain}/MX")
            result.add_edge(
                (EntityType.EMAIL, raw),
                (EntityType.DOMAIN, domain),
                RelationshipType.REFERENCES,
                source_url=f"dns://{domain}/MX",
            )

        await ctx.report(100)
        result.summary = {"has_mx": has_mx, "deliverable": deliverable_heuristic}
        return result
