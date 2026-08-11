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


# ── B-008: em dashes are baselineable, and the wiring is asserted ────────────
# "Implemented is not wired" (B-007). Adding em_dash_check to BASELINEABLE without
# the recorder invocation and the CI baseline arg would leave a gate that CAN carry
# debt and never does.

def test_em_dash_check_is_baselineable():
    from pipeline.lib.baseline import BASELINEABLE, NEVER_BASELINEABLE
    # It used to be in NEITHER list, so assert_baselineable refused it as "not in the
    # allow-list" and a legacy client's every PR was permanently red.
    assert "em_dash_check" in BASELINEABLE
    assert "em_dash_check" not in NEVER_BASELINEABLE


def test_the_recorder_knows_how_to_invoke_em_dash_check(tmp_path):
    from pipeline.lib.baseline import gate_argv
    p = tmp_path / "client"
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "client-config.yml").write_text(
        "client: acme\ndomain: acme.com\nrepo:\n  framework: nextjs-app-router\n")
    argv = gate_argv("em_dash_check", p)
    assert "pipeline.gates.em_dash_check" in argv
    assert "--out" in argv


def test_the_em_dash_ratchet_accepts_legacy_and_blocks_new(tmp_path, monkeypatch, capsys):
    """The whole point of B-008, end to end: two legacy em dashes recorded, then a
    third one written by us must still fail."""
    import json
    from pipeline.gates import em_dash_check as ed

    out = tmp_path / "out"
    (out / "about").mkdir(parents=True)
    (out / "index.html").write_text("<html><body><p>Legacy — copy.</p></body></html>")
    (out / "about" / "index.html").write_text(
        "<html><body><p>Since 1998 &mdash; three generations.</p></body></html>")

    # Record: every current finding becomes accepted debt.
    monkeypatch.setattr("sys.argv", ["wf-em-dash-check", "--out", str(out),
                                     "--emit-findings", str(tmp_path / "f.json")])
    assert ed.main() == 0
    found = json.loads((tmp_path / "f.json").read_text())      # emit() writes a list
    assert len(found) == 2

    # The fingerprint is recomputed from the emitted finding, exactly as the real
    # recorder does — `to_json` deliberately omits it so the two cannot disagree.
    from pipeline.lib.baseline import Finding
    baseline = tmp_path / "gate-baseline.json"
    baseline.write_text(json.dumps({
        "schema": "meridian-gate-baseline/1", "recorded": "2026-08-07",
        "gates": ["em_dash_check"], "total": 2,
        "entries": [{"gate": "em_dash_check", "code": f["code"],
                     "fingerprint": Finding.from_json(f).fingerprint,
                     "location": f["location"], "recorded": "2026-08-07"}
                    for f in found]}))

    # Legacy accepted.
    monkeypatch.setattr("sys.argv", ["wf-em-dash-check", "--out", str(out),
                                     "--baseline", str(baseline)])
    assert ed.main() == 0
    assert "2 pre-existing accepted as legacy debt" in capsys.readouterr().out

    # A NEW em dash, in copy we wrote, still blocks. The baseline may only shrink.
    (out / "services").mkdir()
    (out / "services" / "index.html").write_text(
        "<html><body><p>Fast — clean — guaranteed.</p></body></html>")
    monkeypatch.setattr("sys.argv", ["wf-em-dash-check", "--out", str(out),
                                     "--baseline", str(baseline)])
    assert ed.main() == 1
    assert "1 NEW em dash" in capsys.readouterr().out


def test_a_line_moving_does_not_turn_legacy_debt_into_a_new_finding(tmp_path, monkeypatch):
    """The line number rides in `detail`, which is never fingerprinted. Without that,
    any edit above a legacy em dash would re-block the PR."""
    import json
    from pipeline.gates import em_dash_check as ed
    from pipeline.lib.baseline import Finding

    fp = lambda path: [Finding.from_json(f).fingerprint
                       for f in json.loads(path.read_text())]

    LINE = "<p>Legacy — copy.</p>"
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text(f"<html><body>\n{LINE}\n</body></html>")
    monkeypatch.setattr("sys.argv", ["wf-em-dash-check", "--out", str(out),
                                     "--emit-findings", str(tmp_path / "a.json")])
    ed.main()
    before = fp(tmp_path / "a.json")

    # The SAME line, three lines further down. Only its position changed — the copy
    # a reviewer accepted is byte-identical, so the finding must be the same one.
    (out / "index.html").write_text(
        f"<html>\n<head><title>x</title></head>\n<body>\n{LINE}\n</body></html>")
    monkeypatch.setattr("sys.argv", ["wf-em-dash-check", "--out", str(out),
                                     "--emit-findings", str(tmp_path / "b.json")])
    ed.main()
    after = fp(tmp_path / "b.json")
    assert before == after


# ── the render source: nine gates must be reachable on an SSR client ─────────
# v3 sharp edge #4. Before this, a client with no static export had `build-site`
# exit 1 and all nine OUT gates skipped — including forbidden_sweep, which is
# NEVER_BASELINEABLE for legal exposure.

BUILD_TREE_GATES = ["check_headings", "em_dash_check", "capsule_check",
                    "noncommodity_check", "fingerprint_check", "orphan_check",
                    "parity_check"]


def test_the_out_gates_key_on_whether_there_is_html_not_on_the_build(workflow):
    """They used to be guarded by `steps.build.outcome == 'success'`, which is false
    for a crawled tree — so wiring the crawl without rewiring the guards would have
    produced the tree and then skipped every gate that reads it."""
    assert "steps.build.outcome == 'success'" not in workflow, (
        "an OUT gate still keys on the build, so a crawled tree would be skipped")
    assert "steps.tree.outputs.ready == 'true'" in workflow


@pytest.mark.parametrize("gate", BUILD_TREE_GATES)
def test_every_build_tree_gate_runs_when_the_tree_came_from_a_crawl(gate, workflow):
    line = invocation(workflow, gate)
    # Each gate's own `if:` sits above its `run:`; find the guard for this step by
    # walking back to the nearest `if:`.
    lines = workflow.splitlines()
    idx = lines.index(line)
    guard = next((lines[i] for i in range(idx, max(idx - 8, -1), -1)
                  if lines[i].lstrip().startswith("if:")), "")
    assert "steps.tree.outputs.ready" in guard, (
        f"{command_for(gate)} is guarded by {guard.strip()!r}, so it cannot run "
        f"against a crawled tree")


def test_no_html_is_an_error_annotation_not_a_silent_skip(workflow):
    # A skipped gate suite reported as anything other than a problem is the failure
    # sharp edge #4 describes: nine gates that judged nothing, reading as fine.
    assert "::error::No HTML to judge" in workflow
    assert "sharp edge #4" in workflow


def test_the_crawl_only_runs_when_the_build_produced_nothing(workflow):
    # A statically exported client must be judged on its OWN build, never on a
    # deployment: the build is what the PR produces, the deployment is what a
    # previous state produced.
    assert "if: steps.build.outcome != 'success' && inputs.render_url != ''" in workflow


def test_a_crawled_tree_does_not_block_the_pr_on_the_failed_build(workflow):
    """B-038 — the last thing standing between an SSR client and a green PR.

    The OUT gates were rewired to key on `steps.tree.outputs.ready`, but the
    BLOCKING list still read `steps.build.outcome`. For a client with no static
    export the build is configured to fail on purpose — that is the entire reason
    `render_url` exists — so the suite would run every gate against the crawled
    tree, pass them all, and still report RED on the build, while the summary
    table two blocks above printed `**crawled** … -> ./out` in the same comment.
    """
    assert '[ "$BUILD" = "failure" ]' not in workflow, (
        "the blocking list still fails the PR on the build outcome, so a client "
        "with no static export can never be green no matter how the crawl went")
    assert '[ "$TREE" != "true" ]' in workflow, (
        "nothing blocks on there being no HTML to judge — a suite that judged "
        "nothing must never read as a pass")
    assert "TREE: ${{ steps.tree.outputs.ready }}" in workflow, (
        "$TREE is used by the blocking list but never exported to it")


def test_the_no_html_message_does_not_claim_the_page_checks_ran(workflow):
    """The message the old BUILD line printed — 'All page checks below were
    skipped' — was false in exactly the case it fired on after a successful crawl.
    Whatever replaces it has to be true whenever it prints."""
    assert "Every page check below was SKIPPED, not passed." in workflow


def test_the_render_snapshot_command_is_installed():
    import tomllib
    scripts = tomllib.loads(Path("pyproject.toml").read_text())["project"]["scripts"]
    assert scripts["wf-render-snapshot"] == "pipeline.audit.snapshot:main"
