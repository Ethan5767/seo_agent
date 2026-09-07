"""Extra technical on-page checks — free, single-page, no engine dependency.

These are the SOP's page-level technical items that `measure.check_page` does
not cover: mobile viewport, lang, HTTPS, Open Graph / Twitter cards, favicon,
rendering (SSR vs CSR — is the content visible to crawlers at all), sitemap
presence, and a structured-data inventory. Pure: given the fetched HTML (+ the
sitemap text the server fetched), return report rows in the same shape as
audit.py, so the UI renders them identically. Every check shows pass or fail.
"""
from __future__ import annotations

import re


def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": f"tech.{what.lower().replace(' ', '_')}", "what": what,
            "why": why, "fix": fix, "detail": detail, "severity": severity}


def _present(html: str, pattern: str) -> bool:
    return re.search(pattern, html, re.IGNORECASE) is not None


def visible_text_ratio(html: str) -> tuple[int, float]:
    """(word_count, text/html char ratio) after stripping script/style/tags —
    the signal for SSR vs CSR: a big HTML doc with almost no readable text is a
    client-rendered shell that crawlers and AI bots see as empty."""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", body)
    words = len(text.split())
    ratio = len(text.strip()) / len(html) if html else 0.0
    return words, ratio


def tech_rows(url: str, html: str, status: int, sitemap: str | None) -> list[dict]:
    rows: list[dict] = []

    # HTTPS
    if url.lower().startswith("https://"):
        rows.append(_row("HTTPS", "ok", "The page is served securely over HTTPS.", "passing"))
    else:
        rows.append(_row("HTTPS", "error",
                         "Google flags non-HTTPS pages as not secure and ranks them lower.",
                         "Serve the site over HTTPS with a valid certificate."))

    # Mobile viewport
    if _present(html, r'<meta[^>]*name=["\']viewport["\']'):
        rows.append(_row("Mobile viewport", "ok",
                         "A viewport meta tag is set — the page adapts to phones.", "passing"))
    else:
        rows.append(_row("Mobile viewport", "error",
                         "Without a viewport tag the page renders desktop-width on phones; Google uses mobile-first indexing.",
                         'Add <meta name="viewport" content="width=device-width, initial-scale=1">.'))

    # lang attribute
    if _present(html, r'<html[^>]*\blang='):
        rows.append(_row("Language declared", "ok",
                         "The <html lang> attribute helps search engines and screen readers.", "passing"))
    else:
        rows.append(_row("Language declared", "warn",
                         "No <html lang> — search engines and screen readers can't tell the page's language.",
                         'Add a lang attribute, e.g. <html lang="en">.'))

    # Open Graph completeness
    og = [t for t in ("og:title", "og:description", "og:image")
          if _present(html, rf'property=["\']{t}["\']')]
    if len(og) == 3:
        rows.append(_row("Open Graph tags", "ok",
                         "og:title, og:description and og:image are all set — clean link previews.", "passing"))
    else:
        missing = [t for t in ("og:title", "og:description", "og:image") if t not in og]
        rows.append(_row("Open Graph tags", "warn",
                         "Incomplete Open Graph tags make shared links look broken on social and chat.",
                         f"Add the missing tag(s): {', '.join(missing)}.", detail=f"missing {len(missing)}"))

    # Twitter card
    if _present(html, r'name=["\']twitter:card["\']'):
        rows.append(_row("Twitter/X card", "ok", "A twitter:card tag is set for rich previews on X.", "passing"))
    else:
        rows.append(_row("Twitter/X card", "warn",
                         "No twitter:card — links shared on X show a plain URL, not a rich card.",
                         'Add <meta name="twitter:card" content="summary_large_image">.'))

    # Favicon
    if _present(html, r'<link[^>]*rel=["\'][^"\']*icon'):
        rows.append(_row("Favicon", "ok", "A favicon is declared.", "passing"))
    else:
        rows.append(_row("Favicon", "warn", "No favicon — the browser tab and results show a blank icon.",
                         'Add <link rel="icon" href="/favicon.ico">.'))

    # Rendering: SSR vs CSR
    words, ratio = visible_text_ratio(html)
    if words < 100 and ratio < 0.05:
        rows.append(_row("Rendering (crawler-visible content)", "error",
                         "The raw HTML has almost no readable text — the page is likely built in the browser (client-side rendering), so search and AI bots see an empty page.",
                         "Serve the content server-side (SSR/SSG) so it's in the HTML on first load.",
                         detail=f"{words} words in raw HTML"))
    else:
        rows.append(_row("Rendering (crawler-visible content)", "ok",
                         "The content is present in the raw HTML — crawlers and AI bots can read it on first load.",
                         "passing", detail=f"{words} words"))

    # Sitemap
    if sitemap and sitemap.strip() and "<loc>" in sitemap.lower():
        n = len(re.findall(r"<loc>", sitemap, re.IGNORECASE))
        rows.append(_row("XML sitemap", "ok", f"A sitemap.xml is served ({n} URLs) so crawlers can find every page.",
                         "passing", detail=f"{n} URLs"))
    else:
        rows.append(_row("XML sitemap", "warn",
                         "No sitemap.xml found — crawlers may miss pages that aren't well linked.",
                         "Publish /sitemap.xml listing every indexable URL."))

    # Structured-data inventory (informational — what schema exists)
    types = sorted(set(re.findall(r'"@type"\s*:\s*"([^"]+)"', html)))
    if types:
        rows.append(_row("Structured data found", "ok",
                         f"Schema types present: {', '.join(types)}.", "passing",
                         detail=", ".join(types)))
    else:
        rows.append(_row("Structured data found", "warn",
                         "No structured data (JSON-LD) at all — search and AI engines get no machine-readable facts.",
                         "Add relevant schema.org JSON-LD (LocalBusiness, Breadcrumb, etc.)."))

    return rows


# ── Video snippets (SOP Measure: video/multimedia audit) — a DataForSEO gap ──

_VIDEO_ID = re.compile(
    r"(?:youtube\.com/embed/|youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{6,})",
    re.IGNORECASE)


def find_video_ids(html: str) -> list[str]:
    """Embedded YouTube video ids on the page (dedup, order preserved)."""
    seen = []
    for vid in _VIDEO_ID.findall(html or ""):
        if vid not in seen:
            seen.append(vid)
    return seen


def video_rows(html: str) -> list[dict]:
    """One row: are embedded videos backed by VideoObject schema (rich-snippet
    eligible)? No video = nothing to optimise (pass)."""
    ids = find_video_ids(html)
    has_native = "<video" in (html or "").lower()
    if not ids and not has_native:
        return [_row("Video snippets", "ok",
                     "No embedded video on this page — nothing to optimise.", "passing")]
    has_schema = '"@type":"VideoObject"' in (html or "").replace(" ", "").replace("'", '"')
    n = len(ids) or 1
    if has_schema:
        return [_row("Video snippets", "ok",
                     f"{n} video(s) with VideoObject schema — eligible for rich video results and AI citation.",
                     "passing", detail=f"{n} video(s)")]
    return [_row("Video snippets", "warn",
                 f"{n} embedded video(s) but no VideoObject schema — Google/AI can't show a rich video snippet.",
                 "add VideoObject JSON-LD (name, description, thumbnailUrl, uploadDate, duration) per video",
                 detail=f"{n} video(s)")]
