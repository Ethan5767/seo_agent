"""The auto-merge is wired into the quality gate, and it is OFF by default.

Automation-spine Task 10, the workflow half. Can't run GitHub Actions here, so
these assert the structure that makes the wiring safe: the master switch exists
and defaults false, and the merge job runs only when BOTH the flag is on AND the
gate job succeeded. If any of these regress, auto-merge could fire when it must
not — the whole point of the spine is that it cannot.
"""
from __future__ import annotations

from pathlib import Path

import yaml

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "quality-gate.reusable.yml"


def _load() -> dict:
    doc = yaml.safe_load(WF.read_text())
    # PyYAML parses the bare `on:` key as the boolean True — accept either.
    trigger = doc.get("on", doc.get(True))
    doc["_trigger"] = trigger
    return doc


def test_workflow_yaml_is_valid():
    doc = _load()
    assert "jobs" in doc and "quality-gate" in doc["jobs"]


def test_automerge_input_defaults_off():
    inputs = _load()["_trigger"]["workflow_call"]["inputs"]
    assert "automerge_enabled" in inputs
    flag = inputs["automerge_enabled"]
    assert flag["type"] == "boolean"
    assert flag["default"] is False, "auto-merge must be OFF for the fleet by default"


def test_auto_merge_job_needs_the_gate_and_the_flag():
    job = _load()["jobs"]["auto-merge"]
    assert job["needs"] == "quality-gate"
    cond = job["if"]
    # Both guards must appear in the run condition.
    assert "inputs.automerge_enabled" in cond
    assert "needs.quality-gate.result == 'success'" in cond


def test_auto_merge_job_can_merge_and_only_merges_on_auto():
    job = _load()["jobs"]["auto-merge"]
    assert job["permissions"]["contents"] == "write"
    assert job["permissions"]["pull-requests"] == "write"
    steps = {s.get("name"): s for s in job["steps"]}
    merge = steps["Merge (AUTO only)"]
    # The actual merge is itself guarded on the AUTO decision.
    assert "steps.decide.outputs.decision == 'AUTO'" in merge["if"]
    assert "gh pr merge" in merge["run"]


# ── Task 11: verify + rollback still fire after an auto-merge ─────────────────

def test_auto_merge_is_an_ordinary_push_to_main_so_deploy_still_fires():
    """Auto-merge must not bypass the post-merge chain. It does a normal
    `gh pr merge` into the PR base (main), which is exactly the trigger the
    deploy caller watches — so deploy -> verify-live -> auto-rollback still runs.
    """
    merge = {s.get("name"): s for s in _load()["jobs"]["auto-merge"]["steps"]}["Merge (AUTO only)"]
    # It merges the PR (into its base = the default branch), not to a side ref.
    assert "gh pr merge" in merge["run"]

    deploy_caller = WF.parent.parent.parent / ".github" / "examples" / "deploy-prod.yml"
    trigger = yaml.safe_load(deploy_caller.read_text())
    on = trigger.get("on", trigger.get(True))
    # The deploy (with built-in verify-live + auto-rollback) fires on push to main
    # — the push an auto-merge produces. The chain is intact by construction.
    assert on["push"]["branches"] == ["main"]
