"""Response-header and live-origin checks (pipeline/scanner/headers_check.py).

Pure: the fetched headers and redirect chain in, rows out. Nothing here touches
the network — the fetchers are injected, the same contract every other free
check module uses.

These checks were impossible until `common.curl_full` existed: `curl -sL`
returned the body alone, so a security header, an X-Robots-Tag, a cache header
and every redirect hop were all invisible, and a soft-404 read as a live page.
"""
from pipeline.scanner.headers_check import (header_rows, redirect_rows,
                                            soft_404_rows, ssl_rows)

SECURE = {
    "strict-transport-security": "max-age=63072000; includeSubDomains",
    "content-security-policy": "default-src 'self'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "cache-control": "public, max-age=3600",
    "content-encoding": "br",
}


def _by(rows):
    return {r["code"]: r for r in rows}


# ── security headers ────────────────────────────────────────────────────────

def test_every_security_header_present_passes():
    by = _by(header_rows(SECURE))
    for code in ("headers.hsts", "headers.content_security_policy", "headers.x-content-type-options",
                 "headers.x-frame-options", "headers.referrer-policy"):
        assert by[code]["severity"] == "ok", code


def test_a_missing_security_header_is_named_one_row_each():
    by = _by(header_rows({}))
    assert by["headers.hsts"]["severity"] == "warn"
    assert "Strict-Transport-Security" in by["headers.hsts"]["why"]
    assert by["headers.x-content-type-options"]["severity"] == "warn"


def test_a_short_hsts_max_age_is_not_a_pass():
    by = _by(header_rows({**SECURE, "strict-transport-security": "max-age=600"}))
    assert by["headers.hsts"]["severity"] == "warn"
    assert "600" in by["headers.hsts"]["detail"]


def test_x_robots_tag_noindex_is_critical_and_read_from_the_header():
    """Only the meta tag was ever checked. A noindex in the header hides a page
    from Google just as completely, and nothing on any screen said so."""
    by = _by(header_rows({**SECURE, "x-robots-tag": "noindex, nofollow"}))
    assert by["headers.x-robots-tag"]["severity"] == "error"
    assert "noindex" in by["headers.x-robots-tag"]["detail"]


def test_x_robots_tag_without_noindex_passes():
    by = _by(header_rows({**SECURE, "x-robots-tag": "max-image-preview:large"}))
    assert by["headers.x-robots-tag"]["severity"] == "ok"


def test_compression_and_cache_are_reported_from_their_headers():
    by = _by(header_rows(SECURE))
    assert by["headers.compression"]["severity"] == "ok"
    assert "br" in by["headers.compression"]["detail"]
    assert by["headers.cache-control"]["severity"] == "ok"
    missing = _by(header_rows({}))
    assert missing["headers.compression"]["severity"] == "warn"
    assert missing["headers.cache-control"]["severity"] == "warn"


def test_no_headers_at_all_reports_unreachable_not_a_clean_bill():
    """An origin that answered nothing must never read as a site with no header
    problems — the rule the gates already hold themselves to (exit 4)."""
    rows = header_rows(None)
    assert len(rows) == 1
    assert rows[0]["code"] == "headers.not_read"
    assert rows[0]["severity"] == "info"


# ── redirects ───────────────────────────────────────────────────────────────

def test_a_single_permanent_hop_passes():
    by = _by(redirect_rows("https://x.com/", [{"status": 301, "location": "https://www.x.com/"},
                                              {"status": 200, "location": ""}]))
    assert by["redirect.chain"]["severity"] == "ok"
    assert "1 hop" in by["redirect.chain"]["detail"]


def test_a_chain_over_one_hop_is_flagged_with_every_hop():
    chain = [{"status": 308, "location": "https://x.com/"},
             {"status": 308, "location": "https://www.x.com/"},
             {"status": 307, "location": "/en"},
             {"status": 200, "location": ""}]
    by = _by(redirect_rows("http://x.com/", chain))
    assert by["redirect.chain"]["severity"] == "warn"
    assert "3 hops" in by["redirect.chain"]["detail"]
    assert "308" in by["redirect.chain"]["why"] and "307" in by["redirect.chain"]["why"]


def test_a_temporary_redirect_into_the_final_page_is_called_out():
    """A 307/302 on the canonical entry path tells Google the move is temporary,
    so the destination inherits nothing."""
    by = _by(redirect_rows("https://x.com/", [{"status": 307, "location": "/en"},
                                              {"status": 200, "location": ""}]))
    assert by["redirect.temporary"]["severity"] == "warn"
    assert "307" in by["redirect.temporary"]["detail"]


def test_a_redirect_loop_is_an_error():
    by = _by(redirect_rows("https://x.com/", [{"status": 301, "location": "https://x.com/a"},
                                              {"status": 301, "location": "https://x.com/"},
                                              {"status": 301, "location": "https://x.com/a"}]))
    assert by["redirect.loop"]["severity"] == "error"


def test_http_and_apex_entry_points_are_checked_separately(monkeypatch):
    """apex -> www and http -> https sit outside the internal link graph, so the
    page crawl can never see them."""
    from pipeline.scanner import headers_check
    seen = []

    def fake(url, **kw):
        seen.append(url)
        if url.startswith("http://"):
            return {"status": 200, "chain": [{"status": 200, "location": ""}], "headers": {}, "body": ""}
        return {"status": 200, "chain": [{"status": 301, "location": "https://www.x.com/"},
                                         {"status": 200, "location": ""}], "headers": {}, "body": ""}

    by = _by(headers_check.entry_point_rows("https://www.x.com/en", fetch=fake))
    assert "http://x.com/" in seen and "https://x.com/" in seen
    # http:// answering 200 with no redirect means the insecure URL is live.
    assert by["redirect.https_upgrade"]["severity"] == "error"
    assert by["redirect.apex"]["severity"] == "ok"


# ── soft 404 ────────────────────────────────────────────────────────────────

def test_a_missing_url_answering_200_is_a_soft_404():
    by = _by(soft_404_rows("https://x.com/", fetch=lambda u, **k: {
        "status": 200, "headers": {}, "chain": [{"status": 200, "location": ""}], "body": "<h1>Home</h1>"}))
    assert by["hygiene.soft_404"]["severity"] == "error"


def test_a_missing_url_answering_404_passes():
    by = _by(soft_404_rows("https://x.com/", fetch=lambda u, **k: {
        "status": 404, "headers": {}, "chain": [{"status": 404, "location": ""}], "body": "<h1>Not found</h1>"}))
    assert by["hygiene.soft_404"]["severity"] == "ok"
    assert "404" in by["hygiene.soft_404"]["detail"]


def test_a_missing_url_redirected_to_a_live_page_is_also_a_soft_404():
    """A 307 to the homepage is the same lie as a 200: nothing tells a crawler
    the URL is gone."""
    by = _by(soft_404_rows("https://x.com/", fetch=lambda u, **k: {
        "status": 200, "headers": {}, "body": "<h1>Home</h1>",
        "chain": [{"status": 307, "location": "/en"}, {"status": 200, "location": ""}]}))
    assert by["hygiene.soft_404"]["severity"] == "error"
    assert "307" in by["hygiene.soft_404"]["detail"]


# ── TLS ─────────────────────────────────────────────────────────────────────

def test_a_certificate_expiring_soon_warns_and_names_the_days():
    by = _by(ssl_rows("https://x.com/", probe=lambda host, port=443: {"days": 12, "issuer": "Let's Encrypt",
                                                                     "not_after": "2026-09-28 00:00:00"}))
    assert by["security.ssl_expiry"]["severity"] == "warn"
    assert "12" in by["security.ssl_expiry"]["detail"]


def test_a_healthy_certificate_passes():
    by = _by(ssl_rows("https://x.com/", probe=lambda host, port=443: {"days": 60, "issuer": "R11",
                                                                     "not_after": "2026-11-15 00:00:00"}))
    assert by["security.ssl_expiry"]["severity"] == "ok"


def test_an_expired_certificate_is_an_error():
    by = _by(ssl_rows("https://x.com/", probe=lambda host, port=443: {"days": -1, "issuer": "R11",
                                                                     "not_after": "2026-09-15 00:00:00"}))
    assert by["security.ssl_expiry"]["severity"] == "error"


def test_a_tls_probe_that_fails_says_so_and_does_not_pass_the_site():
    by = _by(ssl_rows("https://x.com/", probe=lambda host, port=443: {"error": "timed out"}))
    assert by["security.ssl_expiry"]["severity"] == "info"
    assert "timed out" in by["security.ssl_expiry"]["detail"]


def test_a_plain_http_url_is_not_given_a_certificate_verdict():
    assert ssl_rows("http://x.com/", probe=lambda host, port=443: {"days": 90}) == []
