"""The cycle-emit workflow, asserted against the file that actually ships.

Three things are proven here, and every one of them is a real defect this repo
has already paid for once:

1. **The `wf-*` entry points resolve.** `pyproject.toml` claiming a console
   script is not the same as the module exposing a callable `main`. A typo here
   surfaces as a red CI run in a CLIENT repo, which is the worst place to find it.

2. **The exit-code -> action mapping.** This test does not re-implement the
   table; it EXTRACTS the verdict step's shell out of
   `.github/workflows/cycle-emit.reusable.yml` and runs it under bash for every
   code in the contract. If someone edits the workflow and drops the 9 case, this
   goes red. A mapping test that mirrors the logic instead of executing it would
   not.

3. **Workflow hygiene** — parseable YAML, `bash -n` clean run blocks, every
   `uses:` a 40-hex SHA, and workflow_dispatch-only in the caller (never a cron).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"
EXAMPLES = REPO / ".github" / "examples"
CYCLE_EMIT = WORKFLOWS / "cycle-emit.reusable.yml"

#: The four generate-stage entry points Phase 2 registers, plus the claim/mark
#: tool the workflow leans on for rerun safety.
NEW_ENTRY_POINTS = {
    "wf-distill": "pipeline.generate.distill:main",
    "wf-classify": "pipeline.generate.classify:main",
    "wf-brief": "pipeline.generate.brief:main",
    "wf-emit-ts": "pipeline.generate.emit_ts:main",
}

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(wf: dict) -> list[dict]:
    return [s for job in wf["jobs"].values() for s in job.get("steps", [])]


# ---------------------------------------------------------------------------
# 1. entry points
# ---------------------------------------------------------------------------

def test_generate_entry_points_are_declared():
    tomllib = pytest.importorskip("tomllib")   # 3.11+; the package floor is 3.10
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    for name, target in NEW_ENTRY_POINTS.items():
        assert scripts.get(name) == target, f"{name} must map to {target}"


@pytest.mark.parametrize("name,target", sorted(NEW_ENTRY_POINTS.items()))
def test_entry_point_target_is_callable(name, target):
    """The declared `module:attr` must actually import and be callable.

    Declaring a console script for a module with no `main` produces a package
    that installs fine and explodes on first use.
    """
    import importlib

    modname, attr = target.split(":")
    mod = importlib.import_module(modname)
    assert callable(getattr(mod, attr)), f"{target} is not callable"


@pytest.mark.parametrize("name", sorted(NEW_ENTRY_POINTS))
def test_installed_console_script_help_exits_zero(name):
    """If the package is installed in this environment, `--help` must exit 0.

    Skipped (not failed) when the scripts are not on PATH — the suite must stay
    runnable from a bare checkout.
    """
    exe = shutil.which(name)
    if exe is None:
        pytest.skip(f"{name} is not installed on PATH (pip install -e . to cover this)")
    proc = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"{name} --help exited {proc.returncode}\n{proc.stderr}"


# ---------------------------------------------------------------------------
# 2. the exit-code -> action mapping, executed (not mirrored)
# ---------------------------------------------------------------------------

def _verdict_script() -> str:
    wf = _load(CYCLE_EMIT)
    for step in _steps(wf):
        if step.get("id") == "verdict":
            return step["run"]
    raise AssertionError("no step with id 'verdict' in cycle-emit.reusable.yml")


def _run_verdict(tmp_path: Path, emit_exit: str, emit_log: str | None) -> dict[str, str]:
    """Execute the real verdict shell and return its GITHUB_OUTPUT as a dict."""
    out_file = tmp_path / f"out-{emit_exit}"
    out_file.write_text("")
    log_path = tmp_path / f"emit-{emit_exit}.log"
    if emit_log is not None:
        log_path.write_text(emit_log)
    proc = subprocess.run(
        ["bash", "-c", _verdict_script()],
        env={
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "EMIT_EXIT": emit_exit,
            "EMIT_LOG": str(log_path),
            "GITHUB_OUTPUT": str(out_file),
        },
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"verdict script itself failed:\n{proc.stderr}"
    parsed: dict[str, str] = {}
    for line in out_file.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            parsed[k] = v
    return parsed


def _summary(exit_code: int, emitted=0, held=0, blocked=0, flagged=0) -> str:
    return (f"some emitter chatter\n"
            f"EMIT_SUMMARY emitted={emitted} held={held} blocked={blocked} "
            f"flagged={flagged} exit={exit_code}\n")


@pytest.mark.parametrize("rc,emitted,held,blocked", [
    (0, 3, 0, 0),    # clean
    (1, 3, 0, 0),    # emitted with warn flags
    (15, 2, 1, 0),   # some pages HELD — what emitted still ships
])
def test_proceeding_exit_codes_open_a_pr(tmp_path, rc, emitted, held, blocked):
    got = _run_verdict(tmp_path, str(rc), _summary(rc, emitted, held, blocked))
    assert got["proceed"] == "true", f"exit {rc} must proceed to a PR"
    assert got["emitted"] == str(emitted)
    assert got["held"] == str(held)


@pytest.mark.parametrize("rc,blocked", [
    (9, 2),    # REFUSED — a BLOCK finding
    (16, 0),   # unsegmentable DOCX / zero pages
    (2, 0),    # usage / input / dependency error
])
def test_refusing_exit_codes_open_no_pr(tmp_path, rc, blocked):
    got = _run_verdict(tmp_path, str(rc), _summary(rc, 0, 0, blocked))
    assert got["proceed"] == "false", f"exit {rc} must NOT open a PR"
    assert got["reason"], "a refusal must carry a human-readable reason"


def test_unknown_exit_code_refuses(tmp_path):
    """An exit code nobody planned for is a refusal, never a PR."""
    got = _run_verdict(tmp_path, "42", None)
    assert got["proceed"] == "false"
    assert "42" in got["reason"]


def test_contradictory_verdict_refuses(tmp_path):
    """EMIT_SUMMARY says clean, the process says refused -> no PR.

    The emitter prints its verdict twice on purpose. If those two ever disagree,
    the only safe reading is "do not open a PR".
    """
    got = _run_verdict(tmp_path, "9", _summary(0, emitted=5))
    assert got["proceed"] == "false"
    assert "contradict" in got["reason"].lower()


def test_missing_emit_log_still_refuses_safely(tmp_path):
    """No log at all (emitter died before printing) must not become a PR."""
    got = _run_verdict(tmp_path, "2", None)
    assert got["proceed"] == "false"


# ---------------------------------------------------------------------------
# 3. workflow hygiene
# ---------------------------------------------------------------------------

ALL_WORKFLOWS = sorted(WORKFLOWS.glob("*.yml")) + sorted(EXAMPLES.glob("*.yml"))


@pytest.mark.parametrize("path", ALL_WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_valid_yaml(path):
    assert isinstance(_load(path), dict)


def _uses_refs(wf: dict) -> list[str]:
    """Every real `uses:` in a workflow — job-level (reusable call) and step-level.

    Read from the PARSED yaml, never by regex over the text: these files carry
    long prose headers that quote `uses:` lines, and a regex sweep matches the
    prose and reports a phantom failure.
    """
    refs: list[str] = []
    for job in wf.get("jobs", {}).values():
        if isinstance(job.get("uses"), str):
            refs.append(job["uses"])
        for step in job.get("steps", []) or []:
            if isinstance(step.get("uses"), str):
                refs.append(step["uses"])
    return refs


@pytest.mark.parametrize("path", ALL_WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_sha_pinned(path):
    """A mutable ref in a workflow that can write to a client repo is a supply
    chain hole. Local `./...` composite actions and `uses:` of our own reusable
    workflows (pinned by tag, by design) are the two exceptions."""
    for ref in _uses_refs(_load(path)):
        if ref.startswith("./") or "seo-content-pipeline/.github/workflows" in ref:
            continue
        assert "@" in ref, f"{ref} has no ref"
        assert SHA_RE.match(ref.split("@", 1)[1]), f"{ref} is not pinned to a 40-hex SHA"


@pytest.mark.parametrize("path", ALL_WORKFLOWS, ids=lambda p: p.name)
def test_run_blocks_are_syntactically_valid_bash(path, tmp_path):
    """`bash -n` every run block. A shell typo in a workflow is only discovered
    at runtime, in CI, in someone else's repo."""
    wf = _load(path)
    for job_name, job in wf.get("jobs", {}).items():
        for i, step in enumerate(job.get("steps", []) or []):
            script = step.get("run")
            if not script:
                continue
            f = tmp_path / f"{path.stem}-{job_name}-{i}.sh"
            f.write_text(script)
            proc = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
            assert proc.returncode == 0, (
                f"{path.name} :: {job_name} :: step {i} "
                f"({step.get('name', step.get('id', '?'))}) is not valid bash:\n{proc.stderr}")


def test_cycle_emit_is_workflow_call_only():
    wf = _load(CYCLE_EMIT)
    triggers = wf[True] if True in wf else wf["on"]      # PyYAML reads bare `on:` as True
    assert set(triggers) == {"workflow_call"}, (
        "the reusable cycle-emit workflow must be workflow_call only — a schedule "
        "here would be a cron that opens PRs against live client sites")


def test_cycle_emit_declares_no_write_secret():
    """The ONLY secret is the read-only pipeline checkout token. If a cross-repo
    WRITE PAT ever appears here, the whole per-client design has been undone."""
    wf = _load(CYCLE_EMIT)
    call = wf[True]["workflow_call"] if True in wf else wf["on"]["workflow_call"]
    assert set(call.get("secrets", {})) == {"PIPELINE_REPO_TOKEN"}


def test_cycle_emit_permissions_are_least_privilege():
    wf = _load(CYCLE_EMIT)
    assert wf["permissions"] == {"contents": "read"}, "workflow default must be read-only"
    job = wf["jobs"]["cycle-emit"]
    assert job["permissions"] == {"contents": "write", "pull-requests": "write"}


def test_cycle_emit_never_pushes_main_or_merges():
    text = CYCLE_EMIT.read_text(encoding="utf-8")
    assert "gh pr merge" not in text, "this workflow must never merge"
    assert not re.search(r"git push\s+origin\s+main", text), "this workflow must never push main"
    assert "--force-with-lease" in text, "the branch push must be lease-guarded"


def test_example_caller_is_dispatch_only_and_pinned():
    example = EXAMPLES / "cycle-emit.yml"
    wf = _load(example)
    triggers = wf[True] if True in wf else wf["on"]
    assert set(triggers) == {"workflow_dispatch"}, (
        "the client-side caller must be workflow_dispatch only — a human starts a cycle")
    uses = wf["jobs"]["cycle-emit"]["uses"]
    assert "cycle-emit.reusable.yml@v" in uses, f"caller must pin an exact tag, got {uses}"
    assert not uses.endswith("@main")


def test_example_caller_names_the_one_required_secret():
    text = (EXAMPLES / "cycle-emit.yml").read_text(encoding="utf-8")
    assert "PIPELINE_REPO_TOKEN" in text
    assert "secrets: inherit" in text
    # A secret VALUE must never be in a file. Only the name.
    assert not re.search(r"(ghp_|github_pat_)[A-Za-z0-9_]{10,}", text)


def test_no_client_workflow_hardcodes_a_client():
    """cycle-emit is per-client but the REUSABLE half must stay client-generic —
    the BUG-016 class (Acme's trade/state baked into shared code)."""
    # Executable lines only. The header and the inline comments legitimately name
    # the pilot when explaining the design; what must never happen is a client
    # name reaching a command, an input default or a path.
    lines = [ln.split("#", 1)[0].lower()
             for ln in CYCLE_EMIT.read_text(encoding="utf-8").splitlines()]
    text = "\n".join(lines)
    for token in ("acme", "northstar", "roofing contractor", "charlotte"):
        assert token not in text, (
            f"{token!r} appears in the fleet-wide reusable workflow — "
            "client specifics belong in the caller's `with:` and the client's own config")
