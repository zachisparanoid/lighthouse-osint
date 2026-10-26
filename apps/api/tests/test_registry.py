"""Collector registry: auto-discovery + capability/enablement metadata.

No DB — the registry only walks the ``app.collectors`` package and instantiates
each concrete collector.
"""
from __future__ import annotations

from app.collectors import registry
from lighthouse_shared import EntityType

_EXPECTED_NAMES = {
    "dns_records",
    "github_user",
    "shodan",
    "email_breach",
    "company_records",
}
# Collectors gated behind a BYOK key.
_KEYED = {"shodan", "email_breach", "company_records"}


def _by_name(caps: list[dict]) -> dict[str, dict]:
    return {c["name"]: c for c in caps}


def test_all_collectors_discovers_fourteen() -> None:
    cols = registry.all_collectors()
    assert len(cols) == 14
    names = {c.name for c in cols}
    assert _EXPECTED_NAMES.issubset(names)


def test_capabilities_keyed_collectors_disabled_without_key() -> None:
    caps = _by_name(registry.capabilities({}, set()))

    for name in _KEYED:
        info = caps[name]
        assert info["key_present"] is False
        assert info["enabled"] is False

    # Free collectors are enabled out of the box.
    assert caps["dns_records"]["key_present"] is True
    assert caps["dns_records"]["enabled"] is True
    assert caps["github_user"]["enabled"] is True


def test_capabilities_key_present_enables_collector() -> None:
    caps = _by_name(registry.capabilities({"shodan": True}, set()))
    assert caps["shodan"]["key_present"] is True
    assert caps["shodan"]["enabled"] is True


def test_capabilities_disabled_set_disables_free_collector() -> None:
    caps = _by_name(registry.capabilities({}, {"dns_records"}))
    # Still free / no key needed, but explicitly disabled.
    assert caps["dns_records"]["key_present"] is True
    assert caps["dns_records"]["enabled"] is False


def test_collectors_for_ip() -> None:
    names = {c.name for c in registry.collectors_for(EntityType.IP)}
    assert {"ip_geo", "reverse_dns", "rdap_whois", "shodan", "http_fingerprint"}.issubset(names)
