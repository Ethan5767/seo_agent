"""Lighthouse (Google) via the PageSpeed Insights API — the audit we trust
because it's Google's own engine, not our regex.

PSI runs Lighthouse in Google's cloud and returns the full `lighthouseResult`
over HTTP (free, ~25k/day with a key). Each Lighthouse category is its own
Measure tool (Performance / SEO / Accessibility / Best practices) so the operator
can pick them individually — but they share ONE PSI call per scan, cached on the
scan context, so four selected cards still cost one round-trip.

`category_rows(doc, key, label)` is pure (canned PSI response in, rows out) and
unit-tested offline; `get_psi`/`category_tool` do the cached HTTP call with an
injectable caller.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from pipeline.scanner.rows import make_row
from pipeline.lib.env import load_env

load_env()

PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = [("performance", "Performance"), ("seo", "SEO"),
              ("accessibility", "Accessibility"), ("best-practices", "Best practices")]


_row = make_row("lh")


def _score_row(cat: dict, label: str) -> dict | None:
    score = cat.get("score")
    if score is None:
        return None
    pct = round(score * 100)
    sev = "ok" if pct >= 90 else "warn" if pct >= 50 else "error"
    return _row(f"Lighthouse: {label}", sev,
                f"Google Lighthouse {label} score: {pct}/100.",
                "keep it up" if sev == "ok" else f"raise the {label} score", detail=f"{pct}/100")


def category_rows(doc: dict, cat_key: str, label: str) -> list[dict]:
    """Rows for one Lighthouse category: the headline score, plus its failing
    audits (perf keeps to the score only — its audit list is noisy and CrUX
    already covers field speed)."""
    lr = (doc or {}).get("lighthouseResult") or {}
    cats = lr.get("categories") or {}
    audits = lr.get("audits") or {}
    cat = cats.get(cat_key)
    if not cat:
        return []
    rows: list[dict] = []
    sr = _score_row(cat, label)
    if sr:
        rows.append(sr)
    if cat_key == "performance":
        return rows
    for ref in cat.get("auditRefs") or []:
        audit = audits.get(ref.get("id")) or {}
        score = audit.get("score")
        mode = audit.get("scoreDisplayMode")
        if score is None or score >= 1 or mode in ("manual", "notApplicable", "informative"):
            continue
        title = audit.get("title") or ref.get("id") or "audit"
        desc = (audit.get("description") or "").split("[Learn")[0].strip()
        rows.append(_row(title, "error" if score == 0 else "warn",
                         desc[:220] or "Lighthouse flagged this audit.",
                         "see Lighthouse guidance", detail=label))
    return rows


def parse_lighthouse(doc: dict) -> list[dict]:
    """All four categories at once (used for a combined view / tests)."""
    rows: list[dict] = []
    for key, label in CATEGORIES:
        rows.extend(category_rows(doc, key, label))
    if not rows:
        return [_row("Lighthouse", "info",
                     "No Lighthouse result returned for this URL.",
                     "check the URL is public and try again")]
    return rows


# PSI field-data metric -> (CrUX metric key, divisor to CrUX units). PSI reports
# CLS as the score x 100 (e.g. 5 = 0.05); the others are milliseconds.
_PSI_FIELD = {
    "LARGEST_CONTENTFUL_PAINT_MS": ("largest_contentful_paint", 1),
    "INTERACTION_TO_NEXT_PAINT": ("interaction_to_next_paint", 1),
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": ("cumulative_layout_shift", 100),
}


def psi_field_metrics(doc: dict) -> tuple:
    """(metrics, status) in `providers.crux_metrics` shape, from the real-user
    Chrome (CrUX) data PageSpeed Insights returns alongside Lighthouse.

    The CrUX API itself can be refused by a key's API restrictions (the
    operator's key: 403 API_KEY_SERVICE_BLOCKED) while the PageSpeed key works,
    and PSI carries the same field data. Origin-level first, then the page. A
    metric Chrome has too little data for is left out, never estimated."""
    from pipeline.audit.providers import CWV_LABELS, CWV_GOOD, _crux_verdict
    for key, scope in (("originLoadingExperience", "origin"), ("loadingExperience", "page")):
        exp = (doc or {}).get(key) or {}
        raw = exp.get("metrics") or {}
        metrics = []
        for psi_name, (metric, div) in _PSI_FIELD.items():
            p = (raw.get(psi_name) or {}).get("percentile")
            if not isinstance(p, (int, float)):
                continue
            value = p / div
            metrics.append({"metric": CWV_LABELS[metric], "p75": value if div != 1 else int(p),
                            "good": CWV_GOOD[metric], "verdict": _crux_verdict(metric, value)})
        if metrics:
            return metrics, f"ok (Chrome field data via PageSpeed Insights, {scope} {exp.get('id', '')})"
    return [], "no field data: PageSpeed Insights returned no Chrome field data for this site"


def _key() -> str:
    return (
        os.environ.get("PAGESPEED_API_KEY")
        or os.environ.get("PSI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("CRUX_API_KEY")
        or ""
    )


def get_psi(ctx, call=None) -> tuple:
    """(doc, err) — fetch PSI once per scan, cached on ctx so the four Lighthouse
    tools share a single API call."""
    cached = getattr(ctx, "_psi", None)
    if cached is None:
        call = call or _psi_call
        cached = call(ctx.url, _key())
        ctx._psi = cached  # ctx is the scan's SimpleNamespace — always writable
    return cached


def category_tool(ctx, cat_key: str, label: str, call=None) -> tuple:
    """(rows, status, cost) — one Lighthouse category as a Measure tool. Cost $0."""
    key = _key()
    if not key and call is None:
        row = _row(f"Lighthouse: {label}", "info",
                   f"Google speed / Lighthouse API key not configured. Set PAGESPEED_API_KEY, PSI_API_KEY, or GOOGLE_API_KEY in .env.",
                   "set PAGESPEED_API_KEY in .env",
                   detail="not configured")
        row["code"] = f"lh.{cat_key.replace('-', '_')}_disabled"
        return [row], "skipped: no Google speed key set up yet", 0.0
    doc, err = get_psi(ctx, call)
    if err:
        return [], err, 0.0
    return category_rows(doc, cat_key, label), "ok (Google Lighthouse)", 0.0


def page_scores(urls, limit: int | None = None, call=None, workers: int = 4) -> tuple:
    """(rows, status) — Lighthouse Performance for each crawled page.

    One PSI run only ever judged the audited URL, so a single "Performance 95"
    stood for a whole site. Depth is the operator's call (10 / 25 / every
    crawled page) because each page is one PSI round trip: free, but not
    instant. Runs a few at a time; PSI is per-URL and has no batch form.

    Pages PSI refused are listed as such, never folded in with the fast ones —
    an unmeasured page must not read as a passing one.
    """
    targets = [u for u in (urls or [])][: limit if limit else None]
    if not targets:
        return [], "no pages: nothing was crawled to measure"
    call = call or _psi_call
    key = _key()

    scored: list[tuple] = []          # (url, percent)
    refused: list[tuple] = []         # (url, why)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for url, (doc, err) in zip(targets, pool.map(lambda u: call(u, key), targets)):
            cat = (((doc or {}).get("lighthouseResult") or {}).get("categories") or {}).get("performance") or {}
            score = cat.get("score")
            if err or score is None:
                refused.append((url, err or "PageSpeed Insights returned no Performance score"))
            else:
                scored.append((url, round(score * 100)))

    rows: list[dict] = []
    below50 = sorted([s for s in scored if s[1] < 50], key=lambda s: s[1])
    below90 = sorted([s for s in scored if 50 <= s[1] < 90], key=lambda s: s[1])
    if below50:
        r = _row("Pages below 50", "error",
                 "Google scores these pages' performance below 50 out of 100, the band Lighthouse calls poor.",
                 "start with the slowest page listed here; templated pages usually share one cause",
                 detail=f"{len(below50)} of {len(scored)} measured")
        r["code"], r["pages"] = "lh.pages_below_50", [u for u, _ in below50]
        rows.append(r)
    if below90:
        r = _row("Pages below 90", "warn",
                 "Google scores these pages' performance between 50 and 89 out of 100 — short of the good band.",
                 "raise the slowest of these; the fixes are usually shared across a template",
                 detail=f"{len(below90)} of {len(scored)} measured")
        r["code"], r["pages"] = "lh.pages_below_90", [u for u, _ in below90]
        rows.append(r)
    if refused:
        r = _row("Pages not measured", "info",
                 "PageSpeed Insights did not return a Performance score for these pages, so their speed is unknown.",
                 "re-run the depth, or check the pages are publicly reachable",
                 detail=f"{len(refused)} page(s): {refused[0][1]}")
        r["code"], r["pages"] = "lh.pages_not_measured", [u for u, _ in refused]
        rows.append(r)

    if scored:
        worst = min(scored, key=lambda s: s[1])
        best = max(scored, key=lambda s: s[1])
        median = sorted(p for _, p in scored)[len(scored) // 2]
        good = len(scored) - len(below50) - len(below90)
        r = _row("Pages measured", "ok" if good == len(scored) else "info",
                 f"Lighthouse Performance across {len(scored)} page(s): median {median}/100, "
                 f"worst {worst[1]}/100 ({worst[0]}), best {best[1]}/100.",
                 "keep it up" if good == len(scored) else "work down the pages listed above",
                 detail=f"{len(scored)} page(s) measured, {good} in the good band")
        r["code"] = "lh.pages_measured"
        rows.append(r)

    measured_note = f"{len(scored)} page(s)"
    if refused:
        measured_note += f", {len(refused)} refused"
    return rows, f"ok (Google Lighthouse, {measured_note})"


def pages_tool(ctx, call=None) -> tuple:
    """(rows, status, cost) — Lighthouse Performance across the crawled pages.

    Measures every page the crawl reached; `lighthouse_pages` in the scan
    request caps that when fewer round trips are wanted. With no multi-page
    crawl there is one page — what a single PSI run always did. Free either
    way; each page is one round trip, so depth is time.
    """
    urls = list(getattr(ctx, "crawled_urls", None) or [ctx.url])
    # Depth defaults to every page the crawl reached — the tool is named for the
    # site, not this page — and `lighthouse_pages` caps it when an operator wants
    # fewer round trips than the crawl went deep.
    depth = int(getattr(ctx, "lighthouse_pages", 0) or 0)
    rows, status = page_scores(urls, limit=depth if depth > 0 else None, call=call)
    return rows, status, 0.0


def _psi_call(url: str, key: str) -> tuple:
    params = [("url", url), ("strategy", "mobile")]
    for cat, _ in CATEGORIES:
        params.append(("category", cat.upper().replace("-", "_")))
    if key:
        params.append(("key", key))
    full = PSI + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(full, timeout=90) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from PageSpeed Insights"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
