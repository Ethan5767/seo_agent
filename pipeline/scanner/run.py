"""Drive one full cycle over a repo, reusing the existing stages.

Model B (agency-owned): measure -> plan -> remediate(edit) -> commit -> diff +
auto-merge decision. Model A (client-owned): measure -> plan -> a BRIEF built
from the planned work + recommendations; the code is never touched. No stage
logic is reimplemented here — this is orchestration only.

Note: Model A does NOT call `remediate --recommend`. That engine mode only
briefs items a prior run already refused (CMS-unreachable copy); on a fresh
cycle it has nothing to brief. The honest Model-A deliverable is the worklist +
per-finding recommendation, which is what a client applies by hand.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from pipeline.audit import automerge_gate as ag
from pipeline.audit import measure, plan, remediate as rem
from pipeline.scanner.config import ensure_config
from pipeline.scanner.recommendations import recommend


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout


def _ensure_repo(repo: Path) -> None:
    if not (repo / ".git").is_dir():
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.email=scan@local", "-c", "user.name=scan",
             "commit", "-q", "-m", "scan: baseline")


def _measure_and_plan(repo: Path, url: str) -> None:
    argv = sys.argv
    try:
        sys.argv = ["wf-site-health", "--project", str(repo), "--url", url]
        measure.main()
        sys.argv = ["wf-site-plan", "--project", str(repo)]
        plan.main()
    finally:
        sys.argv = argv


def _worklist(repo: Path, cycle: str) -> list[dict]:
    path = repo / "docs" / "audit" / cycle / "worklist.json"
    if not path.is_file():
        return []
    return json.loads(path.read_text()).get("items", [])


def _brief(items: list[dict]) -> str:
    """A human-readable change-file: one block per planned item, with the fix."""
    lines = ["# Recommended changes (apply these yourself — Model A)", ""]
    for i in items:
        rec = recommend(i.get("code", ""))
        lines += [
            f"## {i.get('url','')} — {i.get('code','')}",
            f"- What: {i.get('kind','')}",
            f"- Why: {rec['why']}",
            f"- Fix: {rec['fix']}",
            "",
        ]
    return "\n".join(lines)


def run_cycle(repo: Path, url: str, model: str, cycle: str | None = None) -> dict:
    repo = Path(repo)
    ensure_config(repo, url, tier=1)
    _ensure_repo(repo)
    cycle = cycle or date.today().strftime("%Y-%m")
    _measure_and_plan(repo, url)
    items = _worklist(repo, cycle)

    if model.upper() == "A":
        return {"model": "A", "worklist": items, "brief": _brief(items)}

    # Model B: edit the code, commit, judge the diff.
    changelog, _code = rem.remediate(repo, cycle, max_items=20, max_files=20,
                                     model="sonnet", timeout=300, dry_run=False)
    (repo / "docs" / "audit" / changelog["cycle"] / "changelog.json").write_text(
        json.dumps(changelog, indent=2, sort_keys=True) + "\n")

    base = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "-b", "scan-fix")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=scan@local", "-c", "user.name=scan",
         "commit", "-q", "-m", "scan: apply fixes")
    diff = _git(repo, "diff", f"{base}..HEAD")
    decision = ag.decide_pr(repo, base, gates_passed=True, enabled=True)
    return {"model": "B", "changelog": changelog, "diff": diff,
            "decision": {"action": decision.action, "reason": decision.reason}}
