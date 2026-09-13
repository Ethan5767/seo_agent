"""Guard the check catalog against drift: every label in STATIC_CHECKS must be a
label the real row-producer actually emits (pass or fail). If a producer's labels
change, this fails until the catalog is updated — the catalog can't silently lie."""
from pipeline.scanner import audit, content, eeat, extra_checks
from pipeline.scanner.checks import STATIC_CHECKS, checks_for, DYNAMIC_CHECKS

_HTML = ("<html><head><title>x</title><meta name='author' content='me'>"
         "<meta name='viewport' content='width=device-width'>"
         "<script type='application/ld+json'>{\"@type\":\"LocalBusiness\"}</script></head><body>"
         "<h1>H</h1><p>hello world text here</p><table><td>1</td></table>"
         "<ul><li>a</li></ul><a href='/a'>x</a><a href='https://y.com'>y</a></body></html>")


def _labels(rows):
    return {r.get("what") for r in rows}


def _emitted(tool_key: str) -> set:
    if tool_key == "seo":
        return _labels(audit.seo_rows("https://e.com/", _HTML, 200, {}))
    if tool_key == "aeo":
        return _labels(audit.aeo_rows("User-agent: *\nAllow: /", _HTML))
    if tool_key == "content":
        return _labels(content.content_rows(_HTML))
    if tool_key == "eeat":
        return _labels(eeat.eeat_rows(_HTML))
    if tool_key == "tech":
        return _labels(extra_checks.tech_rows("https://e.com/", _HTML, 200, "<urlset></urlset>"))
    if tool_key == "perf":
        return {"LCP (Largest Contentful Paint)", "INP (Interaction to Next Paint)",
                "CLS (Cumulative Layout Shift)"}  # producer needs CrUX; labels are the catalog's own
    return set()


def test_seo_catalog_matches_source_of_truth():
    # seo rows carry the canonical label only when passing (a fail row shows a
    # code-derived label), so guard against SEO_CHECKS itself — the actual source.
    assert STATIC_CHECKS["seo"] == [label for label, _codes, _why in audit.SEO_CHECKS]


def test_fixed_label_tools_really_emit_their_catalog_labels():
    # aeo/content/eeat/tech use stable labels (same string pass or fail), so every
    # catalog label must appear in real producer output.
    for key in ("aeo", "content", "eeat", "tech"):
        emitted = _emitted(key)
        for label in STATIC_CHECKS[key]:
            assert label in emitted, f"catalog check {label!r} not emitted by tool {key}: {sorted(emitted)}"


def test_static_catalog_counts():
    assert len(STATIC_CHECKS["seo"]) == 10
    # 6 -> 8: the AEO tool gained a training-crawler check (blocking GPTBot and
    # friends is a business decision, distinct from blocking a citation crawler)
    # and an answer-engine schema check (FAQPage / QAPage / HowTo / Article).
    assert len(STATIC_CHECKS["aeo"]) == 8
    assert len(STATIC_CHECKS["content"]) == 5


def test_checks_for_falls_back_to_dynamic_then_empty():
    assert checks_for("seo") == STATIC_CHECKS["seo"]
    assert checks_for("backlinks") == DYNAMIC_CHECKS["backlinks"]
    assert checks_for("nonexistent") == []


def test_total_catalog_is_large():
    total = sum(len(v) for v in STATIC_CHECKS.values()) + sum(len(v) for v in DYNAMIC_CHECKS.values())
    assert total >= 100   # the "~140 checks" the UI divides into rows
