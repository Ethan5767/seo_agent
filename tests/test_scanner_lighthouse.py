"""Lighthouse / PageSpeed Insights parser — pure, offline (canned PSI response)."""
from types import SimpleNamespace

from pipeline.scanner.lighthouse import parse_lighthouse, category_rows, category_tool

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


def test_category_tool_returns_one_category():
    ctx = SimpleNamespace(url="https://x.com")
    rows, status, cost = category_tool(ctx, "seo", "SEO", call=lambda u, k: (PSI, None))
    assert cost == 0.0 and any(r["what"] == "Lighthouse: SEO" for r in rows)
    assert not any(r["what"] == "Lighthouse: Performance" for r in rows)  # only its own category


def test_four_categories_share_one_psi_call():
    ctx = SimpleNamespace(url="https://x.com")
    n = {"c": 0}

    def fake(u, k):
        n["c"] += 1
        return (PSI, None)

    category_tool(ctx, "seo", "SEO", call=fake)
    category_tool(ctx, "performance", "Performance", call=fake)
    category_tool(ctx, "accessibility", "Accessibility", call=fake)
    assert n["c"] == 1  # fetched once, cached on ctx, reused by the others


def test_category_tool_surfaces_error():
    ctx = SimpleNamespace(url="https://x.com")
    rows, status, cost = category_tool(ctx, "seo", "SEO", call=lambda u, k: (None, "HTTP 429 from PageSpeed Insights"))
    assert rows == [] and "429" in status


def test_category_rows_scopes_audits():
    # a11y category lists image-alt (its audit), not meta-description (an SEO audit)
    whats = [r["what"] for r in category_rows(PSI, "accessibility", "Accessibility")]
    assert "Image elements do not have [alt] attributes" in whats
    assert "Document does not have a meta description" not in whats
