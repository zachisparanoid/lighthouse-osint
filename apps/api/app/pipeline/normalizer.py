"""Canonicalize raw selectors so the same real-world thing always dedupes to one entity.

Examples: ``Example.COM.`` -> ``example.com``; an IDN like ``bücher.de`` -> its punycode
``xn--bcher-kva.de``; ``+1 (415) 555-0100`` -> ``+14155550100``; ``WWW.x.com/path`` (typed as
a domain) is reclassified to a subdomain. The normalizer may correct the entity *type*.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import idna
import tldextract

from lighthouse_shared import EntityType

# Use the bundled public-suffix snapshot; never fetch over the network at runtime.
_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)


@dataclass
class Normalized:
    type: EntityType
    value: str
    label: str


def _domain(raw: str) -> Normalized:
    host = raw.strip().lower().rstrip(".")
    if "://" in host:
        host = urlparse(host).hostname or host
    host = host.split("/")[0].split("@")[-1]
    # IDN -> punycode (a-label); keep the human form as label.
    label = host
    try:
        host = idna.encode(host, uts46=True).decode("ascii")
    except (idna.IDNAError, UnicodeError):
        pass
    ext = _extract(host)
    if ext.subdomain:
        return Normalized(EntityType.SUBDOMAIN, host, label)
    registered = ext.registered_domain or host
    return Normalized(EntityType.DOMAIN, registered, label if label != host else registered)


def _ip(raw: str) -> Normalized:
    v = raw.strip()
    try:
        ip = ipaddress.ip_address(v)
        return Normalized(EntityType.IP, str(ip), str(ip))
    except ValueError:
        return Normalized(EntityType.IP, v, v)


def _email(raw: str) -> Normalized:
    v = raw.strip().lower()
    return Normalized(EntityType.EMAIL, v, v)


def _username(raw: str) -> Normalized:
    label = raw.strip().lstrip("@")
    return Normalized(EntityType.USERNAME, label.lower(), label)


def _phone(raw: str) -> Normalized:
    import phonenumbers

    v = raw.strip()
    for region in (None, "US"):
        try:
            parsed = phonenumbers.parse(v, region)
            if phonenumbers.is_possible_number(parsed):
                e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                intl = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                return Normalized(EntityType.PHONE, e164, intl)
        except phonenumbers.NumberParseException:
            continue
    return Normalized(EntityType.PHONE, re.sub(r"[^\d+]", "", v) or v, v)


def _url(raw: str) -> Normalized:
    v = raw.strip()
    if "://" not in v:
        v = "http://" + v
    p = urlparse(v)
    host = (p.hostname or "").lower()
    try:
        host = idna.encode(host, uts46=True).decode("ascii")
    except (idna.IDNAError, UnicodeError):
        pass
    netloc = host + (f":{p.port}" if p.port else "")
    normalized = urlunparse((p.scheme.lower(), netloc, p.path or "/", "", p.query, ""))
    return Normalized(EntityType.URL, normalized, raw.strip())


def _asn(raw: str) -> Normalized:
    digits = re.sub(r"\D", "", raw)
    value = f"AS{digits}" if digits else raw.strip().upper()
    return Normalized(EntityType.ASN, value, value)


def _hash(raw: str) -> Normalized:
    v = raw.strip().lower()
    return Normalized(EntityType.FILE_HASH, v, v)


def _text(entity_type: EntityType, raw: str) -> Normalized:
    label = re.sub(r"\s+", " ", raw.strip())
    return Normalized(entity_type, label.lower(), label)


_DISPATCH = {
    EntityType.DOMAIN: _domain,
    EntityType.SUBDOMAIN: _domain,
    EntityType.IP: _ip,
    EntityType.EMAIL: _email,
    EntityType.USERNAME: _username,
    EntityType.PHONE: _phone,
    EntityType.URL: _url,
    EntityType.ASN: _asn,
    EntityType.FILE_HASH: _hash,
}


def normalize(entity_type: EntityType, raw: str) -> Normalized:
    raw = raw or ""
    fn = _DISPATCH.get(entity_type)
    if fn is not None:
        # _domain handles both DOMAIN and SUBDOMAIN dispatch keys.
        return fn(raw) if fn is not _domain else _domain(raw)
    # person, organization, location, breach, social_profile, certificate
    if entity_type == EntityType.SOCIAL_PROFILE and ("://" in raw):
        n = _url(raw)
        return Normalized(EntityType.SOCIAL_PROFILE, n.value, raw.strip())
    if entity_type == EntityType.CERTIFICATE:
        return Normalized(EntityType.CERTIFICATE, raw.strip().lower(), raw.strip())
    return _text(entity_type, raw)
