from pipeline.scanner.onpage import onpage_deep_rows

GOOD = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>T</title>'
        '<meta name="description" content="d"></head>'
        '<body><main><img src="/a.png" width="10" height="10" alt="a"></main></body></html>')

BAD = ('<html><head><title>A</title><title>B</title>'
       '<script src="https://x/app.js"></script></head>'
       '<body><center>old</center>'
       '<a href="http://x" target="_blank">x</a>'
       '<img src="http://x/i.png"></body></html>')


def test_good_page_passes_key_checks():
    by = {r["what"]: r for r in onpage_deep_rows("https://s.com/", GOOD, 200)}
    # charset/doctype now owned by DataForSEO Site Health — gap checks only here
    assert by["Semantic <main>"]["severity"] == "ok"
    assert by["Image dimensions"]["severity"] == "ok"


def test_bad_page_flags_problems():
    by = {r["what"]: r for r in onpage_deep_rows("https://s.com/", BAD, 200)}
    assert by["Single title"]["severity"] == "warn"          # two <title>
    assert by["External link safety"]["severity"] == "warn"  # _blank no noopener
    assert by["Semantic <main>"]["severity"] == "warn"       # no <main>
    # mixed-content / deprecated-html / render-blocking now owned by DataForSEO
