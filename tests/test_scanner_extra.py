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


# ── Video snippets ───────────────────────────────────────────────────────────
from pipeline.scanner.extra_checks import find_video_ids, video_rows


def test_finds_youtube_ids():
    html = '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>'
    assert find_video_ids(html) == ["dQw4w9WgXcQ"]


def test_video_without_schema_warns():
    html = '<iframe src="https://youtu.be/abc123xyz"></iframe>'
    assert video_rows(html)[0]["severity"] == "warn"


def test_video_with_schema_ok():
    html = ('<iframe src="https://youtu.be/abc123xyz"></iframe>'
            '<script type="application/ld+json">{"@type":"VideoObject"}</script>')
    assert video_rows(html)[0]["severity"] == "ok"


def test_no_video_is_pass():
    assert video_rows("<html><body>no video</body></html>")[0]["severity"] == "ok"
