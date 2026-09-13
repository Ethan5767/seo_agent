"""Free multi-page crawl — pure page discovery + cross-page merge, offline."""
from pipeline.scanner.multipage import discover_pages, merge_by_code

SITEMAP = """<urlset>
  <url><loc>https://x.com/</loc></url>
  <url><loc>https://x.com/services</loc></url>
  <url><loc>https://x.com/about</loc></url>
  <url><loc>https://evil.com/spam</loc></url>
</urlset>"""


def test_discover_from_sitemap_same_origin_only():
    pages = discover_pages("https://x.com/", SITEMAP, "", limit=10)
    assert pages[0] == "https://x.com/"                 # homepage always first
    assert "https://x.com/services" in pages and "https://x.com/about" in pages
    assert "https://evil.com/spam" not in pages         # off-origin dropped


def test_discover_caps_and_dedups():
    sm = "<urlset>" + "".join(f"<url><loc>https://x.com/p{i}</loc></url>" for i in range(20)) + "</urlset>"
    pages = discover_pages("https://x.com/", sm, "", limit=5)
    assert len(pages) == 5 and len(set(pages)) == 5     # capped + unique


def test_discover_falls_back_to_html_links():
    html = '<a href="/team">Team</a> <a href="https://x.com/pricing">Pricing</a> <a href="https://off.com/x">off</a>'
    pages = discover_pages("https://x.com/", "", html, limit=10)
    assert "https://x.com/team" in pages and "https://x.com/pricing" in pages
    assert not any("off.com" in p for p in pages)


def test_merge_by_code_collects_failing_pages():
    per_page = [
        ("https://x.com/a", [{"code": "seo.title", "what": "Title", "why": "w", "fix": "f", "severity": "warn"}]),
        ("https://x.com/b", [{"code": "seo.title", "what": "Title", "why": "w", "fix": "f", "severity": "error"}]),
        ("https://x.com/c", [{"code": "seo.title", "what": "Title", "why": "w", "fix": "f", "severity": "ok"}]),
    ]
    rows = merge_by_code(per_page)
    by = {r["code"]: r for r in rows}
    assert by["seo.title"]["severity"] == "error"       # worst wins
    assert set(by["seo.title"]["pages"]) == {"https://x.com/a", "https://x.com/b"}  # only failing pages
    assert by["seo.title"]["detail"] == "2 page(s)"


def test_build_report_crawls_and_attributes_pages():
    from pipeline.scanner import server
    # 3 pages; /b + /c have no <title> (title missing), homepage has one.
    pages = {
        "https://x.com/": '<html><head><title>Home</title></head><body><main><h1>H</h1></main></body></html>',
        "https://x.com/b": '<html><head></head><body><h1>B</h1></body></html>',
        "https://x.com/c": '<html><head></head><body><h1>C</h1></body></html>',
    }
    sitemap = "<urlset><url><loc>https://x.com/b</loc></url><url><loc>https://x.com/c</loc></url></urlset>"

    def fake_fetch(u):
        return (pages.get(u, ""), 200, "", sitemap)

    rep = server.build_report("https://x.com/", fetch=fake_fetch, crux=None,
                              selected={"seo"}, crawl_pages=3)
    title = next(r for r in rep["seo"] if r["code"] == "health.title_missing")
    assert set(title["pages"]) == {"https://x.com/b", "https://x.com/c"}  # exact pages


def test_build_report_single_page_unchanged():
    from pipeline.scanner import server
    fake = lambda u: ('<html><head></head><body></body></html>', 200, "", "")
    rep = server.build_report("https://x.com/", fetch=fake, crux=None, selected={"seo"}, crawl_pages=1)
    # single-page: rows have no cross-page `pages` attribution
    assert all("pages" not in r for r in rep["seo"])


def test_merge_all_ok_stays_single_ok_no_pages():
    per_page = [
        ("https://x.com/a", [{"code": "tech.https", "what": "HTTPS", "why": "w", "fix": "f", "severity": "ok"}]),
        ("https://x.com/b", [{"code": "tech.https", "what": "HTTPS", "why": "w", "fix": "f", "severity": "ok"}]),
    ]
    rows = merge_by_code(per_page)
    assert len(rows) == 1 and rows[0]["severity"] == "ok" and rows[0]["pages"] == []


def test_a_passing_check_survives_the_multi_page_merge():
    """`merge_by_code` skips codeless rows, and every passing check used to be
    emitted with `code: ""`. So on a multi-page crawl - `seo`, `schema`,
    `content`, `video`, `eeat` and `internal` all run per page - every pass was
    dropped at the merge and the scan reported failures only. Now that a pass
    carries its check's code (`audit._pass_row`), it merges like any other row.
    """
    per_page = [
        ("https://x.com/", [{"code": "health.title_missing", "what": "Page title",
                             "severity": "ok", "why": "", "fix": "passing", "detail": ""}]),
        ("https://x.com/a", [{"code": "health.title_missing", "what": "Page title",
                              "severity": "ok", "why": "", "fix": "passing", "detail": ""}]),
    ]
    merged = merge_by_code(per_page)
    assert [r["code"] for r in merged] == ["health.title_missing"]
    assert merged[0]["severity"] == "ok"
    assert merged[0]["pages"] == []      # an all-ok check names no failing page


def test_one_failing_page_outranks_the_pages_that_passed():
    """Worst severity wins, and only the failing pages are named - the reason a
    pass row can safely share the failure's code."""
    per_page = [
        ("https://x.com/", [{"code": "health.title_missing", "what": "Page title",
                             "severity": "ok", "why": "", "fix": "passing", "detail": ""}]),
        ("https://x.com/a", [{"code": "health.title_missing", "what": "Page title",
                              "severity": "error", "why": "", "fix": "add one", "detail": ""}]),
    ]
    merged = merge_by_code(per_page)
    assert len(merged) == 1
    assert merged[0]["severity"] == "error"
    assert merged[0]["pages"] == ["https://x.com/a"]
