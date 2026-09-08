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


def test_merge_all_ok_stays_single_ok_no_pages():
    per_page = [
        ("https://x.com/a", [{"code": "tech.https", "what": "HTTPS", "why": "w", "fix": "f", "severity": "ok"}]),
        ("https://x.com/b", [{"code": "tech.https", "what": "HTTPS", "why": "w", "fix": "f", "severity": "ok"}]),
    ]
    rows = merge_by_code(per_page)
    assert len(rows) == 1 and rows[0]["severity"] == "ok" and rows[0]["pages"] == []
