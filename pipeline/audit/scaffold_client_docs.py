#!/usr/bin/env python3
"""Create the standard `docs/` tree in a client repo. Idempotent and additive.

    wf-scaffold-client-docs <client-repo> --slug <slug> [--dry-run] [--include-optional]

**It never overwrites an existing file.** A repo with real history is left
exactly as it is; only what is missing gets created. That is what makes it safe
to run on all five clients, and safe to re-run.

Why this exists. Every client `docs/` tree was hand-made and by 2026-07-28 no two
of the five matched — BLH-North had no work log, no cycle-logs and no
intake-archive, so a cycle could run there with nowhere to record what shipped.
`bootstrap_config.py` created one file and nothing in the engine knew about the
rest. Run this when onboarding a client, and before that client's first cycle.

Pairs with `wf-client-docs-check`, which fails a build when a required doc is
missing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.lib.client_docs import DOC_SPECS, REQUIRED, audit, render


def scaffold(repo: Path, slug: str, include_optional: bool, dry_run: bool) -> int:
    specs = DOC_SPECS if include_optional else REQUIRED
    created, skipped, manual = [], [], []

    for d in specs:
        target = repo / d.path

        if d.is_dir:
            keep = target / ".gitkeep"
            if target.is_dir() and any(target.iterdir()):
                skipped.append(f"{d.path}/ (exists, has content)")
                continue
            if keep.is_file():
                skipped.append(f"{d.path}/ (exists)")
                continue
            created.append(f"{d.path}/.gitkeep")
            if not dry_run:
                target.mkdir(parents=True, exist_ok=True)
                keep.write_text(d.keep)
            continue

        if target.is_file():
            skipped.append(d.path)
            continue

        if not d.template:
            # client-config.yml is generated from the live site by
            # wf-bootstrap-config. Writing an empty stub here would be worse than
            # absent: every gate would load it and silently read wrong values.
            manual.append(d.path)
            continue

        created.append(d.path)
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(d, slug))

    tag = "WOULD CREATE" if dry_run else "CREATED"
    for p in created:
        print(f"{tag}: {p}")
    for p in skipped:
        print(f"KEPT (already present): {p}")
    for p in manual:
        print(f"MANUAL: {p} — generate with `wf-bootstrap-config <repo> <domain>`. "
              f"Not stubbed: an empty config makes every gate read wrong values.")

    print(f"\n{tag.split()[-1].lower()}={len(created)}  kept={len(skipped)}  manual={len(manual)}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Scaffold the standard docs/ tree in a client repo.")
    ap.add_argument("repo", type=Path, help="Path to the client repo checkout")
    ap.add_argument("--slug", required=True, help="Client slug, e.g. blueline-hvac-north")
    ap.add_argument("--include-optional", action="store_true", help="Also create optional docs")
    ap.add_argument("--dry-run", action="store_true", help="Print what would change, write nothing")
    args = ap.parse_args()

    if not args.repo.is_dir():
        print(f"ERROR: {args.repo} is not a directory", file=sys.stderr)
        sys.exit(2)

    missing_req, _ = audit(args.repo)
    if missing_req:
        print(f"Missing {len(missing_req)} required doc(s) in {args.repo.name}:")
        for d in missing_req:
            print(f"  - {d.path}  — {d.why}")
        print()
    else:
        print(f"{args.repo.name}: all required docs already present.\n")

    sys.exit(scaffold(args.repo, args.slug, args.include_optional, args.dry_run))


if __name__ == "__main__":
    main()
