"""The ratchet has to be WIRED, not merely implemented (B-007).

`lib/baseline.py` was complete, tested, and called by nothing on a PR. Every
baselineable gate in `quality-gate.reusable.yml` ran bare, so a client's
inherited debt was reported as blocking and the first PR against any real site
was red across the board. The module being correct is not the property that
matters — the property that matters is that the workflow passes the flag.

These tests read the workflow as text and assert the wiring, because that is the
only artifact the failure lived in. They also catch the two ways it rots: a new
baselineable gate added without the flag, and a gate named in `BASELINEABLE`
that no longer exists (`pages_are_data_check` sat there for a release after the
emitter was deleted).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.lib.baseline import BASELINEABLE, NEVER_BASELINEABLE

WORKFLOW = Path(".github/workflows/quality-gate.reusable.yml")
GATES_DIR = Path("pipeline/gates")
BASELINE_ARG = "steps.baseline.outputs.arg"


def command_for(gate: str) -> str:
    """capsule_check -> wf-capsule-check, the console script pyproject installs."""
    return "wf-" + gate.replace("_", "-")


@pytest.fixture(scope="module")
def workflow() -> str:
    return WORKFLOW.read_text()


def invocation(workflow: str, gate: str) -> str:
    """The line that runs this gate. Fails loudly rather than vacuously passing
    on a gate the workflow does not run at all."""
    cmd = command_for(gate)
    hits = [ln for ln in workflow.splitlines()
            if cmd in ln and not ln.lstrip().startswith("#")]
    assert hits, f"{cmd} is never invoked in {WORKFLOW}"
    assert len(hits) == 1, f"{cmd} invoked {len(hits)} times; the test assumes one"
    return hits[0]


# ── the wiring itself ────────────────────────────────────────────────────────

@pytest.mark.parametrize("gate", sorted(BASELINEABLE))
def test_every_baselineable_gate_receives_the_baseline(gate, workflow):
    assert BASELINE_ARG in invocation(workflow, gate), (
        f"{command_for(gate)} runs without the baseline, so a client's "
        f"pre-existing findings would block their first PR (B-007)")


@pytest.mark.parametrize("gate", sorted(NEVER_BASELINEABLE))
def test_no_never_baselineable_gate_receives_it(gate, workflow):
    # These refuse a baseline at exit 3 anyway; the point is that the workflow
    # never even offers one. A fabricated credential or an out-of-tier edit must
    # not be grandfatherable by editing a JSON file in the client's own repo.
    assert BASELINE_ARG not in invocation(workflow, gate), (
        f"{command_for(gate)} is in NEVER_BASELINEABLE — {NEVER_BASELINEABLE[gate]}")


def test_the_baseline_is_resolved_by_asking_whether_the_file_exists(workflow):
    """A client with no recording yet must run BARE, not fail.

    `Baseline.load` refuses a path that is not there, and that refusal is right:
    a typo'd path silently disarming the ratchet fleet-wide is the worse bug. So
    the workflow decides between "flag" and "no flag" by testing the file, and
    never hands a gate a path that does not exist."""
    assert "if [ -f docs/gate-baseline.json ]" in workflow
    assert 'echo "arg=--baseline docs/gate-baseline.json"' in workflow
    assert 'echo "arg="' in workflow


def test_a_run_with_no_baseline_warns_rather_than_passing_quietly(workflow):
    # Running bare is legitimate on day one and illegitimate on day ninety. The
    # annotation is what stops it from becoming the permanent state.
    assert "::warning::No docs/gate-baseline.json" in workflow
    assert "wf-gate-baseline --project . --out docs/gate-baseline.json" in workflow


# ── the two sets stay honest ─────────────────────────────────────────────────

@pytest.mark.parametrize("gate", sorted(BASELINEABLE | set(NEVER_BASELINEABLE)))
def test_every_named_gate_still_exists(gate):
    assert (GATES_DIR / f"{gate}.py").is_file(), (
        f"{gate} is named in the baseline sets but pipeline/gates/{gate}.py is gone")


def test_the_two_sets_are_disjoint():
    assert not (BASELINEABLE & set(NEVER_BASELINEABLE))
