"""The handoff gate is WIRED, not merely implemented.

B-007's lesson, and the reason `docs/gate-reference.md` carried this gate as
"implemented but NOT wired" for a day: `lib/baseline.py` was complete, tested,
and called by nothing on a PR for a whole release. A green unit test proves the
function works. It proves nothing about whether CI runs it.

Three things have to be true together, and each has broken independently before:
  * the step exists and invokes the console entry point
  * the step's outcome is READ by the loop that fails the run (B-038: the sticky
    comment said one thing and the annotation another, because the two lists
    were edited separately)
  * the step's env var is declared, or the shell reads an empty string (B-063:
    $TREE was a step OUTPUT, never declared as env, so `"" != "true"` was always
    true and every client's PR went red for a year)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/quality-gate.reusable.yml"
TEXT = WORKFLOW.read_text()


def block(start: str, end: str) -> str:
    i = TEXT.index(start)
    return TEXT[i:TEXT.index(end, i)]


EVALUATE = block("- name: Evaluate gates", "Quality Gate GREEN")
REPORT = block("- name: Build report (step summary)", "- name: Upsert sticky PR comment")


@pytest.mark.parametrize("cmd", ["wf-e2e-check", "wf-client-docs-check"])
def test_the_gate_is_actually_invoked(cmd):
    assert re.search(rf"^\s+.*\b{re.escape(cmd)}\b", TEXT, re.M), \
        f"{cmd} is implemented but nothing in the workflow runs it"


@pytest.mark.parametrize("step_id,var", [("e2e", "E2E"), ("client_docs", "CLIENT_DOCS")])
def test_the_step_declares_an_id_and_both_consumers_read_it(step_id, var):
    assert f"id: {step_id}\n" in TEXT, f"step {step_id} has no id, so no outcome to read"
    for name, chunk in (("evaluate", EVALUATE), ("report", REPORT)):
        assert f"{var}: ${{{{ steps.{step_id}.outcome }}}}" in chunk, \
            f"{var} is not declared as env in the {name} step — B-063, the shell sees an empty string"


def test_the_failing_loop_reads_the_new_gates():
    # The loop IS the verdict. The add_fail list only writes the comment.
    loop = EVALUATE[EVALUATE.index("for g in "):EVALUATE.index("; do")]
    for var in ("E2E", "CLIENT_DOCS"):
        assert var in loop, f"{var} is reported but never fails the run"


def test_every_gate_the_loop_reads_has_a_registry_entry():
    # Attribution: a red run must name which gate and which exit code.
    loop = EVALUATE[EVALUATE.index("for g in "):EVALUATE.index("; do")]
    names = [w for w in re.split(r"[\s\\]+", loop) if w.isupper() and len(w) > 2]
    reg = EVALUATE[EVALUATE.index("reg() {"):EVALUATE.index("red=0")]
    for n in names:
        assert f"{n})" in reg, f"{n} can fail the run with no exit-code registry entry"


def test_the_comment_explains_each_new_failure_in_words():
    body = REPORT[REPORT.index("add_fail() {"):]
    for var, must_say in (("E2E", "traces to no measurement"), ("CLIENT_DOCS", "wf-scaffold-client-docs")):
        line = next((l for l in body.splitlines() if f'"${var}" = "failure"' in l), None)
        assert line, f"{var} can fail with no plain-English line in the sticky comment"
        assert must_say in line, f"the {var} line must tell the reader what to do"


def test_e2e_runs_on_every_pr_not_only_when_a_tree_was_built():
    # It reads docs/audit/**, not the built HTML. Gating it on steps.tree would
    # mean a client whose build failed also loses provenance checking, at exactly
    # the moment the PR is least trustworthy.
    step = block('- name: "CHAIN:', "- name: Build report")
    assert "steps.tree.outputs.ready" not in step, \
        "the chain gate needs no build tree; do not gate it on one"
    assert "--only-if-claimed" in step, \
        "without the flag every ordinary human PR is exit 4 and the run goes red"


def test_client_docs_defaults_to_advisory():
    # Blocking on day one would turn the existing fleet red for a missing
    # directory rather than for anything wrong with the change under review.
    inputs = block("client_docs_blocking:", "node_version:")
    assert "default: false" in inputs
    step = block('- name: "PRE: client-docs contract', '- name: Build (shared')
    assert "--warn-only" in step, "the non-blocking path must pass --warn-only"
    assert "inputs.client_docs_blocking" in step, "there must be a way to opt in"


def test_the_gate_count_in_the_docs_matches_what_the_workflow_runs():
    # gate-reference.md tracked "20 implementations exist; 19 are wired" as a
    # deliberate gap. The gap is now closed, so the prose must not still claim it.
    ref = (WORKFLOW.parents[2] / "docs/gate-reference.md").read_text()
    assert "19 are wired" not in ref, \
        "gate-reference.md still records the e2e gate as unwired"
