#!/usr/bin/env python3
"""Where does this cycle stand, and what should I run next?

    wf-cycle-status <client-repo> --client <slug> [--cycle YYYY-MM]
    wf-cycle-status <client-repo> --client <slug> --mark emit --status done --detail "12 pages"
    wf-cycle-status <client-repo> --client <slug> --claim distill

**Run this first, every time.** Alex and Robin both drive this pipeline and
never see each other's screens. This reads the shared, git-backed state in the
client repo and reports what is already finished, who finished it, and when — so
whoever sits down second does not repeat work or guess.

`--claim <step>` is the machine-readable form: exit 0 means go ahead, exit 3
means someone already did it. Wrap a step in it and reruns become safe no-ops.

⚠️ **Pull first.** The state is only as current as your checkout. That is the
same `git pull --ff-only` rule as everything else in `CLAUDE.md`.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline.lib.cycle_state import (
    DONE,
    FAILED,
    PENDING,
    RUNNING,
    SKIPPED,
    STEP_NAMES,
    CycleState,
)


def current_cycle() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def warn_if_stale(repo: Path) -> None:
    """A cycle state read from a stale checkout is worse than none."""
    try:
        subprocess.run(["git", "-C", str(repo), "fetch", "--quiet"],
                       capture_output=True, timeout=20)
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", "HEAD..@{u}"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        if out.isdigit() and int(out) > 0:
            print(f"⚠️  This checkout is {out} commit(s) BEHIND origin. "
                  f"Run `git -C {repo} pull --ff-only` before trusting the state below.\n")
    except Exception:
        pass  # not a git repo, no upstream, or offline — not worth failing over


def main() -> None:
    ap = argparse.ArgumentParser(description="Report or update shared cycle state.")
    ap.add_argument("repo", type=Path, help="Path to the client repo checkout")
    ap.add_argument("--client", required=True, help="Client slug")
    ap.add_argument("--cycle", default=None, help="Cycle as YYYY-MM (default: current month)")
    ap.add_argument("--claim", metavar="STEP", choices=STEP_NAMES,
                    help="Exit 0 if this step should run, 3 if it is already done")
    ap.add_argument("--mark", metavar="STEP", choices=STEP_NAMES, help="Record a step result")
    ap.add_argument("--status", choices=[PENDING, RUNNING, DONE, SKIPPED, FAILED], default=DONE)
    ap.add_argument("--detail", default="", help="Short note stored with the step")
    ap.add_argument("--force", action="store_true", help="Claim a step even if already done")
    ap.add_argument("--no-fetch", action="store_true", help="Skip the staleness check")
    args = ap.parse_args()

    if not args.repo.is_dir():
        print(f"ERROR: {args.repo} is not a directory", file=sys.stderr)
        sys.exit(2)

    cycle = args.cycle or current_cycle()
    if not args.no_fetch:
        warn_if_stale(args.repo)

    st = CycleState.load(args.repo, args.client, cycle)

    if args.claim:
        go, why = st.claim(args.claim, force=args.force)
        if go:
            print(f"RUN: {args.claim} — {why}")
            sys.exit(0)
        print(f"SKIP: {args.claim} — {why}")
        sys.exit(3)

    if args.mark:
        st.mark(args.mark, args.status, args.detail,
                at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        p = st.save()
        print(f"recorded {args.mark} = {args.status}")
        print(f"  {p}")
        print("\n⚠️  COMMIT AND PUSH this file, or the other side will not see it.")
        print(st.render())
        return

    print(st.render())


if __name__ == "__main__":
    main()
