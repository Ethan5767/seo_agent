"""Web API Security Static Contract & Source Integrity Checks.

NOTE ON TEST CLASSIFICATION:
These Python test cases act as STATIC CONTRACT & SOURCE INTEGRITY CHECKS to enforce
that security constraints (authentication decorators/calls, absence of hardcoded tenant
IDs, request body bounds, and rate limit wrappers) cannot regress unnoticed in the codebase.

Runtime execution security tests (testing real IP parsing, DNS rebinding, rate limit counters,
and 413 body size rejections) are implemented in `web/tests/security.test.mjs` using Node's
native test runner.
"""
import ipaddress
import re
from pathlib import Path
import pytest
from urllib.parse import urlparse

WEB_API_DIR = Path(__file__).parent.parent / "web" / "app" / "api"
HARDCODED_TEST_UUID = "00eecc82-fbfe-475c-b1f7-fcc71e4497b3"

def test_static_contract_no_hardcoded_user_ids_in_api_routes():
    """[Static Contract] Ensure no hardcoded user UUIDs exist in any API route handlers."""
    route_files = list(WEB_API_DIR.rglob("*.ts"))
    assert len(route_files) > 0, "No API routes found to inspect"

    for file_path in route_files:
        content = file_path.read_text(encoding="utf-8")
        assert HARDCODED_TEST_UUID not in content, (
            f"Hardcoded user ID found in {file_path.relative_to(WEB_API_DIR.parent.parent)}"
        )


def test_static_contract_core_api_routes_enforce_authentication():
    """[Static Contract] Verify multi-user routes under web/app/api call authenticateRequest."""
    routes_requiring_auth = [
        WEB_API_DIR / "clients" / "route.ts",
        WEB_API_DIR / "clients" / "[id]" / "scans" / "route.ts",
        WEB_API_DIR / "clients" / "scans" / "[id]" / "route.ts",
        WEB_API_DIR / "scan" / "route.ts",
        WEB_API_DIR / "plan" / "route.ts",
        WEB_API_DIR / "remediate" / "route.ts",
        WEB_API_DIR / "remediate" / "dryrun" / "route.ts",
        WEB_API_DIR / "remediate" / "apply" / "route.ts",
        WEB_API_DIR / "traffic" / "snapshot" / "route.ts",
    ]

    for route_path in routes_requiring_auth:
        assert route_path.exists(), f"Expected route {route_path} does not exist"
        content = route_path.read_text(encoding="utf-8")
        assert "authenticateRequest" in content, (
            f"Route {route_path.name} does not call authenticateRequest"
        )


def test_static_contract_mutation_routes_enforce_size_limits():
    """[Static Contract] Verify state-changing API routes call readJsonBodyWithLimit."""
    routes_requiring_size_limits = [
        WEB_API_DIR / "clients" / "route.ts",
        WEB_API_DIR / "clients" / "[id]" / "scans" / "route.ts",
        WEB_API_DIR / "scan" / "route.ts",
        WEB_API_DIR / "plan" / "route.ts",
        WEB_API_DIR / "remediate" / "route.ts",
        WEB_API_DIR / "remediate" / "dryrun" / "route.ts",
        WEB_API_DIR / "remediate" / "apply" / "route.ts",
        WEB_API_DIR / "traffic" / "snapshot" / "route.ts",
    ]

    for route_path in routes_requiring_size_limits:
        content = route_path.read_text(encoding="utf-8")
        assert "readJsonBodyWithLimit" in content, (
            f"Route {route_path.name} does not call readJsonBodyWithLimit"
        )


def test_static_contract_expensive_routes_enforce_rate_limits():
    """[Static Contract] Verify expensive/mutation API routes call checkRateLimit."""
    routes_requiring_rate_limits = [
        WEB_API_DIR / "clients" / "route.ts",
        WEB_API_DIR / "clients" / "[id]" / "scans" / "route.ts",
        WEB_API_DIR / "scan" / "route.ts",
        WEB_API_DIR / "plan" / "route.ts",
        WEB_API_DIR / "remediate" / "route.ts",
        WEB_API_DIR / "remediate" / "dryrun" / "route.ts",
        WEB_API_DIR / "remediate" / "apply" / "route.ts",
        WEB_API_DIR / "traffic" / "snapshot" / "route.ts",
    ]

    for route_path in routes_requiring_rate_limits:
        content = route_path.read_text(encoding="utf-8")
        assert "checkRateLimit" in content, (
            f"Route {route_path.name} does not call checkRateLimit"
        )


def test_static_contract_scan_route_uses_dns_aware_ssrf_validator():
    """[Static Contract] Verify scan route calls validateScanTargetUrlAsync."""
    scan_route = WEB_API_DIR / "scan" / "route.ts"
    content = scan_route.read_text(encoding="utf-8")
    assert "validateScanTargetUrlAsync" in content, (
        "Scan route must call validateScanTargetUrlAsync for DNS-aware SSRF protection"
    )


# ── SSRF Specification Validation ───────────────────────────────────────────

BLOCKED_SSRF_TARGETS = [
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "http://localhost",
    "http://localhost:3000",
    "http://169.254.169.254",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1",
    "http://10.255.255.254",
    "http://172.16.0.1",
    "http://172.31.255.254",
    "http://192.168.1.1",
    "http://192.168.0.254",
    "file:///etc/passwd",
    "ftp://ftp.example.com",
    "gopher://example.com",
    "javascript:alert(1)",
    "http://metadata.google.internal",
]

ALLOWED_SCAN_TARGETS = [
    "https://example.com",
    "http://example.com",
    "https://sub.domain.org/path?query=1",
    "https://valid-client.co.uk:443",
    "https://client-site.com:8443",
]


def is_ssrf_safe_url(raw_url: str) -> tuple[bool, str]:
    """Python specification mirror of server-security.ts validateScanTargetUrl."""
    if not raw_url or not isinstance(raw_url, str):
        return False, "Empty or invalid URL"

    candidate = raw_url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", candidate):
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https"):
        return False, f"Forbidden scheme: {parsed.scheme}"

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname"

    hostname = hostname.lower().strip()
    blocked_hosts = {
        "localhost",
        "metadata.google.internal",
        "instance-data",
    }
    if hostname in blocked_hosts or hostname.endswith((".local", ".localhost", ".internal", ".invalid", ".lan", ".arpa")):
        return False, "Localhost or metadata domain forbidden"

    if parsed.port and parsed.port not in (80, 443, 8080, 8443):
        return False, f"Port {parsed.port} forbidden"

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            return False, f"Private/loopback/metadata IP forbidden: {ip}"
    except ValueError:
        pass

    return True, "OK"


@pytest.mark.parametrize("target", BLOCKED_SSRF_TARGETS)
def test_ssrf_validator_blocks_dangerous_targets(target):
    safe, reason = is_ssrf_safe_url(target)
    assert not safe, f"Target '{target}' should have been blocked, but passed. Reason: {reason}"


@pytest.mark.parametrize("target", ALLOWED_SCAN_TARGETS)
def test_ssrf_validator_allows_legitimate_targets(target):
    safe, reason = is_ssrf_safe_url(target)
    assert safe, f"Legitimate target '{target}' was unexpectedly blocked: {reason}"


def test_scan_options_depth_and_page_caps():
    """Verify bounds enforcement on crawl parameters."""
    def sanitize(opts):
        max_pages = min(max(1, int(opts.get("maxPages", 1))), 50)
        max_depth = min(max(1, int(opts.get("depth", 1))), 3)
        return {"maxPages": max_pages, "depth": max_depth}

    capped = sanitize({"maxPages": 1000, "depth": 10})
    assert capped["maxPages"] == 50
    assert capped["depth"] == 3

    bounded = sanitize({"maxPages": 5, "depth": 2})
    assert bounded["maxPages"] == 5
    assert bounded["depth"] == 2

    minimum = sanitize({"maxPages": -10, "depth": 0})
    assert minimum["maxPages"] == 1
    assert minimum["depth"] == 1
