"""Pure audit assembly — given already-fetched inputs, return report rows.

No network and no HTTP here (the server does the fetching), so the whole
assembly is unit-testable offline. SEO reuses measure.check_page; AEO reuses
robots_aicrawler_check; performance reuses providers.crux_findings.
"""
from __future__ import annotations

import re

from pipeline.audit import measure
from pipeline.gates.robots_aicrawler_check import (
    DEFAULT_CITATION_UAS, parse_groups, root_blocked, rules_for_ua,
)
from pipeline.scanner.recommendations import recommend

_ERROR_CODES = {
    "health.title_missing", "health.title_length",
    "health.desc_missing", "health.h1_count",
    "health.canonical_mismatch", "health.noindex_present",
}


def _row(code: str, detail: str) -> dict:
    r = recommend(code, detail)
    return {
        "code": code,
        "what": code.split(".", 1)[-1].replace("_", " "),
        "why": r["why"],
        "fix": r["fix"],
        "detail": detail,
        "severity": "error" if code in _ERROR_CODES else "warn",
    }


# The full universal on-page checklist: (label, codes-that-mean-it-failed,
# pass-explanation). Every one runs on any URL with no config, so each is either
# a failing finding or a green pass — nothing hidden.
SEO_CHECKS = [
    ("Page title", ["health.title_missing", "health.title_length"],
     "Present and within Google's 30-60 character range."),
    ("Meta description", ["health.desc_missing", "health.desc_length"],
     "Present and within the 120-160 character range."),
    ("Single main heading (H1)", ["health.h1_count"],
     "Exactly one <h1> — a clear main topic."),
    ("Canonical tag", ["health.canonical_mismatch"],
     "Present and pointing at this page's own URL."),
    ("Indexable (not noindexed)", ["health.noindex_present"],
     "The page is allowed in search results."),
    ("Social preview image", ["health.og_image_missing"],
     "og:image present — shows a thumbnail when shared."),
    ("LocalBusiness schema", ["health.schema_business_missing"],
     "Structured data Google and AI can read the business from."),
    ("Breadcrumb schema", ["health.schema_breadcrumb_missing"],
     "BreadcrumbList structured data present."),
    ("Image alt text", ["health.img_alt_missing"],
     "Every content image has alt text."),
    ("Content depth", ["health.thin_content"],
     "Enough substantive copy to answer the intent."),
]


def _pass_row(label: str, why: str) -> dict:
    return {"code": "", "what": label, "why": why, "fix": "passing",
            "detail": "", "severity": "ok"}


def seo_rows(url: str, html: str, status: int, cfg: dict) -> list[dict]:
    """The full SEO checklist — every check, pass (green) or fail — so nothing is
    hidden. A check that produced a finding shows the problem; every other check
    shows as passing."""
    findings = measure.check_page(url, html, status, cfg)
    by_code: dict[str, str] = {f.code: f.to_json().get("detail", "") for f in findings}
    rows: list[dict] = []
    for label, codes, pass_why in SEO_CHECKS:
        hit = [c for c in codes if c in by_code]
        if hit:
            rows.extend(_row(c, by_code[c]) for c in hit)
        else:
            rows.append(_pass_row(label, pass_why))
    return rows


def aeo_rows(robots_text: str | None, html: str) -> list[dict]:
    """The full AEO checklist — AI citation crawlers + LocalBusiness schema —
    each shown pass or fail, nothing hidden."""
    rows: list[dict] = []

    # 1. robots.txt allows the AI citation crawlers
    if not robots_text or not robots_text.strip():
        rows.append(_row("aeo.robots_missing", "no robots.txt served"))
    else:
        groups = parse_groups(robots_text)
        blocked = []
        for ua in DEFAULT_CITATION_UAS:
            rules, _matched = rules_for_ua(groups, ua)  # returns (rules, matched)
            if root_blocked(rules):
                blocked.append(ua)
                rows.append(_row("aeo.crawler_blocked", ua))
        if not blocked:
            rows.append(_pass_row(
                "AI crawlers allowed",
                "robots.txt lets every AI citation crawler (ChatGPT, Perplexity, "
                "Google, Bing, Claude) read the site."))

    # 2. LocalBusiness schema for entity extraction
    if '"@type":"LocalBusiness"' not in html.replace(" ", "").replace("'", '"'):
        rows.append(_row("health.schema_business_missing", "no LocalBusiness JSON-LD"))
    else:
        rows.append(_pass_row(
            "LocalBusiness schema",
            "AI engines can read the business's name, address and phone directly."))

    # 3. Answer-first structure (the genuine gap DataForSEO has no tool for):
    # can an AI engine lift a clean Q&A/answer from the page?
    rows.append(_answer_structure_row(html))
    return rows


_INTERROGATIVE_H = re.compile(r"<h[23][^>]*>[^<]*\?\s*</h[23]>", re.IGNORECASE)


def _answer_structure_row(html: str) -> dict:
    """AI answer engines lift question→answer blocks. A page with interrogative
    headings or FAQ schema is extractable; one without is not."""
    has_faq = '"@type":"FAQPage"' in html.replace(" ", "").replace("'", '"')
    has_q_heading = _INTERROGATIVE_H.search(html or "") is not None
    if has_faq or has_q_heading:
        return _pass_row(
            "Answer-first structure",
            "The page has question/answer blocks AI engines can extract and cite.")
    return {"code": "aeo.no_answer_structure", "what": "Answer-first structure",
            "why": "No question→answer blocks, so AI answer engines can't easily lift a citable answer from the page.",
            "fix": "add interrogative headings (\"How much does X cost?\") with a concise answer right below, or FAQ schema",
            "severity": "warn", "detail": ""}


_CWV_WHY = {
    "LCP": "Largest Contentful Paint — how fast the main content appears. Good <= 2.5s.",
    "INP": "Interaction to Next Paint — how fast the page responds to a tap/click. Good <= 200ms.",
    "CLS": "Cumulative Layout Shift — how much the page jumps while loading. Good <= 0.1.",
}
_VERDICT_SEV = {"good": "ok", "needs-improvement": "warn", "poor": "error"}


def perf_rows(crux) -> list[dict]:
    """Rows from providers.crux_metrics output — every CWV metric, pass and fail,
    with its real p75. `crux` is None (no key -> 'enable' row) or a
    (metrics, status) tuple; an empty metrics list means CrUX has no field data
    for this site (too little traffic), which is surfaced, never faked."""
    if crux is None:
        r = recommend("crux.disabled")
        return [{
            "code": "crux.disabled", "what": "core web vitals not measured",
            "why": r["why"], "fix": r["fix"], "detail": "", "severity": "info",
        }]
    metrics, status = crux
    if not metrics:
        return [{
            "code": "crux.nodata", "what": "core web vitals — no field data",
            "why": "CrUX only has field data for pages with enough Chrome traffic.",
            "fix": status or "not enough traffic for a CrUX record",
            "detail": "", "severity": "info",
        }]
    rows = []
    for m in metrics:
        verdict = m["verdict"]
        rows.append({
            "code": f"crux.{m['metric'].lower()}",
            "what": f"{m['metric']} {m['p75']} (p75)",
            "why": _CWV_WHY.get(m["metric"], "Core Web Vital."),
            "fix": "passing" if verdict == "good" else f"{verdict}: bring below {m['good']}",
            "detail": verdict,
            "severity": _VERDICT_SEV.get(verdict, "warn"),
        })
    return rows


# Every result group the report can carry, in display order. Adding a group is
# one entry here — assemble and the UI both key off it, no positional coupling.
GROUP_KEYS = ("seo", "aeo", "perf", "tech", "site", "rankings", "keywords", "ai")


def assemble(groups: dict) -> dict:
    """Combine result groups (a {key: rows} dict) into one report with a headline
    score. Unknown keys are ignored; missing ones default to empty."""
    out = {k: groups.get(k) or [] for k in GROUP_KEYS}
    counts = {"error": 0, "warn": 0, "info": 0, "ok": 0}
    for rows in out.values():
        for r in rows:
            counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    # Only real problems move the score; "ok"/"info" and the informational
    # rankings/keywords/ai groups do not.
    out["score"] = max(0, 100 - 10 * counts["error"] - 3 * counts["warn"])
    out["counts"] = counts
    return out
