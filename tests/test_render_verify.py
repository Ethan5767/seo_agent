"""Unit and integration tests for scoped headless render triage in Measure stage."""
from __future__ import annotations

import pytest

import pipeline.audit.measure as m
import pipeline.audit.render_verify as rv


CSR_RAW_SHELL = """<!DOCTYPE html>
<html>
<head>
  <title>Test Application Shell</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="/static/css/main.chunk.css">
  <link rel="preload" href="/static/js/bundle.js" as="script">
</head>
<body>
  <div id="root"></div>
  <script src="/static/js/runtime.js"></script>
  <script src="/static/js/vendors.chunk.js"></script>
  <script src="/static/js/main.chunk.js"></script>
</body>
</html>
"""

HYDRATED_WITH_ANSWER_AND_SCHEMA = """<!DOCTYPE html>
<html>
<head>
  <title>Test App</title>
  <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "LocalBusiness", "name": "Acme Services"}
  </script>
</head>
<body>
  <main>
    <h1>Expert Roofing Services In Charlotte NC</h1>
    <p>We provide full residential and commercial roof replacement, storm damage inspection, and gutter installation with licensed specialists across Mecklenburg County.</p>
    <p>Call our office today for a same-day written quote and complete warranty details.</p>
  </main>
</body>
</html>
"""

HYDRATED_MINIMAL_ONLY = """<!DOCTYPE html>
<html>
<head><title>Test App</title></head>
<body>
  <div id="root">
    <span>Loading application state...</span>
  </div>
</body>
</html>
"""


def test_render_verify_opt_in_gating():
    """When render_verify is not enabled in cfg, standard CSR heuristic runs without triage."""
    called = False

    def mock_fetcher(url):
        nonlocal called
        called = True
        return HYDRATED_WITH_ANSWER_AND_SCHEMA, None

    findings = m.check_page(
        "https://example.com/",
        CSR_RAW_SHELL,
        200,
        cfg={"render_verify": False},
        render_fetcher=mock_fetcher,
    )

    assert not called, "Headless fetcher should not be called when render_verify is False"
    codes = [f.code for f in findings]
    assert "health.csr_empty_shell" in codes
    assert "health.csr_content_gap" not in codes

    csr_finding = next(f for f in findings if f.code == "health.csr_empty_shell")
    assert "render-verify unavailable" not in csr_finding.detail


def test_render_verify_playwright_unavailable_fallback(monkeypatch):
    """When render_verify is True but Playwright is not installed, attach lower-confidence note."""
    monkeypatch.setattr(m, "is_playwright_available", lambda: False)

    findings = m.check_page(
        "https://example.com/",
        CSR_RAW_SHELL,
        200,
        cfg={"render_verify": True},
        render_fetcher=None,
    )

    codes = [f.code for f in findings]
    assert "health.csr_empty_shell" in codes
    assert "health.csr_content_gap" not in codes

    csr_finding = next(f for f in findings if f.code == "health.csr_empty_shell")
    expected_note = "render-verify unavailable — install requirements-render.txt for confirmation"
    assert expected_note in csr_finding.detail


def test_render_verify_detects_answer_and_schema_gap():
    """When render_verify is True and hydrated DOM reveals missing answer/schema, emit error finding."""
    def mock_fetcher(url):
        return HYDRATED_WITH_ANSWER_AND_SCHEMA, None

    findings = m.check_page(
        "https://example.com/",
        CSR_RAW_SHELL,
        200,
        cfg={"render_verify": True},
        render_fetcher=mock_fetcher,
    )

    codes = [f.code for f in findings]
    assert "health.csr_empty_shell" in codes
    assert "health.csr_content_gap" in codes

    gap = next(f for f in findings if f.code == "health.csr_content_gap")
    assert gap.severity == "error"
    assert "words: 0 ->" in gap.detail or "words:" in gap.detail
    assert "jsonld: 0 -> 1" in gap.detail
    assert "AI crawlers" in gap.why
    assert "GPTBot" in gap.why
    assert "ClaudeBot" in gap.why
    assert "PerplexityBot" in gap.why

    # Verify to_json preserves metadata
    json_rep = gap.to_json()
    assert json_rep["code"] == "health.csr_content_gap"
    assert json_rep["severity"] == "error"
    assert "AI crawlers" in json_rep["why"]


def test_render_verify_without_gap_is_warning():
    """When hydrated DOM also lacks substantial content and schema, emit warning severity."""
    def mock_fetcher(url):
        return HYDRATED_MINIMAL_ONLY, None

    findings = m.check_page(
        "https://example.com/",
        CSR_RAW_SHELL,
        200,
        cfg={"render_verify": True},
        render_fetcher=mock_fetcher,
    )

    codes = [f.code for f in findings]
    assert "health.csr_content_gap" in codes

    gap = next(f for f in findings if f.code == "health.csr_content_gap")
    assert gap.severity == "warn"
    assert "jsonld: 0 -> 0" in gap.detail


def test_render_verify_fetch_error_handling():
    """When headless fetch fails, emit warning finding with error details."""
    def mock_fetcher(url):
        return None, "Connection refused or timed out after 30s"

    findings = m.check_page(
        "https://example.com/",
        CSR_RAW_SHELL,
        200,
        cfg={"render_verify": True},
        render_fetcher=mock_fetcher,
    )

    gap = next(f for f in findings if f.code == "health.csr_content_gap")
    assert gap.severity == "warn"
    assert "render-verify error" in gap.detail
    assert "Connection refused" in gap.detail


def test_diff_hydrated_content_unit():
    """Verify standalone diff calculation for words, JSON-LD, top-of-fold, and why text."""
    diff = rv.diff_hydrated_content(CSR_RAW_SHELL, HYDRATED_WITH_ANSWER_AND_SCHEMA)
    assert diff["raw_words"] == 3
    assert diff["rendered_words"] > 20
    assert diff["raw_jsonld_count"] == 0
    assert diff["rendered_jsonld_count"] == 1
    assert diff["top_of_fold_gap"] is True
    assert diff["jsonld_gap"] is True
    assert diff["severity"] == "error"
    assert "words: 3 ->" in diff["detail"]
    assert "jsonld: 0 -> 1" in diff["detail"]
    assert "AI crawlers" in diff["why"]


def test_extract_jsonld_blocks_and_entities():
    """Verify JSON-LD block and @type extraction helpers."""
    html = """
    <script type="application/ld+json">{"@type": "Organization", "name": "Org1"}</script>
    <div>Middle</div>
    <script type="application/ld+json">{"@type": "LocalBusiness", "name": "Biz2"}</script>
    """
    blocks = rv.extract_jsonld_blocks(html)
    assert len(blocks) == 2
    types = rv.extract_jsonld_entity_types(html)
    assert types == {"Organization", "LocalBusiness"}


def test_extract_top_of_fold_text():
    """Verify top-of-fold text extraction cleans non-body tags."""
    html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <script>const x = 1;</script>
        <noscript>Enable JS</noscript>
        <svg><text>Ignored</text></svg>
        <main><h1>Main Title</h1><p>First paragraph with substantive information.</p></main>
      </body>
    </html>
    """
    text = rv.extract_top_of_fold_text(html)
    assert "Main Title" in text
    assert "First paragraph with substantive information." in text
    assert "color: red" not in text
    assert "const x = 1" not in text


@pytest.mark.integration
@pytest.mark.skipif(not rv.is_playwright_available(), reason="Playwright is not installed")
@pytest.mark.skip(reason="Live browser integration test requiring unblocked network; run explicitly with -m integration")
def test_real_browser_headless_render():
    """Real browser integration test (opt-in only, skipped by default in hermetic suite)."""
    html, err = rv.render_page_playwright("https://example.com")
    assert err is None
    assert html is not None
    assert "<html" in html.lower()
