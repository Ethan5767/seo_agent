#!/usr/bin/env python3
"""score.py — findings.json -> an SEO score and an AEO score, plus cycle progress.

WHY A PASS RATE AND NOT A WEIGHTED SUM
--------------------------------------
The unit is a **(page, check) pair**: a check either fires on a page or it does
not.

    score = 100 x (1 - failing_pairs / total_pairs)

    total_pairs   = urls_checked x (codes in this family that actually ran)
    failing_pairs = distinct (location, code) pairs present in findings.json

Three properties fall out of that shape, and each one is a real failure this
module exists to avoid:

1. **It cannot be swamped by multiplicity.** B-009 emitted 1158
   `health.img_alt_missing` findings from one page and one broken regex — 91% of
   the run. Counting distinct pairs means one page contributes at most one failure
   per check, however many images are on it.
2. **A check that never ran cannot inflate it.** `tel_link_missing`,
   `phone_missing`, `ga4_missing` and `forbidden_phrase` are skipped when their
   config field is unset (`measure._CONFIG_GATED`). Those codes leave the
   DENOMINATOR entirely and are named in `skipped`. Scoring an unmeasured check as
   a pass is the "green means not measured" lie the whole rail is built against.
3. **Unmeasured is not 100.** `urls_checked == 0` returns `None`, and every caller
   renders that as "not measured".

The weighted-severity alternative was rejected deliberately: the weights would be
invented here, and every weight becomes an argument later. A pass rate is a fact
about what was measured.

WHAT SEO AND AEO MEAN HERE
--------------------------
Only the codes `measure.check_page` can actually emit. AEO rests on FOUR checks
(schema x3, thin content), so it moves in large steps on a small site — that is a
property of what is measurable from the live HTML, not a bug, and `total` is
returned alongside `score` so a caller can say so.
"""
from __future__ import annotations

# code -> family. Every code `measure.check_page` emits appears exactly once; a
# code missing from here is scored by neither family, which is why
# `test_every_measurable_code_is_scored` exists.
SEO_CODES = {
    "health.status_not_200",
    "health.title_missing",
    "health.title_length",
    "health.desc_missing",
    "health.desc_length",
    "health.h1_count",
    "health.canonical_mismatch",
    "health.noindex_present",
    "health.og_image_missing",
    "health.img_alt_missing",
    "health.forbidden_phrase",
    "health.phone_missing",
    "health.tel_link_missing",
    "health.ga4_missing",
}

# Answer-engine surface: can a machine read what this page is and answer from it.
AEO_CODES = {
    "health.schema_business_missing",
    "health.schema_faq_missing",
    "health.schema_breadcrumb_missing",
    "health.thin_content",
}

FAMILIES = {"seo": SEO_CODES, "aeo": AEO_CODES}

# A check that does not run without a config value, and the config path it needs.
# Mirrors measure._CONFIG_GATED — the same four, expressed as code -> getter, so
# the denominator drops exactly the checks that were skipped.
#
# ponytail: which checks ran is derived from the config as it reads NOW, not as it
# read when the cycle was measured. Fill in `ga4_id` after August's run and
# August's score shifts. The alternative is stamping `checks_run` into
# findings.json, which is a second source of truth and a schema change — not worth
# it until a cycle's score is quoted to a client.
CONFIG_GATED = {
    "health.tel_link_missing": lambda c: (c.get("nap") or {}).get("phone_tel"),
    "health.phone_missing": lambda c: (c.get("nap") or {}).get("phone"),
    "health.ga4_missing": lambda c: c.get("ga4_id"),
    "health.forbidden_phrase": lambda c: c.get("forbidden_phrases"),
}


def skipped_codes(cfg: dict) -> set:
    """Codes that could not have fired, because the config they need is unset."""
    cfg = cfg or {}
    return {code for code, get in CONFIG_GATED.items() if not get(cfg)}


def family_score(findings_doc: dict, cfg: dict, codes: set) -> dict:
    """{score, failing, total, skipped} for one family, or score=None if nothing
    was measured.

    A findings doc that is not a dict (a read error) is `None`, never 100: the
    caller must not be able to mistake an unreadable artifact for a clean site.
    """
    if not isinstance(findings_doc, dict):
        return {"score": None, "failing": 0, "total": 0, "skipped": []}
    urls = findings_doc.get("urls_checked")
    if not isinstance(urls, int) or urls <= 0:
        return {"score": None, "failing": 0, "total": 0, "skipped": []}

    skipped = skipped_codes(cfg) & codes
    scored = codes - skipped
    total = urls * len(scored)
    if total == 0:
        return {"score": None, "failing": 0, "total": 0, "skipped": sorted(skipped)}

    # DISTINCT (page, code) pairs. This is the line that makes 1158 alt findings on
    # one page cost one pair rather than 1158.
    pairs = {(f.get("location"), f.get("code"))
             for f in findings_doc.get("findings", [])
             if isinstance(f, dict) and f.get("code") in scored}
    failing = min(len(pairs), total)      # a pair outside the measured URL set
    return {"score": round(100 * (1 - failing / total)), "failing": failing,
            "total": total, "skipped": sorted(skipped)}


def score(findings_doc: dict, cfg: dict = None) -> dict:
    """{"seo": {...}, "aeo": {...}} for one cycle's findings."""
    return {name: family_score(findings_doc, cfg or {}, codes)
            for name, codes in FAMILIES.items()}


def fixed_fingerprints(changelog: dict) -> set:
    """Fingerprints of findings this cycle's changelog claims are fixed.

    A CLAIM, not a measurement — `acceptance_check` is what verifies it. Named for
    what it is so no caller can read it as a result.
    """
    if not isinstance(changelog, dict):
        return set()
    return {i.get("finding_fp") for i in changelog.get("items", [])
            if isinstance(i, dict) and i.get("status") == "fixed" and i.get("finding_fp")}


def projected(findings_doc: dict, changelog: dict, cfg: dict = None) -> dict:
    """The score this cycle WOULD carry if every claimed fix holds.

    Recomputed over the findings with the claimed-fixed fingerprints removed,
    rather than by arithmetic on the score, because removing a finding can leave
    another finding of the same code on the same page — in which case that pair is
    still failing and the score must not move.
    """
    done = fixed_fingerprints(changelog)
    if not done or not isinstance(findings_doc, dict):
        return score(findings_doc, cfg)
    remaining = dict(findings_doc)
    remaining["findings"] = [f for f in findings_doc.get("findings", [])
                             if isinstance(f, dict) and f.get("fingerprint") not in done]
    return score(remaining, cfg)


def progress(worklist: dict, changelog: dict) -> dict:
    """How much of this cycle's work is left — the "how many findings remain"
    answer, from the two artifacts that know.

    `remaining` counts ACTIONABLE items only. A tier-blocked item is visible and
    counted separately (never silently dropped, per plan.py), but it is not work
    this client's tier can do, so folding it into "remaining" would make every
    client permanently unfinished.
    """
    worklist = worklist if isinstance(worklist, dict) else {}
    changelog = changelog if isinstance(changelog, dict) else {}
    items = [i for i in worklist.get("items", []) if isinstance(i, dict)]
    actionable = [i for i in items if not i.get("tier_blocked")]
    blocked = len(items) - len(actionable)

    by_status: dict = {}
    for entry in changelog.get("items", []):
        if isinstance(entry, dict) and entry.get("id"):
            by_status[entry["id"]] = entry.get("status")
    fixed = sum(1 for i in actionable if by_status.get(i.get("id")) == "fixed")
    # Attempted-and-not-fixed is its own state: those items are still work, but a
    # re-run has already tried them once, which is worth seeing before spending
    # again.
    attempted = sum(1 for i in actionable
                    if i.get("id") in by_status and by_status[i["id"]] != "fixed")

    counts = worklist.get("counts") or {}
    return {
        "actionable": len(actionable),
        "fixed": fixed,
        "attempted_not_fixed": attempted,
        "remaining": len(actionable) - fixed,
        "tier_blocked": blocked,
        "unclassified": counts.get("unclassified"),
        "cost_usd": changelog.get("cost_usd"),
        "runs": changelog.get("runs"),
    }


def series(cycles: list) -> list:
    """[{cycle, seo, aeo, projected_seo, projected_aeo, has_claims}] oldest first.

    `cycles` is [(ym, findings_doc, changelog_doc)]. One pure function so the chart
    and any future report render the same numbers — a second implementation of
    "the score over time" is a second answer to the same question.
    """
    out = []
    for ym, findings, changelog, cfg in cycles:
        measured = score(findings, cfg)
        claims = fixed_fingerprints(changelog)
        proj = projected(findings, changelog, cfg) if claims else None
        out.append({
            "cycle": ym,
            "seo": measured["seo"]["score"],
            "aeo": measured["aeo"]["score"],
            "projected_seo": proj["seo"]["score"] if proj else None,
            "projected_aeo": proj["aeo"]["score"] if proj else None,
            "has_claims": bool(claims),
        })
    return sorted(out, key=lambda r: r["cycle"])
