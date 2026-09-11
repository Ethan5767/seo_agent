"""Pure audit assembly — given already-fetched inputs, return report rows.

No network and no HTTP here (the server does the fetching), so the whole
assembly is unit-testable offline. SEO reuses measure.check_page; AEO reuses
robots_aicrawler_check; performance reuses providers.crux_findings.
"""
from __future__ import annotations

import re

from pipeline.audit import measure
from pipeline.gates.robots_aicrawler_check import (
    DEFAULT_CITATION_UAS, DEFAULT_TRAINING_UAS, parse_groups, root_blocked,
    rules_for_ua,
)
from pipeline.scanner.recommendations import recommend

# schema.org types that mean "this is a business", so a dentist, restaurant or
# clinic using the correct subtype is not reported as having no business schema.
# The old check was a substring match on "LocalBusiness" alone.
_BUSINESS_TYPES = {
    "localbusiness", "organization", "corporation", "medicalorganization",
    "medicalbusiness", "hospital", "dentist", "physician", "restaurant",
    "store", "professionalservice", "homeandconstructionbusiness",
    "legalservice", "financialservice", "automotivebusiness", "lodgingbusiness",
    "healthandbeautybusiness", "sportsactivitylocation", "educationalorganization",
    "governmentorganization", "ngo", "travelagency", "realestateagent",
}

# The types answer engines lean on hardest when deciding what to quote and who
# to attribute it to.
_ANSWER_TYPES = {"faqpage", "qapage", "howto", "article", "newsarticle",
                 "blogposting", "techarticle"}

_TYPE_RE = re.compile(r'"@type"\s*:\s*"([^"]+)"', re.IGNORECASE)


def _schema_types(html: str) -> set[str]:
    """Every @type declared anywhere in the page, lowercased.

    A regex rather than a JSON parse on purpose: real pages nest entities in
    @graph arrays, split JSON-LD across several script tags, and ship invalid
    JSON often enough that a parse failure would silently drop the whole check.
    """
    return {t.strip().lower() for t in _TYPE_RE.findall(html or "")}

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

        # Citation crawlers fetch a page to answer a question and cite it. One
        # blocked here means the site cannot be cited at all: a real problem.
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

        # Training crawlers harvest content to train models. Blocking them is a
        # deliberate business decision many clients make, so it is reported as
        # information, never as a defect. Reporting both kinds identically lost
        # the single distinction that matters most in AEO.
        trained = [ua for ua in DEFAULT_TRAINING_UAS
                   if root_blocked(rules_for_ua(groups, ua)[0])]
        if trained:
            rows.append({
                "code": "aeo.training_crawler_blocked",
                "what": "AI training crawlers blocked",
                "why": "These crawlers harvest content to train models rather than to "
                       "cite it. Blocking them does not affect whether AI engines can "
                       "cite this site, so this is a business decision, not a fault.",
                "fix": "no action needed unless the client wants their content used "
                       "for model training",
                "severity": "info",
                "detail": ", ".join(trained),
            })
        else:
            rows.append(_pass_row(
                "AI training crawlers allowed",
                "GPTBot, ClaudeBot, Google-Extended and CCBot may use this site's "
                "content for model training. Block them in robots.txt if the client "
                "would rather they did not."))

    # 2. Business schema for entity extraction. Any schema.org business type
    # counts, not just the literal "LocalBusiness".
    types = _schema_types(html)
    if types & _BUSINESS_TYPES:
        rows.append(_pass_row(
            "Business schema",
            "AI engines can read the business's name, address and phone directly."))
    else:
        rows.append(_row("health.schema_business_missing", "no business JSON-LD"))

    # 2b. The schema types answer engines quote from.
    answer_types = types & _ANSWER_TYPES
    if answer_types:
        rows.append(_pass_row(
            "Answer-engine schema",
            f"Marked up as {', '.join(sorted(answer_types))}, which answer engines "
            "use to lift and attribute answers."))
    else:
        rows.append({
            "code": "aeo.answer_schema_missing",
            "what": "Answer-engine schema",
            "why": "FAQPage, QAPage, HowTo and Article tell an answer engine what "
                   "kind of answer a page holds. Without one it has to guess from "
                   "prose, and guesses less often become citations.",
            "fix": "add FAQPage, QAPage, HowTo or Article JSON-LD, whichever matches "
                   "the page",
            "severity": "warn",
            "detail": "",
        })

    # 2c. An Article nobody wrote is hard to cite with confidence.
    if types & {"article", "newsarticle", "blogposting", "techarticle"} and \
            not re.search(r'"author"\s*:', html or "", re.IGNORECASE):
        rows.append({
            "code": "aeo.article_author_missing",
            "what": "Article author",
            "why": "Answer engines weigh authorship when deciding what to attribute. "
                   "An article with no author is harder to cite with confidence.",
            "fix": 'add an "author" to the Article JSON-LD, with a Person or '
                   "Organization name",
            "severity": "warn",
            "detail": "",
        })

    # 3. Answer-first structure (the genuine gap DataForSEO has no tool for):
    # can an AI engine lift a clean Q&A/answer from the page?
    rows.append(_answer_structure_row(html))
    # 4. GEO signals — concrete data/quotes/tables are the evidence-based levers
    # that measurably raise AI-citation odds (specific facts beat vague claims).
    rows.extend(_geo_rows(html))
    return rows


_STAT_RE = re.compile(r"\d+(?:\.\d+)?\s?%|\$\s?\d[\d,]*|\b\d{4}\b|\b\d[\d,]{3,}\b")
_CITE_RE = re.compile(r"<blockquote|<cite\b|according to|\bstudy\b|\bresearch\b|\bsurvey\b|source:", re.IGNORECASE)


def _geo_rows(html: str) -> list[dict]:
    """Answer-engine readiness: pages rich in concrete data, cited sources and
    structured tables get cited by AI engines far more than vague prose."""
    h = html or ""
    text = re.sub(r"<[^>]+>", " ", h)
    stats = len(_STAT_RE.findall(text))
    has_cite = _CITE_RE.search(h) is not None
    has_table = "<table" in h.lower() and "<td" in h.lower()
    return [
        {"code": "aeo.statistics", "what": "Statistics and data",
         "why": "Concrete figures (counts, %, years, prices) are the single biggest lever for being cited by AI answer engines — they favour specific data over vague claims.",
         "fix": "add real numbers to key statements (e.g. \"served 12,450 patients in 2023\")",
         "severity": "ok" if stats >= 3 else "warn", "detail": f"{stats} data point(s)"},
        {"code": "aeo.citations", "what": "Quotes and citations",
         "why": "Quoted experts, cited studies and \"according to\" phrasing raise trust and AI-citation odds.",
         "fix": "quote experts/studies and cite the source for key claims",
         "severity": "ok" if has_cite else "info", "detail": ""},
        {"code": "aeo.data_tables", "what": "Data tables",
         "why": "Semantic tables let AI engines lift facts (specs, prices, comparisons) cleanly.",
         "fix": "put comparable facts in a <table> instead of prose",
         "severity": "ok" if has_table else "info", "detail": ""},
    ]


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


def assemble(groups: dict) -> dict:
    """Combine result groups (a {key: rows} dict, in insertion/display order) into
    one report with a headline score. Passes every group through as-is, so adding
    a new tool/card needs no change here — the group just appears."""
    counts = {"error": 0, "warn": 0, "info": 0, "ok": 0}
    for rows in groups.values():
        for r in rows:
            counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    # Only real problems move the score; "ok"/"info" and the informational
    # rankings/keywords/ai groups do not.
    score = max(0, 100 - 10 * counts["error"] - 3 * counts["warn"])
    return {**groups, "score": score, "counts": counts}
