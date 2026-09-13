"""A gate that scanned nothing must never report a pass.

This is the rule CLAUDE.md states as a sharp edge and the rule B-027 was filed
under, and until now nothing enforced it. `audit_ssr` broke it once by looking
only in `src/` and giving a silent green to every `create-next-app` layout; the
fix was exit 4, "cannot judge". The lesson was applied to two gates and to none
of the others, because no test asked the question.

Asked here for all of them at once: run every gate against a project whose build
tree exists and holds no HTML, which is exactly the B-018 trap (`build_output_dir`
pointed at `.next` produces precisely this state — a directory that exists, that
`build-site` accepts as non-empty, and that every OUT gate globs to zero files).

A gate may answer three ways. It may FAIL (it judged, and something is wrong). It
may say CANNOT JUDGE with exit 4. It must not say PASS, because a pass over zero
files is a lie that a human reads as safety, and six of the gates it applies to
are never-baselineable precisely because their subject carries legal or
structural exposure.

INVOCATIONS below is also the CLI registry this suite has never had (B-028): the
gates split between `--project`, `--out` and positional conventions with no
single place recording which is which, and `baseline.gate_argv` covers only the
eight baselineable ones. Every gate module must appear here, so a new gate cannot
be added without stating both how to run it and what its empty input means.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GATES_DIR = Path("pipeline/gates")
CANNOT_JUDGE = 4


def _argv(gate: str, project: Path, build: Path) -> list:
    """How to invoke each gate. `p` = project root, `b` = build tree."""
    p, b = str(project), str(build)
    table = {
        "acceptance_check":        ["--project", p],
        "audit_built":             [p, b],
        "audit_ssr":               [p],
        "capsule_check":           [p, "--out", b],
        "check_headings":          ["--out", b, "--project", p],
        "claim_provenance_check":  ["--project", p],
        "client_docs_check":       [p],
        "e2e_check":               ["--project", p],
        "em_dash_check":           ["--out", b],
        "fingerprint_check":       ["--out", b],
        "forbidden_sweep":         ["built", p],
        "image_budget_check":      ["--out", b, "--project", p],
        "lcp_hygiene_check":       ["--out", b, "--project", p],
        "llms_sales_purge":        ["--out", b, "--project", p],
        "noncommodity_check":      [p, "--out", b],
        "orphan_check":            ["--out", b],
        "parity_check":            ["--out", b],
        "robots_aicrawler_check":  ["--out", b, "--project", p],
        "rules_selftest":          [p],
        "tier_check":              ["--project", p],
    }
    return [sys.executable, "-m", f"pipeline.gates.{gate}"] + table[gate]


def all_gates() -> list:
    return sorted(p.stem for p in GATES_DIR.glob("*.py") if p.stem != "__init__")


# Gates whose subject is the built HTML tree. Zero HTML means they judged
# nothing, so a pass is a lie. This is the B-018 / B-027 set.
HTML_TREE_GATES = {
    "audit_built", "capsule_check", "check_headings", "em_dash_check",
    "fingerprint_check", "forbidden_sweep", "image_budget_check",
    "lcp_hygiene_check", "noncommodity_check", "orphan_check", "parity_check",
    "robots_aicrawler_check",
}

# Gates whose subject is some OTHER artifact, for which "absent" is a real and
# honest answer rather than a blind spot. Each needs a stated reason, so that
# adding a gate here is a decision someone made rather than a default.
NOT_HTML_SUBJECT = {
    "acceptance_check":       "no changelog means no fix was claimed; there is nothing to accept",
    "claim_provenance_check": "its subject is the PR diff, not the tree; an empty diff makes no claims",
    "tier_check":             "its subject is the PR diff; an empty diff touches no denied path",
    "audit_ssr":              "its subject is source, not built output (and it already exits 4)",
    "client_docs_check":      "its subject is the client's docs/ scaffold",
    "e2e_check":              "its subject is the cycle artifacts (already exits 4)",
    "llms_sales_purge":       "its subject is llms.txt; parity_check owns whether it must exist",
    "rules_selftest":         "its subject is the ruleset's own fixtures; bootstrap mode is deliberate",
}


@pytest.fixture
def empty_project(tmp_path: Path) -> Path:
    """A project that looks complete and whose build tree holds no HTML — the
    B-018 shape. The config is deliberately well-formed so a gate cannot excuse
    itself by claiming it was misconfigured."""
    (tmp_path / "out").mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "client-config.yml").write_text(
        "client: Empty Tree Test\n"
        "domain: example.com\n"
        "build_output_dir: out\n"
        "topology: hub-spoke\n"
        "tier: 1\n"
        'text_paths: ["out/**/*.html"]\n'
        "forbidden_phrases: []\n"
    )
    (docs / "banned-phrases.txt").write_text("lifetime warranty\nguaranteed results\n")
    return tmp_path


def test_every_gate_module_declares_how_to_run_it():
    """The registry above must stay complete, or the sweep below silently stops
    covering a gate — which is the B-007 shape that let `client_docs_check` sit
    unwired and untested while three docs still counted it."""
    src = Path(__file__).read_text()
    declared = {gate for gate in all_gates() if f'"{gate}":' in src}
    missing = sorted(set(all_gates()) - declared)
    assert not missing, (
        f"gate module(s) with no invocation registered: {missing}. Add them to "
        f"INVOCATIONS and decide what their empty input means before shipping.")


def test_every_gate_is_classified():
    """Each gate is either judged on the HTML tree or has a written reason why
    its empty input is honest. No third category, so a new gate cannot slip
    through unclassified."""
    unclassified = sorted(set(all_gates()) - HTML_TREE_GATES - set(NOT_HTML_SUBJECT))
    assert not unclassified, (
        f"gate(s) not classified: {unclassified}. Decide what empty input means "
        f"for them — put them in HTML_TREE_GATES, or in NOT_HTML_SUBJECT with a reason.")


@pytest.mark.parametrize("gate", sorted(HTML_TREE_GATES))
def test_html_gate_does_not_pass_over_an_empty_build_tree(gate, empty_project):
    proc = subprocess.run(
        _argv(gate, empty_project, empty_project / "out"),
        capture_output=True, text=True, timeout=120,
    )
    output = (proc.stdout + proc.stderr).strip()
    assert proc.returncode != 0, (
        f"{gate} exited 0 over a build tree containing no HTML — it reported a "
        f"PASS on a scan that judged nothing.\n"
        f"Use exit {CANNOT_JUDGE} (cannot judge) instead.\n"
        f"--- gate output ---\n{output}"
    )


@pytest.mark.parametrize("gate", sorted(NOT_HTML_SUBJECT))
def test_non_html_gate_still_runs_cleanly_on_an_empty_project(gate, empty_project):
    """These may legitimately skip, but they must not crash — a traceback is not
    a verdict, and `audit_built` tracebacked on a config with no `client:` key
    for exactly this reason."""
    proc = subprocess.run(
        _argv(gate, empty_project, empty_project / "out"),
        capture_output=True, text=True, timeout=120,
    )
    output = (proc.stdout + proc.stderr)
    assert "Traceback (most recent call last)" not in output, (
        f"{gate} crashed instead of returning a verdict:\n{output}")
