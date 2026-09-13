#!/usr/bin/env python3
"""
e2e_check.py — the whole-pipeline handoff gate (gate #20).

Every other gate judges the built HTML or the diff. None of them proves the
pipeline's own JSON chain is internally consistent:

    findings.json  (measure)  -> worklist.json (plan)  -> changelog.json (remediate)

Each arrow is supposed to be a strict refinement of the one before it: the plan
may only carry findings that were measured, and the remediation may only claim
items that were planned. When that chain is intact a green PR means "the fix the
agent shipped traces all the way back to a measurement". When it is broken —
a worklist item with no finding, a changelog entry for an item nobody planned —
the provenance the rest of the gates assume is already gone, and no per-file
check can see it because each artifact is valid on its own.

This gate re-reads all three artifacts for a cycle and asserts:
    1. all three exist, parse, and carry their declared SCHEMA string;
    2. every worklist item's finding_fp is a real finding fingerprint;
    3. every changelog item's finding_fp was actually planned (is in the worklist).

Exit codes:
    0   the chain is intact (or, with --only-if-claimed, nothing was claimed)
    21  the chain is broken (mismatch, bad schema, unparseable artifact, or a
        remediation claimed against artifacts that are not in the PR)
    4   cannot judge — the cycle is missing one of the three artifacts, or
        findings.json is empty. A partial chain is NOT a pass: a gate that
        scanned nothing must never report green (CLAUDE.md sharp-edge #4).

`--only-if-claimed` is what makes this safe to run on EVERY pull request. Three
ways a chain can be absent, and they are three different facts:

    nothing claimed        -> not applicable. An ordinary human PR carries no
                              changelog.json; there is no remediation to trace.
    claimed but unmeasured -> BROKEN (21). A changelog.json with no findings or
                              worklist beside it is a fix that traces to nothing,
                              which is the exact break this gate exists to catch.
                              Deleting the upstream artifacts must never buy a
                              green.
    measured but empty     -> cannot judge (4). Nothing to reconcile either way.

Without the flag the first case is exit 4, which is correct for a human running
the command against a cycle and wrong for CI running it against every PR.

Usage:
    wf-e2e-check --project <client-repo>            # newest measured cycle
    wf-e2e-check --project <client-repo> --cycle 2026-09
    wf-e2e-check --project . --only-if-claimed      # how CI invokes it
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.audit.measure import SCHEMA as FINDINGS_SCHEMA
from pipeline.audit.plan import SCHEMA as WORKLIST_SCHEMA, audit_dir, cycles
from pipeline.audit.remediate import SCHEMA as CHANGELOG_SCHEMA

PASS, FAIL, CANNOT_JUDGE = 0, 21, 4


def _load(path: Path):
    """(doc, error). A missing or unparseable artifact is an error string, never
    a raised exception — the caller decides whether that is fatal or unjudgeable."""
    if not path.is_file():
        return None, f"missing: {path.name}"
    try:
        return json.loads(path.read_text()), None
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"unparseable {path.name}: {exc}"


def reconcile(findings: dict, worklist: dict, changelog: dict) -> list:
    """Return a list of provenance breaks (empty list = intact chain)."""
    breaks: list[str] = []

    if findings.get("schema") != FINDINGS_SCHEMA:
        breaks.append(f"findings.json schema is {findings.get('schema')!r}, "
                      f"expected {FINDINGS_SCHEMA!r}")
    if worklist.get("schema") != WORKLIST_SCHEMA:
        breaks.append(f"worklist.json schema is {worklist.get('schema')!r}, "
                      f"expected {WORKLIST_SCHEMA!r}")
    if changelog.get("schema") != CHANGELOG_SCHEMA:
        breaks.append(f"changelog.json schema is {changelog.get('schema')!r}, "
                      f"expected {CHANGELOG_SCHEMA!r}")

    finding_fps = {f.get("fingerprint") for f in findings.get("findings", [])
                   if f.get("fingerprint")}
    worklist_fps = {i.get("finding_fp") for i in worklist.get("items", [])
                    if i.get("finding_fp")}

    for fp in sorted(worklist_fps - finding_fps):
        breaks.append(f"worklist item traces to finding {fp} which is not in findings.json")

    for item in changelog.get("items", []):
        fp = item.get("finding_fp")
        if fp and fp not in worklist_fps:
            breaks.append(f"changelog item {item.get('id', '?')} claims finding {fp} "
                          f"which was never planned (not in worklist.json)")

    return breaks


def check_cycle(project, cycle: str, only_if_claimed: bool = False) -> tuple:
    """(exit_code, message) for one cycle's handoff chain.

    `only_if_claimed` narrows the gate to PRs that actually claim a remediation.
    It changes ONE case — an absent changelog.json — and deliberately leaves the
    dangerous neighbour alone: a changelog that IS present while its findings or
    worklist are not is reported as a break, not skipped.
    """
    cdir = audit_dir(project) / cycle
    findings, f_err = _load(cdir / "findings.json")
    worklist, w_err = _load(cdir / "worklist.json")
    changelog, c_err = _load(cdir / "changelog.json")

    claimed = (cdir / "changelog.json").is_file()

    if only_if_claimed and not claimed:
        return PASS, (f"not applicable — no changelog.json in {cycle}, so this "
                      f"pull request claims no remediation to trace.")

    if only_if_claimed and claimed and (f_err or w_err):
        # A fix attributed to a measurement that is not in the pull request. The
        # artifacts ship INSIDE the PR by design (Model A), so their absence is
        # not "we cannot see them" — it is that they were never there.
        gone = "; ".join(e for e in (f_err, w_err) if e)
        return FAIL, (f"handoff chain BROKEN: this pull request claims remediation "
                      f"(changelog.json is present) but the artifacts it must "
                      f"refine are not here — {gone}. A fix that traces to no "
                      f"measurement and no plan has no provenance at all.")

    missing = [e for e in (f_err, w_err, c_err) if e]
    if missing:
        return CANNOT_JUDGE, ("cannot judge the chain — " + "; ".join(missing)
                              + ". A partial chain is not a pass.")
    if not findings.get("findings"):
        return CANNOT_JUDGE, "cannot judge — findings.json holds zero findings"

    breaks = reconcile(findings, worklist, changelog)
    if breaks:
        return FAIL, ("handoff chain BROKEN:\n  - " + "\n  - ".join(breaks))
    n = len(findings.get("findings", []))
    m = len(worklist.get("items", []))
    k = len(changelog.get("items", []))
    return PASS, (f"chain intact: {n} findings -> {m} planned items -> {k} "
                  f"remediation entries, every arrow traces back.")


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-e2e-check",
        description="Assert the findings -> worklist -> changelog handoff chain is intact.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--cycle", help="YYYY-MM to check (default: the newest measured)")
    ap.add_argument("--only-if-claimed", action="store_true",
                    help="Treat a PR with no changelog.json as not applicable rather "
                         "than unjudgeable. How CI runs it, so an ordinary human PR "
                         "is not blocked by a chain it never claimed to have.")
    args = ap.parse_args()

    cycle = args.cycle
    if not cycle:
        available = cycles(args.project)
        if not available:
            if args.only_if_claimed:
                # Never measured, so nothing can have been claimed. `cycles()`
                # keys on findings.json, so this branch is also reached by a
                # changelog with no findings beside it — check that directly
                # rather than assuming, or the break above becomes unreachable.
                orphan = sorted(audit_dir(args.project).glob("*/changelog.json")) \
                    if audit_dir(args.project).is_dir() else []
                if not orphan:
                    print("e2e-check NOT APPLICABLE: no measured cycle and no "
                          "changelog.json — this pull request claims no remediation.")
                    return PASS
                cycle = orphan[-1].parent.name
            else:
                print(f"CANNOT JUDGE: no measured cycle under {audit_dir(args.project)}",
                      file=sys.stderr)
                return CANNOT_JUDGE
        else:
            cycle = available[-1]

    code, msg = check_cycle(args.project, cycle, only_if_claimed=args.only_if_claimed)
    label = {PASS: "PASS", FAIL: "FAIL", CANNOT_JUDGE: "CANNOT JUDGE"}[code]
    stream = sys.stdout if code == PASS else sys.stderr
    print(f"e2e-check [{cycle}] {label}: {msg}", file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main())
