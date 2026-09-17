"""Tests for the handoff gate (gate #20).

`docs/gate-reference.md` said this gate ships UNVERIFIED and must not be wired
into the workflow that blocks every client's production PR until it has tests
and a green run — the B-007 "implemented is not wired" lesson, applied on
purpose. This file is the first half of that; `test_e2e_wiring.py` is the second.

The interesting cases are not the happy path. They are the three ways a chain
can be absent, which are NOT the same fact:

    nothing claimed        -> not applicable. This PR is not a remediation.
    claimed but unmeasured -> BROKEN. A fix that traces to no measurement is the
                              exact provenance break the gate exists for.
    measured but empty     -> cannot judge. Nothing to reconcile either way.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.audit.measure import SCHEMA as FINDINGS_SCHEMA
from pipeline.audit.plan import SCHEMA as WORKLIST_SCHEMA
from pipeline.audit.remediate import SCHEMA as CHANGELOG_SCHEMA
from pipeline.gates import e2e_check
from pipeline.gates.e2e_check import CANNOT_JUDGE, FAIL, PASS, check_cycle, reconcile

CYCLE = "2026-09"


def write_cycle(project: Path, *, findings=None, worklist=None, changelog=None,
                cycle: str = CYCLE) -> Path:
    """Write whichever artifacts were asked for. Omitted ones stay absent, which
    is the state the gate has to distinguish."""
    cdir = project / "docs" / "audit" / cycle
    cdir.mkdir(parents=True, exist_ok=True)
    if findings is not None:
        (cdir / "findings.json").write_text(json.dumps(findings))
    if worklist is not None:
        (cdir / "worklist.json").write_text(json.dumps(worklist))
    if changelog is not None:
        (cdir / "changelog.json").write_text(json.dumps(changelog))
    return cdir


def intact(fp: str = "fp-aaa"):
    return (
        {"schema": FINDINGS_SCHEMA, "findings": [{"fingerprint": fp}]},
        {"schema": WORKLIST_SCHEMA, "items": [{"id": "W1", "finding_fp": fp}]},
        {"schema": CHANGELOG_SCHEMA, "items": [{"id": "C1", "finding_fp": fp}]},
    )


# ── the chain itself ─────────────────────────────────────────────────────────

def test_an_intact_chain_passes(tmp_path):
    f, w, c = intact()
    write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    code, msg = check_cycle(tmp_path, CYCLE)
    assert code == PASS, msg
    assert "1 findings -> 1 planned items -> 1 remediation entries" in msg


def test_a_planned_item_with_no_finding_is_a_break(tmp_path):
    f, w, c = intact()
    w["items"][0]["finding_fp"] = "fp-invented"
    c["items"][0]["finding_fp"] = "fp-invented"
    write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    code, msg = check_cycle(tmp_path, CYCLE)
    assert code == FAIL
    assert "fp-invented" in msg and "not in findings.json" in msg


def test_a_fix_for_something_nobody_planned_is_a_break(tmp_path):
    # The one that matters most: the agent shipped an edit and attributed it to
    # a finding the plan never authorized it to touch.
    f, w, c = intact()
    c["items"] = [{"id": "C9", "finding_fp": "fp-unplanned"}]
    write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    code, msg = check_cycle(tmp_path, CYCLE)
    assert code == FAIL
    assert "C9" in msg and "never planned" in msg


@pytest.mark.parametrize("artifact,key", [
    ("findings", "findings.json"), ("worklist", "worklist.json"), ("changelog", "changelog.json"),
])
def test_a_wrong_schema_string_is_a_break(tmp_path, artifact, key):
    f, w, c = intact()
    {"findings": f, "worklist": w, "changelog": c}[artifact]["schema"] = "something-else/1"
    write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    code, msg = check_cycle(tmp_path, CYCLE)
    assert code == FAIL
    assert key in msg


def test_reconcile_ignores_changelog_entries_that_claim_no_finding(tmp_path):
    # Housekeeping commits inside a remediation PR carry no finding_fp. They are
    # not claims, so they have nothing to trace back to.
    f, w, c = intact()
    c["items"].append({"id": "C2"})
    assert reconcile(f, w, c) == []


# ── the three ways a chain can be absent ─────────────────────────────────────

def test_a_partial_chain_is_never_a_pass(tmp_path):
    f, w, _ = intact()
    write_cycle(tmp_path, findings=f, worklist=w)  # no changelog
    code, msg = check_cycle(tmp_path, CYCLE)
    assert code == CANNOT_JUDGE
    assert "not a pass" in msg


def test_zero_findings_is_cannot_judge_not_green(tmp_path):
    # CLAUDE.md sharp edge #4: a gate that scanned nothing must never pass.
    _, w, c = intact()
    write_cycle(tmp_path, findings={"schema": FINDINGS_SCHEMA, "findings": []},
                worklist=w, changelog=c)
    code, msg = check_cycle(tmp_path, CYCLE)
    assert code == CANNOT_JUDGE
    assert "zero findings" in msg


def test_an_unparseable_artifact_is_not_a_pass(tmp_path):
    f, w, c = intact()
    cdir = write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    (cdir / "worklist.json").write_text("{not json")
    code, msg = check_cycle(tmp_path, CYCLE)
    assert code in (FAIL, CANNOT_JUDGE)
    assert "worklist.json" in msg


# ── --only-if-claimed: the flag that makes this safe to wire ─────────────────

def test_no_changelog_at_all_is_not_applicable(tmp_path):
    # An ordinary human PR against a client repo claims no remediation. There is
    # nothing to reconcile, so the gate must not turn every such PR red.
    f, w, _ = intact()
    write_cycle(tmp_path, findings=f, worklist=w)
    code, msg = check_cycle(tmp_path, CYCLE, only_if_claimed=True)
    assert code == PASS
    assert "claims no remediation" in msg


def test_a_pr_with_no_audit_directory_at_all_is_not_applicable(tmp_path):
    code, msg = check_cycle(tmp_path, CYCLE, only_if_claimed=True)
    assert code == PASS
    assert "claims no remediation" in msg


def test_claiming_a_fix_with_no_measurement_is_a_break_not_a_skip(tmp_path):
    # The hole --only-if-claimed could have opened. A changelog WITHOUT the
    # findings and worklist it is supposed to refine is not "nothing to judge";
    # it is a fix that traces to nothing, which is precisely what this gate is
    # for. Deleting the two upstream artifacts must not buy a green.
    _, _, c = intact()
    write_cycle(tmp_path, changelog=c)
    code, msg = check_cycle(tmp_path, CYCLE, only_if_claimed=True)
    assert code == FAIL
    assert "claims remediation" in msg
    for missing in ("findings.json", "worklist.json"):
        assert missing in msg


def test_only_if_claimed_still_reconciles_a_complete_chain(tmp_path):
    f, w, c = intact()
    c["items"] = [{"id": "C9", "finding_fp": "fp-unplanned"}]
    write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    assert check_cycle(tmp_path, CYCLE, only_if_claimed=True)[0] == FAIL


def test_an_unparseable_changelog_never_reads_as_nothing_claimed(tmp_path):
    # A truncated write must not be indistinguishable from an absent file, or
    # corrupting one byte disables the gate.
    f, w, c = intact()
    cdir = write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    (cdir / "changelog.json").write_text("{")
    code, msg = check_cycle(tmp_path, CYCLE, only_if_claimed=True)
    assert code != PASS
    assert "changelog.json" in msg


# ── the CLI ──────────────────────────────────────────────────────────────────

def run_main(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["wf-e2e-check", *argv])
    return e2e_check.main()


def test_cli_defaults_to_the_newest_measured_cycle(tmp_path, monkeypatch, capsys):
    f, w, c = intact()
    write_cycle(tmp_path, findings=f, worklist=w, changelog=c, cycle="2026-08")
    f2, w2, c2 = intact("fp-bbb")
    write_cycle(tmp_path, findings=f2, worklist=w2, changelog=c2, cycle="2026-09")
    assert run_main(monkeypatch, ["--project", str(tmp_path)]) == PASS
    assert "[2026-09]" in capsys.readouterr().out


def test_cli_with_no_measured_cycle_cannot_judge(tmp_path, monkeypatch):
    assert run_main(monkeypatch, ["--project", str(tmp_path)]) == CANNOT_JUDGE


def test_cli_with_no_measured_cycle_and_only_if_claimed_is_not_applicable(tmp_path, monkeypatch, capsys):
    # A client repo that has never been measured still gets ordinary PRs.
    assert run_main(monkeypatch, ["--project", str(tmp_path), "--only-if-claimed"]) == PASS
    assert "no remediation" in capsys.readouterr().out


def test_cli_prints_a_break_to_stderr(tmp_path, monkeypatch, capsys):
    f, w, c = intact()
    c["items"] = [{"id": "C9", "finding_fp": "fp-unplanned"}]
    write_cycle(tmp_path, findings=f, worklist=w, changelog=c)
    assert run_main(monkeypatch, ["--project", str(tmp_path)]) == FAIL
    assert "BROKEN" in capsys.readouterr().err
