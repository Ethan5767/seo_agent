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

from pipeline.scanner.rows import make_row

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
    return os.environ.get("PAGESPEED_API_KEY") or os.environ.get("CRUX_API_KEY") or ""


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
    doc, err = get_psi(ctx, call)
    if err:
        return [], err, 0.0
    return category_rows(doc, cat_key, label), "ok (Google Lighthouse)", 0.0


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
