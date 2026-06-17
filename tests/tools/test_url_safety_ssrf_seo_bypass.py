"""Regression tests: trusted SEO domains must NOT bypass SSRF protection.

CRITICAL #2 fix verification — url_safety.py previously allowed trusted SEO
HTTPS hostnames (ahrefs.com, semrush.com, etc.) to resolve to ANY private IP,
not just the RFC 2544 benchmark range (198.18.0.0/15) that was the original
intent.

Bug: `_allows_private_ip_resolution` returned True for trusted SEO + HTTPS,
then `is_safe_url` short-circuited the entire `_is_blocked_ip()` check, so
127.0.0.1 / 10.x / 192.168.x all passed. DNS rebinding attack: attacker
controls ahrefs.com DNS -> 127.0.0.1 -> SSRF.

Fix: `_is_blocked_ip` is always evaluated; the `allow_private_ip` exception
only applies when the resolved IP is also in _is_benchmark_ip (198.18.0.0/15).

6 required cases from the bug report, plus boundary and multi-domain coverage.
"""

from __future__ import annotations

import ipaddress
from unittest.mock import patch

import pytest

from tools.url_safety import _is_benchmark_ip, _reset_allow_private_cache, is_safe_url


def _mock_dns(ip: str):
    """Return a socket.getaddrinfo-compatible result resolving to `ip`."""
    return [(2, 1, 6, "", (ip, 0))]


@pytest.fixture(autouse=True)
def reset_cache():
    """Each test gets a clean allow_private cache state."""
    _reset_allow_private_cache()
    yield
    _reset_allow_private_cache()


# ---------------------------------------------------------------------------
# CRITICAL #2 — the 6 required regression cases
# ---------------------------------------------------------------------------


class TestSsrfSeoBypassFixed:
    """Trusted SEO domains must NOT bypass SSRF for non-benchmark private IPs."""

    def test_ahrefs_resolves_to_loopback_is_blocked(self):
        """ahrefs.com -> 127.0.0.1 must return False (was True before fix)."""
        with patch("socket.getaddrinfo", return_value=_mock_dns("127.0.0.1")):
            assert is_safe_url("https://ahrefs.com/blog") is False

    def test_ahrefs_resolves_to_rfc1918_10_is_blocked(self):
        """ahrefs.com -> 10.0.0.1 must return False (was True before fix)."""
        with patch("socket.getaddrinfo", return_value=_mock_dns("10.0.0.1")):
            assert is_safe_url("https://ahrefs.com/site-explorer") is False

    def test_ahrefs_resolves_to_rfc1918_192168_is_blocked(self):
        """ahrefs.com -> 192.168.0.1 must return False (was True before fix)."""
        with patch("socket.getaddrinfo", return_value=_mock_dns("192.168.0.1")):
            assert is_safe_url("https://ahrefs.com/keywords-explorer") is False

    def test_ahrefs_resolves_to_benchmark_is_allowed(self):
        """ahrefs.com -> 198.18.1.1 (RFC 2544 benchmark) must return True.

        This is the original intent: break retry storms on networks that
        mis-resolve SEO tool domains to the benchmark range.
        """
        with patch("socket.getaddrinfo", return_value=_mock_dns("198.18.1.1")):
            assert is_safe_url("https://ahrefs.com/blog") is True

    def test_non_trusted_domain_resolves_to_loopback_is_blocked(self):
        """non-trusted-domain.com -> 127.0.0.1 must return False (original behaviour)."""
        with patch("socket.getaddrinfo", return_value=_mock_dns("127.0.0.1")):
            assert is_safe_url("https://non-trusted-domain.com/") is False

    def test_ahrefs_resolves_to_public_ip_is_allowed(self):
        """ahrefs.com -> 8.8.8.8 (public IP) must return True."""
        with patch("socket.getaddrinfo", return_value=_mock_dns("8.8.8.8")):
            assert is_safe_url("https://ahrefs.com/blog") is True


# ---------------------------------------------------------------------------
# Additional trusted SEO domains — same loopback/RFC-1918 blocking applies
# ---------------------------------------------------------------------------


class TestSsrfSeoBypassOtherTrustedDomains:
    """The fix applies to all trusted SEO suffixes, not just ahrefs.com."""

    @pytest.mark.parametrize("url,ip", [
        ("https://semrush.com/", "127.0.0.1"),
        ("https://www.semrush.com/dashboard", "10.1.2.3"),
        ("https://similarweb.com/", "192.168.1.100"),
        ("https://moz.com/learn", "172.16.0.1"),
        ("https://backlinko.com/hub", "127.0.0.1"),
        ("https://neilpatel.com/blog", "10.0.0.1"),
        ("https://screamingfrog.co.uk/", "192.168.0.254"),
    ])
    def test_trusted_seo_domain_private_ip_blocked(self, url, ip):
        """Each trusted SEO domain must still block loopback and RFC-1918 IPs."""
        with patch("socket.getaddrinfo", return_value=_mock_dns(ip)):
            assert is_safe_url(url) is False, (
                f"{url} resolving to {ip} should be blocked after CRITICAL #2 fix"
            )

    @pytest.mark.parametrize("url", [
        "https://semrush.com/",
        "https://www.moz.com/learn",
        "https://backlinko.com/hub",
    ])
    def test_trusted_seo_domain_benchmark_ip_allowed(self, url):
        """Benchmark-range IPs remain allowed for all trusted SEO domains."""
        with patch("socket.getaddrinfo", return_value=_mock_dns("198.18.5.100")):
            assert is_safe_url(url) is True, (
                f"{url} with benchmark IP should still be allowed"
            )


# ---------------------------------------------------------------------------
# DNS rebinding scenario: subdomain trusted, IP is private
# ---------------------------------------------------------------------------


class TestDnsRebindingViaTrustedSubdomain:
    """Subdomains of trusted SEO domains must also block private IPs."""

    def test_www_ahrefs_loopback_blocked(self):
        with patch("socket.getaddrinfo", return_value=_mock_dns("127.0.0.1")):
            assert is_safe_url("https://www.ahrefs.com/") is False

    def test_blog_ahrefs_rfc1918_blocked(self):
        with patch("socket.getaddrinfo", return_value=_mock_dns("10.0.0.5")):
            assert is_safe_url("https://blog.ahrefs.com/post") is False

    def test_www_semrush_loopback_blocked(self):
        with patch("socket.getaddrinfo", return_value=_mock_dns("127.0.0.1")):
            assert is_safe_url("https://www.semrush.com/") is False


# ---------------------------------------------------------------------------
# _is_benchmark_ip helper unit tests
# ---------------------------------------------------------------------------


class TestIsBenchmarkIp:
    """Direct unit tests for the new _is_benchmark_ip helper."""

    @pytest.mark.parametrize("ip_str", [
        "198.18.0.0",
        "198.18.0.1",
        "198.18.1.1",
        "198.19.255.254",
        "198.19.255.255",
    ])
    def test_benchmark_ips_return_true(self, ip_str):
        ip = ipaddress.ip_address(ip_str)
        assert _is_benchmark_ip(ip) is True, f"{ip_str} should be in benchmark range"

    @pytest.mark.parametrize("ip_str", [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.0.1",
        "172.16.0.1",
        "169.254.169.254",
        "8.8.8.8",
        "198.17.255.255",   # just below 198.18.0.0/15
        "198.20.0.0",       # just above 198.19.255.255
        "100.64.0.1",
    ])
    def test_non_benchmark_ips_return_false(self, ip_str):
        ip = ipaddress.ip_address(ip_str)
        assert _is_benchmark_ip(ip) is False, f"{ip_str} should NOT be in benchmark range"

    def test_ipv6_address_returns_false(self):
        """IPv6 addresses are not in the IPv4 benchmark range."""
        ip = ipaddress.ip_address("::1")
        assert _is_benchmark_ip(ip) is False

    def test_ipv6_mapped_ipv4_returns_false(self):
        """IPv4-mapped IPv6 is not a plain IPv4Address instance."""
        ip = ipaddress.ip_address("::ffff:198.18.0.1")
        assert _is_benchmark_ip(ip) is False


# ---------------------------------------------------------------------------
# Always-blocked cloud metadata: trusted SEO domain must NOT bypass these
# ---------------------------------------------------------------------------


class TestTrustedSeoDoesNotBypassCloudMetadata:
    """Cloud metadata IPs are always blocked regardless of trusted domain."""

    @pytest.mark.parametrize("ip", [
        "169.254.169.254",   # AWS/GCP/Azure metadata
        "169.254.170.2",     # AWS ECS task metadata
        "100.100.100.200",   # Alibaba Cloud metadata
    ])
    def test_cloud_metadata_always_blocked_for_trusted_seo(self, ip):
        with patch("socket.getaddrinfo", return_value=_mock_dns(ip)):
            assert is_safe_url("https://ahrefs.com/spoofed") is False, (
                f"Cloud metadata IP {ip} must be blocked even for trusted SEO domain"
            )
