"""Free multi-page crawl helpers — pure, offline-tested.

`discover_pages` picks which URLs the free lane audits (homepage + same-origin
sitemap/nav URLs, capped). `merge_by_code` folds per-page findings into one row
per check, keeping the worst severity and the list of pages that failed it — the
same finding shape the UI already renders. No orphan inference (that produced
false results before); we only run existing per-page checks on real pages.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from pipeline.lib.html import sitemap_locs

_HREF = re.compile(r'href=["\']([^"\'#]+)["\']', re.IGNORECASE)
_SEV_RANK = {"error": 3, "warn": 2, "info": 1, "ok": 0}
_ACTIONABLE = ("error", "warn")


def _origin(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def discover_pages(homepage: str, sitemap_text: str, html: str, limit: int = 10) -> list[str]:
    """Homepage first, then same-origin URLs from the sitemap (or, if none, from
    the page's links). Order-preserving dedup, capped at `limit`."""
    origin = _origin(homepage)
    out: list[str] = [homepage]
    seen = {homepage.rstrip("/")}

    candidates = sitemap_locs(sitemap_text)
    if not candidates:
        candidates = [urljoin(homepage, h) for h in _HREF.findall(html or "")]

    for raw in candidates:
        url = raw.strip()
        if not url.startswith(("http://", "https://")):
            continue
        if _origin(url) != origin:
            continue
        key = url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
        if len(out) >= limit:
            break
    return out[:limit]


def merge_by_code(per_page: list) -> list[dict]:
    """`[(url, rows), ...]` -> one row per code: worst severity seen, plus the
    URLs where it was actionable (error/warn). An all-ok check stays one ok row
    with no pages."""
    merged: dict[str, dict] = {}
    pages: dict[str, list] = {}
    for url, rows in per_page or []:
        for r in rows or []:
            code = r.get("code")
            if not code:
                continue
            cur = merged.get(code)
            if cur is None or _SEV_RANK.get(r.get("severity"), 0) > _SEV_RANK.get(cur.get("severity"), 0):
                merged[code] = dict(r)
            if r.get("severity") in _ACTIONABLE and url:
                pages.setdefault(code, [])
                if url not in pages[code]:
                    pages[code].append(url)

    out = []
    for code, row in merged.items():
        affected = pages.get(code, [])[:25]
        row = dict(row)
        row["pages"] = affected
        if affected:
            row["detail"] = f"{len(affected)} page(s)"
        out.append(row)
    return out
