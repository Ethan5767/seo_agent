#!/usr/bin/env python3
"""tier_check — the PR diff must stay inside the tier the repo declared (v3 §4.2).

WHY THIS GATE IS THE ONE THAT MAKES TIERING REAL
------------------------------------------------
The tier is also injected into the agent's prompt, but that is efficiency, not
safety: a prompt is a request and a gate is a fact. This walks every path in the
diff and refuses on any path or operation the tier does not permit.

    T1  modify files matching `text_paths`.                No creates, no deletes.
    T2  T1 + create under `content.location`,
        + modify the `content.registry` files that wire a new page in.  No deletes.
    T3  anything not denied.                               Deletes allowed.

**The deny floor applies at every tier, T3 included**, and it is unioned in from
`lib/common.DEFAULT_DENY` rather than read from the client config alone — a repo
that forgets the block still cannot have its gates, its own tier declaration, or
its deploy config edited by the thing those files exist to judge.

The verdict itself lives in `lib/common.tier_verdict`, because `remediate` asks
the same question before it lets the agent near a file. Two copies of this rule
would drift, and the copy that drifts loose is the one that ships.

Usage:
  wf-tier-check --project . [--base origin/main] [--diff-file PATH]

Exit: 0 permitted · 17 refused · 2 usage (no diff could be resolved)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from pipeline.lib.common import client_profile, load_config, tier_verdict

REFUSED_EXIT = 17
USAGE_EXIT = 2

# Candidate merge bases, in order. A PR checkout usually has the base branch as a
# remote ref; a local run usually does not.
_BASE_CANDIDATES = ("origin/main", "origin/master", "main", "master", "HEAD~1")


class DiffError(RuntimeError):
    """No diff could be resolved — refuse rather than pass an unexamined PR."""


def _git(project, *args) -> str:
    r = subprocess.run(["git", "-C", str(project), *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise DiffError(r.stderr.strip() or f"git {' '.join(args)} failed")
    return r.stdout


def resolve_base(project, base: str | None) -> str:
    """The ref to diff against. An explicit --base that does not exist is a usage
    error, never a silent fallback: diffing against the wrong base is how a gate
    reports clean on changes it never looked at."""
    if base:
        try:
            _git(project, "rev-parse", "--verify", f"{base}^{{commit}}")
        except DiffError:
            raise DiffError(f"--base {base!r} is not a commit in this repo")
        return base
    for cand in _BASE_CANDIDATES:
        try:
            _git(project, "rev-parse", "--verify", f"{cand}^{{commit}}")
            return cand
        except DiffError:
            continue
    raise DiffError("no base ref found (tried " + ", ".join(_BASE_CANDIDATES) +
                    ") — pass --base explicitly")


def parse_name_status(text: str) -> list:
    """git --name-status output -> [(op, path)].

    A rename (`R100 old new`) is judged as a DELETE of the old path plus a CREATE
    of the new one. Collapsing it to a single "modify" is exactly how a T1 agent
    would move a file out of its allow-list and keep editing it.
    """
    out: list = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0].strip()
        op = status[0].upper()
        if op in ("R", "C") and len(parts) >= 3:
            out.append(("D" if op == "R" else "M", parts[1].strip()))
            out.append(("A", parts[2].strip()))
        elif len(parts) >= 2:
            out.append((op, parts[1].strip()))
    return out


def changed_paths(project, base: str | None, diff_file: str | None) -> list:
    if diff_file:
        return parse_name_status(Path(diff_file).read_text())
    ref = resolve_base(project, base)
    return parse_name_status(_git(project, "diff", "--name-status", f"{ref}...HEAD"))


def judge(profile: dict, changes: list) -> tuple:
    """Returns (allowed, refused) as lists of (op, path, reason)."""
    allowed, refused = [], []
    for op, path in changes:
        ok, reason = tier_verdict(profile, path, op)
        (allowed if ok else refused).append((op, path, reason))
    return allowed, refused


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-tier-check",
        description="Refuse any changed path or operation the declared tier does not permit.")
    ap.add_argument("--project", default=".", help="client repo root")
    ap.add_argument("--base", help="ref to diff against (default: origin/main, then main, then HEAD~1)")
    ap.add_argument("--diff-file", help="read `git diff --name-status` output from a file instead")
    args = ap.parse_args()

    profile = client_profile(load_config(args.project), args.project)
    try:
        changes = changed_paths(args.project, args.base, args.diff_file)
    except (DiffError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return USAGE_EXIT

    if not changes:
        print("[OK] tier-check: the diff is empty — nothing to judge.")
        return 0

    allowed, refused = judge(profile, changes)
    tier = profile.get("tier")
    label = f"T{tier}" if tier else "no tier declared"

    for op, path, reason in refused:
        print(f"[REFUSED] {reason}")
    for op, path, reason in allowed:
        print(f"[ok] {reason}")

    if refused:
        sys.stdout.flush()
        print(f"\n[BLOCKED] {len(refused)} of {len(changes)} changed path(s) exceed "
              f"{label}. Either the agent went outside its authority or this repo "
              f"should declare a higher tier — deliberately, in a human PR.",
              file=sys.stderr)
        return REFUSED_EXIT
    print(f"\n[OK] tier-check: {len(changes)} changed path(s), all within {label}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
