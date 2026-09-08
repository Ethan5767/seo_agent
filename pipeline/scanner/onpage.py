"""Deep on-page checks — the gaps DataForSEO's on-page crawl does NOT cover.

DataForSEO's on-page audit (Site Health card) is the source of truth for
everything it crawls: charset, doctype, render-blocking, deprecated tags, H2s,
meta-refresh, placeholder/lorem, flash, mixed-content (https->http), meta
keywords. Per the DataForSEO-first rule we do NOT re-implement those.

What stays here is only what DataForSEO's crawl can't see on the one page we
already fetched: multiple title/description/canonical tags, target=_blank
safety, CLS-risk image dimensions, DOM weight, link volume, hreflang, semantic
<main>, URL hygiene, heading order, iframe/inline-style weight, empty links,
apple-touch-icon. Free, synchronous, pure (HTML in, rows out).
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit


from pipeline.scanner.rows import make_row
_row = make_row("op")


def _ok(what, why):
    return _row(what, "ok", why, "passing")


def onpage_deep_rows(url: str, html: str, status: int) -> list[dict]:
    h = html or ""
    low = h.lower()
    rows: list[dict] = []

    # Single <title> / single meta description (multiple on ONE page — DataForSEO
    # only flags duplicates ACROSS pages, not two tags on the same page).
    if len(re.findall(r"<title[\s>]", low)) > 1:
        rows.append(_row("Single title", "warn", "More than one <title> tag — search engines pick one unpredictably.",
                         "Keep exactly one <title>."))
    if len(re.findall(r'<meta[^>]*name=["\']description["\']', low)) > 1:
        rows.append(_row("Single meta description", "warn", "Multiple meta description tags — conflicting snippets.",
                         "Keep exactly one meta description."))

    # target=_blank without rel=noopener (security + tab-nabbing)
    blanks = re.findall(r"<a\b[^>]*target=[\"']_blank[\"'][^>]*>", low)
    unsafe = [a for a in blanks if "noopener" not in a and "noreferrer" not in a]
    if unsafe:
        rows.append(_row("External link safety", "warn",
                         f"{len(unsafe)} target=_blank link(s) without rel=noopener — a security/perf risk.",
                         'Add rel="noopener" to target=_blank links.', detail=f"{len(unsafe)}"))

    # Images without width/height (layout shift / CLS)
    imgs = re.findall(r"<img\b[^>]*>", low)
    no_dims = [i for i in imgs if not (re.search(r"\bwidth=", i) and re.search(r"\bheight=", i))]
    if imgs:
        if no_dims:
            rows.append(_row("Image dimensions", "warn",
                             f"{len(no_dims)}/{len(imgs)} image(s) missing width/height — causes layout shift (CLS).",
                             "Set width and height on <img> so the browser reserves space.",
                             detail=f"{len(no_dims)} of {len(imgs)}"))
        else:
            rows.append(_ok("Image dimensions", "All images declare width/height (no layout shift)."))

    # DOM weight
    elements = len(re.findall(r"<[a-zA-Z]", h))
    if elements > 1500:
        rows.append(_row("DOM size", "warn",
                         f"~{elements} elements — a heavy DOM slows rendering and hurts INP.",
                         "Simplify the markup / paginate long lists.", detail=f"~{elements} nodes"))

    # Link volume
    links = len(re.findall(r"<a\b[^>]*href=", low))
    if links > 100:
        rows.append(_row("Link volume", "warn",
                         f"{links} links on the page — excessive linking dilutes authority per link.",
                         "Trim to the meaningful links.", detail=f"{links} links"))

    # hreflang (multi-region signal — informational)
    if re.search(r'<link[^>]*hreflang=', low):
        rows.append(_ok("hreflang", "hreflang alternates are declared (multi-language/region aware)."))

    # Semantic landmark
    if "<main" not in low:
        rows.append(_row("Semantic <main>", "warn",
                         "No <main> landmark — weaker structure for assistive tech and content extraction.",
                         "Wrap the primary content in <main>."))
    else:
        rows.append(_ok("Semantic <main>", "A <main> landmark marks the primary content."))

    # ── URL hygiene ──────────────────────────────────────────────────────────
    parts = urlsplit(url)
    if len(url) > 115:
        rows.append(_row("URL length", "warn", f"URL is long ({len(url)} chars) — long URLs read poorly and truncate in results.",
                         "shorten the slug", detail=f"{len(url)} chars"))
    if "_" in parts.path:
        rows.append(_row("URL underscores", "warn", "URL uses underscores — Google treats hyphens as word separators, not underscores.",
                         "use hyphens in slugs"))
    if parts.path != parts.path.lower():
        rows.append(_row("URL case", "warn", "URL has uppercase letters — can create duplicate-URL issues.",
                         "use lowercase URLs"))
    if parts.query:
        rows.append(_row("URL parameters", "info", "URL has query parameters — prefer clean paths for key landing pages.",
                         "use a clean path where possible"))

    # ── Headings ─────────────────────────────────────────────────────────────
    if re.search(r"<h1", low) and re.search(r"<h3", low) and not re.search(r"<h2", low):
        rows.append(_row("Heading order", "warn", "Heading levels skip (H1 → H3 with no H2) — confuses structure/readers.",
                         "don't skip heading levels"))

    # ── Misc technical (single-page only — DataForSEO owns site-wide) ─────────
    if len(re.findall(r'rel=["\']canonical', low)) > 1:
        rows.append(_row("Single canonical", "warn", "Multiple canonical tags — conflicting signals to Google.",
                         "keep exactly one canonical"))
    iframes = len(re.findall(r"<iframe\b", low))
    if iframes > 3:
        rows.append(_row("Iframe count", "warn", f"{iframes} iframes — heavy and often slow/insecure.",
                         "reduce iframes", detail=f"{iframes}"))
    inline = len(re.findall(r'\bstyle=["\']', low))
    if inline > 25:
        rows.append(_row("Inline styles", "warn", f"{inline} inline style attributes — move to CSS for caching + smaller HTML.",
                         "extract to a stylesheet", detail=f"{inline}"))
    empties = len(re.findall(r'href=["\'](?:#|)["\']', low))
    if empties:
        rows.append(_row("Empty links", "warn", f"{empties} empty / '#' link(s) — dead anchors waste crawl + confuse users.",
                         "give links a real destination", detail=f"{empties}"))
    if not re.search(r'rel=["\'][^"\']*apple-touch-icon', low):
        rows.append(_row("Apple touch icon", "info", "No apple-touch-icon — the home-screen icon on iOS falls back to a screenshot.",
                         "add <link rel=apple-touch-icon>"))

    return rows
