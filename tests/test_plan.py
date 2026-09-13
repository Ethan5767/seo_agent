"""plan.py — the ratchet over the monthly cycle folders.

Hermetic: every cycle is a findings.json written under tmp_path. The lane tests
are the ones that matter — REGRESSION is the lane the module exists for, and it
is the one a naive "in last month? no -> NEW" implementation silently loses.
"""
from __future__ import annotations

import json

import pytest

from pipeline.audit import plan as p


def finding(code="health.desc_length", location="/roofing/", context="", detail="len=71",
            ordinal=0, fp=None):
    return {"gate": "site_health", "code": code, "location": location, "context": context,
            "detail": detail, "ordinal": ordinal,
            "fingerprint": fp or f"{code}:{location}:{context}:{ordinal}"}


def write_cycle(project, cycle, findings, domain="example.com"):
    d = project / "docs" / "audit" / cycle
    d.mkdir(parents=True, exist_ok=True)
    (d / "findings.json").write_text(json.dumps({
        "schema": "site-health/1", "generated": f"{cycle}-05", "domain": domain,
        "urls_checked": 3, "urls_unreachable": 0, "findings": findings,
    }, indent=2, sort_keys=True) + "\n")
    return d


@pytest.fixture
def project(make_project):
    return make_project(config=dict(client="test-client", domain="example.com", tier=1,
                                    text_paths=["src/data/**/*.ts"]))


# ── the four lanes ───────────────────────────────────────────────────────────

def test_first_cycle_is_all_new(project):
    write_cycle(project, "2026-06", [finding()])
    wl, _report, _doc, lanes, *_ = p.plan(project)
    assert wl["prior_cycle"] is None
    assert set(lanes.values()) == {"NEW"}
    assert wl["counts"]["NEW"] == 1


def test_carried_finding_is_persisting(project):
    write_cycle(project, "2026-06", [finding()])
    write_cycle(project, "2026-07", [finding()])
    wl, _r, _d, lanes, *_ = p.plan(project)
    assert list(lanes.values()) == ["PERSISTING"]
    assert wl["counts"] == {**wl["counts"], "PERSISTING": 1, "NEW": 0, "RESOLVED": 0}


def test_gone_finding_is_resolved(project):
    write_cycle(project, "2026-06", [finding()])
    write_cycle(project, "2026-07", [])
    wl, report, _d, _l, *_ = p.plan(project)
    assert wl["counts"]["RESOLVED"] == 1
    assert "Resolved (1)" in report


def test_fixed_then_returned_is_regression_not_new(project):
    """The lane the module exists for. Absent from the previous cycle but present
    in an earlier one means the fix did not hold — that is not a NEW finding."""
    write_cycle(project, "2026-05", [finding()])
    write_cycle(project, "2026-06", [])
    write_cycle(project, "2026-07", [finding()])
    wl, report, _d, lanes, *_ = p.plan(project)
    assert list(lanes.values()) == ["REGRESSION"]
    assert wl["counts"]["REGRESSION"] == 1 and wl["counts"]["NEW"] == 0
    assert "Regression (1)" in report


def test_lane_ignores_detail_churn(project):
    """detail is excluded from the fingerprint, so a finding that merely got
    worse stays PERSISTING rather than becoming NEW."""
    write_cycle(project, "2026-06", [finding(detail="len=71")])
    write_cycle(project, "2026-07", [finding(detail="len=210")])
    _wl, _r, _d, lanes, *_ = p.plan(project)
    assert list(lanes.values()) == ["PERSISTING"]


# ── the tier filter ──────────────────────────────────────────────────────────

def test_tier1_blocks_structural_work_but_keeps_it_visible(project):
    write_cycle(project, "2026-07", [finding(code="health.desc_length"),
                                     finding(code="health.h1_count", detail="count=2")])
    wl, report, _d, _l, *_ = p.plan(project)
    by_kind = {i["kind"]: i for i in wl["items"]}
    assert by_kind["meta_description_out_of_band"]["tier_blocked"] is False
    assert by_kind["h1_count_wrong"]["tier_blocked"] is True     # template work, needs T3
    assert wl["counts"]["actionable"] == 1 and wl["counts"]["tier_blocked"] == 1
    # visible and counted, never silently dropped
    assert "Not Actionable" in report and "health.h1_count" in report


def test_thin_content_is_actionable_at_t1(project):
    """A page cannot be measured as thin unless it is LIVE, so the fix is always
    an edit to copy that already exists — never a page creation. Blocking it at
    T1 cost lee 15 items whose target files were all already in text_paths."""
    write_cycle(project, "2026-07", [finding(code="health.thin_content", detail="words=120")])
    wl, _report, _d, _l, *_ = p.plan(project)
    assert wl["items"][0]["kind"] == "thin_content"
    assert wl["items"][0]["tier_blocked"] is False
    assert wl["counts"]["actionable"] == 1 and wl["counts"]["tier_blocked"] == 0


def test_no_declared_tier_blocks_everything(make_project):
    proj = make_project(config=dict(client="c", domain="example.com"))
    write_cycle(proj, "2026-07", [finding()])
    wl, _r, _d, _l, *_ = p.plan(proj)
    assert wl["tier"] is None
    assert all(i["tier_blocked"] for i in wl["items"])


def test_unknown_code_never_enters_the_worklist(project):
    """No ACTIONS entry means no machine-checkable acceptance, so it belongs in
    the report under NEEDS A HUMAN, not in the worklist phase 4 will re-check."""
    write_cycle(project, "2026-07", [finding(code="health.brand_new_check")])
    wl, report, _d, _l, *_ = p.plan(project)
    assert wl["items"] == []
    assert wl["counts"]["unclassified"] == 1
    assert "Needs a Human" in report and "health.brand_new_check" in report


def test_every_item_carries_acceptance(project):
    write_cycle(project, "2026-07", [finding(code=c, location=f"/p{i}/")
                                     for i, c in enumerate(p.ACTIONS)])
    wl, _r, _d, _l, *_ = p.plan(project)
    assert len(wl["items"]) == len(p.ACTIONS)
    for item in wl["items"]:
        assert item["acceptance"]["check"] == "code_absent"
        assert item["acceptance"]["code"] == item["code"]


# ── artifacts ────────────────────────────────────────────────────────────────

def test_writes_artifacts_and_stamps_lanes_on_findings(project):
    write_cycle(project, "2026-07", [finding()])
    out = p.write_artifacts(project, *p.plan(project))
    assert (out / "worklist.json").is_file() and (out / "report.md").is_file()
    doc = json.loads((out / "findings.json").read_text())
    assert doc["findings"][0]["lane"] == "NEW"     # the fleet view reads lanes here
    assert "cycle" not in doc


def test_rerun_is_byte_identical(project):
    """Two runs over an unchanged cycle must not produce a noise diff."""
    write_cycle(project, "2026-07", [finding()])
    out = p.write_artifacts(project, *p.plan(project))
    first = [(out / n).read_text() for n in ("worklist.json", "report.md", "findings.json")]
    p.write_artifacts(project, *p.plan(project))
    assert [(out / n).read_text() for n in ("worklist.json", "report.md", "findings.json")] == first


def test_explicit_cycle_plans_the_past(project):
    write_cycle(project, "2026-06", [finding()])
    write_cycle(project, "2026-07", [])
    wl, _r, _d, _l, *_ = p.plan(project, "2026-06")
    assert wl["cycle"] == "2026-06" and wl["counts"]["NEW"] == 1


def test_missing_findings_is_a_usage_error(project):
    with pytest.raises(p.PlanError):
        p.plan(project)
    write_cycle(project, "2026-07", [finding()])
    with pytest.raises(p.PlanError):
        p.plan(project, "2026-01")


def test_unparseable_findings_refuses(project):
    d = write_cycle(project, "2026-07", [finding()])
    (d / "findings.json").write_text("{not json")
    with pytest.raises(p.PlanError):
        p.plan(project)


def test_main_exit_codes(project, monkeypatch):
    write_cycle(project, "2026-07", [])
    monkeypatch.setattr("sys.argv", ["wf-site-plan", "--project", str(project)])
    assert p.main() == 0                                      # clean
    write_cycle(project, "2026-08", [finding()])
    assert p.main() == 1                                      # findings written


def test_main_usage_error(project, monkeypatch):
    monkeypatch.setattr("sys.argv", ["wf-site-plan", "--project", str(project)])
    assert p.main() == 2                                      # nothing measured yet


# ── widening the fix loop (B-078) ────────────────────────────────────────────
#
# ACTIONS had 18 entries, every one a health.* code, so the agent could attempt
# 18 of the ~215 things the product measures — 8%, and 8 of 41 on a default-tier
# client. The gap was never difficulty: the 28 onpage.* checks are single-tag
# edits whose acceptance is the existing code_absent re-measure. Nobody had
# written the line.
#
# What is added is bounded by the six-part safety rule, and what is DELIBERATELY
# left out matters as much:
#   - URL shape (length, case, underscores, parameters) is a migration, not a
#     fix. Changing a URL without a redirect deindexes the page.
#   - single_canonical means several canonicals; choosing which survives is a
#     judgement with an unbounded blast radius. Deindexing class, human only.
#   - dom_size, link_volume, iframe_count, subheadings need judgement.

def test_the_fix_loop_covers_the_onpage_family():
    from pipeline.audit.plan import ACTIONS
    onpage = [c for c in ACTIONS if c.startswith("onpage.")]
    assert len(onpage) >= 12, (
        f"only {len(onpage)} onpage codes are actionable; the family is the "
        f"cheapest available widening of the fix loop")


def test_nothing_in_the_deindexing_class_is_ever_automated():
    from pipeline.audit.plan import ACTIONS
    forbidden = [
        "onpage.url_length", "onpage.url_case", "onpage.url_underscores",
        "onpage.url_parameters",     # changing a URL without a redirect deindexes it
        "onpage.single_canonical",   # choosing a surviving canonical is a judgement
        "health.noindex_present",    # removing a noindex may be deliberate
    ]
    for code in forbidden:
        if code == "health.noindex_present":
            continue  # pre-existing T3 entry, out of scope for this change
        assert code not in ACTIONS, (
            f"{code} can remove pages from the index. Recommend it; never apply it.")


def test_every_action_has_doctrine_the_writer_can_follow():
    """An ACTIONS entry with no SKILL.md row tells the agent to fix something
    without saying what good looks like."""
    from pathlib import Path
    from pipeline.audit.plan import ACTIONS
    skill = Path("skills/site-remediation/SKILL.md").read_text()
    missing = sorted({kind for (kind, _t, _e) in ACTIONS.values() if f"`{kind}`" not in skill})
    assert not missing, f"actions with no doctrine in SKILL.md: {missing}"
