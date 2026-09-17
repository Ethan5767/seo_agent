"""Scoped headless rendering triage check for client-rendered shells (CSR).

Used when a page trips the raw-HTML CSR heuristic (< 100 readable words,
text/markup ratio < 0.05). If Playwright is installed and render_verify is
enabled in client config, does a single headless render to verify whether
answer-first text or JSON-LD entities only appear post-hydration.
"""
from __future__ import annotations

import re
from typing import Callable

from pipeline.lib.common import visible_text_ratio

_JSONLD_RE = re.compile(
    r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def is_playwright_available() -> bool:
    """Return True if playwright is importable and available in the environment."""
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except (ImportError, Exception):
        return False


def render_page_playwright(url: str, timeout_ms: int = 30000) -> tuple[str | None, str | None]:
    """Execute a single headless Chromium fetch of the URL and return (html, error)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Playwright is not installed"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                viewport={"width": 1365, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = page.content()
            browser.close()
            return html, None
    except Exception as exc:
        return None, str(exc)


def extract_jsonld_blocks(html: str) -> list[str]:
    """Extract raw JSON-LD text content from <script type='application/ld+json'> tags."""
    if not html:
        return []
    return [block.strip() for block in _JSONLD_RE.findall(html) if block.strip()]


def extract_jsonld_entity_types(html: str) -> set[str]:
    """Extract @type strings from JSON-LD blocks."""
    types: set[str] = set()
    for block in extract_jsonld_blocks(html):
        for match in re.findall(r'"@type"\s*:\s*"([^"]+)"', block):
            types.add(match)
    return types


def extract_top_of_fold_text(html: str, max_words: int = 100) -> str:
    """Extract the first substantial visible content words from the document body."""
    if not html:
        return ""
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.IGNORECASE | re.DOTALL)
    content = body_match.group(1) if body_match else html
    # Strip script, style, svg, noscript
    cleaned = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", content, flags=re.IGNORECASE | re.DOTALL)
    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", cleaned)
    words = text.split()
    return " ".join(words[:max_words]).strip()


def diff_hydrated_content(raw_html: str, rendered_html: str) -> dict:
    """Diff raw HTML vs rendered HTML for word counts, JSON-LD entities, and top-of-fold text."""
    raw_words, _ = visible_text_ratio(raw_html)
    rendered_words, _ = visible_text_ratio(rendered_html)

    raw_blocks = extract_jsonld_blocks(raw_html)
    rendered_blocks = extract_jsonld_blocks(rendered_html)

    raw_types = extract_jsonld_entity_types(raw_html)
    rendered_types = extract_jsonld_entity_types(rendered_html)

    raw_top = extract_top_of_fold_text(raw_html)
    rendered_top = extract_top_of_fold_text(rendered_html)

    # Top-of-fold answer text exists post-render but was absent pre-render
    has_raw_top = len(raw_top.split()) >= 20
    has_rendered_top = len(rendered_top.split()) >= 20
    top_of_fold_gap = has_rendered_top and not has_raw_top

    # JSON-LD entity types or blocks exist post-render but were absent pre-render
    jsonld_gap = bool(rendered_types - raw_types) or (len(rendered_blocks) > len(raw_blocks))

    # Error if answer-first content (top-of-fold text) or JSON-LD entities are present
    # post-render but absent pre-render; warning otherwise
    severity = "error" if (top_of_fold_gap or jsonld_gap) else "warn"

    detail = f"words: {raw_words} -> {rendered_words}, jsonld: {len(raw_blocks)} -> {len(rendered_blocks)}"
    why = (
        "AI crawlers (GPTBot, ClaudeBot, PerplexityBot, etc.) do not execute JS, so if the "
        "answer/entity content only exists post-render, those crawlers see the same empty "
        "shell the raw-HTML scan sees — this finding is a leading indicator, not a false positive to dismiss."
    )

    return {
        "raw_words": raw_words,
        "rendered_words": rendered_words,
        "raw_jsonld_count": len(raw_blocks),
        "rendered_jsonld_count": len(rendered_blocks),
        "top_of_fold_gap": top_of_fold_gap,
        "jsonld_gap": jsonld_gap,
        "severity": severity,
        "detail": detail,
        "why": why,
    }
