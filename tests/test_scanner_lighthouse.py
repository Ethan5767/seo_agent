"""Lighthouse / PageSpeed Insights parser — pure, offline (canned PSI response)."""
from types import SimpleNamespace

from pipeline.scanner.lighthouse import parse_lighthouse, category_rows, category_tool

PSI = {"lighthouseResult": {
    "categories": {
        "performance": {"score": 0.95, "title": "Performance"},
        "seo": {"score": 0.82, "title": "SEO", "auditRefs": [
            {"id": "document-title"}, {"id": "meta-description"}, {"id": "http-status-code"}]},
        "accessibility": {"score": 0.7, "title": "Accessibility", "auditRefs": [{"id": "image-alt"}]},
        "best-practices": {"score": 1.0, "title": "Best practices", "auditRefs": []},
    },
    "audits": {
        "document-title": {"title": "Has a <title>", "score": 1, "scoreDisplayMode": "binary"},
        "meta-description": {"title": "Document does not have a meta description", "score": 0,
                             "scoreDisplayMode": "binary", "description": "Meta descriptions… [Learn more](x)"},
        "http-status-code": {"title": "Page has successful HTTP status", "score": 1, "scoreDisplayMode": "binary"},
        "image-alt": {"title": "Image elements do not have [alt] attributes", "score": 0,
                      "scoreDisplayMode": "binary", "description": "Informative elements should aim…"},
    },
}}


def test_category_scores_emitted():
    by = {r["what"]: r for r in parse_lighthouse(PSI)}
    assert by["Lighthouse: Performance"]["severity"] == "ok"      # 95
    assert by["Lighthouse: SEO"]["severity"] == "warn"            # 82
    assert by["Lighthouse: Accessibility"]["severity"] == "warn"  # 70
    assert by["Lighthouse: Best practices"]["severity"] == "ok"   # 100
    assert by["Lighthouse: SEO"]["detail"] == "82/100"


def test_failing_audits_listed_passing_skipped():
    whats = [r["what"] for r in parse_lighthouse(PSI)]
    assert "Document does not have a meta description" in whats   # score 0 → flagged
    assert "Image elements do not have [alt] attributes" in whats
    assert "Has a <title>" not in whats                           # score 1 → skipped
    assert "Page has successful HTTP status" not in whats


def test_meta_description_is_error_severity():
    by = {r["what"]: r for r in parse_lighthouse(PSI)}
    assert by["Document does not have a meta description"]["severity"] == "error"  # score 0
    assert "Learn more" not in by["Document does not have a meta description"]["why"]  # link stripped


def test_empty_result_is_honest_info():
    rows = parse_lighthouse({})
    assert rows and rows[0]["severity"] == "info"


def test_category_tool_returns_one_category():
    ctx = SimpleNamespace(url="https://x.com")
    rows, status, cost = category_tool(ctx, "seo", "SEO", call=lambda u, k: (PSI, None))
    assert cost == 0.0 and any(r["what"] == "Lighthouse: SEO" for r in rows)
    assert not any(r["what"] == "Lighthouse: Performance" for r in rows)  # only its own category


def test_four_categories_share_one_psi_call():
    ctx = SimpleNamespace(url="https://x.com")
    n = {"c": 0}

    def fake(u, k):
        n["c"] += 1
        return (PSI, None)

    category_tool(ctx, "seo", "SEO", call=fake)
    category_tool(ctx, "performance", "Performance", call=fake)
    category_tool(ctx, "accessibility", "Accessibility", call=fake)
    assert n["c"] == 1  # fetched once, cached on ctx, reused by the others


def test_category_tool_surfaces_error():
    ctx = SimpleNamespace(url="https://x.com")
    rows, status, cost = category_tool(ctx, "seo", "SEO", call=lambda u, k: (None, "HTTP 429 from PageSpeed Insights"))
    assert rows == [] and "429" in status


def test_category_rows_scopes_audits():
    # a11y category lists image-alt (its audit), not meta-description (an SEO audit)
    whats = [r["what"] for r in category_rows(PSI, "accessibility", "Accessibility")]
    assert "Image elements do not have [alt] attributes" in whats
    assert "Document does not have a meta description" not in whats


# ── Lighthouse across the crawled pages ─────────────────────────────────────
#
# One PSI run measured the audited URL and nothing else, so "Performance 95" on
# a 167-page site was one page's verdict standing in for all of them. The depth
# is the operator's choice (10 / 25 / every crawled page), because each page is
# one PSI round trip.

def _doc(score):
    return {"lighthouseResult": {"categories": {"performance": {"score": score, "title": "Performance"}}}}


SITE = {"https://x.com/": 0.95, "https://x.com/a": 0.42, "https://x.com/b": 0.71, "https://x.com/c": 0.30}


def _call(url, key):
    return (_doc(SITE[url]), None) if url in SITE else (None, "HTTP 400 from PageSpeed Insights")


def test_page_scores_measures_each_url_and_ranks_the_worst_first():
    from pipeline.scanner.lighthouse import page_scores
    rows, status = page_scores(list(SITE), call=_call)
    by = {r["code"]: r for r in rows}
    assert "ok (Google Lighthouse, 4 page(s))" == status
    slow = by["lh.pages_below_50"]
    assert slow["severity"] == "error"
    assert slow["pages"] == ["https://x.com/c", "https://x.com/a"], "worst first"
    assert by["lh.pages_below_90"]["pages"] == ["https://x.com/b"]
    # The summary row is a fact, not a verdict: with slow pages in the set it
    # stays `info` so it cannot score as a passing check while pages fail.
    assert by["lh.pages_measured"]["severity"] == "info"
    assert "4" in by["lh.pages_measured"]["detail"]


def test_a_site_where_every_page_is_fast_passes():
    from pipeline.scanner.lighthouse import page_scores
    fast = {"https://f.com/": 0.95, "https://f.com/a": 0.92}
    rows, _ = page_scores(list(fast), call=lambda u, k: (_doc(fast[u]), None))
    by = {r["code"]: r for r in rows}
    assert by["lh.pages_measured"]["severity"] == "ok"
    assert "lh.pages_below_50" not in by and "lh.pages_below_90" not in by


def test_page_scores_limit_is_the_operators_depth():
    from pipeline.scanner.lighthouse import page_scores
    rows, status = page_scores(list(SITE), limit=2, call=_call)
    assert "2 page(s)" in status
    measured = {r["code"]: r for r in rows}["lh.pages_measured"]
    assert "2" in measured["detail"]


def test_a_page_psi_refuses_is_named_never_counted_as_fast():
    from pipeline.scanner.lighthouse import page_scores
    rows, status = page_scores(["https://x.com/", "https://x.com/gone"], call=_call)
    by = {r["code"]: r for r in rows}
    assert by["lh.pages_not_measured"]["severity"] == "info"
    assert by["lh.pages_not_measured"]["pages"] == ["https://x.com/gone"]
    assert "1" in by["lh.pages_measured"]["detail"]


def test_no_urls_measures_nothing_and_says_so():
    from pipeline.scanner.lighthouse import page_scores
    rows, status = page_scores([], call=_call)
    assert rows == []
    assert "no pages" in status


def test_the_pages_tool_measures_what_the_crawl_found_at_the_chosen_depth(monkeypatch):
    """Wiring, not parsing: the depth an operator picks must reach PSI, and the
    pages it measures must be the crawled ones (B-007 — a tool nothing calls at
    the right depth is a tool that does not exist)."""
    from pipeline.scanner import lighthouse
    from pipeline.scanner import server

    asked = []

    def fake_call(url, key):
        asked.append(url)
        return _doc(0.4), None

    monkeypatch.setattr(lighthouse, "_psi_call", fake_call)
    # Trailing slashes: the crawler normalises links to the directory form and
    # fetches that, so the fixture serves what it will actually ask for.
    PAGES = {"https://x.com/": "<html><head><title>T</title></head><body><h1>H</h1>"
                               '<a href="/b/">b</a><a href="/c/">c</a></body></html>',
             "https://x.com/b/": "<html><body><h1>B</h1></body></html>",
             "https://x.com/c/": "<html><body><h1>C</h1></body></html>"}
    fetch = lambda u: (PAGES.get(u, ""), 200 if u in PAGES else 404, "", "")
    rep = server.build_report("https://x.com/", fetch=fetch, crux=None,
                              selected={"lh_pages"}, crawl_pages=3, lighthouse_pages=3)
    assert sorted(asked) == sorted(PAGES), f"measured {asked}"
    assert len(asked) == len(set(asked)), "each page measured once"
    codes = {r["code"] for rows in rep.values() if isinstance(rows, list) for r in rows if isinstance(r, dict)}
    assert "lh.pages_below_50" in codes


def test_without_a_multi_page_crawl_it_measures_the_audited_url_alone(monkeypatch):
    from pipeline.scanner import lighthouse
    from pipeline.scanner import server
    asked = []
    monkeypatch.setattr(lighthouse, "_psi_call", lambda u, k: (asked.append(u), (_doc(0.95), None))[1])
    fetch = lambda u: ("<html><head><title>T</title></head><body><h1>H</h1></body></html>", 200, "", "")
    server.build_report("https://x.com/", fetch=fetch, crux=None, selected={"lh_pages"})
    assert asked == ["https://x.com/"]


def test_the_depth_cap_trims_the_crawl(monkeypatch):
    """An operator who crawled 25 pages may still want Lighthouse on 10 of them:
    each page is a round trip to Google."""
    from pipeline.scanner import lighthouse
    from pipeline.scanner import server
    asked = []
    monkeypatch.setattr(lighthouse, "_psi_call", lambda u, k: (asked.append(u), (_doc(0.9), None))[1])
    PAGES = {"https://y.com/": '<html><head><title>T</title></head><body><h1>H</h1>'
                               '<a href="/b/">b</a><a href="/c/">c</a></body></html>',
             "https://y.com/b/": "<html><body><h1>B</h1></body></html>",
             "https://y.com/c/": "<html><body><h1>C</h1></body></html>"}
    fetch = lambda u: (PAGES.get(u, ""), 200 if u in PAGES else 404, "", "")
    server.build_report("https://y.com/", fetch=fetch, crux=None, selected={"lh_pages"},
                        crawl_pages=3, lighthouse_pages=2)
    assert len(asked) == 2, f"measured {asked}"
