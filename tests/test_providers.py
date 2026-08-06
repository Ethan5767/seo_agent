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
