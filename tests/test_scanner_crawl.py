"""Whole-site crawl + site-wide findings (pipeline/scanner/crawl.py).

A fake 5-URL site, fetched through an injected callable (no network):
  /          Home, links -> /a/, /b/
  /a/        title "Dup", links -> /
  /b/        title "Dup"  (duplicate title with /a/), links -> /missing/
  /missing/  404          (broken internal link, reached from /b/)
  /orphan/   200, in sitemap but linked by nobody  (orphan)
"""
from pipeline.scanner.crawl import crawl_site, site_rows, links_in

PAGES = {
    "https://s.com/": '<title>Home</title><a href="/a/">a</a> <a href="/b/">b</a>',
    "https://s.com/a/": '<title>Dup</title><a href="/">home</a>',
    "https://s.com/b/": '<title>Dup</title><a href="/missing/">x</a>',
    "https://s.com/orphan/": "<title>Orphan</title>",
}
SITEMAP = ("<urlset><loc>https://s.com/</loc><loc>https://s.com/a/</loc>"
           "<loc>https://s.com/b/</loc><loc>https://s.com/orphan/</loc></urlset>")


def fetch(url):
    if url == "https://s.com/missing/":
        return "", 404
    html = PAGES.get(url)
    return (html, 200) if html is not None else ("", 404)


def test_links_are_same_site_and_normalized():
    got = links_in("https://s.com/", PAGES["https://s.com/"])
    assert got == {"https://s.com/a/", "https://s.com/b/"}


def test_crawl_reaches_linked_pages_not_the_orphan():
    c = crawl_site("https://s.com/", fetch, sitemap_text=SITEMAP, max_pages=25)
    assert "https://s.com/orphan/" not in c["reachable"]  # only via sitemap
    assert "https://s.com/a/" in c["reachable"]


def test_site_rows_find_dup_title_broken_link_and_orphan():
    rows = site_rows(crawl_site("https://s.com/", fetch, sitemap_text=SITEMAP))
    codes = {r["code"] for r in rows}
    assert "site.duplicate_page_titles" in codes
    assert "site.broken_internal_link" in codes
    assert "site.orphan_page" in codes
    # the summary is always present
    assert any(r["what"] == "Pages crawled" for r in rows)


def test_broken_link_is_an_error_and_orphan_is_a_warn():
    rows = {r["code"]: r for r in site_rows(crawl_site("https://s.com/", fetch, sitemap_text=SITEMAP))}
    assert rows["site.broken_internal_link"]["severity"] == "error"
    assert rows["site.orphan_page"]["severity"] == "warn"


def test_capped_crawl_suppresses_orphan_false_positives():
    # cap at 1 page: the crawl can't judge orphans -> info note, no warns
    rows = site_rows(crawl_site("https://s.com/", fetch, sitemap_text=SITEMAP, max_pages=1))
    codes = {r["code"] for r in rows}
    assert "site.orphan_page" not in codes          # no false orphan warnings
    assert "site.orphan_check" in codes             # honest "incomplete" note instead
    assert next(r for r in rows if r["code"] == "site.orphan_check")["severity"] == "info"


def test_js_nav_site_not_flagged_as_hundreds_of_orphans():
    # homepage has NO raw-HTML links (JS menu); sitemap lists 4 pages.
    js_pages = {
        "https://j.com/": "<title>Home</title>",           # no <a> links
        "https://j.com/a/": "<title>A</title>",
        "https://j.com/b/": "<title>B</title>",
        "https://j.com/c/": "<title>C</title>",
    }
    smap = "<urlset><loc>https://j.com/</loc><loc>https://j.com/a/</loc><loc>https://j.com/b/</loc><loc>https://j.com/c/</loc></urlset>"
    def jfetch(u):
        h = js_pages.get(u)
        return (h, 200) if h is not None else ("", 404)
    rows = site_rows(crawl_site("https://j.com/", jfetch, sitemap_text=smap, max_pages=25))
    codes = {r["code"] for r in rows}
    assert "site.orphan_page" not in codes           # not a wall of false orphans
    note = next(r for r in rows if r["code"] == "site.orphan_check")
    assert note["severity"] == "info"
    assert "JavaScript" in note["why"]
