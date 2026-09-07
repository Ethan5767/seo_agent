"""Web brand mentions — DataForSEO Content Analysis. Where the brand is talked
about across the web (news/blogs/forums) and the sentiment. Read-only measure.

Endpoint not in the tested INPUTS-17 doc — parser built to the documented
Content Analysis shape; verify against a live response. Pure parser + injectable
caller.
"""
from __future__ import annotations

from pipeline.scanner.dataforseo import _tool, LOCATION_CODE, LANGUAGE_CODE


def _row(what, severity, why, fix, detail=""):
    return {"code": f"mention.{what.lower().replace(' ', '_')}", "what": what,
            "why": why, "fix": fix, "detail": detail, "severity": severity}


def parse_mentions(doc: dict, brand: str) -> list[dict]:
    try:
        result = doc["tasks"][0]["result"][0] or {}
    except (KeyError, IndexError, TypeError):
        result = {}
    items = result.get("items") or []
    total = result.get("total_count") or len(items)
    if not total:
        return [_row("Web mentions", "info",
                     f"No web mentions found for '{brand}' — real mentions (news/forums/blogs) build the reputation Google and AI trust.",
                     "earn mentions on relevant sites/press")]
    rows = [_row("Web mentions", "ok",
                 f"'{brand}' is mentioned across ~{total} web page(s).",
                 "keep earning quality mentions", detail=f"~{total}")]
    sent = result.get("sentiment_connotations") or result.get("sentiment") or {}
    pos = sent.get("positive") or 0
    neg = sent.get("negative") or 0
    if neg and neg >= pos:
        rows.append(_row("Mention sentiment", "warn",
                         f"Negative-leaning sentiment ({neg} neg vs {pos} pos) — a reputation risk.",
                         "respond to and address the negative mentions", detail=f"{neg} neg / {pos} pos"))
    elif pos:
        rows.append(_row("Mention sentiment", "ok",
                         f"Positive-leaning sentiment ({pos} pos vs {neg} neg).",
                         "passing", detail=f"{pos} pos / {neg} neg"))
    return rows


def brand_mentions(brand: str, call=None) -> tuple:
    """(rows, status, cost) — web mentions + sentiment for `brand`."""
    from pipeline.scanner.dataforseo import call as _call
    call = call or _call
    if not brand:
        return [], "skipped: no brand name", 0.0
    return _tool("/v3/content_analysis/search/live",
                 [{"keyword": brand, "location_code": LOCATION_CODE,
                   "language_code": LANGUAGE_CODE, "limit": 100}],
                 lambda d: parse_mentions(d, brand), call=call, status="ok (verify live)")
