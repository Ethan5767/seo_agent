from pipeline.scanner.validate import sitemap_validation_rows, hreflang_rows, validate_rows


def test_valid_sitemap():
    sm = "<urlset><loc>https://s.com/</loc><loc>https://s.com/a/</loc></urlset>"
    by = {r["what"]: r for r in sitemap_validation_rows(sm)}
    assert by["Sitemap valid"]["severity"] == "ok" and by["Sitemap valid"]["detail"] == "2 URLs"


def test_sitemap_http_urls_warn():
    sm = "<urlset><loc>http://s.com/</loc></urlset>"
    by = {r["what"]: r for r in sitemap_validation_rows(sm)}
    assert by["Sitemap URL scheme"]["severity"] == "warn"


def test_sitemap_index_ok():
    sm = "<sitemapindex><sitemap><loc>https://s.com/sm1.xml</loc></sitemap></sitemapindex>"
    assert sitemap_validation_rows(sm)[0]["what"] == "Sitemap index"


def test_no_sitemap_no_rows():
    assert sitemap_validation_rows("") == []


def test_hreflang_missing_x_default_warns():
    html = '<link rel="alternate" hreflang="en" href="/en/"><link rel="alternate" hreflang="km" href="/km/">'
    by = {r["what"]: r for r in hreflang_rows(html)}
    assert by["hreflang x-default"]["severity"] == "warn"


def test_hreflang_with_x_default_ok():
    html = ('<link rel="alternate" hreflang="en" href="/en/">'
            '<link rel="alternate" hreflang="x-default" href="/">')
    by = {r["what"]: r for r in hreflang_rows(html)}
    assert by["hreflang set"]["severity"] == "ok"


def test_no_hreflang_no_rows():
    assert hreflang_rows("<html></html>") == []
