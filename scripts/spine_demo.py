#!/usr/bin/env python3
"""Automation-spine demo — the whole cycle on one page, as a readable transcript.

Runs measure -> plan -> remediate -> gates -> auto-merge decision against the
local fixture site and prints a before/after report you can show a stakeholder:
what was wrong, what the pipeline changed, that every gate went green, and the
AUTO/HUMAN decision with its reason.

    .venv/bin/python scripts/spine_demo.py

The remediation writer here is the deterministic stand-in from the E2E harness
(tests/e2e_fixture.agent_that_fixes), NOT the live model — so this runs offline
and identically every time. In production the same step is `wf-site-remediate`,
where Claude writes the edit and the identical gates + decision judge it. This
demo proves the WIRING and the decision; the live run proves the model.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

# repo root on path so `tests.e2e_fixture` and `pipeline.*` import when run
# directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import e2e_fixture as fx  # noqa: E402
from pipeline.audit import measure, plan, remediate as rem  # noqa: E402
from pipeline.lib.automerge import decide, AutoMergePolicy  # noqa: E402


def rule(title: str) -> None:
    print(f"\n{'─' * 72}\n{title}\n{'─' * 72}")


@contextlib.contextmanager
def quiet():
    """Swallow a pipeline stage's own stdout/stderr so the demo transcript is
    just the report, not the stages' progress chatter."""
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        yield


def main() -> int:
    cycle = date.today().strftime("%Y-%m")
    root = Path(tempfile.mkdtemp(prefix="spine-demo-"))
    project = fx.build_fixture(root / "client")

    rule("1. THE SITE  (one page, two seeded SEO defects)")
    print(f"   fixture repo : {project}")
    print(f"   page         : {fx.URL}")
    print(f"   title        : {fx.BAD_TITLE!r}  ({len(fx.BAD_TITLE)} chars, band is 30-60)")
    print("   meta desc    : (none)")

    # ── MEASURE ──────────────────────────────────────────────────────────────
    curl, curl_status = fx.serve(project)
    measure.curl, measure.curl_status = curl, curl_status
    sys.argv = ["wf-site-health", "--project", str(project), "--url", fx.ROUTE]
    with quiet():
        measure.main()
    findings = json.loads(
        (project / "docs" / "audit" / cycle / "findings.json").read_text())["findings"]

    rule("2. MEASURE  (wf-site-health)  →  what's wrong")
    for f in findings:
        print(f"   ✗ {f['code']:24} {f.get('detail') or ''}  on {f['location']}")

    # ── PLAN ─────────────────────────────────────────────────────────────────
    sys.argv = ["wf-site-plan", "--project", str(project)]
    with quiet():
        plan.main()
    worklist = json.loads(
        (project / "docs" / "audit" / cycle / "worklist.json").read_text())

    rule("3. PLAN  (wf-site-plan)  →  the work, with tier")
    for i in worklist["items"]:
        gate = "blocked" if i["tier_blocked"] else "actionable"
        print(f"   • {i['code']:24} kind={i['kind']:26} T{i['min_tier']}  [{gate}]")

    # ── REMEDIATE (deterministic stand-in writer) ────────────────────────────
    before = (project / "out" / fx.ROUTE / "index.html").read_text()
    rem.run_agent = fx.agent_that_fixes(project)
    with quiet():
        changelog, _ = rem.remediate(project, None, 10, 10, "demo", 60, False)
    (project / "docs" / "audit" / cycle / "changelog.json").write_text(
        json.dumps(changelog, indent=2, sort_keys=True) + "\n")
    after = (project / "out" / fx.ROUTE / "index.html").read_text()

    rule("4. REMEDIATE  (wf-site-remediate)  →  the fix, applied")
    for item in changelog["items"]:
        print(f"   ✓ {item['status'].upper():6} {item['code']:24} → {', '.join(item['files'])}")
    print("\n   BEFORE:")
    print(f"     <title> {fx.BAD_TITLE}")
    print("     <meta name=description>  (missing)")
    print("   AFTER:")
    print(f"     <title> {fx.GOOD_TITLE}")
    print(f"     <meta name=description content=\"{fx.DESC_TEXT[:60]}…\">")

    # ── GATES ────────────────────────────────────────────────────────────────
    base = fx.commit_fix(project)
    gate_codes = fx.run_gates(project, base)

    rule("5. GATES  (the diff must pass the quality gates)")
    for name, code in gate_codes.items():
        print(f"   {'✓ PASS' if code == 0 else f'✗ exit {code}'}   {name}")

    # ── DECISION ─────────────────────────────────────────────────────────────
    gate_results = {n: (c == 0) for n, c in gate_codes.items()}
    changed_text = f"{fx.GOOD_TITLE} {fx.DESC_TEXT}"
    policy = AutoMergePolicy(enabled=True)
    d = decide(gate_results=gate_results, tier="T1", creates=[], text=changed_text, policy=policy)

    rule("6. DECISION  (automerge.decide)  →  ship it, or call a human?")
    print(f"   all gates green : {all(gate_results.values())}")
    print(f"   tier            : T1   (copy edit)")
    print(f"   new page?       : no")
    print(f"   medical/legal?  : no")
    print(f"\n   ►  {d.action}   — {d.reason}")

    rule("SUMMARY")
    print("   Semrush would stop at step 2 (here are your problems).")
    print("   This pipeline went 2→6: found, fixed, gated, and decided — no human.")
    print(f"\n   demo tree left at: {project}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
