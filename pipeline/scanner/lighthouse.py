"""Lighthouse (Google) via the PageSpeed Insights API — the audit we trust
because it's Google's own engine, not our regex.

PSI runs Lighthouse in Google's cloud and returns the full `lighthouseResult`
over HTTP (free, ~25k/day with a key, works key-less at a low rate). We surface
the four category scores (Performance / SEO / Accessibility / Best practices)
plus the specific failing audits from the SEO, Accessibility and Best-practices
categories.

`parse_lighthouse(doc)` is pure (canned PSI response in, rows out) and unit-
tested offline; `run_lighthouse(url, call, key)` does the HTTP call with an
injectable caller.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

PSI = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = [("performance", "Performance"), ("seo", "SEO"),
              ("accessibility", "Accessibility"), ("best-practices", "Best practices")]
# Which categories' individual failing audits we list (perf audits are noisy and
# CrUX already covers field speed, so we keep perf to its headline score only).
DETAIL_CATS = ("seo", "accessibility", "best-practices")


def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": "lh." + what.lower().replace(" ", "_").replace(":", ""), "what": what,
            "why": why, "fix": fix, "detail": detail, "severity": severity}


def parse_lighthouse(doc: dict) -> list[dict]:
    lr = (doc or {}).get("lighthouseResult") or {}
    cats = lr.get("categories") or {}
    audits = lr.get("audits") or {}
    if not cats:
        return [_row("Lighthouse", "info",
                     "No Lighthouse result returned for this URL.",
                     "check the URL is public and try again")]
    rows: list[dict] = []

    # Headline category scores (0-100).
    for key, label in CATEGORIES:
        cat = cats.get(key)
        if not cat or cat.get("score") is None:
            continue
        pct = round(cat["score"] * 100)
        sev = "ok" if pct >= 90 else "warn" if pct >= 50 else "error"
        rows.append(_row(f"Lighthouse: {label}", sev,
                         f"Google Lighthouse {label} score: {pct}/100.",
                         "keep it up" if sev == "ok" else f"raise the {label} score", detail=f"{pct}/100"))

    # Specific failing audits from the SEO / a11y / best-practices categories.
    seen = set()
    for key in DETAIL_CATS:
        cat = cats.get(key) or {}
        for ref in (cat.get("auditRefs") or []):
            aid = ref.get("id")
            if not aid or aid in seen:
                continue
            audit = audits.get(aid) or {}
            score = audit.get("score")
            mode = audit.get("scoreDisplayMode")
            # Skip passing (score>=1), informational, manual and N/A audits.
            if score is None or score >= 1 or mode in ("manual", "notApplicable", "informative"):
                continue
            seen.add(aid)
            title = audit.get("title") or aid
            desc = (audit.get("description") or "").split("[Learn")[0].strip()
            rows.append(_row(title, "error" if score == 0 else "warn",
                             desc[:220] or "Lighthouse flagged this audit.",
                             "see Lighthouse guidance", detail=key))
    return rows


def run_lighthouse(url: str, call=None, key: str = "") -> tuple:
    """(rows, status, cost) — Lighthouse via PSI. Cost is $0 (free Google API)."""
    call = call or _psi_call
    key = key or os.environ.get("PAGESPEED_API_KEY") or os.environ.get("CRUX_API_KEY") or ""
    doc, err = call(url, key)
    if err:
        return [], err, 0.0
    return parse_lighthouse(doc), "ok (Google Lighthouse)", 0.0


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
