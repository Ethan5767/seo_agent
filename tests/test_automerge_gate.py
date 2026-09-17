"""Tests for the PR-level auto-merge decision CLI (pipeline/audit/automerge_gate.py).

Automation-spine Task 10, the decision half: given a client repo and the PR's
base..head, derive the risk inputs from the real diff (tier from config, created
files + changed copy from git) and run automerge.decide. The workflow half (the
guarded `gh pr merge` step) is wired in quality-gate.reusable.yml and calls this.

Reuses the E2E fixture: build -> measure -> plan -> remediate -> commit the fix
onto a PR branch, then judge that branch.
"""
from __future__ import annotations

import json
from pathlib import Path

from tests import e2e_fixture as fx
from pipeline.audit import automerge_gate as ag


def _fixed_pr(tmp_path: Path, monkeypatch) -> tuple:
    """Return (project, base_sha) for a fixture whose seeded T1 fix is committed
    on a PR branch — the exact state the workflow calls the decision on."""
    from pipeline.audit import measure, plan, remediate as rem

    project = fx.build_fixture(tmp_path / "client")
    curl, curl_status = fx.serve(project)
    monkeypatch.setattr(measure, "curl", curl)
    monkeypatch.setattr(measure, "curl_status", curl_status)
    monkeypatch.setattr("sys.argv", ["wf-site-health", "--project", str(project), "--url", fx.ROUTE])
    measure.main()
    monkeypatch.setattr("sys.argv", ["wf-site-plan", "--project", str(project)])
    plan.main()
    monkeypatch.setattr(rem, "run_agent", fx.agent_that_fixes(project))
    changelog, _ = rem.remediate(project, None, 10, 10, "fake", 60, False)
    (project / "docs" / "audit" / changelog["cycle"] / "changelog.json").write_text(
        json.dumps(changelog, indent=2, sort_keys=True) + "\n")
    base = fx.commit_fix(project)
    return project, base


# ── deriving the risk inputs from the real diff ──────────────────────────────

def test_changed_paths_sees_the_page_edit_and_the_shipped_artifacts(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    created, modified = ag.changed_paths(project, base)
    # The page edit is a modify; the audit trail (findings/worklist/changelog)
    # ships in the PR as new files — that's the real shape of a remediation PR.
    assert modified == [f"out/{fx.ROUTE}index.html"]
    assert created and all(p.startswith("docs/audit/") for p in created), created


def test_public_creates_excludes_the_audit_trail(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    created, _ = ag.changed_paths(project, base)
    # None of the shipped artifacts count as a new public page.
    assert ag.public_creates(created) == []


def test_added_text_carries_the_new_copy(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    text = ag.added_text(project, base)
    assert fx.GOOD_TITLE in text
    assert "description" in text


# ── the decision ─────────────────────────────────────────────────────────────

def test_safe_t1_fix_with_green_gates_is_auto(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    d = ag.decide_pr(project, base, gates_passed=True, enabled=True)
    assert d.action == "AUTO", d.reason


def test_red_gates_force_human(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    d = ag.decide_pr(project, base, gates_passed=False, enabled=True)
    assert d.action == "HUMAN"


def test_disabled_forces_human(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    d = ag.decide_pr(project, base, gates_passed=True, enabled=False)
    assert d.action == "HUMAN"


def test_a_new_page_forces_human(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    # add a brand-new page on the same branch -> a create -> high risk
    newp = project / "out" / "new-page" / "index.html"
    newp.parent.mkdir(parents=True, exist_ok=True)
    newp.write_text("<html><head><title>New</title></head><body><h1>New</h1></body></html>")
    fx._git(project, "add", "-A")
    fx._git(project, "-c", "user.email=e2e@test", "-c", "user.name=e2e",
            "commit", "-q", "-m", "add a page")
    d = ag.decide_pr(project, base, gates_passed=True, enabled=True)
    assert d.action == "HUMAN"


# ── the CLI entry ─────────────────────────────────────────────────────────────

def test_main_prints_decision_and_writes_github_output(tmp_path, monkeypatch):
    project, base = _fixed_pr(tmp_path, monkeypatch)
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    monkeypatch.setattr("sys.argv", [
        "wf-automerge-decide", "--project", str(project), "--base", base,
        "--gates-passed", "true", "--enabled",
    ])
    code = ag.main()
    assert code == 0  # a decision is data, never a failed run
    out = gh_out.read_text()
    assert "decision=AUTO" in out
