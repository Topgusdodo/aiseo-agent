"""CGNAT + multicast SSRF regression tests for _normalize_public_url.

Verifies that _is_private_host (and the _normalize_public_url chain that calls
it) correctly blocks:
  - CGNAT addresses (RFC 6598, 100.64.0.0/10) — not flagged by any stdlib
    ipaddress is_* attribute prior to this fix
  - IPv4 multicast (224.0.0.0/4) — flagged only by is_multicast, which was
    previously missing from the guard
  - IPv6 multicast (ff00::/8) — same gap; note _SAFE_HOST_RE may intercept
    the bracket notation first, but the result is still a block

All cases that MUST raise use:
    pytest.raises(ValueError, match=r"must target a public website")

Cases outside the blocked ranges must NOT raise (fail-open sanity checks).
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def normalize(url: str, guard_module):
    """Call _normalize_public_url with a canonical field name."""
    return guard_module._normalize_public_url(value=url, field="site_url")


# ---------------------------------------------------------------------------
# CGNAT (RFC 6598, 100.64.0.0/10) — must be BLOCKED
# ---------------------------------------------------------------------------

def test_cgnat_lower_boundary_raises(aiseo_guard):
    """100.64.0.1 is the first usable CGNAT address — must be blocked."""
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://100.64.0.1/", aiseo_guard)


def test_cgnat_upper_boundary_raises(aiseo_guard):
    """100.127.255.254 is the last usable CGNAT address — must be blocked."""
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://100.127.255.254/", aiseo_guard)


def test_cgnat_alibaba_metadata_raises(aiseo_guard):
    """100.100.100.100 is Alibaba's instance metadata endpoint — must be blocked."""
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://100.100.100.100/", aiseo_guard)


# ---------------------------------------------------------------------------
# Just outside CGNAT range — must NOT raise
# ---------------------------------------------------------------------------

def test_below_cgnat_does_not_raise(aiseo_guard):
    """100.63.255.255 is just below the CGNAT block — must pass through.

    This address is in the public range (not RFC 6598 CGNAT).  Other guards
    (hostname suffix, no-dot, obfuscation) do not apply to a plain decimal
    dotted-quad like this, so _normalize_public_url must accept it.
    """
    result = normalize("http://100.63.255.255/", aiseo_guard)
    assert "100.63.255.255" in result


def test_above_cgnat_does_not_raise(aiseo_guard):
    """100.128.0.0 is just above the CGNAT block — must pass through."""
    result = normalize("http://100.128.0.0/", aiseo_guard)
    assert "100.128.0.0" in result


# ---------------------------------------------------------------------------
# IPv4 multicast (224.0.0.0/4) — must be BLOCKED
# ---------------------------------------------------------------------------

def test_multicast_ipv4_lower_boundary_raises(aiseo_guard):
    """224.0.0.1 is the lower boundary of IPv4 multicast — must be blocked."""
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://224.0.0.1/", aiseo_guard)


def test_multicast_ipv4_upper_boundary_raises(aiseo_guard):
    """239.255.255.255 (SSDP, last multicast addr) — must be blocked."""
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://239.255.255.255/", aiseo_guard)


def test_multicast_just_below_range_does_not_raise(aiseo_guard):
    """223.255.255.255 is the last public IPv4 address before multicast — must pass."""
    result = normalize("http://223.255.255.255/", aiseo_guard)
    assert "223.255.255.255" in result


# ---------------------------------------------------------------------------
# IPv6 multicast — must be BLOCKED
# ---------------------------------------------------------------------------

def test_multicast_ipv6_link_local_raises(aiseo_guard):
    """ff02::1 is IPv6 link-local all-nodes multicast.

    _SAFE_HOST_RE blocks bracket-notation IPv6 before _is_private_host runs,
    so the chain still produces ValueError with the correct message.
    """
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://[ff02::1]/", aiseo_guard)


# ---------------------------------------------------------------------------
# Public IP sanity checks — must NOT raise
# ---------------------------------------------------------------------------

def test_google_dns_does_not_raise(aiseo_guard):
    """8.8.8.8 is a public Google DNS IP — guard must not block it."""
    result = normalize("http://8.8.8.8/", aiseo_guard)
    assert "8.8.8.8" in result


def test_cloudflare_dns_does_not_raise(aiseo_guard):
    """1.1.1.1 is Cloudflare's public DNS — must not be blocked."""
    result = normalize("http://1.1.1.1/", aiseo_guard)
    assert "1.1.1.1" in result
