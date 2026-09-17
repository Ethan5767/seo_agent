"""Optional Googlebot-like rendering and raw/rendered parity checks."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit
from pipeline.lib.html import page_title

_TEXT = re.compile(r"<body[^>]*>(.*?)</body>", re.I | re.S)
_LINK = re.compile(r"<a\b[^>]*\bhref=[\"']([^\"']+)", re.I)
_META = re.compile(r"<meta\b[^>]*(?:name|property)=[\"']([^\"']+)[\"'][^>]*content=[\"']([^\"']*)", re.I)
_JSONLD = re.compile(r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.I | re.S)


def _text(html: str) -> str:
    body = _TEXT.search(html or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body.group(1) if body else html or "")).strip()


def _links(base: str, html: str) -> set[str]:
    return {urljoin(base, href).split("#", 1)[0] for href in _LINK.findall(html or "") if not href.startswith(("javascript:", "#", "mailto:", "tel:"))}


def diff_documents(url: str, raw_html: str, rendered_html: str) -> list[dict]:
    """Produce normalized legacy-shaped rows for raw/rendered deltas."""
    raw_text, rendered_text = _text(raw_html), _text(rendered_html)
    raw_links, rendered_links = _links(url, raw_html), _links(url, rendered_html)
    rows: list[dict] = []
    if rendered_text and len(rendered_text) > len(raw_text) * 1.2:
        rows.append({"code": "render.content_delta", "what": "Content added only after JavaScript", "severity": "warn",
                     "why": "Raw HTML crawlers may not see content that appears only after rendering.",
                     "fix": "Server-render important content or provide a crawlable fallback.",
                     "detail": f"{len(raw_text)} → {len(rendered_text)} text characters", "confidence": "high"})
    added_links = sorted(rendered_links - raw_links)
    if added_links:
        rows.append({"code": "render.link_delta", "what": "Links added only after JavaScript", "severity": "warn",
                     "why": "Search crawlers may miss navigation that exists only in the rendered DOM.",
                     "fix": "Use real <a href> links in the initial HTML for important navigation.",
                     "detail": f"{len(added_links)} added link(s)", "pages": added_links[:100], "confidence": "high"})
    raw_title = page_title(raw_html) or ""
    rendered_title = page_title(rendered_html) or ""
    if raw_title != rendered_title:
        rows.append({"code": "render.metadata_delta", "what": "Title differs after JavaScript", "severity": "warn",
                     "why": "Google may index a title different from the one a basic crawler sees.",
                     "fix": "Set the canonical title in server-rendered HTML.", "detail": f"raw={raw_title!r}; rendered={rendered_title!r}", "confidence": "high"})
    raw_meta = set(_META.findall(raw_html or ""))
    rendered_meta = set(_META.findall(rendered_html or ""))
    if rendered_meta - raw_meta:
        rows.append({"code": "render.meta_delta", "what": "Meta tags added only after JavaScript", "severity": "warn",
                     "why": "Metadata added after load may be missed or inconsistently processed.",
                     "fix": "Emit canonical, robots, and social metadata in the initial response.", "detail": f"{len(rendered_meta - raw_meta)} added tag(s)", "confidence": "high"})
    raw_schema, rendered_schema = set(_JSONLD.findall(raw_html or "")), set(_JSONLD.findall(rendered_html or ""))
    if rendered_schema - raw_schema:
        rows.append({"code": "render.schema_delta", "what": "Structured data added only after JavaScript", "severity": "warn",
                     "why": "Rich-result markup added after load is less reliable for crawlers to discover.",
                     "fix": "Render important JSON-LD in the initial HTML.", "detail": f"{len(rendered_schema - raw_schema)} added block(s)", "confidence": "medium"})
    return rows or [{"code": "render.no_delta", "what": "Raw and rendered HTML agree", "severity": "ok",
                     "why": "Important text, links, metadata, and structured data were present before JavaScript ran.",
                     "fix": "passing", "detail": "no material delta", "confidence": "high"}]


def render_url(url: str, mobile: bool = False) -> tuple[str | None, str | None]:
    """Render with Playwright when installed; otherwise return a clear state."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Playwright is not installed"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                                           viewport={"width": 390, "height": 844} if mobile else {"width": 1365, "height": 900},
                                           is_mobile=mobile)
            page = context.new_page()
            errors: list[str] = []
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            browser.close()
            return html, "; ".join(errors[:5]) or None
    except Exception as exc:  # browser/network failures are a measured state
        return None, str(exc)


def rendering_rows(url: str, raw_html: str, rendered_html: str | None = None, error: str | None = None) -> list[dict]:
    if rendered_html is None:
        return [{"code": "render.unavailable", "what": "Headless render unavailable", "severity": "info",
                 "why": "Raw HTML checks ran, but a browser render could not be completed.",
                 "fix": "Install/run the Playwright Chromium worker to unlock rendered parity checks.",
                 "detail": error or "no rendered document", "confidence": "low"}]
    rows = diff_documents(url, raw_html, rendered_html)
    if error:
        rows.append({"code": "render.console_errors", "what": "Browser console errors", "severity": "warn",
                     "why": "Console errors can indicate hydration or client-side rendering failures.",
                     "fix": "Resolve the browser errors and re-run the render.", "detail": error, "confidence": "medium"})
    return rows
