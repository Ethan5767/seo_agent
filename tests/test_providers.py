"""Phase 6 — CrUX, Search Console and DataForSEO.

Only the PURE parsers are covered, which is the honest boundary: the network
paths have never run against the live APIs, and a mocked HTTP round-trip would
prove that the mock matches the code, not that the code matches the vendor.

The property that matters most here is not a parse — it is that a provider with
no credentials returns a SKIP, and that the skip is carried into the artifact. A
provider that silently returned zero findings would make a site look cleaner than
last month, and the ratchet would report the difference as RESOLVED.
"""
from __future__ import annotations

import pytest

from pipeline.audit import providers as p


# ── every skip is loud ───────────────────────────────────────────────────────

@pytest.mark.parametrize("fn,env", [
    (p.crux_findings, ["CRUX_API_KEY"]),
    (p.gsc_findings, ["GSC_ACCESS_TOKEN"]),
    (p.dataforseo_findings, ["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"]),
    (p.serp_findings, ["BRIGHTDATA_API_KEY", "BRIGHTDATA_SERP_ZONE"]),
])
def test_no_credentials_is_a_named_skip_not_an_empty_measurement(fn, env, monkeypatch):
    for key in env:
        monkeypatch.delenv(key, raising=False)
    findings, status = fn("example.com")
    assert findings == []
    assert status.startswith("skipped:")
    assert env[0] in status


# ── CrUX ─────────────────────────────────────────────────────────────────────

def _record(lcp=None, cls=None, inp=None):
    metrics = {}
    if lcp is not None:
        metrics["largest_contentful_paint"] = {"percentiles": {"p75": lcp}}
    if cls is not None:
        metrics["cumulative_layout_shift"] = {"percentiles": {"p75": cls}}
    if inp is not None:
        metrics["interaction_to_next_paint"] = {"percentiles": {"p75": inp}}
    return {"metrics": metrics}


def test_crux_fires_only_outside_the_good_band():
    assert p.parse_crux(_record(lcp=2100, cls="0.05", inp=150), "/") == []
    codes = [f.code for f in p.parse_crux(_record(lcp=4100, cls="0.31", inp=520), "/")]
    assert sorted(codes) == ["crux.cls_above_good", "crux.inp_above_good",
                             "crux.lcp_above_good"]


def test_crux_cls_arrives_as_a_string_and_is_still_compared_numerically():
    """The CrUX API returns CLS as a string. Comparing it as one makes '0.31' <
    '0.1' false for the wrong reason and right by accident."""
    assert [f.code for f in p.parse_crux(_record(cls="0.31"), "/")] == ["crux.cls_above_good"]
    assert p.parse_crux(_record(cls="0.09"), "/") == []


def test_crux_puts_the_volatile_number_in_detail():
    """`detail` is excluded from the fingerprint, so a page whose LCP degrades
    stays PERSISTING rather than becoming a new finding."""
    a = p.parse_crux(_record(lcp=4100), "/")[0]
    b = p.parse_crux(_record(lcp=9900), "/")[0]
    assert a.detail != b.detail
    assert a.fingerprint == b.fingerprint


def test_a_metric_absent_from_the_record_emits_nothing():
    assert p.parse_crux({}, "/") == []
    assert p.parse_crux(_record(lcp=None), "/") == []


def test_crux_queries_the_resolved_origin_not_the_configured_domain(monkeypatch):
    """A client configured as the bare apex whose site redirects to www must be
    queried at the host Chrome actually recorded traffic against — proven live
    2026-08-14: bare wikipedia.org had no CrUX record, en.wikipedia.org did."""
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "www.example.com")
    seen = []

    def fake(endpoint, payload=None, headers=None, timeout=45):
        seen.append(payload)
        return {"record": {}}, None

    monkeypatch.setattr(p, "_request", fake)
    findings, status = p.crux_findings("example.com")
    assert seen == [{"origin": "https://www.example.com"}]
    assert "resolved to www.example.com" in status


def test_a_subdomain_of_the_configured_domain_is_trusted(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "shop.example.com")
    seen = []
    monkeypatch.setattr(p, "_request", lambda e, payload=None, **k: (seen.append(payload), ({"record": {}}, None))[1])
    findings, status = p.crux_findings("example.com")
    assert seen == [{"origin": "https://shop.example.com"}]


def test_an_unresolvable_domain_falls_back_to_the_configured_string(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "")
    seen = []

    def fake(endpoint, payload=None, headers=None, timeout=45):
        seen.append(payload)
        return {"record": {}}, None

    monkeypatch.setattr(p, "_request", fake)
    findings, status = p.crux_findings("example.com")
    assert seen == [{"origin": "https://example.com"}]
    assert "resolved to" not in status


def test_a_resolved_host_that_is_not_the_same_site_is_not_trusted(monkeypatch):
    """B-037's exact scenario: an auth wall (Vercel Deployment Protection,
    Cloudflare Access, Netlify password protection) 302s every route to ITS
    OWN domain, which curl_final_host correctly reports. CrUX has abundant
    real field data for vercel.com — querying it and calling the result the
    client's would be invention, not a measurement."""
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "vercel.com")
    seen = []

    def fake(endpoint, payload=None, headers=None, timeout=45):
        seen.append(payload)
        return {"record": {}}, None

    monkeypatch.setattr(p, "_request", fake)
    findings, status = p.crux_findings("example.com")
    assert seen == [{"origin": "https://example.com"}]
    assert "resolved to" not in status


def test_per_url_mode_does_not_resolve_the_origin(monkeypatch):
    """Per-URL queries are already absolute; resolution only applies to the
    origin-level default path."""
    monkeypatch.setenv("CRUX_API_KEY", "k")

    def boom(url):
        raise AssertionError("curl_final_host must not be called in per-URL mode")

    monkeypatch.setattr(p, "curl_final_host", boom)
    monkeypatch.setattr(p, "_request", lambda *a, **k: ({"record": {}}, None))
    findings, status = p.crux_findings("example.com", urls=["https://example.com/a/"])
    assert status.startswith("ok:")


def test_the_no_field_data_message_names_the_resolved_host(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "www.example.com")
    monkeypatch.setattr(p, "_request", lambda *a, **k: (None, "HTTP 404 from x"))
    findings, status = p.crux_findings("example.com")
    assert findings == []
    assert "www.example.com" in status
    assert "too little traffic" in status


# ── Search Console ───────────────────────────────────────────────────────────

def _row(page, impressions=0, ctr=0.0, position=10.0, query=None):
    keys = [query, page] if query else [page]
    return {"keys": keys, "impressions": impressions, "ctr": ctr, "position": position}


def test_low_ctr_needs_real_impression_volume():
    rows = [_row("https://a.com/x/", impressions=5000, ctr=0.004),
            _row("https://a.com/y/", impressions=12, ctr=0.0)]
    codes = [(f.code, f.location) for f in p.parse_gsc_pages(rows)]
    assert codes == [("gsc.low_ctr", "/x/")], "12 impressions is noise, not a CTR problem"


def test_a_measured_page_the_index_never_showed_is_a_finding():
    rows = [_row("https://a.com/x/", impressions=500, ctr=0.2)]
    found = p.parse_gsc_pages(rows, ["https://a.com/x/", "https://a.com/ghost/"])
    assert [(f.code, f.location) for f in found] == [("gsc.no_impressions", "/ghost/")]


def test_cannibalization_needs_two_competing_pages():
    one = [_row("https://a.com/x/", 500, query="roof repair")]
    assert p.parse_gsc_cannibalization(one) == []
    two = one + [_row("https://a.com/y/", 300, position=4.0, query="roof repair")]
    found = p.parse_gsc_cannibalization(two)
    assert len(found) == 1
    assert found[0].code == "gsc.cannibalization"
    assert found[0].context == "roof repair"
    assert found[0].location == "/y/", "reported against the better-ranking page"


def test_cannibalization_ignores_negligible_impressions():
    rows = [_row("https://a.com/x/", 3, query="q"), _row("https://a.com/y/", 2, query="q")]
    assert p.parse_gsc_cannibalization(rows) == []


# ── DataForSEO ───────────────────────────────────────────────────────────────

def test_dataforseo_pages_produce_the_crawl_wide_findings_http_cannot_see():
    items = [
        {"url": "https://a.com/gone/", "status_code": 404, "click_depth": 1, "checks": {}},
        {"url": "https://a.com/deep/", "status_code": 200, "click_depth": 6, "checks": {}},
        {"url": "https://a.com/dupe/", "status_code": 200, "click_depth": 2,
         "checks": {"duplicate_title": True, "no_image_alt": False}},
    ]
    found = {(f.code, f.location) for f in p.parse_dataforseo_pages(items)}
    assert ("dfs.broken_page", "/gone/") in found
    assert ("dfs.click_depth", "/deep/") in found
    assert ("dfs.duplicate_title", "/dupe/") in found
    assert not any(c == "dfs.image_alt_missing" for c, _ in found), "a False check is not a hit"


def test_dataforseo_ignores_a_check_it_has_no_code_for():
    items = [{"url": "https://a.com/x/", "status_code": 200, "checks": {"invented": True}}]
    assert p.parse_dataforseo_pages(items) == []


def test_dataforseo_tolerates_a_missing_field():
    assert p.parse_dataforseo_pages([{"url": "https://a.com/x/"}]) == []
    assert p.parse_dataforseo_pages([]) == []


# ── provider findings never reach the acceptance gate ────────────────────────

def test_a_provider_code_cannot_be_verified_against_a_build(tmp_path):
    """`check_page` never emits a crux/gsc/dfs code, so "the code no longer fires"
    would be vacuously true. A vacuous pass is worse than no gate."""
    from pipeline.gates import acceptance_check as acc
    out = tmp_path / "out"
    (out / "x").mkdir(parents=True)
    (out / "x" / "index.html").write_text("<html></html>")
    item = {"id": "wi-1", "url": "/x/", "status": "fixed",
            "acceptance": {"check": "code_absent", "code": "crux.lcp_above_good"}}
    ok, msg = acc.verify_item(item, out, {}, "a.com")
    assert not ok and "external provider" in msg


# ── Bright Data SERP ─────────────────────────────────────────────────────────

def _serp(*ranked):
    """A brd_json=1 payload: (rank, link) pairs in the `organic` array."""
    return {"organic": [{"rank": r, "global_rank": r, "link": u,
                         "title": "t", "description": "d"} for r, u in ranked]}


def test_page_one_is_not_a_finding():
    payload = _serp((3, "https://acme.com/roofing/"))
    assert p.parse_serp(payload, "acme.com", "metal roofing") == []


def test_page_two_fires_with_the_query_as_context():
    payload = _serp((1, "https://other.com/"), (14, "https://acme.com/roofing/"))
    found = p.parse_serp(payload, "acme.com", "metal roofing")
    assert [f.code for f in found] == ["serp.page_two"]
    assert found[0].context == "metal roofing"
    assert found[0].location == "/"


def test_rank_and_url_are_volatile_so_they_live_in_detail():
    """The fingerprint must survive a rank change, or the ratchet reports
    RESOLVED plus NEW every single cycle and means nothing."""
    a = p.parse_serp(_serp((12, "https://acme.com/a/")), "acme.com", "q")[0]
    b = p.parse_serp(_serp((27, "https://acme.com/b/")), "acme.com", "q")[0]
    assert a.detail != b.detail
    assert a.fingerprint == b.fingerprint


def test_absent_from_the_results_is_a_finding():
    found = p.parse_serp(_serp((1, "https://other.com/")), "acme.com", "siding")
    assert [f.code for f in found] == ["serp.absent"]
    assert found[0].context == "siding"


def test_ranking_far_down_reads_as_absent_and_says_the_rank():
    """The old fall-through reported "not in the top 1 organic results" about a
    page that WAS the only result — a detail line contradicting its own payload,
    written straight into findings.json."""
    found = p.parse_serp(_serp((61, "https://acme.com/deep/")), "acme.com", "q")
    assert [f.code for f in found] == ["serp.absent"]
    assert "rank=61" in found[0].detail
    assert "top 1" not in found[0].detail


def test_the_best_rank_wins_regardless_of_array_order():
    """Banding inside the scan made the verdict depend on the order the results
    happened to arrive in: a client ranking #4 read as absent because a #61 hit
    for the same site was listed first."""
    payload = _serp((61, "https://acme.com/deep/"), (4, "https://acme.com/good/"))
    assert p.parse_serp(payload, "acme.com", "q") == []


def test_two_queries_are_two_findings():
    """`location` is always "/", so the query in `context` is the ONLY thing
    separating one SERP finding from another. If it stopped discriminating,
    twenty seed queries would collapse into a single finding."""
    a = p.parse_serp(_serp((1, "https://other.com/")), "acme.com", "roof repair")[0]
    b = p.parse_serp(_serp((1, "https://other.com/")), "acme.com", "gutter repair")[0]
    assert a.fingerprint != b.fingerprint


def test_rank_zero_is_not_swallowed_by_the_fallback():
    """A truthiness test sent a 0 to the fallback. Nothing ranks 0 today, so this
    guards the shape, not a live case."""
    payload = {"organic": [{"rank": 0, "global_rank": 99, "link": "https://acme.com/"}]}
    assert p.parse_serp(payload, "acme.com", "q") == []


def test_organic_rank_beats_global_rank():
    """Confirmed live: a #1 organic result returns rank=1, global_rank=4, because
    global_rank counts the ads and SERP features stacked above it. The bands are
    organic positions, so reading global_rank would fire serp.page_two at a site
    that ranks first on a SERP with eleven features above the fold."""
    payload = {"organic": [{"rank": 1, "global_rank": 14, "link": "https://acme.com/"}]}
    assert p.parse_serp(payload, "acme.com", "q") == []


def test_global_rank_is_read_when_rank_is_absent():
    payload = {"organic": [{"global_rank": 14, "link": "https://acme.com/x/"}]}
    found = p.parse_serp(payload, "acme.com", "q")
    assert [f.code for f in found] == ["serp.page_two"]
    assert "rank=14" in found[0].detail


def test_a_lookalike_domain_is_not_the_client():
    """Substring matching would make notacme.com count as acme.com and report a
    rank the client does not have."""
    found = p.parse_serp(_serp((2, "https://notacme.com/x/")), "acme.com", "q")
    assert [f.code for f in found] == ["serp.absent"]


def test_www_and_bare_host_are_the_same_site():
    assert p.parse_serp(_serp((4, "https://www.acme.com/x/")), "acme.com", "q") == []


def test_an_empty_result_set_is_not_evidence_of_absence():
    """No organic array means the fetch or the parse failed. Emitting
    `serp.absent` there would invent a finding out of a broken response."""
    assert p.parse_serp({}, "acme.com", "q") == []
    assert p.parse_serp({"organic": []}, "acme.com", "q") == []
    assert p.parse_serp(None, "acme.com", "q") == []


def test_no_seed_queries_is_a_skip_not_a_clean_sweep(monkeypatch):
    """Zero queries measured must never look like zero problems found."""
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    findings, status = p.serp_findings("acme.com", [])
    assert findings == []
    assert status.startswith("skipped:") and "seed_queries" in status


def test_every_query_failing_is_a_failure_not_a_measurement(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    monkeypatch.setattr(p, "_request", lambda *a, **k: (None, "HTTP 429"))
    findings, status = p.serp_findings("acme.com", ["a", "b"])
    assert findings == []
    assert status.startswith("failed:")
    assert "HTTP 429" in status          # the reason, not just the fact


def test_a_partial_failure_is_named_in_the_status(monkeypatch):
    """A query silently dropped would make the site look cleaner than it is,
    which is exactly what the status string exists to prevent."""
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")

    def fake(url, payload=None, headers=None, timeout=45):
        if "bad" in payload["url"]:
            return None, "HTTP 500"
        return {"organic": [{"rank": 1, "link": "https://other.com/"}]}, None

    monkeypatch.setattr(p, "_request", fake)
    findings, status = p.serp_findings("acme.com", ["good", "bad"])
    assert status.startswith("partial: 1/2"), "'ok:' would lead with ok for a half-measured run"
    assert "1 failed" in status
    assert [f.code for f in findings] == ["serp.absent"]


def test_blank_queries_are_the_same_skip_as_no_queries(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    findings, status = p.serp_findings("acme.com", ["", "   "])
    assert findings == []
    assert status.startswith("skipped:") and "seed_queries" in status


def test_the_query_is_url_encoded_into_the_google_target(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    seen = {}

    def fake(url, payload=None, headers=None, timeout=45):
        seen.update(payload)
        return {"organic": [{"rank": 1, "link": "https://acme.com/"}]}, None

    monkeypatch.setattr(p, "_request", fake)
    p.serp_findings("acme.com", ["metal roofing & siding"])
    assert "metal+roofing+%26+siding" in seen["url"]
    assert "brd_json=1" in seen["url"]
    assert seen["zone"] == "z"
