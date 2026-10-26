"""ScopeGuard: the gate that keeps collection public-only and in-scope.

Pure unit tests — no DB, no network. Exercises IP/host/URL rules against a
denylist of ``*.gov``/``*.mil`` plus a CIDR and a couple of literals.
"""
from __future__ import annotations

import pytest

from app.collectors.base import ScopeGuard, ScopeViolation
from lighthouse_shared import EntityType

DENYLIST = ["*.gov", "*.mil", "127.0.0.1", "10.0.0.0/8"]


@pytest.fixture
def guard() -> ScopeGuard:
    return ScopeGuard(DENYLIST)


# ---------------------------------------------------------------- check_target ---
def test_public_domain_allowed(guard: ScopeGuard) -> None:
    # Must not raise.
    guard.check_target(EntityType.DOMAIN, "example.com")


def test_gov_domain_denied(guard: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        guard.check_target(EntityType.DOMAIN, "x.gov")


def test_private_ip_denied(guard: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        guard.check_target(EntityType.IP, "192.168.1.1")


def test_cidr_denylisted_ip_denied(guard: ScopeGuard) -> None:
    # 10.5.5.5 is private (always blocked) and also caught by the 10.0.0.0/8 CIDR rule.
    with pytest.raises(ScopeViolation):
        guard.check_target(EntityType.IP, "10.5.5.5")


def test_loopback_ip_denied(guard: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        guard.check_target(EntityType.IP, "127.0.0.1")


def test_public_ip_allowed(guard: ScopeGuard) -> None:
    guard.check_target(EntityType.IP, "8.8.8.8")


# ------------------------------------------------------------ assert_url_allowed ---
def test_url_http_allowed(guard: ScopeGuard) -> None:
    guard.assert_url_allowed("http://example.com")


def test_url_ftp_scheme_denied(guard: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        guard.assert_url_allowed("ftp://x")


def test_url_private_host_denied(guard: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        guard.assert_url_allowed("http://10.0.0.1")


def test_url_file_scheme_denied(guard: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        guard.assert_url_allowed("file:///etc")


# -------------------------------------------------------------- is_host_allowed ---
def test_wildcard_suffix_host_denied(guard: ScopeGuard) -> None:
    assert guard.is_host_allowed("sub.example.gov") is False


def test_public_host_allowed(guard: ScopeGuard) -> None:
    assert guard.is_host_allowed("example.com") is True
