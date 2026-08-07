"""score.py — the SEO/AEO pass rate, cycle progress, and the chart series.

Hermetic and pure: every input is a dict built here. What is worth testing is not
the arithmetic, it is the three properties that make the number honest — one page
cannot be counted many times, an unmeasured check cannot inflate it, and an
unmeasured cycle is not 100.
"""
from __future__ import annotations

import pytest

from pipeline.audit.measure import _CONFIG_GATED, check_page
from pipeline.lib.score import (
    AEO_CODES,
    SEO_CODES,
    family_score,
    fixed_fingerprints,
    progress,
    projected,
    score,
    series,
    skipped_codes,
)

# A config with every gated field set, so nothing is skipped unless a test says so.
FULL_CFG = {
    "nap": {"phone": "555-0100", "phone_tel": "5550100"},
    "ga4_id": "G-ABC12345",
    "forbidden_phrases": [{"pattern": r"\$[0-9]"}],
}


def finding(code, location="/", fp=None, ordinal=0):
    return {"code": code, "location": location, "ordinal": ordinal,
            "fingerprint": fp or f"{code}:{location}:{ordinal}"}


def doc(findings, urls=1):
    return {"schema": "site-health/1", "urls_checked": urls, "findings": findings}


# ── the score is a pass rate over (page, check) pairs ────────────────────────

def test_a_clean_measured_site_scores_100():
    assert score(doc([]), FULL_CFG)["seo"]["score"] == 100
    assert score(doc([]), FULL_CFG)["aeo"]["score"] == 100


def test_one_failing_check_on_one_page_costs_exactly_one_pair():
    # 14 SEO codes, all measurable under FULL_CFG, one page -> 14 pairs.
    s = family_score(doc([finding("health.title_missing")]), FULL_CFG, SEO_CODES)
    assert (s["failing"], s["total"]) == (1, 14)
    assert s["score"] == round(100 * (1 - 1 / 14))


def test_every_check_failing_on_every_page_scores_zero():
    findings = [finding(c, loc) for c in SEO_CODES for loc in ("/", "/a/")]
    s = family_score(doc(findings, urls=2), FULL_CFG, SEO_CODES)
    assert s["failing"] == s["total"] == 28
    assert s["score"] == 0


# ── property 1: one broken check on one page cannot swamp the score (B-009) ──

def test_a_thousand_alt_findings_on_one_page_cost_one_pair():
    """B-009 emitted 1158 img_alt_missing findings from one page and one broken
    regex — 91% of the run. A per-finding score would have read that as a site in
    ruins; a per-pair score reads it as one failing check on one page."""
    many = [finding("health.img_alt_missing", "/", fp=f"fp{i}", ordinal=i)
            for i in range(1158)]
    s = family_score(doc(many), FULL_CFG, SEO_CODES)
    assert s["failing"] == 1
    assert s["score"] == round(100 * (1 - 1 / 14))


def test_the_same_code_on_two_pages_is_two_pairs():
    # Distinctness is per (page, code) — not per code, or a site-wide problem would
    # cost the same as a single-page one.
    s = family_score(doc([finding("health.title_missing", "/"),
                          finding("health.title_missing", "/a/")], urls=2),
                     FULL_CFG, SEO_CODES)
    assert s["failing"] == 2


# ── property 2: a check that never ran leaves the denominator ────────────────

def test_an_unset_config_field_shrinks_the_denominator_rather_than_scoring_a_pass():
    """measure.py SKIPS these checks when the config is unset. Counting a skipped
    check as a pass is the "green means not measured" lie the rail exists to
    prevent — so the code leaves the denominator and is named."""
    bare = family_score(doc([]), {}, SEO_CODES)
    assert bare["total"] == 10                     # 14 - 4 config-gated
    assert set(bare["skipped"]) == set(_CONFIG_GATED_CODES())
    assert bare["score"] == 100                    # what DID run, all passed


def _CONFIG_GATED_CODES():
    return {code for _, code, _ in _CONFIG_GATED}


def test_the_skip_list_matches_what_measure_actually_skips():
    """Two lists that must agree: measure decides what runs, score decides what
    counts. If they drift, the score silently starts including a check that never
    fired — the exact failure this property exists to stop."""
    assert skipped_codes({}) == _CONFIG_GATED_CODES()
    assert skipped_codes(FULL_CFG) == set()


def test_a_partially_configured_client_scores_only_what_ran():
    cfg = {"ga4_id": "G-ABC12345"}                 # ga4 runs, the other three do not
    s = family_score(doc([]), cfg, SEO_CODES)
    assert s["total"] == 11
    assert "health.ga4_missing" not in s["skipped"]
    assert "health.phone_missing" in s["skipped"]


def test_aeo_is_never_config_gated():
    # Schema and word count need no config, so AEO always scores over all four.
    assert family_score(doc([]), {}, AEO_CODES)["total"] == 4


# ── property 3: unmeasured is not a clean site ───────────────────────────────

def test_a_cycle_with_no_urls_checked_is_unscored_not_perfect():
    assert score(doc([], urls=0), FULL_CFG)["seo"]["score"] is None


def test_an_unreadable_findings_doc_is_unscored_not_perfect():
    # read_artifact returns {"error": ...} for unparseable JSON, and None when the
    # file is absent. Neither is a 100.
    assert score({"error": "unparseable findings.json"}, FULL_CFG)["seo"]["score"] is None
    assert score(None, FULL_CFG)["seo"]["score"] is None


def test_a_missing_urls_checked_is_unscored():
    assert score({"findings": []}, FULL_CFG)["seo"]["score"] is None


# ── the families cover exactly what can be measured ──────────────────────────

def test_every_measurable_code_is_scored_by_exactly_one_family():
    """A code measure.py can emit but score.py does not know is a finding that
    costs nothing — the site gets worse and the number does not move."""
    html = "<html><body><img src=/a.png><p>short</p></body></html>"
    emitted = {f.code for f in check_page("https://x.com/", html, 404, FULL_CFG)}
    # Only codes that need config we did not give are allowed to be absent here.
    unknown = emitted - SEO_CODES - AEO_CODES
    assert unknown == set(), f"unscored codes measure.py emits: {unknown}"
    assert SEO_CODES & AEO_CODES == set(), "a code in both families is counted twice"


# ── projected: a claim, computed as a claim ──────────────────────────────────

def test_a_claimed_fix_lifts_the_projected_score_only():
    findings = [finding("health.title_missing", "/", fp="fp1")]
    changelog = {"items": [{"id": "wi-1", "finding_fp": "fp1", "status": "fixed"}]}
    assert score(doc(findings), FULL_CFG)["seo"]["score"] < 100
    assert projected(doc(findings), changelog, FULL_CFG)["seo"]["score"] == 100


def test_only_fixed_items_are_projected():
    findings = [finding("health.title_missing", "/", fp="fp1")]
    for status in ("error", "no_change", "refused", "dry-run"):
        changelog = {"items": [{"id": "wi-1", "finding_fp": "fp1", "status": status}]}
        assert fixed_fingerprints(changelog) == set()
        assert projected(doc(findings), changelog, FULL_CFG)["seo"]["score"] < 100


def test_a_pair_with_a_second_finding_still_fails_after_one_is_fixed():
    """This is why `projected` recomputes rather than doing arithmetic on the
    score: two img_alt findings on one page are ONE pair, so fixing one of them
    must not move the number."""
    findings = [finding("health.img_alt_missing", "/", fp="fp1", ordinal=0),
                finding("health.img_alt_missing", "/", fp="fp2", ordinal=1)]
    changelog = {"items": [{"id": "wi-1", "finding_fp": "fp1", "status": "fixed"}]}
    before = score(doc(findings), FULL_CFG)["seo"]["score"]
    assert projected(doc(findings), changelog, FULL_CFG)["seo"]["score"] == before


def test_a_changelog_without_fingerprints_projects_nothing():
    # Pre-B-013 changelogs carry no finding_fp. Guessing from (url, code) would be
    # wrong on exactly the pages that have two findings of one code.
    findings = [finding("health.title_missing", "/", fp="fp1")]
    changelog = {"items": [{"id": "wi-1", "status": "fixed"}]}
    assert projected(doc(findings), changelog, FULL_CFG)["seo"]["score"] == \
        score(doc(findings), FULL_CFG)["seo"]["score"]


# ── progress: how many findings are left ─────────────────────────────────────

def wl(*items):
    return {"items": list(items), "counts": {"unclassified": 3}}


def wi(n, blocked=False):
    return {"id": f"wi-2026-08-{n:04d}", "tier_blocked": blocked}


def test_remaining_is_actionable_minus_fixed():
    p = progress(wl(wi(1), wi(2), wi(3)),
                 {"items": [{"id": "wi-2026-08-0001", "status": "fixed"}]})
    assert (p["actionable"], p["fixed"], p["remaining"]) == (3, 1, 2)


def test_a_tier_blocked_item_is_counted_but_never_left_to_do():
    """Blocked items stay visible (plan.py never silently drops them) but folding
    them into `remaining` would leave every T1 client permanently unfinished."""
    p = progress(wl(wi(1), wi(2, blocked=True)), {})
    assert (p["actionable"], p["remaining"], p["tier_blocked"]) == (1, 1, 1)


def test_attempted_and_not_fixed_is_its_own_state():
    # Still work, but a run has already tried it once — worth seeing before
    # spending again.
    p = progress(wl(wi(1), wi(2)),
                 {"items": [{"id": "wi-2026-08-0001", "status": "error"}]})
    assert p["attempted_not_fixed"] == 1
    assert p["remaining"] == 2


def test_progress_over_a_cycle_with_no_changelog_is_all_remaining():
    p = progress(wl(wi(1), wi(2)), None)
    assert (p["fixed"], p["remaining"]) == (0, 2)


def test_progress_survives_a_missing_worklist():
    assert progress(None, None)["remaining"] == 0


# ── the series the chart draws ───────────────────────────────────────────────

def test_the_series_is_oldest_first_and_carries_the_projection_separately():
    rows = series([
        ("2026-08", doc([finding("health.title_missing", "/", fp="fp1")]),
         {"items": [{"id": "w", "finding_fp": "fp1", "status": "fixed"}]}, FULL_CFG),
        ("2026-07", doc([finding("health.title_missing", "/", fp="fp1")]), {}, FULL_CFG),
    ])
    assert [r["cycle"] for r in rows] == ["2026-07", "2026-08"]
    # July claimed nothing, so it has no projection to draw — a dashed segment over
    # a cycle nobody remediated would invent a claim.
    assert rows[0]["projected_seo"] is None and rows[0]["has_claims"] is False
    assert rows[1]["projected_seo"] == 100 and rows[1]["has_claims"] is True


def test_an_unmeasured_cycle_appears_in_the_series_as_a_gap():
    rows = series([("2026-08", doc([], urls=0), {}, FULL_CFG)])
    assert rows[0]["seo"] is None
