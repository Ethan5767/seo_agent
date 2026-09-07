#!/usr/bin/env python3
"""PR-level auto-merge decision — the CI half of the automation spine.

The quality gate has already run; this decides whether a green PR may merge
without a human. It derives the risk inputs from the REAL diff — the declared
tier from the client config, the created files and the changed copy from
`git diff base..head` — and hands them to `automerge.decide`, whose rules are
the single source of truth (all gates green + T1 + no new page + no YMYL claim).

It NEVER merges anything and never fails the run: it prints AUTO or HUMAN with a
reason and writes `decision=<AUTO|HUMAN>` to $GITHUB_OUTPUT. The workflow reads
that output and runs `gh pr merge` only on AUTO, only when the per-client
`automerge_enabled` flag is on. Decision here, action there — kept apart on
purpose so this stays pure and testable.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from pipeline.lib.automerge import AutoMergePolicy, Decision, decide
from pipeline.lib.common import client_profile, load_config


def _git(project, *args: str) -> str:
    return subprocess.run(["git", "-C", str(project), *args],
                          capture_output=True, text=True, check=True).stdout


def changed_paths(project, base: str, head: str = "HEAD") -> tuple:
    """(created, modified) repo-relative paths in base..head.

    A create (git status A/C) is the signal that a new page/route appeared —
    `automerge.risk_level` treats any create as high-risk. Renames (R) count as a
    create of the new path, since a new URL is a new page to the crawler.
    """
    out = _git(project, "diff", "--name-status", f"{base}..{head}")
    created, modified = [], []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]  # for R<score> the last column is the new path
        if status.startswith(("A", "C", "R")):
            created.append(path)
        else:
            modified.append(path)
    return sorted(created), sorted(modified)


def public_creates(created: list) -> list:
    """The created paths that are new PUBLIC pages — the only creates the
    auto-merge risk check cares about.

    Every remediation PR also creates the pipeline's own audit trail
    (docs/audit/<cycle>/findings.json, worklist.json, changelog.json — they ship
    inside the PR by design, Model A) and may touch docs/human-worklist.md. Those
    are metadata, never routes the crawler indexes, so counting them as "a new
    page" would force EVERY real PR to a human and defeat the whole spine. Public
    pages live under the build output / page source, never under docs/.
    """
    return [p for p in created if not p.startswith("docs/")]


def added_text(project, base: str, head: str = "HEAD") -> str:
    """The added lines of the diff (the copy this PR introduces), joined.

    This — not the whole page — is what the YMYL risk check judges: the question
    is whether the CHANGE touches a medical/legal claim, so an incidental word
    already on the page must not risk-flag an edit that never went near it.
    """
    out = _git(project, "diff", "--unified=0", f"{base}..{head}")
    added = [ln[1:] for ln in out.splitlines()
             if ln.startswith("+") and not ln.startswith("+++")]
    return "\n".join(added)


def _tier_str(project) -> str:
    """The declared tier as automerge expects it ("T1"/"T2"/"T3"), or "" when no
    tier is declared — which `decide` treats as ineligible (deny by default)."""
    profile = client_profile(load_config(str(project)), str(project))
    tier = profile.get("tier")
    return f"T{tier}" if isinstance(tier, int) else ""


def decide_pr(project, base: str, gates_passed: bool, head: str = "HEAD",
              enabled: bool = True) -> Decision:
    """Run the auto-merge decision for base..head of a client repo."""
    created, _ = changed_paths(project, base, head)
    text = added_text(project, base, head)
    creates = public_creates(created)
    # This job runs only after the quality gate finished, so the gate suite is
    # represented as one green/red signal. `decide` still enforces the rest
    # (tier, creates, YMYL) on top of it.
    gate_results = {"quality_gate": bool(gates_passed)}
    policy = AutoMergePolicy(enabled=enabled)
    return decide(gate_results=gate_results, tier=_tier_str(project),
                  creates=creates, text=text, policy=policy)


def _emit_github_output(decision: Decision) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"decision={decision.action}\n")
        fh.write(f"reason={decision.reason}\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-automerge-decide",
        description="Decide AUTO or HUMAN for a green PR. Prints the verdict and "
                    "writes decision=<AUTO|HUMAN> to $GITHUB_OUTPUT. Never merges.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--base", required=True, help="base ref (e.g. origin/main)")
    ap.add_argument("--head", default="HEAD", help="head ref (default HEAD)")
    ap.add_argument("--gates-passed", choices=["true", "false"], required=True,
                    help="did the quality gate pass? (the workflow passes its result)")
    ap.add_argument("--enabled", action="store_true",
                    help="the per-client auto-merge opt-in is ON. Omit and every "
                         "decision is HUMAN — the safe default.")
    args = ap.parse_args()

    d = decide_pr(Path(args.project), args.base, args.gates_passed == "true",
                  head=args.head, enabled=args.enabled)
    print(f"[{d.action}] {d.reason}")
    _emit_github_output(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
