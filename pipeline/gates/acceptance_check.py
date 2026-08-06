#!/usr/bin/env python3
"""acceptance_check — re-measure what the run claims it fixed (v3 §4.3).

WHY THIS CLOSES THE LOOP
------------------------
This is what makes the system trustworthy: a change is done because **the
original measurement now passes**, not because a model said so. It also kills the
most common agent failure by far — a confident summary describing a fix that
never landed.

    changelog.json says work item wi-2026-08-0031 fixed health.desc_length on
    /roof-replacement-charlotte-nc/.  This gate reads that page out of the BUILD
    OUTPUT, re-runs the exact check that produced the finding, and refuses if the
    finding is still there.

Every acceptance criterion `plan.py` writes is the same shape —
`{"check": "code_absent", "code": "health.desc_length"}` — so this gate
implements one thing rather than eighteen, and it re-uses `measure.check_page`
verbatim. A second implementation of "what does a bad meta description look like"
would drift from the one that produced the finding, and then the loop proves
nothing.

Silence is not proof. Three cases refuse rather than pass:

- a claimed URL with **no page in the build output** — nothing was verified
- an item whose acceptance code **still fires**
- an item claiming a `check` this gate does not implement

Runs once, pre-merge, in Actions. v2 ran it again post-deploy to backstop
auto-merge; with a human merging, the next cycle's measurement covers that ground.

Usage:
  wf-acceptance-check --project . --out ./out [--cycle YYYY-MM]

Exit: 0 verified (or nothing claimed) · 20 a claimed fix did not land · 2 usage
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.audit.measure import check_page
from pipeline.lib.common import client_profile, load_config, resolve_build_dir

FAILED_EXIT = 20
USAGE_EXIT = 2

SUPPORTED_CHECKS = {"code_absent"}


class AcceptanceError(RuntimeError):
    """Usage failure — unreadable artifact, or no build output to verify against."""


def find_changelog(project, cycle: str | None) -> tuple:
    """(cycle, doc) for the newest cycle carrying a changelog.json, or (None, None).

    No changelog means nothing claims to fix anything, which is a real and common
    state (a docs-only PR). That is a SKIP, not a pass and not a failure.
    """
    audit = Path(project) / "docs" / "audit"
    if not audit.is_dir():
        return None, None
    names = sorted(d.name for d in audit.iterdir()
                   if d.is_dir() and (d / "changelog.json").is_file())
    if cycle and cycle not in names:
        raise AcceptanceError(f"no changelog.json in docs/audit/{cycle}"
                              + (f" (have: {', '.join(names)})" if names else ""))
    target = cycle or (names[-1] if names else None)
    if not target:
        return None, None
    path = audit / target / "changelog.json"
    try:
        return target, json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{path} is not valid JSON: {exc}")


def built_page(build_dir: Path, url_path: str):
    """The built HTML for a site path, or None. Tries `<path>/index.html` then
    `<path>.html` — the two shapes a static export produces."""
    rel = (url_path or "/").split("?")[0].split("#")[0].strip("/")
    for candidate in ((build_dir / rel / "index.html") if rel else (build_dir / "index.html"),
                      build_dir / f"{rel}.html" if rel else None):
        if candidate and candidate.is_file():
            return candidate
    return None


def verify_item(item: dict, build_dir: Path, cfg: dict, domain: str) -> tuple:
    """(passed, message) for one claimed fix."""
    acceptance = item.get("acceptance") or {}
    check = acceptance.get("check")
    if check not in SUPPORTED_CHECKS:
        return False, (f"{item.get('id')}: acceptance check {check!r} is not implemented — "
                       f"refusing rather than reporting an unverified fix as verified")

    code = acceptance.get("code") or ""
    # Only `check_page` codes can be re-measured here. A phase-6 provider finding
    # (crux.*, gsc.*, dfs.*) is measured against Google's field dataset or a paid
    # crawl, neither of which exists in a build directory — and `check_page` would
    # never emit the code, so "the code no longer fires" would be vacuously true.
    # A vacuous pass is worse than no gate at all.
    if not code.startswith("health."):
        return False, (f"{item.get('id')}: {code!r} cannot be re-measured against the build "
                       f"output — it comes from an external provider. Verify it in the next "
                       f"cycle's measurement, not here")

    url_path = item.get("url") or "/"
    page = built_page(build_dir, url_path)
    if page is None:
        return False, (f"{item.get('id')}: {url_path} has no page in the build output "
                       f"({build_dir}) — nothing was verified, so nothing is proven")

    url = f"https://{domain}{url_path if url_path.startswith('/') else '/' + url_path}"
    findings = check_page(url, page.read_text(errors="replace"), 200, cfg)
    context = (item.get("evidence") or {}).get("context") or ""
    still = [f for f in findings
             if f.code == code and (not context or f.context == context)]
    if still:
        return False, (f"{item.get('id')}: {code} STILL FIRES on {url_path} "
                       f"({still[0].detail or 'no detail'}) — the fix did not land")
    return True, f"{item.get('id')}: {code} is gone from {url_path}"


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-acceptance-check",
        description="Re-run each claimed fix's acceptance criterion against the built output.")
    ap.add_argument("--project", default=".", help="client repo root")
    ap.add_argument("--out", help="build output dir (default: resolved from the client config)")
    ap.add_argument("--cycle", help="YYYY-MM to verify (default: the newest with a changelog)")
    args = ap.parse_args()

    project = Path(args.project)
    cfg = load_config(str(project))
    profile = client_profile(cfg, str(project))

    try:
        cycle, doc = find_changelog(project, args.cycle)
    except AcceptanceError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return USAGE_EXIT

    if not doc:
        print("[SKIP] acceptance-check: no docs/audit/*/changelog.json — this PR claims "
              "to fix nothing, so there is nothing to re-measure.")
        return 0

    items = [i for i in doc.get("items", []) if i.get("status") == "fixed"]
    if not items:
        print(f"[SKIP] acceptance-check: {cycle} changelog claims 0 fixed items.")
        return 0

    build_dir = Path(args.out) if args.out else project / resolve_build_dir(profile, project).lstrip("./")
    if not build_dir.is_dir():
        print(f"[ERROR] build output {build_dir} does not exist — build before verifying. "
              f"An unverifiable claim is not a passing one.", file=sys.stderr)
        return USAGE_EXIT

    domain = cfg.get("domain") or "example.com"
    failed = []
    for item in items:
        ok, msg = verify_item(item, build_dir, cfg, domain)
        print(("[ok] " if ok else "[FAILED] ") + msg)
        if not ok:
            failed.append(msg)

    if failed:
        sys.stdout.flush()
        print(f"\n[BLOCKED] {len(failed)} of {len(items)} claimed fix(es) did not clear the "
              f"finding they claim to fix. A change is done when the original measurement "
              f"passes, not when a summary says so.", file=sys.stderr)
        return FAILED_EXIT
    print(f"\n[OK] acceptance-check: all {len(items)} claimed fix(es) re-measured clean "
          f"against {build_dir}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
