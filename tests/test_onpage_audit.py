"""The on-page audit: what it runs, what the health score counts, and the
per-page summary the Dashboard and Site Audit tables read.

Operator, 2026-09-15: "Run audit" ran all 16 free tools, and the health score
counted keyword rankings and Lighthouse rows, so running Rankings raised "Site
Health" with no change to the site. The audit is now a named tool set, and the
score counts only the groups that set produces.
"""

from pipeline.scanner import server
from pipeline.scanner.audit import HEALTH_SCORE_VERSION, SCORED_GROUPS, assemble
from pipeline.scanner.crawl import site_rows


def _row(code, severity):
    return {"code": code, "severity": severity, "what": code, "why": "", "fix": "", "detail": ""}


# ── The tool set ────────────────────────────────────────────────────────────

def test_the_onpage_audit_is_free_and_reads_only_the_site():
    keys = {t.key: t for t in server.TOOLS}
    assert server.ONPAGE_AUDIT_TOOLS == ("seo", "onpage", "tech", "schema", "validate", "internal")
    for k in server.ONPAGE_AUDIT_TOOLS:
        assert k in keys, f"{k} is not a scanner tool"
        assert keys[k].group == "free", f"{k} costs money; the on-page audit must not"


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
    assert HEALTH_SCORE_VERSION == 3


def test_scored_groups_are_the_audit_tools_plus_the_crawl():
    assert set(SCORED_GROUPS) == set(server.ONPAGE_AUDIT_TOOLS) | {"site"}


def test_rankings_and_lighthouse_rows_do_not_move_site_health():
    audit = {"seo": [_row("health.title_missing", "ok"), _row("health.h1_missing", "error")]}
    alone = assemble(dict(audit))
    with_paid = assemble({**audit,
                          "rankings": [_row("dfs.ranked_keyword", "ok") for _ in range(15)],
                          "lh_seo": [_row("lh.lighthouse_seo", "ok")]})
    assert alone["score"] == 50
    assert with_paid["score"] == 50, "15 ranked keywords raised the site's health"
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
