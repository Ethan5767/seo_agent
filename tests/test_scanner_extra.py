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


# ── Internal link structure ──────────────────────────────────────────────────
from pipeline.scanner.extra_checks import internal_link_rows


def test_generic_anchor_flagged():
    html = '<a href="/services/">click here</a> <a href="/about/">Our roofing services</a>'
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", html)}
    assert by["Internal links"]["severity"] == "ok"      # 2 internal links
    assert by["Anchor text quality"]["severity"] == "warn"  # "click here"


def test_no_internal_links_warns():
    html = '<a href="https://external.com/">out</a>'
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", html)}
    assert by["Internal links"]["severity"] == "warn"


def test_nofollow_internal_flagged():
    html = '<main><a href="/a/" rel="nofollow">Great services page</a><a href="/b/">About our team</a></main>'
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", html)}
    assert by["Nofollow internal links"]["severity"] == "warn"


def test_links_only_in_nav_warn_contextual():
    html = '<nav><a href="/a/">Home page</a><a href="/b/">Services page</a></nav><main><p>no links</p></main>'
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", html)}
    assert by["Contextual links"]["severity"] == "warn"  # links only in nav, none in main content


def test_in_content_links_pass_contextual():
    html = '<nav><a href="/a/">Nav item</a></nav><main><a href="/b/">In-content link about roofing</a></main>'
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", html)}
    assert by["Contextual links"]["severity"] == "ok"


def test_over_optimized_anchor_flagged():
    links = "".join('<a href="/p%d/">best roofing houston</a>' % i for i in range(7))
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", "<main>" + links + "</main>")}
    assert by["Anchor over-optimization"]["severity"] == "warn"


def test_external_authority_leak():
    html = '<a href="/in/">Internal page</a>' + "".join('<a href="https://x%d.com/">ext</a>' % i for i in range(3))
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", html)}
    assert by["Outbound links"]["severity"] == "warn"  # 3 external > 1 internal


def test_image_link_without_alt():
    html = '<main><a href="/gallery/"><img src="/x.jpg"></a></main>'
    by = {r["what"]: r for r in internal_link_rows("https://s.com/", html)}
    assert by["Image link context"]["severity"] == "warn"


# ── B-093: the video rows belong to the Video tool ───────────────────────────

def test_video_rows_are_stamped_for_the_video_view_not_technical():
    """`extra_checks` binds its module `_row` to "tech", and `video_rows` lived
    here, so every schema row went out as `tech.video_snippets`.

    Nothing caught it because the pass path never reaches this function:
    `youtube.video_rows_full` answers "no video on this page" with its own
    `video.`-stamped row and returns before calling in. Only a page that ACTUALLY
    has a video took the broken branch - the one case the tool exists for.
    """
    from pipeline.scanner.extra_checks import video_rows
    cases = [
        "<html><body>no video at all</body></html>",
        '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>',
        '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>'
        '<script>{"@type":"VideoObject"}</script>',
        '<video src="clip.mp4"></video>',
    ]
    for html in cases:
        for row in video_rows(html):
            assert row["code"].startswith("video."), (
                f"{row['code']} lands in the Technical view; the Video view filters on "
                f"`video.` and would show nothing for a page that has a video"
            )


def test_the_schema_row_matches_the_recommendation_that_exists_for_it():
    """`recommendations.py` keys this finding as `video.video_snippets` and says
    so in a comment. A row stamped `tech.` silently matches nothing, so the
    remediation for the most important video finding never fired."""
    from pipeline.scanner.extra_checks import video_rows
    from pipeline.scanner.recommendations import RECOMMENDATIONS

    rows = video_rows('<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>')
    assert rows[0]["severity"] == "warn"
    assert rows[0]["code"] in RECOMMENDATIONS, (
        f"{rows[0]['code']} has no recommendation; the table keys on video.video_snippets"
    )


def test_every_video_tool_row_reaches_the_video_view():
    """The whole tool, not just the schema half. `video_rows_full` composes two
    sources - this module and youtube.py - and they were stamped differently."""
    from pipeline.scanner.youtube import video_rows_full
    html = '<iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>'
    rows, _status, _cost = video_rows_full(html, call=lambda ids, key: ({"items": [
        {"id": "dQw4w9WgXcQ", "snippet": {"title": "T", "description": "D", "thumbnails": {}},
         "contentDetails": {"duration": "PT1M"}},
    ]}, None), key="fake-key-not-used-by-the-stub")
    assert {r["code"] for r in rows} == {"video.video_snippets", "video.video_metadata"}
