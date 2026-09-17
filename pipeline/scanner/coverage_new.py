"""Small, owned Site Audit checks that are not covered by existing tools."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit

from pipeline.scanner.rows import make_row

_row = make_row("coverage")


def js_navigation_rows(html: str) -> list[dict]:
    """Find navigation-looking elements without a real anchor href."""
    html = html or ""
    candidates = re.findall(r"<(?:button|div|span)[^>]*(?:onclick|router\.|navigate\(|data-href)[^>]*>", html, re.I)
    anchors = re.findall(r"<a\b[^>]*\bhref\s*=", html, re.I)
    if candidates:
        return [_row("js_only_navigation", "warn",
                     f"Found {len(candidates)} navigation-like element(s) without a real <a href> link.",
                     "Use a crawlable <a href> for primary navigation.", detail=f"{len(candidates)} candidate(s)")]
    return [_row("js_only_navigation", "ok",
                  f"Navigation uses real links ({len(anchors)} anchor(s) found).", "passing", detail=f"{len(anchors)} anchor(s)")]


def parameter_inventory_rows(crawl: dict) -> list[dict]:
    """Classify query parameters observed in crawled URLs."""
    urls = [str(p.get("url") or "") for p in (crawl.get("pages") or [])]
    seen: dict[str, set[str]] = {}
    for url in urls:
        for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
            seen.setdefault(key.lower(), set()).add(value)
    if not seen:
        return [_row("parameter_inventory", "ok", "No query parameters were observed in the crawled URLs.", "passing", detail="0 parameters")]
    tracking = {"utm_source", "utm_medium", "utm_campaign", "gclid", "fbclid", "ref"}
    rows = []
    for key, values in sorted(seen.items()):
        kind = "tracking" if key in tracking or key.startswith("utm_") else "functional/unknown"
        severity = "warn" if kind == "functional/unknown" and len(values) > 3 else "info"
        rows.append(_row(f"parameter_{key}", f"Parameter: {key}", severity,
                         f"Observed {len(values)} value(s) for a {kind} URL parameter.",
                         "Canonicalize or constrain crawlable parameter URLs.", detail=f"{kind}, {len(values)} value(s)"))
    return rows


def interstitial_rows(html: str) -> list[dict]:
    """Conservative static signal for full-viewport mobile overlays."""
    html = html or ""
    patterns = re.findall(r"<(?:div|section)[^>]*(?:modal|interstitial|popup|overlay|consent)[^>]*>", html, re.I)
    if patterns:
        return [_row("mobile_interstitial", "info",
                     "A modal/overlay-like element exists in the HTML; viewport coverage requires a mobile render.",
                     "Verify it does not cover primary content above the fold on mobile.", detail=f"{len(patterns)} candidate(s)")]
    return [_row("mobile_interstitial", "ok", "No modal or interstitial marker was found in the static HTML.", "passing", detail="static check")]
