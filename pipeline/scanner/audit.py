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
from pipeline.scanner.recommendations import recommend, severity_of

# schema.org Article types. An Article is judged on authorship; anything else is
# not an article and the check does not apply to it at all.
_ARTICLE_TYPES = {"article", "newsarticle", "blogposting", "techarticle"}

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

def _row(code: str, detail: str, what: str | None = None) -> dict:
    """A finding. `what` defaults to the code's own slug; a check that has a
    human name passes it, so the same code reads the same whether it passed or
    failed. `rowsForView` de-duplicates on code plus `what`, so a label that
    flips with the outcome makes one check look like two.
    """
    r = recommend(code, detail)
    return {
        "code": code,
        "what": what or code.split(".", 1)[-1].replace("_", " "),
        "why": r["why"],
        "fix": r["fix"],
        "detail": detail,
        "severity": severity_of(code),
    }


# The full universal on-page checklist: (label, codes-that-mean-it-failed,
# pass-explanation). Every one runs on any URL with no config, so each is either
# a failing finding or a green pass — nothing hidden.
#
# **The FIRST code is the check's identity.** A check can fail for several
# reasons (a title is missing, or it is the wrong length) but it passes as one
# thing, so its pass row is stamped with codes[0]. Reordering a check's codes
# therefore renames it to the ratchet and to the report views. Add variants at
# the end. `test_the_pass_row_is_stamped_with_the_checks_first_code` pins this.
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


#: What a failing SEO check is called. Without a name, `_row` fell back to the
#: code ("title length", "h1 count"), which is what an issue list showed the
#: operator. A pass keeps the check's label; a failure names the problem.
FAILURE_NAMES = {
    "health.title_missing": "Page title missing",
    "health.title_length": "Page title too long or too short",
    "health.desc_missing": "Meta description missing",
    "health.desc_length": "Meta description too long or too short",
    "health.h1_count": "Page does not have exactly one H1",
    "health.canonical_mismatch": "Canonical tag missing or pointing elsewhere",
    "health.noindex_present": "Page is set to noindex",
    "health.og_image_missing": "Social preview image missing",
    "health.schema_business_missing": "LocalBusiness schema missing",
    "health.schema_breadcrumb_missing": "Breadcrumb schema missing",
    "health.img_alt_missing": "Images missing alt text",
    "health.thin_content": "Thin content",
}


def _check(code: str, label: str, failures: list[str], pass_why: str) -> list[dict]:
    """One check's rows: a finding per failure, or a single pass row.

    `failures` is the detail string for each failing instance - usually zero or
    one, but the crawler check has one per blocked user agent. Empty means the
    check passed.

    The helper exists so that a check's code and name are each written ONCE.
    Before it, every check spelled both twice, in two separately-built dicts a
    branch apart, and nothing could catch the two spellings drifting - two codes
    is a perfectly valid state, just not the intended one. The name drifting was
    not hypothetical: the same check called itself "AI training crawlers
    blocked" when it failed and "AI training crawlers allowed" when it passed,
    which reads as two checks to anything grouping by name.
    """
    if failures:
        return [_row(code, detail, label) for detail in failures]
    return [_pass_row(code, label, pass_why)]


def _pass_row(code: str, label: str, why: str) -> dict:
    """The passing counterpart of `_row`, carrying the SAME code as the finding
    it is the absence of.

    A pass row used to be emitted with `code: ""`. Every consumer keyed on the
    code dropped it: the report views match rows by code, so a site where every
    AI check passed rendered an EMPTY "Crawler Findings" screen showing "Run a
    scan" - indistinguishable from never having scanned. A check that ran and
    passed must never look like a check that did not run.

    The code also makes the pass positive evidence for the ratchet: `plan.py`
    can now tell "the finding is gone because it was fixed" from "the finding is
    gone because the tool did not run this month". A pass row is never
    actionable (severity "ok"), so it cannot become a work item.
    """
    return {"code": code, "what": label, "why": why, "fix": "passing",
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
            rows.extend(_row(c, by_code[c], FAILURE_NAMES.get(c, label)) for c in hit)
        else:
            rows.append(_pass_row(codes[0], label, pass_why))
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
        blocked = [ua for ua in DEFAULT_CITATION_UAS
                   if root_blocked(rules_for_ua(groups, ua)[0])]
        rows += _check(
            "aeo.crawler_blocked", "AI citation crawlers", blocked,
            "robots.txt lets every AI citation crawler (ChatGPT, Perplexity, "
            "Google, Bing, Claude) read the site.")

        # Training crawlers harvest content to train models. Blocking them is a
        # deliberate business decision many clients make, so it is reported as
        # information, never as a defect. Reporting both kinds identically lost
        # the single distinction that matters most in AEO.
        trained = [ua for ua in DEFAULT_TRAINING_UAS
                   if root_blocked(rules_for_ua(groups, ua)[0])]
        rows += _check(
            "aeo.training_crawler_blocked", "AI training crawlers",
            [", ".join(trained)] if trained else [],
            "GPTBot, ClaudeBot, Google-Extended and CCBot may use this site's "
            "content for model training. Block them in robots.txt if the client "
            "would rather they did not.")

    # 2. Business schema for entity extraction. Any schema.org business type
    # counts, not just the literal "LocalBusiness".
    types = _schema_types(html)
    rows += _check(
        "health.schema_business_missing", "Business schema",
        [] if types & _BUSINESS_TYPES else ["no business JSON-LD"],
        "AI engines can read the business's name, address and phone directly.")

    # 2b. The schema types answer engines quote from.
    answer_types = types & _ANSWER_TYPES
    rows += _check(
        "aeo.answer_schema_missing", "Answer-engine schema",
        [] if answer_types else [""],
        f"Marked up as {', '.join(sorted(answer_types))}, which answer engines "
        "use to lift and attribute answers.")

    # 2c. An Article nobody wrote is hard to cite with confidence. The check
    # only applies to Articles, so a page that is not one emits nothing at all -
    # but an Article that DOES name its author has passed a check, and said so
    # nowhere until this became a `_check` like the rest.
    if types & _ARTICLE_TYPES:
        has_author = re.search(r'"author"\s*:', html or "", re.IGNORECASE)
        rows += _check(
            "aeo.article_author_missing", "Article author",
            [] if has_author else [""],
            "The Article JSON-LD names an author, which answer engines weigh "
            "when deciding what to attribute.")

    # 3. Answer-first structure (the genuine gap DataForSEO has no tool for):
    # can an AI engine lift a clean Q&A/answer from the page?
    rows += _answer_structure_rows(html)
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
         "why": "Specific figures give an answer engine something exact to quote, and stated prices and dates are among the few content factors a 2026 controlled study found to help consistently. Treat it as a quality signal, not a lever with a known effect size.",
         "fix": "add real numbers to key statements (e.g. \"served 12,450 patients in 2023\")",
         "severity": "ok" if stats >= 3 else "warn", "detail": f"{stats} data point(s)"},
        {"code": "aeo.citations", "what": "Quotes and citations",
         "why": "Quoted experts and cited studies are what an answer engine can attribute, and they make a claim checkable by a reader. The large citation lift once reported for adding quotations was measured on a 2023 model and did not reproduce on 2026 engines, so this is reported as a content-quality signal rather than a promised gain.",
         "fix": "quote experts/studies and cite the source for key claims",
         "severity": "ok" if has_cite else "info", "detail": ""},
        {"code": "aeo.data_tables", "what": "Data tables",
         "why": "A table puts comparable facts somewhere a reader and a machine can both find them. Note that formatting changes alone showed little effect in 2026 testing: the table helps because of the facts in it, not because it is a table.",
         "fix": "put comparable facts in a <table> instead of prose",
         "severity": "ok" if has_table else "info", "detail": ""},
    ]


_INTERROGATIVE_H = re.compile(r"<h[23][^>]*>[^<]*\?\s*</h[23]>", re.IGNORECASE)


def _answer_structure_rows(html: str) -> list[dict]:
    """AI answer engines lift question→answer blocks. A page with interrogative
    headings or FAQ schema is extractable; one without is not."""
    has_faq = '"@type":"FAQPage"' in html.replace(" ", "").replace("'", '"')
    has_q_heading = _INTERROGATIVE_H.search(html or "") is not None
    return _check(
        "aeo.no_answer_structure", "Answer-first structure",
        [] if (has_faq or has_q_heading) else [""],
        "The page has question/answer blocks AI engines can extract and cite.")


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
    if not metrics and str(status or "").startswith("error:"):
        # A refused or failed request is not "not enough traffic". A 403 from a
        # key whose restrictions exclude the Chrome UX Report API was shown as
        # "CrUX only has field data for pages with enough Chrome traffic",
        # blaming the site for a key setting (2026-09-14).
        reason = str(status).removeprefix("error: ")
        if "403" in reason:
            reason += (" (the API key is not allowed to call the Chrome UX Report API: in Google Cloud, "
                       "APIs & Services > Credentials > this key > API restrictions, add Chrome UX Report API)")
        from pipeline.scanner.rows import unavailable_row
        return [unavailable_row("perf", f"CrUX request failed: {reason}", "Core Web Vitals (CrUX)")]
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


#: Bumped whenever `health_score` changes, so a score movement caused by US is
#: distinguishable from one caused by the site. Without it, a formula change
#: silently rewrites every client's history and the ratchet cannot tell the
#: difference. Lighthouse has revised its weights five times; unversioned, that
#: would look like every site on earth improving or degrading on the same day.
HEALTH_SCORE_VERSION = 3

#: The groups Site Health is computed over: the on-page audit's tools
#: (`server.ONPAGE_AUDIT_TOOLS`) plus `site`, where the crawl files its
#: site-wide rows. Version 3 (2026-09-15). Until then every group counted, so
#: fifteen top-10 keyword rows from Rankings, or a Lighthouse category row,
#: raised "Site Health" with no change to a single page. Those rows still ship
#: and still have their own panels; they are just not a verdict on the pages.
SCORED_GROUPS = frozenset({"seo", "onpage", "tech", "schema", "validate", "internal", "site"})


def health_score(counts: dict) -> int | None:
    """Share of gradeable checks that passed, 0-100, or None when none ran.

    **The whole formula, deliberately:** `ok / (ok + warn + error)`. Info rows
    are not gradeable - they report a fact rather than a verdict - so they are
    excluded from both halves rather than counted as passes.

    It replaces `max(0, 100 - 10*errors - 3*warns)`, which was a penalty model
    with an arbitrary clamp, and was wrong in three ways that mattered:

      * **It saturated.** Any site with ten or more errors scored 0, so a client
        who fixed 200 of 400 errors saw no movement at all - exactly the clients
        who most need to show progress.
      * **It had no denominator.** A ten-page site and a hundred-thousand-page
        site with the same absolute error count scored the same.
      * **It was not the only one.** The web tier carried two more formulas with
        different weights and a different floor, so one scan had three health
        numbers (B-055).

    This one is monotonic by construction: fixing a finding moves a row from
    error or warn into ok, which can only raise the result. That is the property
    the ratchet needs and the penalty model did not have - some suite tools document
    that its own score can fall while the issue count falls, which makes a
    number nobody can report against.

    None, not zero, when nothing gradeable ran. A scan that measured nothing
    must never report a health of 0%, which reads as "everything is broken"
    rather than "we did not look".
    """
    graded = counts.get("ok", 0) + counts.get("warn", 0) + counts.get("error", 0)
    if graded <= 0:
        return None
    return round(100 * counts.get("ok", 0) / graded)


def not_measured_row(group: str) -> dict:
    """The single honest row a group emits when the page was never fetched."""
    return {
        "code": f"{group}.not_measured",
        "what": "Not measured — the page could not be fetched",
        "why": "Nothing was read from this URL, so no check on this page ran. "
               "This is the absence of a measurement, not a clean result.",
        "fix": "Check that the URL is reachable and is not blocking the scanner "
               "at the edge (Cloudflare, a WAF, or a login wall), then scan again.",
        "detail": "",
        "severity": "info",
    }


def assemble(groups: dict, reachable: bool = True, page_independent=frozenset()) -> dict:
    """Combine result groups (a {key: rows} dict, in insertion/display order) into
    one report with a headline score. Passes every group through as-is, so adding
    a new tool/card needs no change here — the group just appears.

    The headline number is a summary, not the product. Per-category scores
    (`web/lib/pillars.derivePillars`) are what an operator and a client should
    read: a single composite invites people to optimise the number instead of
    the site, which is a measured effect and not a stylistic worry - reporting
    one measure rather than several demonstrably increases that substitution
    (Choi, Hecht & Tayler 2012). The counts travel beside the score for exactly
    that reason.
    """
    # B-074. Every row builder below takes `html` and most never see `status`,
    # so an empty body reads to them exactly like a page that genuinely lacks
    # the feature: `tech.https` "passes", `onpage.mixed_content` "passes", and a
    # site the scanner never reached scored 40/100 with 23 checks marked ok.
    #
    # `health_score` already refuses to score an empty grade set — its docstring
    # says a scan that measured nothing must never report a health of 0%, which
    # reads as "everything is broken" rather than "we did not look". The guard
    # could not fire because the builders manufactured gradeable rows first.
    #
    # So the verdicts are dropped at the one place that knows: absence of
    # evidence is not evidence of compliance, which is the rule the gate suite
    # settled on as exit 4.
    #
    # Groups in `page_independent` are kept: their data never came from our fetch
    # (DataForSEO queries by domain, the source lane reads the repo), so "the page
    # could not be fetched" is not true of them, and rewriting them threw away
    # paid results whose cost stayed on the scan.
    if not reachable:
        groups = {name: (rows if name in page_independent else [not_measured_row(name)])
                  for name, rows in groups.items()}

    counts = {"error": 0, "warn": 0, "info": 0, "ok": 0}
    counts_all = {"error": 0, "warn": 0, "info": 0, "ok": 0}
    for name, rows in groups.items():
        for r in rows:
            counts_all[r["severity"]] = counts_all.get(r["severity"], 0) + 1
            if name in SCORED_GROUPS:
                counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    # `graded` is the score's denominator, shipped beside it because the score
    # is only comparable between scans that graded the same checks. Enabling a
    # tool raises the score with no change to the site: adding `onpage` (28
    # checks, 24 of them passing on a simple page) moved example.com from 33 to
    # 51. That is not a measurement error, it is the score answering a different
    # question - and a client shown two numbers from two tool sets is being
    # misled unless the denominator travels with them.
    graded = counts["ok"] + counts["warn"] + counts["error"]
    #
    # `counts` and `graded` are the score's own inputs (scored groups only);
    # `counts_all` is every row, for screens that summarise the whole report.
    return {**groups, "score": health_score(counts), "counts": counts,
            "counts_all": counts_all, "graded": graded,
            "score_version": HEALTH_SCORE_VERSION}
