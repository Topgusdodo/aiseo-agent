"""P0-A Phase 2.1 boundary regression tests for _normalize_public_url.

These tests verify the current behavior of the _normalize_public_url +
_is_private_host chain against 10 SSRF/private-host vectors, plus 4 new
cases that exercise _is_numeric_ip_obfuscated false-positive and
true-positive boundaries added in Phase 2.

All cases call: _normalize_public_url(value="http://<host>/", field="site_url")
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def normalize(url: str, guard_module):
    """Thin wrapper — call _normalize_public_url via the session fixture."""
    return guard_module._normalize_public_url(value=url, field="site_url")


# ---------------------------------------------------------------------------
# Case 1: Public domain — must NOT raise (fail-open sanity check)
# ---------------------------------------------------------------------------

def test_case01_public_domain_does_not_raise(aiseo_guard):
    """http://example.com/ is a public domain and must pass through."""
    # Arrange
    url = "http://example.com/"

    # Act / Assert — must not raise
    result = normalize(url, aiseo_guard)
    assert "example.com" in result


# ---------------------------------------------------------------------------
# Cases 2–10: Private / internal hosts — all must raise ValueError
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url, case_id, description",
    [
        (
            "http://db01/",
            "case02_no_dot_hostname",
            "no-dot bare label — expect blocked",
        ),
        (
            "http://app.corp/",
            "case03_dot_corp_intranet",
            ".corp TLD private-intranet — expect blocked",
        ),
        (
            "http://intranet.lan/",
            "case04_dot_lan_intranet",
            ".lan TLD private-intranet — expect blocked",
        ),
        (
            "http://service.local/",
            "case05_dot_local_mdns",
            ".local mDNS already in denylist — expect blocked",
        ),
        (
            "http://x.localhost/",
            "case06_dot_localhost_rfc6761",
            ".localhost RFC 6761 subdomain — expect blocked",
        ),
        (
            "http://169.254.169.254/",
            "case07_aws_metadata_link_local",
            "169.254/16 link-local (AWS metadata) — expect blocked by _is_private_host",
        ),
        (
            "http://0177.0.0.1/",
            "case08_octal_loopback",
            "octal 0177.0.0.1 = 127.0.0.1 — blocked by _is_numeric_ip_obfuscated",
        ),
        (
            "http://0x7f000001/",
            "case09_hex_loopback",
            "hex 0x7f000001 = 127.0.0.1 — blocked by _is_numeric_ip_obfuscated",
        ),
        (
            "http://user@evil.com/",
            "case10_url_auth_credentials",
            "URL credentials user@host — blocked by lines 581-582",
        ),
    ],
    ids=[
        "case02_no_dot",
        "case03_dot_corp",
        "case04_dot_lan",
        "case05_dot_local",
        "case06_dot_localhost",
        "case07_link_local_ip",
        "case08_octal_ip",
        "case09_hex_ip",
        "case10_url_auth",
    ],
)
def test_private_host_raises_value_error(aiseo_guard, url, case_id, description):
    """Each private/internal URL must raise ValueError via _is_private_host guard chain."""
    if case_id == "case10_url_auth_credentials":
        match = r"credentials"
    else:
        match = r"must target a public website"
    with pytest.raises(ValueError, match=match):
        normalize(url, aiseo_guard)


# ---------------------------------------------------------------------------
# Bonus: IPv6 loopback [::1] — must be blocked by _SAFE_HOST_RE
# ---------------------------------------------------------------------------

def test_bonus_ipv6_loopback_raises(aiseo_guard):
    """http://[::1]/ — IPv6 bracket notation must be blocked by _SAFE_HOST_RE."""
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://[::1]/", aiseo_guard)


# ---------------------------------------------------------------------------
# Phase 2.1 new cases: _is_numeric_ip_obfuscated false-positive boundary
# ---------------------------------------------------------------------------

def test_case_saas_subdomain_01_example_com_does_not_raise(aiseo_guard):
    """01.example.com is a legitimate SaaS subdomain — must NOT raise.

    5-segment host is not a dotted-quad; _is_numeric_ip_obfuscated must not
    trigger on non-IPv4-shaped hosts.
    """
    # Arrange
    url = "http://01.example.com/"

    # Act / Assert — must pass through without raising
    result = normalize(url, aiseo_guard)
    assert "example.com" in result


def test_case_saas_subdomain_s3_0_amazonaws_does_not_raise(aiseo_guard):
    """s3-0.amazonaws.com is a legitimate AWS subdomain — must NOT raise.

    Token 's3-0' is not all-digits, so _is_numeric_ip_obfuscated must return
    False and the URL must pass through.
    """
    # Arrange
    url = "http://s3-0.amazonaws.com/"

    # Act / Assert — must pass through without raising
    result = normalize(url, aiseo_guard)
    assert "amazonaws.com" in result


def test_case_octal_dotted_quad_raises(aiseo_guard):
    """001.002.003.004 — dotted-quad with leading-zero segments must be blocked.

    All 4 segments are all-digits with leading zeros; _is_numeric_ip_obfuscated
    must detect octal obfuscation and raise ValueError.
    """
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://001.002.003.004/", aiseo_guard)


def test_case_hex_dotted_quad_raises(aiseo_guard):
    """0x7f.0.0.1 — dotted-quad with 0x segment must be blocked.

    First segment has 0x prefix; _is_numeric_ip_obfuscated must detect hex
    obfuscation and raise ValueError.
    """
    with pytest.raises(ValueError, match=r"must target a public website"):
        normalize("http://0x7f.0.0.1/", aiseo_guard)
