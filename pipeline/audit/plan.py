#!/usr/bin/env python3
"""plan.py — findings + history -> four lanes, a typed worklist, and report.md.

WHY THIS EXISTS (v3 §4.6)
-------------------------
Without a ratchet, run #2 reports the same 400 legacy issues as run #1 and people
stop reading it. The monthly folders under `docs/audit/` ARE the time series, so
the ratchet is a set comparison over fingerprints, not a second baseline file:

    PERSISTING   in the previous cycle and still here
    NEW          never seen in any earlier cycle
    REGRESSION   seen before, gone, and BACK   <- the lane that earns the module
    RESOLVED     in the previous cycle, gone now

Fingerprints come from `lib/baseline.py` verbatim (they exclude `detail`, so a
finding cannot become "new" merely by getting worse). There is no second ratchet.

THE TIER FILTER
---------------
The report lists EVERY finding. The worklist carries only what the tier permits.
A "thin content, needs a new page" finding at T1 stays visible and counted as
NOT ACTIONABLE AT THIS TIER, never silently dropped, which is also how the report
tells you a client should move up a tier.

A code with no entry in ACTIONS has no machine-checkable acceptance, so it does
not belong in the worklist at all — it goes to the report under NEEDS A HUMAN.
`acceptance` is load-bearing: phase 4's `acceptance_check` re-runs it against the
built output and refuses if the finding it claims to fix is still there.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from pipeline.lib.common import client_profile, load_config

SCHEMA = "site-plan-worklist/1"
LANES = ("REGRESSION", "NEW", "PERSISTING", "RESOLVED")
_CYCLE_RE = re.compile(r"^\d{4}-\d{2}$")

# ── what the agent may be asked to fix, and at which tier ────────────────────
# code -> (kind, min_tier, expect)
#
# `min_tier` is the lowest tier whose path allow-list can plausibly reach the
# fix: T1 edits existing copy (titles, metas, alt text, phrasing), T2 writes new
# content, T3 touches templates, routing and layout. It is a PLANNING hint, not
# the enforcement — `tier_check` (phase 4) judges the actual diff.
#
# `expect` is carried for the human reading the item; the acceptance CHECK is
# always the same one thing, so phase 4 implements one check and not eighteen:
# re-measure the URL and refuse if the code still fires.
ACTIONS = {
    # T1 — copy the agent may edit in place
    "health.title_missing":     ("title_missing",                 1, {"min": 30, "max": 60}),
    "health.title_length":      ("title_out_of_band",             1, {"min": 30, "max": 60}),
    "health.desc_missing":      ("meta_description_missing",      1, {"min": 120, "max": 160}),
    "health.desc_length":       ("meta_description_out_of_band",  1, {"min": 120, "max": 160}),
    "health.img_alt_missing":   ("image_alt_missing",             1, None),
    "health.forbidden_phrase":  ("forbidden_phrase_live",         1, None),
    "health.phone_missing":     ("nap_phone_missing",             1, None),
    # `thin_content` is T1, not T2: measure.py only measures URLs that are LIVE,
    # so a page cannot be measured as thin unless it already exists. The fix is
    # always "expand the copy that is there", never "create a page" — and on a
    # data-driven repo (lee: `LEARN_GUIDES` in one .ts file, dynamic [slug]
    # routes) there is no file to create at all. It sat at 2 until 2026-08-08 and
    # blocked 15 items on lee whose target files were all already in text_paths.
    # tier_check still judges the real diff, so a client whose copy is NOT in
    # text_paths still gets refused — at the diff, which is where it belongs.
    "health.thin_content":      ("thin_content",                  1, {"min_words": 500}),
    # T2 — needs new content written
    "health.schema_faq_missing": ("schema_faq_missing",           2, None),
    # T3 — template, layout, routing, analytics
    "health.status_not_200":    ("url_not_200",                   3, {"status": 200}),
    "health.h1_count":          ("h1_count_wrong",                3, {"count": 1}),
    "health.canonical_mismatch": ("canonical_mismatch",           3, None),
    "health.noindex_present":   ("noindex_present",               3, None),
    "health.og_image_missing":  ("og_image_missing",              3, None),
    "health.schema_business_missing": ("schema_business_missing", 3, None),
    "health.schema_breadcrumb_missing": ("schema_breadcrumb_missing", 3, None),
    "health.tel_link_missing":  ("tel_link_missing",              3, None),
    "health.ga4_missing":       ("ga4_tag_missing",               3, None),
}


class PlanError(RuntimeError):
    """Usage failure — no findings to plan against, or an unreadable artifact."""


# ── the cycle folders are the time series ────────────────────────────────────

def audit_dir(project) -> Path:
    return Path(project) / "docs" / "audit"


def cycles(project) -> list:
    """Every `docs/audit/<YYYY-MM>/` holding a findings.json, oldest first."""
    root = audit_dir(project)
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir()
                  if d.is_dir() and _CYCLE_RE.match(d.name) and (d / "findings.json").is_file())


def read_findings(project, cycle: str) -> dict:
    path = audit_dir(project) / cycle / "findings.json"
    try:
        doc = json.loads(path.read_text())
    except FileNotFoundError:
        raise PlanError(f"no findings.json in {path.parent} — run wf-site-health first")
    except json.JSONDecodeError as exc:
        raise PlanError(f"{path} is not valid JSON: {exc}")
    if not isinstance(doc, dict) or not isinstance(doc.get("findings"), list):
        raise PlanError(f"{path} is not a site-health findings document")
    return doc


def _fps(doc: dict) -> dict:
    return {f["fingerprint"]: f for f in doc.get("findings", []) if f.get("fingerprint")}


def assign_lanes(current: dict, prior: dict, ever_before: set) -> dict:
    """fingerprint -> lane, for the CURRENT findings only.

    REGRESSION is the whole point: absent from the previous cycle but seen in an
    earlier one means the fix did not hold. Collapsing it into NEW would hide the
    single most useful signal the history carries.
    """
    lanes = {}
    for fp in current:
        if fp in prior:
            lanes[fp] = "PERSISTING"
        elif fp in ever_before:
            lanes[fp] = "REGRESSION"
        else:
            lanes[fp] = "NEW"
    return lanes


# ── work items ───────────────────────────────────────────────────────────────

def work_item(idx: int, cycle: str, finding: dict, lane: str, tier) -> dict | None:
    """One typed work item, or None when the code has no acceptance mapping.

    An item with no machine-checkable acceptance does not belong in the worklist;
    the caller reports it under NEEDS A HUMAN instead.
    """
    action = ACTIONS.get(finding.get("code"))
    if not action:
        return None
    kind, min_tier, expect = action
    acceptance = {"check": "code_absent", "code": finding["code"]}
    if expect:
        acceptance["expect"] = expect
    return {
        "id": f"wi-{cycle}-{idx:04d}",
        "finding_fp": finding["fingerprint"],
        "url": finding.get("location", ""),
        "kind": kind,
        "code": finding["code"],
        "lane": lane,
        "min_tier": min_tier,
        # No declared tier means no authority, which is the safe default: every
        # item is visible and none is actionable. See common.validate_profile.
        "tier_blocked": tier is None or tier < min_tier,
        "evidence": {"context": finding.get("context", ""), "detail": finding.get("detail", "")},
        "acceptance": acceptance,
    }


def build_worklist(doc: dict, lanes: dict, tier) -> tuple:
    """Returns (items, unclassified) — unclassified findings have no ACTIONS entry."""
    items, unclassified, n = [], [], 0
    for f in doc.get("findings", []):
        fp = f.get("fingerprint")
        if not fp:
            continue
        n += 1
        item = work_item(n, doc.get("cycle") or "", f, lanes.get(fp, "NEW"), tier)
        (items.append(item) if item else unclassified.append(f))
    return items, unclassified


# ── report.md ────────────────────────────────────────────────────────────────

def _group(rows: list) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(r.get("code", "?"), []).append(r)
    return dict(sorted(out.items()))


def _lines(rows: list) -> str:
    body = []
    for code, group in _group(rows).items():
        body.append(f"\n**`{code}`** ({len(group)})\n")
        for r in sorted(group, key=lambda x: x.get("location") or x.get("url") or ""):
            where = r.get("location") or r.get("url") or ""
            detail = r.get("detail") or (r.get("evidence") or {}).get("detail") or ""
            ctx = r.get("context") or (r.get("evidence") or {}).get("context") or ""
            extra = " ".join(x for x in (f"[{ctx}]" if ctx else "", detail) if x)
            body.append(f"- `{where}`{'  ' + extra if extra else ''}")
    return "\n".join(body) + "\n"


def render_report(doc: dict, cycle: str, prior_cycle, lanes: dict, resolved: list,
                  items: list, unclassified: list, tier) -> str:
    by_lane = {lane: [] for lane in LANES}
    for f in doc.get("findings", []):
        lane = lanes.get(f.get("fingerprint"))
        if lane:
            by_lane[lane].append(f)
    by_lane["RESOLVED"] = resolved

    actionable = [i for i in items if not i["tier_blocked"]]
    blocked = [i for i in items if i["tier_blocked"]]
    tier_label = f"T{tier}" if tier else "none declared"

    out = [f"# Site Health Report: {cycle}", ""]
    out.append(f"- Domain: `{doc.get('domain', '?')}`")
    out.append(f"- Measured: {doc.get('generated', '?')} "
               f"({doc.get('urls_checked', '?')} URLs checked, "
               f"{doc.get('urls_unreachable', 0)} unreachable)")
    out.append(f"- Compared Against: {prior_cycle or 'nothing — this is the first cycle'}")
    out.append(f"- Tier: {tier_label}")
    out.append("")
    out.append("## Summary")
    out.append("")
    out.append("| Lane | Count |")
    out.append("|---|---|")
    for lane in LANES:
        out.append(f"| {lane} | {len(by_lane[lane])} |")
    out.append("")
    out.append(f"{len(doc.get('findings', []))} current findings. "
               f"{len(actionable)} in the worklist, {len(blocked)} not actionable at "
               f"{tier_label}, {len(unclassified)} needing a human.")
    out.append("")

    for lane in LANES:
        rows = by_lane[lane]
        if not rows:
            continue
        heading = lane.title()
        note = {"REGRESSION": "Seen before, fixed, and back. The fix did not hold.",
                "NEW": "Not present in any earlier cycle.",
                "PERSISTING": "Carried over from the previous cycle.",
                "RESOLVED": "Present last cycle, gone now. No action needed."}[lane]
        out.append(f"## {heading} ({len(rows)})")
        out.append("")
        out.append(note)
        out.append(_lines(rows))

    if blocked:
        out.append(f"## Not Actionable at {tier_label.title() if tier else 'This Tier'} "
                   f"({len(blocked)})")
        out.append("")
        out.append("Visible and counted, never silently dropped. Each line names the tier "
                   "that would unlock it, which is how this report tells you a client "
                   "should move up.")
        out.append("")
        for code, group in _group(blocked).items():
            out.append(f"- `{code}` ({len(group)}) needs T{group[0]['min_tier']}")
        out.append("")

    if unclassified:
        out.append(f"## Needs a Human ({len(unclassified)})")
        out.append("")
        out.append("No machine-checkable acceptance criterion exists for these codes, so "
                   "they are not in the worklist. Read them yourself.")
        out.append(_lines(unclassified))

    return "\n".join(out).rstrip() + "\n"


# ── the CLI ──────────────────────────────────────────────────────────────────

def plan(project, cycle: str | None = None) -> tuple:
    """Returns (worklist_doc, report_text, findings_doc, lanes)."""
    available = cycles(project)
    if not available:
        raise PlanError(f"no cycle with a findings.json under {audit_dir(project)} — "
                        f"run wf-site-health first")
    cycle = cycle or available[-1]
    if cycle not in available:
        raise PlanError(f"cycle {cycle} has no findings.json (have: {', '.join(available)})")

    earlier = [c for c in available if c < cycle]
    prior_cycle = earlier[-1] if earlier else None

    doc = read_findings(project, cycle)
    doc["cycle"] = cycle
    current = _fps(doc)
    prior = _fps(read_findings(project, prior_cycle)) if prior_cycle else {}
    ever_before: set = set()
    for c in earlier:
        ever_before |= set(_fps(read_findings(project, c)))

    lanes = assign_lanes(current, prior, ever_before)
    resolved = [f for fp, f in prior.items() if fp not in current]

    profile = client_profile(load_config(str(project)), str(project))
    tier = profile.get("tier")

    items, unclassified = build_worklist(doc, lanes, tier)
    counts = {lane: sum(1 for l in lanes.values() if l == lane) for lane in LANES[:3]}
    counts["RESOLVED"] = len(resolved)
    counts["actionable"] = sum(1 for i in items if not i["tier_blocked"])
    counts["tier_blocked"] = sum(1 for i in items if i["tier_blocked"])
    counts["unclassified"] = len(unclassified)

    worklist = {
        "schema": SCHEMA,
        "generated": date.today().isoformat(),
        "cycle": cycle,
        "prior_cycle": prior_cycle,
        "domain": doc.get("domain"),
        "tier": tier,
        "counts": counts,
        "items": items,
    }
    report = render_report(doc, cycle, prior_cycle, lanes,
                           sort_findings_json(resolved), items, unclassified, tier)
    return worklist, report, doc, lanes


def sort_findings_json(rows: list) -> list:
    """Deterministic order for raw finding dicts (they are not Finding objects)."""
    return sorted(rows, key=lambda f: (f.get("location", ""), f.get("code", ""),
                                       f.get("context", ""), f.get("ordinal", 0)))


def write_artifacts(project, worklist: dict, report: str, doc: dict, lanes: dict) -> Path:
    out_dir = audit_dir(project) / worklist["cycle"]
    (out_dir / "worklist.json").write_text(json.dumps(worklist, indent=2, sort_keys=True) + "\n")
    (out_dir / "report.md").write_text(report)
    # Stamp the lane back onto each current finding: the fleet view reads lanes
    # off findings.json, and re-running the planner over an unchanged cycle must
    # reproduce the same bytes rather than a noise diff.
    for f in doc.get("findings", []):
        if f.get("fingerprint") in lanes:
            f["lane"] = lanes[f["fingerprint"]]
    doc.pop("cycle", None)
    (out_dir / "findings.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-site-plan",
        description="Partition findings into four lanes and write worklist.json + report.md.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--cycle", help="YYYY-MM to plan (default: the newest cycle measured)")
    args = ap.parse_args()

    try:
        worklist, report, doc, lanes = plan(args.project, args.cycle)
    except PlanError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    out_dir = write_artifacts(args.project, worklist, report, doc, lanes)
    c = worklist["counts"]
    if worklist["tier"] is None:
        print("[WARN] no tier declared in docs/client-config.yml — every work item is "
              "reported NOT ACTIONABLE. Fix with: wf-bootstrap-config <dir> <domain> --add-tier",
              file=sys.stderr)
    if c["REGRESSION"]:
        print(f"[REGRESSION] {c['REGRESSION']} finding(s) were fixed before and are back",
              file=sys.stderr)
    print(f"[OK] {c['NEW']} new, {c['PERSISTING']} persisting, {c['REGRESSION']} regression, "
          f"{c['RESOLVED']} resolved -> {out_dir}")
    print(f"     worklist: {c['actionable']} actionable, {c['tier_blocked']} above tier, "
          f"{c['unclassified']} needing a human")
    return 1 if doc.get("findings") else 0


if __name__ == "__main__":
    sys.exit(main())
