"""Deep single-page on-page checks — pure, offline.

The module the spec listed and nobody wrote. These tests care about two things:
that each check fires on a page that really has the defect, and that it does NOT
fire on a clean page. A check that only ever warns is noise, and a check that
never warns is decoration.
"""

from pipeline.scanner.onpage import onpage_rows, DEPRECATED_TAGS

CLEAN = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>A Perfectly Ordinary Page</title>'
    '<meta name="description" content="Ordinary.">'
    '<link rel="canonical" href="https://x.com/page">'
    '<link rel="apple-touch-icon" href="/t.png">'
    '<script src="/a.js" defer></script></head>'
    '<body><main><h1>H</h1><h2>One</h2><p>Real copy.</p><h2>Two</h2>'
    '<img src="/a.png" width="10" height="10" alt="a">'
    '<a href="/x">text</a></main></body></html>'
)
CLEAN_URL = "https://x.com/page"


def _by(rows):
    return {r["what"]: r for r in rows}


def test_all_twenty_eight_checks_run_on_any_page():
    """The spec says 28. A missing one is a check nobody notices is absent."""
    rows = onpage_rows(CLEAN_URL, CLEAN)
    assert len(rows) == 28, f"expected 28 checks, got {len(rows)}"
    assert len({r["what"] for r in rows}) == 28, "two checks share a name"


def test_every_row_carries_a_code_and_a_severity():
    for r in onpage_rows(CLEAN_URL, CLEAN):
        assert r["code"].startswith("onpage."), r
        assert r["severity"] in ("ok", "warn", "error", "info"), r
        assert r["what"] and r["why"] and r["fix"], r


def test_a_clean_page_raises_nothing_actionable():
    """The other half of the contract: no check may fire on a good page."""
    bad = [r["what"] for r in onpage_rows(CLEAN_URL, CLEAN)
           if r["severity"] in ("warn", "error")]
    assert bad == [], f"clean page flagged: {bad}"


def test_a_totally_empty_document_does_not_throw():
    for html in ("", "<html></html>", None):
        rows = onpage_rows("https://x.com/", html or "")
        assert len(rows) == 28


# ── head hygiene ────────────────────────────────────────────────────────────

def test_charset_and_doctype():
    by = _by(onpage_rows(CLEAN_URL, "<html><head></head><body></body></html>"))
    assert by["Charset"]["severity"] == "warn"
    assert by["Doctype"]["severity"] == "warn"


def test_duplicate_title_description_and_canonical():
    html = ('<head><title>a</title><title>b</title>'
            '<meta name="description" content="a"><meta name="description" content="b">'
            '<link rel="canonical" href="/a"><link rel="canonical" href="/b"></head>')
    by = _by(onpage_rows(CLEAN_URL, html))
    assert by["Single title"]["severity"] == "warn"
    assert by["Single meta description"]["severity"] == "warn"
    # Two canonicals is an ERROR, not a warning: conflicting canonicals are
    # ignored outright, so the page ends up with none at all.
    assert by["Single canonical"]["severity"] == "error"


def test_meta_refresh_and_legacy_keywords():
    html = ('<head><meta http-equiv="refresh" content="0;url=/b">'
            '<meta name="keywords" content="a,b"></head>')
    by = _by(onpage_rows(CLEAN_URL, html))
    assert by["Meta refresh"]["severity"] == "warn"
    # Harmless, so info: it tells competitors your targets and nothing reads it.
    assert by["Legacy meta keywords"]["severity"] == "info"


# ── the URL ─────────────────────────────────────────────────────────────────

def test_url_shape_checks():
    by = _by(onpage_rows("https://x.com/Some_Long_Path?a=1&b=2&c=3", CLEAN))
    assert by["URL underscores"]["severity"] == "info"
    assert by["URL case"]["severity"] == "warn"       # /About and /about split signals
    assert by["URL parameters"]["severity"] == "warn"
    assert by["URL length"]["severity"] == "ok"

    long_url = "https://x.com/" + "a" * 200
    assert _by(onpage_rows(long_url, CLEAN))["URL length"]["severity"] == "info"


# ── the body ────────────────────────────────────────────────────────────────

def test_mixed_content_only_counts_on_an_https_page():
    insecure = '<body><img src="http://x.com/a.png"></body>'
    assert _by(onpage_rows("https://x.com/", insecure))["Mixed content"]["severity"] == "error"
    # On an http page it is not yet a defect; the page itself is the problem.
    assert _by(onpage_rows("http://x.com/", insecure))["Mixed content"]["severity"] == "info"


def test_target_blank_without_noopener():
    by = _by(onpage_rows(CLEAN_URL, '<body><a href="/x" target="_blank">go</a></body>'))
    assert by["External link safety"]["severity"] == "warn"
    safe = '<body><a href="/x" target="_blank" rel="noopener">go</a></body>'
    assert _by(onpage_rows(CLEAN_URL, safe))["External link safety"]["severity"] == "ok"


def test_render_blocking_script_must_be_in_head_and_unqualified():
    head_blocking = '<head><script src="/a.js"></script></head>'
    assert _by(onpage_rows(CLEAN_URL, head_blocking))["Render-blocking scripts"]["severity"] == "warn"
    for ok in ('<head><script src="/a.js" defer></script></head>',
               '<head><script src="/a.js" async></script></head>',
               '<head><script src="/a.js" type="module"></script></head>',
               '<body><script src="/a.js"></script></body>'):
        assert _by(onpage_rows(CLEAN_URL, ok))["Render-blocking scripts"]["severity"] == "ok", ok


def test_image_dimensions_and_the_no_images_case():
    by = _by(onpage_rows(CLEAN_URL, '<body><img src="/a.png"><img src="/b.png" width="1" height="1"></body>'))
    assert by["Image dimensions"]["severity"] == "warn"
    assert "1 of 2" in by["Image dimensions"]["detail"]
    # No images is not a failure, and must not read as one.
    assert _by(onpage_rows(CLEAN_URL, "<body></body>"))["Image dimensions"]["severity"] == "info"


def test_deprecated_elements_are_named_in_the_detail():
    by = _by(onpage_rows(CLEAN_URL, "<body><center><font>x</font></center></body>"))
    assert by["Deprecated HTML"]["severity"] == "warn"
    assert "center" in by["Deprecated HTML"]["detail"] and "font" in by["Deprecated HTML"]["detail"]
    assert len(DEPRECATED_TAGS) >= 8


def test_dom_size_escalates_rather_than_only_warning():
    # Node count is opening tags, so N divs is N nodes, not 2N.
    warn = "<body>" + "<div>x</div>" * 1600 + "</body>"       # ~1600 nodes
    err = "<body>" + "<div>x</div>" * 3200 + "</body>"        # ~3200 nodes
    assert _by(onpage_rows(CLEAN_URL, warn))["DOM size"]["severity"] == "warn"
    assert _by(onpage_rows(CLEAN_URL, err))["DOM size"]["severity"] == "error"


def test_link_volume_and_semantic_main_and_subheadings():
    many = "<body>" + '<a href="/a">a</a>' * 200 + "</body>"
    by = _by(onpage_rows(CLEAN_URL, many))
    assert by["Link volume"]["severity"] == "warn"
    assert by["Semantic main"]["severity"] == "warn"          # none present
    assert by["Subheadings"]["severity"] == "warn"            # no h2

    two_mains = "<body><main></main><main></main></body>"
    assert _by(onpage_rows(CLEAN_URL, two_mains))["Semantic main"]["severity"] == "warn"


def test_heading_order_flags_a_skipped_level():
    by = _by(onpage_rows(CLEAN_URL, "<body><h1>a</h1><h4>b</h4></body>"))
    assert by["Heading order"]["severity"] == "warn"
    # Descending one at a time is fine, and so is going back up.
    fine = "<body><h1>a</h1><h2>b</h2><h3>c</h3><h2>d</h2></body>"
    assert _by(onpage_rows(CLEAN_URL, fine))["Heading order"]["severity"] == "ok"


def test_hreflang_requires_a_self_reference():
    no_self = ('<head><link rel="alternate" hreflang="fr" href="https://x.com/fr">'
               '</head><body></body>')
    assert _by(onpage_rows(CLEAN_URL, no_self))["hreflang"]["severity"] == "warn"
    with_self = (f'<head><link rel="alternate" hreflang="en" href="{CLEAN_URL}">'
                 '<link rel="alternate" hreflang="fr" href="https://x.com/fr"></head>')
    assert _by(onpage_rows(CLEAN_URL, with_self))["hreflang"]["severity"] == "ok"
    # A single-locale site has no hreflang and that is not a gap.
    assert _by(onpage_rows(CLEAN_URL, CLEAN))["hreflang"]["severity"] == "info"


def test_placeholder_text_is_an_error_because_it_shipped():
    for filler in ("Lorem ipsum dolor sit amet", "INSERT TEXT HERE", "Coming soon", "TODO"):
        by = _by(onpage_rows(CLEAN_URL, f"<body><main><p>{filler}</p></main></body>"))
        assert by["Placeholder text"]["severity"] == "error", filler
    # Must not fire on ordinary copy, and must not read the markup as copy.
    assert _by(onpage_rows(CLEAN_URL, CLEAN))["Placeholder text"]["severity"] == "ok"


def test_flash_iframes_inline_styles_and_empty_links():
    by = _by(onpage_rows(CLEAN_URL, '<body><embed src="/a.swf"></body>'))
    assert by["Flash"]["severity"] == "error"

    many_frames = "<body>" + '<iframe src="/a"></iframe>' * 6 + "</body>"
    assert _by(onpage_rows(CLEAN_URL, many_frames))["Iframe count"]["severity"] == "warn"

    styled = "<body>" + '<div style="color:red">x</div>' * 25 + "</body>"
    assert _by(onpage_rows(CLEAN_URL, styled))["Inline styles"]["severity"] == "info"

    assert _by(onpage_rows(CLEAN_URL, '<body><a href="/x"></a></body>'))["Empty links"]["severity"] == "warn"


def test_an_icon_link_with_a_label_is_not_an_empty_link():
    """The commonest false positive: an icon-only link IS labelled, three ways."""
    for ok in ('<a href="/x" aria-label="Home"></a>',
               '<a href="/x" title="Home"></a>',
               '<a href="/x"><img src="/i.png" alt="Home"></a>'):
        by = _by(onpage_rows(CLEAN_URL, f"<body>{ok}</body>"))
        assert by["Empty links"]["severity"] == "ok", ok


def test_no_check_duplicates_what_seo_rows_already_judges():
    """`audit.seo_rows` owns title length, H1 count, canonical presence and
    indexability. Two checks over one fact is how a finding gets two names."""
    names = {r["what"].lower() for r in onpage_rows(CLEAN_URL, CLEAN)}
    for owned in ("page title", "meta description", "single main heading (h1)",
                  "canonical tag", "indexable (not noindexed)", "image alt text"):
        assert owned not in names, f"{owned!r} belongs to seo_rows"
