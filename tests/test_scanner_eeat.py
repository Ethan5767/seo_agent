from pipeline.scanner.eeat import eeat_rows

RICH = ('<html><body><main>'
        '<script type="application/ld+json">{"@type":"Person","name":"Dr X"}</script>'
        '<a href="tel:+855123">call</a> <a href="/privacy">Privacy</a> <a href="/terms">Terms</a>'
        '<div class="testimonial">★★★★★ great</div>'
        '<p>As featured in the news.</p><table><tr><td>x</td></tr></table>'
        '</main></body></html>')

BARE = '<html><body><p>hello</p></body></html>'


def test_rich_page_passes_trust():
    by = {r["what"]: r for r in eeat_rows(RICH)}
    assert by["Author / expertise"]["severity"] == "ok"
    assert by["Contact / trust"]["severity"] == "ok"
    assert by["Policy links"]["severity"] == "ok"
    assert by["Social proof"]["severity"] == "ok"


def test_bare_page_flags_trust_gaps():
    by = {r["what"]: r for r in eeat_rows(BARE)}
    assert by["Author / expertise"]["severity"] == "warn"
    assert by["Contact / trust"]["severity"] == "warn"
    assert by["Policy links"]["severity"] == "warn"
    assert by["Social proof"]["severity"] == "info"
