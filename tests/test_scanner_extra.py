from pipeline.scanner.extra_checks import tech_rows, visible_text_ratio

GOOD = (
    '<!DOCTYPE html><html lang="en"><head>'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<meta property="og:title" content="T"><meta property="og:description" content="D">'
    '<meta property="og:image" content="/o.png"><meta name="twitter:card" content="summary">'
    '<link rel="icon" href="/favicon.ico">'
    '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>'
    "</head><body><main><h1>Real content</h1>"
    + "<p>" + ("word " * 300) + "</p></main></body></html>"
)

BARE = "<html><head></head><body><div id='root'></div></body></html>"


def test_good_page_passes_the_technical_checks():
    rows = tech_rows("https://x.com/", GOOD, 200, "<urlset><loc>https://x.com/</loc></urlset>")
    oks = {r["what"] for r in rows if r["severity"] == "ok"}
    assert {"HTTPS", "Mobile viewport", "Language declared", "Open Graph tags",
            "XML sitemap"} <= oks


def test_bare_shell_flags_csr_and_missing_tags():
    rows = tech_rows("http://x.com/", BARE, 200, None)
    by = {r["what"]: r for r in rows}
    assert by["HTTPS"]["severity"] == "error"            # http, not https
    assert by["Mobile viewport"]["severity"] == "error"  # no viewport
    assert by["Rendering (crawler-visible content)"]["severity"] == "error"  # empty shell
    assert by["XML sitemap"]["severity"] == "warn"       # no sitemap


def test_visible_text_ratio_detects_empty_shell():
    words, ratio = visible_text_ratio(BARE)
    assert words < 100 and ratio < 0.5
