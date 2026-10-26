"""Certificate Transparency collector — public CT logs via crt.sh.

Public source: https://crt.sh (Sectigo's public Certificate Transparency log search).
Enumerates subdomains and certificates issued for a domain by mining the SANs and
common names recorded in publicly logged certificates. No authentication.
"""
from __future__ import annotations

import json

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_BASE = "https://crt.sh/"
_MAX_SUBDOMAINS = 200
_MAX_CERTS = 25


class CertTransparencyCollector(Collector):
    name = "cert_transparency"
    title = "Certificate Transparency (crt.sh)"
    description = "Enumerate subdomains and certificates for a domain from public Certificate Transparency logs."
    accepts = {EntityType.DOMAIN}
    produces = {EntityType.SUBDOMAIN, EntityType.CERTIFICATE, EntityType.DOMAIN}
    cost = CollectorCost.FREE
    rate_limit = "10/m"
    cache_ttl = 43200
    base_reliability = 80
    source_note = "Public Certificate Transparency logs via crt.sh. Subdomain + certificate enumeration."

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        domain = target.value.strip().lower().rstrip(".")
        result = CollectorResult()
        query_url = f"https://crt.sh/?q=%.{domain}"
        await ctx.report(10, "Querying crt.sh")

        resp = await ctx.http.get(_BASE, params={"q": f"%.{domain}", "output": "json"})
        if resp.status_code == 404:
            return CollectorResult(message=f"No CT log entries for {domain}.")
        if resp.status_code == 429:
            retry_after = self._retry_after(resp)
            return CollectorResult.failed("rate limited", retry_after=retry_after)
        if resp.status_code != 200:
            resp.raise_for_status()

        try:
            rows = resp.json()
        except (json.JSONDecodeError, ValueError):
            return CollectorResult(message=f"crt.sh returned non-JSON for {domain}.")

        if not isinstance(rows, list) or not rows:
            return CollectorResult(message=f"No CT log entries for {domain}.")

        await ctx.report(50, "Parsing certificates")

        # --- Subdomains: unique hostnames mined from name_value + common_name ---
        suffix = f".{domain}"
        hostnames: list[str] = []
        seen_hosts: set[str] = set()
        for row in rows:
            candidates: list[str] = []
            name_value = row.get("name_value") or ""
            candidates.extend(name_value.split("\n"))
            cn = row.get("common_name")
            if cn:
                candidates.append(cn)
            for raw in candidates:
                host = (raw or "").strip().lower()
                if not host:
                    continue
                if host.startswith("*."):
                    host = host[2:]
                if not host:
                    continue
                if " " in host or "\t" in host or "@" in host:
                    continue
                if host != domain and not host.endswith(suffix):
                    continue
                if host in seen_hosts:
                    continue
                seen_hosts.add(host)
                hostnames.append(host)
                if len(hostnames) >= _MAX_SUBDOMAINS:
                    break
            if len(hostnames) >= _MAX_SUBDOMAINS:
                break

        for host in hostnames:
            result.add_entity(EntityType.SUBDOMAIN, host, source_url=query_url)
            result.add_edge(
                (EntityType.SUBDOMAIN, host),
                (EntityType.DOMAIN, domain),
                RelationshipType.SUBDOMAIN_OF,
                source_url=query_url,
            )

        # --- Certificates: dedup by serial_number or id, cap at 25 ---
        cert_count = 0
        seen_certs: set[str] = set()
        for row in rows:
            if cert_count >= _MAX_CERTS:
                break
            cert_id = row.get("id")
            serial = row.get("serial_number")
            certval = serial or (str(cert_id) if cert_id is not None else None)
            if not certval or certval in seen_certs:
                continue
            seen_certs.add(certval)
            cert_count += 1
            cert_url = f"https://crt.sh/?id={cert_id}"
            result.add_entity(
                EntityType.CERTIFICATE,
                certval,
                label=row.get("common_name"),
                attributes={
                    "issuer": row.get("issuer_name"),
                    "not_before": row.get("not_before"),
                    "not_after": row.get("not_after"),
                    "common_name": row.get("common_name"),
                },
                source_url=cert_url,
            )
            result.add_edge(
                (EntityType.DOMAIN, domain),
                (EntityType.CERTIFICATE, certval),
                RelationshipType.USES_CERTIFICATE,
                source_url=cert_url,
            )

        # --- Enrich seed domain ---
        result.add_entity(
            EntityType.DOMAIN,
            domain,
            attributes={"subdomains_found": len(hostnames), "certificates_found": cert_count},
            source_url=query_url,
        )

        result.summary = {"subdomains_found": len(hostnames), "certificates_found": cert_count}
        await ctx.report(100)
        return result

    @staticmethod
    def _retry_after(resp) -> int:
        raw = resp.headers.get("Retry-After")
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 60
