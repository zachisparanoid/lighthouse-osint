"""RDAP / WHOIS collector — modern WHOIS over the public RDAP protocol.

Public source: https://rdap.org bootstrap (redirects to the authoritative RDAP server for
the queried domain / IP / ASN). Registration data only — registrar, registrant (when not
redacted for privacy), abuse contacts, registration/expiry dates, and nameservers. No
login-gated or private data.
"""
from __future__ import annotations

from typing import Any

from lighthouse_shared import CollectorCost, EntityType, RelationshipType

from app.collectors.base import CollectionContext, Collector, CollectorResult, EntityRef

_RDAP = "https://rdap.org"

# RDAP event actions -> attribute names we fold onto the seed entity.
_EVENT_MAP = {
    "registration": "registered_on",
    "expiration": "expires_on",
    "last changed": "updated_on",
}

# Registrant-type roles whose org/person we surface as the registrant.
_REGISTRANT_ROLES = {"registrant", "administrative", "technical"}


def _is_redacted(value: str | None) -> bool:
    """RDAP commonly returns placeholder text instead of redacted personal data."""
    if not value or not value.strip():
        return True
    low = value.lower()
    return "redacted" in low or "redacted for privacy" in low


def _parse_vcard(vcard_array: Any) -> dict[str, str]:
    """Extract fn/org/email from a jCard (vcardArray).

    Shape: ["vcard", [ ["version",{},"text","4.0"], ["fn",{},"text","NAME"], ... ]].
    """
    out: dict[str, str] = {}
    if not isinstance(vcard_array, list) or len(vcard_array) < 2:
        return out
    inner = vcard_array[1]
    if not isinstance(inner, list):
        return out
    for element in inner:
        if isinstance(element, list) and len(element) >= 4 and element[0] in ("fn", "org", "email"):
            val = element[3]
            if isinstance(val, list):  # some jCards put structured values in a list
                val = " ".join(str(p) for p in val if p)
            if isinstance(val, str) and val.strip():
                out.setdefault(element[0], val.strip())
    return out


class RDAPWhoisCollector(Collector):
    name = "rdap_whois"
    title = "RDAP / WHOIS"
    description = "Look up registration data (registrar, registrant, dates, nameservers) via public RDAP."
    accepts = {EntityType.DOMAIN, EntityType.IP, EntityType.ASN}
    produces = {EntityType.ORGANIZATION, EntityType.PERSON, EntityType.EMAIL, EntityType.DOMAIN}
    cost = CollectorCost.FREE
    requires_key = None
    rate_limit = "20/m"
    cache_ttl = 86400
    base_reliability = 85
    source_note = "Public RDAP (modern WHOIS) via rdap.org bootstrap. Registration data only."

    async def run(self, target: EntityRef, ctx: CollectionContext) -> CollectorResult:
        value = target.value.strip()
        url = self._endpoint(target.type, value)
        result = CollectorResult()
        await ctx.report(10, "Querying RDAP")

        resp = await ctx.http.get(url)
        if resp.status_code == 404:
            return CollectorResult(message=f"No RDAP record for {value}.")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            try:
                retry_after = int(retry) if retry is not None else 60
            except (TypeError, ValueError):
                retry_after = 60
            return CollectorResult.failed("rate limited by rdap.org", retry_after=retry_after)
        resp.raise_for_status()
        data = resp.json()

        await ctx.report(50, "Parsing registration data")
        seed = (target.type, value)
        seed_attrs = self._seed_attributes(data)
        if seed_attrs:
            result.add_entity(target.type, value, attributes=seed_attrs, source_url=url, raw_excerpt=seed_attrs)

        for entity in data.get("entities") or []:
            self._handle_entity(result, seed, entity, url)

        if target.type == EntityType.DOMAIN:
            for ns in (data.get("nameservers") or [])[:6]:
                host = (ns.get("ldhName") or "").strip().rstrip(".")
                if not host:
                    continue
                result.add_entity(EntityType.DOMAIN, host, attributes={"role": "name_server"}, source_url=url)
                result.add_edge(seed, (EntityType.DOMAIN, host), RelationshipType.REFERENCES,
                                attributes={"record": "NS"}, source_url=url)

        await ctx.report(100)
        result.summary = {
            "handle": data.get("handle"),
            "entities": len(result.entities),
            "edges": len(result.edges),
        }
        return result

    @staticmethod
    def _endpoint(etype: EntityType, value: str) -> str:
        if etype == EntityType.IP:
            return f"{_RDAP}/ip/{value}"
        if etype == EntityType.ASN:
            digits = "".join(ch for ch in value if ch.isdigit())
            return f"{_RDAP}/autnum/{digits}"
        return f"{_RDAP}/domain/{value}"

    @staticmethod
    def _seed_attributes(data: dict[str, Any]) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        for event in data.get("events") or []:
            action = (event.get("eventAction") or "").lower()
            date = event.get("eventDate")
            if action in _EVENT_MAP and date:
                attrs[_EVENT_MAP[action]] = date
        status = data.get("status")
        if status:
            attrs["status"] = status
        handle = data.get("handle")
        if handle:
            attrs["handle"] = handle
        return attrs

    def _handle_entity(self, result, seed, entity: dict[str, Any], url: str) -> None:
        roles = {str(r).lower() for r in (entity.get("roles") or [])}
        card = _parse_vcard(entity.get("vcardArray"))
        org = card.get("org")
        fn = card.get("fn")
        email = card.get("email")

        if "registrar" in roles:
            if org and not _is_redacted(org):
                result.add_entity(EntityType.ORGANIZATION, org, attributes={"role": "registrar"}, source_url=url)
                result.add_edge(seed, (EntityType.ORGANIZATION, org),
                                RelationshipType.REGISTERED_BY, source_url=url)

        if roles & _REGISTRANT_ROLES:
            if org and not _is_redacted(org):
                result.add_entity(EntityType.ORGANIZATION, org, attributes={"role": "registrant"}, source_url=url)
                result.add_edge(seed, (EntityType.ORGANIZATION, org),
                                RelationshipType.REGISTERED_BY, source_url=url)
            elif fn and not _is_redacted(fn):
                result.add_entity(EntityType.PERSON, fn, attributes={"role": "registrant"}, source_url=url)
                result.add_edge(seed, (EntityType.PERSON, fn),
                                RelationshipType.REGISTERED_BY, source_url=url)

        # Emails in RDAP registration data are abuse/registrant/registrar contacts; surface
        # any non-redacted address found on a role-bearing entity. RDAP frequently puts
        # human-readable placeholders ("Please query the RDAP server...") in the email
        # field, so require a real-looking address (has "@") before emitting.
        if email and not _is_redacted(email) and "@" in email and " " not in email:
            result.add_entity(EntityType.EMAIL, email, source_url=url)
            result.add_edge(seed, (EntityType.EMAIL, email), RelationshipType.REFERENCES, source_url=url)
