"""Lighthouse / PageSpeed Insights parser — pure, offline (canned PSI response)."""
from pipeline.scanner.lighthouse import parse_lighthouse, run_lighthouse

PSI = {"lighthouseResult": {
    "categories": {
        "performance": {"score": 0.95, "title": "Performance"},
        "seo": {"score": 0.82, "title": "SEO", "auditRefs": [
            {"id": "document-title"}, {"id": "meta-description"}, {"id": "http-status-code"}]},
        "accessibility": {"score": 0.7, "title": "Accessibility", "auditRefs": [{"id": "image-alt"}]},
        "best-practices": {"score": 1.0, "title": "Best practices", "auditRefs": []},
    },
    "audits": {
        "document-title": {"title": "Has a <title>", "score": 1, "scoreDisplayMode": "binary"},
        "meta-description": {"title": "Document does not have a meta description", "score": 0,
                             "scoreDisplayMode": "binary", "description": "Meta descriptions… [Learn more](x)"},
        "http-status-code": {"title": "Page has successful HTTP status", "score": 1, "scoreDisplayMode": "binary"},
        "image-alt": {"title": "Image elements do not have [alt] attributes", "score": 0,
                      "scoreDisplayMode": "binary", "description": "Informative elements should aim…"},
    },
}}


def test_category_scores_emitted():
    by = {r["what"]: r for r in parse_lighthouse(PSI)}
    assert by["Lighthouse: Performance"]["severity"] == "ok"      # 95
    assert by["Lighthouse: SEO"]["severity"] == "warn"            # 82
    assert by["Lighthouse: Accessibility"]["severity"] == "warn"  # 70
    assert by["Lighthouse: Best practices"]["severity"] == "ok"   # 100
    assert by["Lighthouse: SEO"]["detail"] == "82/100"


def test_failing_audits_listed_passing_skipped():
    whats = [r["what"] for r in parse_lighthouse(PSI)]
    assert "Document does not have a meta description" in whats   # score 0 → flagged
    assert "Image elements do not have [alt] attributes" in whats
    assert "Has a <title>" not in whats                           # score 1 → skipped
    assert "Page has successful HTTP status" not in whats


def test_meta_description_is_error_severity():
    by = {r["what"]: r for r in parse_lighthouse(PSI)}
    assert by["Document does not have a meta description"]["severity"] == "error"  # score 0
    assert "Learn more" not in by["Document does not have a meta description"]["why"]  # link stripped


def test_empty_result_is_honest_info():
    rows = parse_lighthouse({})
    assert rows and rows[0]["severity"] == "info"


def test_run_lighthouse_uses_injected_caller():
    rows, status, cost = run_lighthouse("https://x.com", call=lambda u, k: (PSI, None))
    assert cost == 0.0 and any(r["what"] == "Lighthouse: SEO" for r in rows)


def test_run_lighthouse_surfaces_error():
    rows, status, cost = run_lighthouse("https://x.com", call=lambda u, k: (None, "HTTP 429 from PageSpeed Insights"))
    assert rows == [] and "429" in status
