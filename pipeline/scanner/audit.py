"""Pure audit assembly — given already-fetched inputs, return report rows.

No network and no HTTP here (the server does the fetching), so the whole
assembly is unit-testable offline. SEO reuses measure.check_page; AEO reuses
robots_aicrawler_check; performance reuses providers.crux_findings.
"""
from __future__ import annotations

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


def seo_rows(url: str, html: str, status: int, cfg: dict) -> list[dict]:
    """Run the universal on-page checks and turn each finding into a report row."""
    findings = measure.check_page(url, html, status, cfg)
    return [_row(f.code, f.to_json().get("detail", "")) for f in findings]


def aeo_rows(robots_text: str | None, html: str) -> list[dict]:
    """AI-answer-engine readiness: citation crawlers allowed + LocalBusiness schema."""
    rows: list[dict] = []
    if not robots_text or not robots_text.strip():
        rows.append(_row("aeo.robots_missing", "no robots.txt served"))
    else:
        groups = parse_groups(robots_text)
        for ua in DEFAULT_CITATION_UAS:
            rules, _matched = rules_for_ua(groups, ua)  # returns (rules, matched)
            if root_blocked(rules):
                rows.append(_row("aeo.crawler_blocked", ua))
    if '"@type":"LocalBusiness"' not in html.replace(" ", "").replace("'", '"'):
        rows.append(_row("health.schema_business_missing", "no LocalBusiness JSON-LD"))
    return rows


def perf_rows(crux) -> list[dict]:
    """Rows from providers.crux_findings output, or an honest 'enable' row."""
    if crux is None:
        r = recommend("crux.disabled")
        return [{
            "code": "crux.disabled", "what": "core web vitals not measured",
            "why": r["why"], "fix": r["fix"], "detail": "", "severity": "info",
        }]
    findings, _status = crux
    return [_row(f.code, f.to_json().get("detail", "")) for f in findings]


def assemble(seo: list[dict], aeo: list[dict], perf: list[dict]) -> dict:
    """Combine the three groups into one report with a headline score."""
    rows = seo + aeo + perf
    counts = {"error": 0, "warn": 0, "info": 0}
    for r in rows:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    score = max(0, 100 - 10 * counts["error"] - 3 * counts["warn"])
    return {"seo": seo, "aeo": aeo, "perf": perf, "score": score, "counts": counts}
