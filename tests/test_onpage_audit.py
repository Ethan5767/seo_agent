"""The on-page audit: what it runs, what the health score counts, and the
per-page summary the Dashboard and Site Audit tables read.

Operator, 2026-09-15: "Run audit" ran all 16 free tools, and the health score
counted keyword rankings and Lighthouse rows, so running Rankings raised "Site
Health" with no change to the site. The audit is now a named tool set, and the
score counts only the groups that set produces.
"""

from pipeline.scanner import server
from pipeline.scanner.audit import HEALTH_SCORE_VERSION, SCORED_GROUPS, assemble, health_score, unweighted_health_score
from pipeline.scanner.crawl import site_rows


def _row(code, severity):
    return {"code": code, "severity": severity, "what": code, "why": "", "fix": "", "detail": ""}


# ── The tool set ────────────────────────────────────────────────────────────

def test_the_onpage_audit_runs_every_technical_onpage_tool_only():
    keys = {t.key: t for t in server.TOOLS}
    assert server.ONPAGE_AUDIT_TOOLS == (
        "seo", "site", "onpage", "tech", "headers", "monitor", "schema", "validate",
        "internal", "aeo", "perf", "lh_perf", "lh_seo", "lh_a11y", "lh_bp", "lh_pages", "render", "media", "security", "url")
    for k in server.ONPAGE_AUDIT_TOOLS:
        assert k in keys, f"{k} is not a scanner tool"
    assert keys["site"].group == "dataforseo"
    assert all(keys[k].group == "free" for k in server.ONPAGE_AUDIT_TOOLS if k != "site")


def test_the_web_runs_and_scores_the_same_lists():
    """The web keeps its own copy (it cannot import Python). This pins the copy."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "web/lib/auditBreakdown.ts").read_text()
    def listed(name):
        m = re.search(rf"export const {name}[^=]*=\s*\[([^\]]*)\]", src)
        assert m, f"{name} not found in web/lib/auditBreakdown.ts"
        return re.findall(r'"([^"]+)"', m.group(1))
    assert tuple(listed("ONPAGE_AUDIT_TOOLS")) == server.ONPAGE_AUDIT_TOOLS
    assert set(listed("SCORED_GROUPS")) == set(SCORED_GROUPS)


# ── The score counts the audit, nothing else ────────────────────────────────

def test_score_version_is_bumped_for_the_scope_change():
    assert HEALTH_SCORE_VERSION == 4


def test_weighted_score_prioritises_a_critical_finding_and_keeps_v3_available():
    rows = [_row("health.title_missing", "error"), _row("onpage.charset", "ok")]
    assert health_score(rows) == 17
    assert unweighted_health_score({"ok": 1, "warn": 0, "error": 1}) == 50


def test_every_explicit_weight_uses_the_exact_code_emitted_by_a_check():
    """Pin the policy names to the actual strings emitted by scanner tools.

    A typo here silently demotes a check to the medium default, so this list is
    deliberately exhaustive rather than testing one representative per tier.
    """
    from pipeline.scanner.audit import score_weight
    critical = {
        "health.noindex_present", "headers.x-robots-tag", "health.title_missing",
        "health.canonical_mismatch", "tech.https", "hygiene.soft_404", "redirect.loop",
    }
    high = {
        "health.desc_missing", "health.h1_count", "onpage.single_title",
        "onpage.mixed_content", "tech.mobile_viewport", "tech.xml_sitemap",
        "health.thin_content", "tech.structured_data_found", "schema.structured_data",
        "schema.valid_json-ld", "schema.schema_@type", "redirect.chain",
        "site.duplicate_page_titles", "site.broken_internal_link",
    }
    low = {
        "onpage.apple_touch_icon", "tech.favicon", "tech.twitter/x_card",
        "onpage.legacy_meta_keywords", "onpage.inline_styles", "onpage.url_case",
        "onpage.url_underscores", "onpage.iframe_count",
    }
    assert {code: score_weight(_row(code, "error")) for code in critical} == dict.fromkeys(critical, 10)
    assert {code: score_weight(_row(code, "error")) for code in high} == dict.fromkeys(high, 5)
    assert {code: score_weight(_row(code, "error")) for code in low} == dict.fromkeys(low, 1)
    # Common near-misses from the pre-v4 draft must not become accidental aliases.
    assert score_weight(_row("headers.soft-404", "error")) == 2
    assert score_weight(_row("schema.json_ld_invalid", "error")) == 2


def test_assemble_ships_backend_weight_and_category_on_every_scored_row():
    report = assemble({"seo": [_row("health.title_missing", "error")],
                       "tech": [_row("onpage.charset", "ok")]})
    assert report["score"] == 17
    assert report["score_breakdown"]["total_weight"] == 12
    assert report["seo"][0]["score_weight"] == 10
    assert report["seo"][0]["score_category"] == "titles"
    assert report["tech"][0]["score_weight"] == 2


# Scored: the audit's own page-level checks. Not scored, and why: AEO is its own
# pillar, CrUX is field data that moves without the site changing, and the
# Lighthouse cards are Google's verdict — folding them in grades a page twice.
UNSCORED_AUDIT_TOOLS = {"aeo", "perf", "monitor", "lh_perf", "lh_seo", "lh_a11y", "lh_bp", "lh_pages", "render", "media", "security", "url"}


def test_scored_groups_are_the_audit_tools_plus_the_crawl():
    assert set(SCORED_GROUPS) == (set(server.ONPAGE_AUDIT_TOOLS) - UNSCORED_AUDIT_TOOLS) | {"site"}


def test_every_unscored_audit_tool_is_really_in_the_audit():
    """A name left here after a tool is renamed would silently un-score a real
    check. The exclusions are only honest while they name live tools."""
    assert UNSCORED_AUDIT_TOOLS <= set(server.ONPAGE_AUDIT_TOOLS)
    assert not (UNSCORED_AUDIT_TOOLS & set(SCORED_GROUPS))


def test_rankings_and_lighthouse_rows_do_not_move_site_health():
    audit = {"seo": [_row("health.title_missing", "ok"), _row("health.h1_missing", "error")]}
    alone = assemble(dict(audit))
    with_paid = assemble({**audit,
                          "rankings": [_row("dfs.ranked_keyword", "ok") for _ in range(15)],
                          "lh_seo": [_row("lh.lighthouse_seo", "ok")]})
    assert alone["score"] == 83
    assert with_paid["score"] == 83, "15 ranked keywords raised the site's health"
    assert with_paid["graded"] == 2
    assert with_paid["counts"] == {"error": 1, "warn": 0, "info": 0, "ok": 1}


def test_every_row_is_still_counted_somewhere():
    """The panels for rankings and speed still need their numbers."""
    rep = assemble({"seo": [_row("a", "warn")], "rankings": [_row("b", "ok"), _row("c", "warn")]})
    assert rep["counts_all"] == {"error": 0, "warn": 2, "info": 0, "ok": 1}


def test_a_scan_with_no_audit_groups_has_no_health_score():
    """A Backlinks-only run measured nothing about the site's pages."""
    rep = assemble({"backlinks": [_row("dfs.backlinks", "ok")]})
    assert rep["score"] is None and rep["graded"] == 0


# ── Site-wide rows name their pages ─────────────────────────────────────────

def _walk():
    return {
        "pages": [
            {"url": "https://x.com/", "status": 200, "title": "Same", "desc": "", "links": ["https://x.com/a", "https://x.com/gone"]},
            {"url": "https://x.com/a", "status": 200, "title": "Same", "desc": "", "links": ["https://x.com/gone"]},
            {"url": "https://x.com/gone", "status": 404, "title": "", "desc": "", "links": []},
        ],
        "reachable": {"https://x.com/", "https://x.com/a", "https://x.com/gone"},
        "sitemap_urls": [],
        "capped": False,
    }


def test_duplicate_title_rows_list_the_pages_that_share_it():
    dup = next(r for r in site_rows(_walk()) if r["what"] == "Duplicate page titles")
    assert dup["pages"] == ["https://x.com/", "https://x.com/a"]


def test_broken_link_rows_list_the_pages_that_link_to_it():
    broken = next(r for r in site_rows(_walk()) if r["what"] == "Broken internal link")
    assert broken["pages"] == ["https://x.com/", "https://x.com/a"]


# ── The per-page summary ────────────────────────────────────────────────────

PAGES = {
    "https://x.com/": ('<html><head><title>Home page</title><meta name="description" content="Welcome">'
                       '</head><body><main><h1>Home</h1><p>one two three four</p>'
                       '<a href="/b">B</a><a href="/c">C</a></main></body></html>'),
    "https://x.com/b": '<html><head></head><body><h1>B</h1><p>alpha beta</p><a href="/">home</a></body></html>',
    "https://x.com/c": '<html><head></head><body><h1>C</h1><h1>C2</h1><a href="/">home</a></body></html>',
}
SITEMAP = "<urlset><url><loc>https://x.com/b</loc></url><url><loc>https://x.com/c</loc></url></urlset>"


def _report(**kw):
    fetch = lambda u: (PAGES.get(u, ""), 200 if u in PAGES else 404, "", SITEMAP)
    return server.build_report("https://x.com/", fetch=fetch, crux=None,
                               selected=set(server.ONPAGE_AUDIT_TOOLS), **kw)


def test_the_crawl_summary_has_one_entry_per_page():
    rep = _report(crawl_pages=3)
    pages = rep["crawl"]["pages"]
    assert pages[0]["url"] == "https://x.com/", "the audited URL comes first"
    assert {p["url"] for p in pages} == {"https://x.com/", "https://x.com/b", "https://x.com/c"}
    by = {p["url"]: p for p in pages}
    home = pages[0]
    assert home["status"] == 200
    assert home["title"] == "Home page"
    assert home["has_description"] is True
    assert home["h1_count"] == 1
    assert home["words"] > 0
    assert home["links_out"] == 2
    assert by["https://x.com/c"]["h1_count"] == 2
    assert by["https://x.com/b"]["links_in"] == 1


def test_each_page_carries_its_own_failing_checks():
    rep = _report(crawl_pages=3)
    by = {p["url"]: p for p in rep["crawl"]["pages"]}
    assert "health.title_missing" in by["https://x.com/b"]["issues"]
    assert "health.title_missing" not in by["https://x.com/"]["issues"]
    for p in by.values():
        sevs = list(p["issues"].values())
        assert p["errors"] == sevs.count("error") and p["warnings"] == sevs.count("warn")


def test_the_summary_is_not_a_row_group():
    """Every list at the top of a report is read as rows, by `assemble` and by
    the web's `rowsOf`. The summary is an object, so it can never be graded."""
    rep = _report(crawl_pages=3)
    assert isinstance(rep["crawl"], dict)
    assert rep["crawl"]["requested"] == 3


def test_a_single_page_audit_still_summarises_the_homepage():
    rep = _report(crawl_pages=1)
    assert [p["url"] for p in rep["crawl"]["pages"]] == ["https://x.com/"]


def test_an_unreachable_site_has_no_page_summary():
    fetch = lambda u: ("", 0, "", "")
    rep = server.build_report("https://x.com/", fetch=fetch, crux=None,
                              selected=set(server.ONPAGE_AUDIT_TOOLS), crawl_pages=3)
    assert rep["crawl"] is None


def test_every_seo_check_failure_has_a_plain_name():
    """An issue list showed "title length" and "h1 count": the code, not a name."""
    from pipeline.scanner.audit import FAILURE_NAMES, SEO_CHECKS
    codes = {c for _, cs, _ in SEO_CHECKS for c in cs}
    assert codes == set(FAILURE_NAMES), "a check code without a failure name, or a name for no check"
    rep = _report(crawl_pages=3)
    failing = [r for r in rep["seo"] if r["severity"] in ("error", "warn")]
    assert failing, "the fixture should fail some SEO checks"
    for r in failing:
        assert r["what"] == FAILURE_NAMES[r["code"]]


def test_a_multi_page_scan_fetches_each_page_once():
    """Depth is time: the crawl is serial. It used to fetch every page twice —
    map it, then re-read the body for the per-page tools — so the depth cap sat
    at 25. One read per page is what makes a 100-page audit affordable."""
    seen = []

    def fetch(u):
        seen.append(u)
        return (PAGES.get(u, ""), 200 if u in PAGES else 404, "", SITEMAP)

    server.build_report("https://x.com/", fetch=fetch, crux=None,
                        selected=set(server.ONPAGE_AUDIT_TOOLS), crawl_pages=3)
    pages = [u for u in seen if u in PAGES]
    assert len(pages) == len(set(pages)), f"refetched: {pages}"


def test_the_crawl_depth_cap_reaches_a_real_site():
    assert server.MAX_CRAWL_PAGES >= 100


def test_robots_and_sitemap_are_read_once_per_origin_not_once_per_page(monkeypatch):
    """`_default_fetch` reads the page, robots.txt AND sitemap.xml, and the crawl
    calls it once per page — so a 100-page audit made 200 extra requests for two
    files that cannot change during one scan. Measured on a real 2026-09-16 run:
    ~20s a page, most of it this."""
    from pipeline.lib import common
    from pipeline.audit import measure as M

    asked = []
    server._forget_origin_files()

    def fake_full(url, cache_bust=True, follow=True):
        asked.append(url)
        return {"body": "<html></html>", "status": 200, "headers": {}, "chain": [{"status": 200, "location": ""}]}

    def fake_curl(url, cache_bust=True):
        asked.append(url)
        return "text"

    monkeypatch.setattr(common, "curl_full", fake_full)
    monkeypatch.setattr(M, "curl", fake_curl)

    for path in ("/", "/a", "/b", "/c"):
        server._default_fetch(f"https://x.com{path}")

    assert len([u for u in asked if u.endswith("/robots.txt")]) == 1, asked
    assert len([u for u in asked if u.endswith("/sitemap.xml")]) == 1, asked
    assert len([u for u in asked if "robots" not in u and "sitemap" not in u]) == 4


def test_a_different_origin_reads_its_own_robots_and_sitemap(monkeypatch):
    from pipeline.lib import common
    from pipeline.audit import measure as M
    asked = []
    server._forget_origin_files()
    monkeypatch.setattr(common, "curl_full", lambda url, cache_bust=True, follow=True: (
        asked.append(url), {"body": "", "status": 200, "headers": {}, "chain": []})[1])
    monkeypatch.setattr(M, "curl", lambda url, cache_bust=True: (asked.append(url), "text")[1])
    server._default_fetch("https://x.com/")
    server._default_fetch("https://y.com/")
    assert len([u for u in asked if u.endswith("/robots.txt")]) == 2
