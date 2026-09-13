"""End-to-end automation-spine test (Tasks 5-9).

Runs the real pipeline stages, in order, over the local fixture site
(tests/e2e_fixture.py) with the network and the Claude agent stubbed at their
existing seams — no live site, no live model, fully deterministic:

    measure  -> plan  -> remediate  -> gates  -> automerge.decide

The single assertion the whole spine exists to make: a fix that clears every
seeded defect, stays inside tier T1, and passes the gates is judged AUTO by the
merge-decision layer, while anything riskier is judged HUMAN.

Each stage is added one task at a time; this file grows downward.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


from tests import e2e_fixture as fx


def _run_measure(project: Path, monkeypatch) -> dict:
    """Run the real measure.main against the fixture with curl stubbed, and
    return the findings.json it writes."""
    from pipeline.audit import measure

    curl, curl_status = fx.serve(project)
    monkeypatch.setattr(measure, "curl", curl)
    monkeypatch.setattr(measure, "curl_status", curl_status)
    monkeypatch.setattr(
        "sys.argv",
        ["wf-site-health", "--project", str(project), "--url", fx.ROUTE],
    )
    code = measure.main()
    assert code == 1, "seeded site must report findings (exit 1)"

    cycle = date.today().strftime("%Y-%m")
    return json.loads((project / "docs" / "audit" / cycle / "findings.json").read_text())


# ── Task 5: measure finds exactly the seeded defects ─────────────────────────

def test_measure_finds_the_two_seeded_defects(tmp_path, monkeypatch):
    project = fx.build_fixture(tmp_path / "client")
    doc = _run_measure(project, monkeypatch)

    codes = sorted(f["code"] for f in doc["findings"])
    assert codes == ["health.desc_missing", "health.title_length"], (
        f"fixture must surface exactly the two seeded defects, got {codes}"
    )
    assert doc["urls_checked"] == 1
    assert doc["urls_unreachable"] == 0


# ── Task 6: plan turns the findings into an actionable T1 worklist ───────────

def _run_plan(project: Path, monkeypatch) -> dict:
    from pipeline.audit import plan

    monkeypatch.setattr("sys.argv", ["wf-site-plan", "--project", str(project)])
    code = plan.main()
    assert code == 1, "a cycle with findings must plan and exit 1"

    cycle = date.today().strftime("%Y-%m")
    return json.loads((project / "docs" / "audit" / cycle / "worklist.json").read_text())


def test_plan_produces_two_actionable_t1_items(tmp_path, monkeypatch):
    project = fx.build_fixture(tmp_path / "client")
    _run_measure(project, monkeypatch)
    worklist = _run_plan(project, monkeypatch)

    assert worklist["tier"] == 1  # int tier, per common.client_profile
    codes = sorted(i["code"] for i in worklist["items"])
    assert codes == ["health.desc_missing", "health.title_length"]
    # Both seeded codes are T1 in plan.ACTIONS, so neither is tier-blocked and
    # both are the agent's to work.
    assert worklist["counts"]["actionable"] == 2
    assert worklist["counts"]["tier_blocked"] == 0
    assert all(not i["tier_blocked"] for i in worklist["items"])


# ── Task 7: remediate applies both fixes, inside tier, nothing refused ───────

def _run_remediate(project: Path, monkeypatch) -> tuple:
    from pipeline.audit import remediate as rem

    monkeypatch.setattr(rem, "run_agent", fx.agent_that_fixes(project))
    changelog, code = rem.remediate(project, cycle=None, max_items=10, max_files=10,
                                    model="fake-model", timeout=60, dry_run=False)
    # Persist changelog.json exactly as remediate.main() does — acceptance_check
    # reads it to re-verify each claimed fix.
    out = project / "docs" / "audit" / changelog["cycle"] / "changelog.json"
    out.write_text(json.dumps(changelog, indent=2, sort_keys=True) + "\n")
    return changelog, code


def test_remediate_fixes_both_items_in_tier(tmp_path, monkeypatch):
    project = fx.build_fixture(tmp_path / "client")
    _run_measure(project, monkeypatch)
    _run_plan(project, monkeypatch)
    changelog, code = _run_remediate(project, monkeypatch)

    assert code == 1, "at least one fix applied -> exit 1"
    assert changelog["stopped"] is None, "no out-of-tier refusal"
    statuses = sorted(i["status"] for i in changelog["items"])
    assert statuses == ["fixed", "fixed"]

    # The page on disk now carries both fixes, and only the page changed.
    page = (project / "out" / fx.ROUTE / "index.html").read_text()
    assert fx.GOOD_TITLE in page and fx.BAD_TITLE not in page
    assert 'name="description"' in page
    assert list(changelog["files"]) == [f"out/{fx.ROUTE}index.html"]


# ── Task 8: the gates that judge a T1 copy edit are green on the fixed tree ───

def _run_full_chain(project: Path, monkeypatch) -> dict:
    """measure -> plan -> remediate -> commit the fix -> run the content gates.
    Returns {gate_name: exit_code}."""
    _run_measure(project, monkeypatch)
    _run_plan(project, monkeypatch)
    _run_remediate(project, monkeypatch)
    base = fx.commit_fix(project)
    return fx.run_gates(project, base)


def test_gates_pass_on_the_fixed_fixture(tmp_path, monkeypatch):
    project = fx.build_fixture(tmp_path / "client")
    gate_codes = _run_full_chain(project, monkeypatch)

    # Every content gate the fix is responsible for returns a real pass (exit 0):
    # tier_check (in-tier), acceptance_check (findings actually cleared),
    # headings/em-dash/forbidden/capsule/noncommodity (writing standards).
    assert gate_codes == {
        "tier_check": 0,
        "acceptance_check": 0,
        "check_headings": 0,
        "forbidden_sweep": 0,
        "noncommodity_check": 0,
        "capsule_check": 0,
        "em_dash_check": 0,
    }, gate_codes


# ── Task 9: the merge-decision layer calls this safe fix AUTO ─────────────────

def test_full_cycle_ends_in_an_auto_merge_decision(tmp_path, monkeypatch):
    from pipeline.lib.automerge import decide, AutoMergePolicy

    project = fx.build_fixture(tmp_path / "client")
    gate_codes = _run_full_chain(project, monkeypatch)

    # A gate is "green" for the decision only on a real pass (exit 0). A gate that
    # could not judge (exit 4) is NOT a pass — it means unverified -> HUMAN (FR4).
    gate_results = {name: (code == 0) for name, code in gate_codes.items()}
    assert all(gate_results.values()), gate_codes

    # The YMYL risk check judges the CHANGE, so it gets the text the fix added —
    # the new title + meta description (the diff's added copy) — not the whole
    # page. Passing the entire page would risk-flag any incidental word on it.
    changed_text = f"{fx.GOOD_TITLE} {fx.DESC_TEXT}"
    policy = AutoMergePolicy(enabled=True)  # this client has opted in

    # The seeded fix: tier T1, modifies an existing page (creates nothing), benign
    # copy -> every rail clears -> AUTO.
    d = decide(gate_results=gate_results, tier="T1", creates=[], text=changed_text, policy=policy)
    assert d.action == "AUTO", d.reason

    # And the decision genuinely discriminates: flip any single rail -> HUMAN.
    assert decide(dict(gate_results, tier_check=False), "T1", [], changed_text, policy).action == "HUMAN"
    assert decide(gate_results, "T2", [], changed_text, policy).action == "HUMAN"
    assert decide(gate_results, "T1", ["out/new/index.html"], changed_text, policy).action == "HUMAN"
    assert decide(gate_results, "T1", [], "We cure your disease.", policy).action == "HUMAN"
    # And off-by-default stays off even when everything is green.
    assert decide(gate_results, "T1", [], changed_text).action == "HUMAN"
