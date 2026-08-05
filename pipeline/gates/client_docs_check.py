#!/usr/bin/env python3
"""GATE — every client repo must carry the standard docs tree.

    wf-client-docs-check <client-repo> [--warn-only]

Exit 0 clean · exit 1 a required doc is missing.

What this enforces. A cycle must land in a durable, in-repo record. The intake
ledger is a CI cache and is evictable; `docs/intake-archive/` and
`docs/seo-work-log.md` live in git and are the actual history. Without them a
client can ship work that nothing anywhere records — which was literally true of
BLH-North on 2026-07-28: no work log, no cycle-logs, no intake-archive.

The remedy is never "go read the convention". It is one command, printed in the
failure output, that creates exactly what is missing without touching anything
that exists.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.lib.client_docs import audit


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate: client repo carries the standard docs tree.")
    ap.add_argument("repo", type=Path, nargs="?", default=Path("."),
                    help="Path to the client repo (default: cwd)")
    ap.add_argument("--slug", default="<slug>", help="Client slug, used in the fix hint")
    ap.add_argument("--warn-only", action="store_true",
                    help="Report but always exit 0. For rollout before the gate is made blocking.")
    args = ap.parse_args()

    if not args.repo.is_dir():
        print(f"ERROR: {args.repo} is not a directory", file=sys.stderr)
        sys.exit(2)

    missing_req, missing_opt = audit(args.repo)

    for d in missing_opt:
        print(f"  optional, absent: {d.path} — {d.why}")

    if not missing_req:
        print(f"PASS: client docs contract satisfied ({args.repo.name}).")
        sys.exit(0)

    print(f"\n{'WARN' if args.warn_only else 'FAIL'}: "
          f"{len(missing_req)} required doc(s) missing in {args.repo.name}:\n")
    for d in missing_req:
        print(f"  MISSING  {d.path}")
        print(f"           {d.why}")

    print("\nFix:")
    print(f"  wf-scaffold-client-docs {args.repo} --slug {args.slug}")
    print("  (idempotent and additive — it never overwrites an existing file)")

    sys.exit(0 if args.warn_only else 1)


if __name__ == "__main__":
    main()
