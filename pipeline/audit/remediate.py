#!/usr/bin/env python3
"""remediate.py — Claude Code fixes the worklist, one item at a time (v3 §4.7).

    wf-site-remediate --project . [--cycle YYYY-MM] [--max-items N]
                      [--max-files N] [--model sonnet] [--dry-run]

Reads `docs/audit/<YYYY-MM>/worklist.json`, hands each actionable item to Claude
Code in the client checkout, and writes `docs/audit/<YYYY-MM>/changelog.json`
mapping every changed file back to the work item that changed it.

ONE ITEM PER INVOCATION
-----------------------
The obvious design hands the whole worklist over in one prompt. Then the
file→item mapping has to be taken on the model's word, and `changelog.json` — the
artifact `acceptance_check` re-measures against — becomes a claim rather than an
observation. Running one item at a time makes the mapping a **measurement**: the
files that changed between two `git status` snapshots are the files that item
touched, whatever the model says it did. It costs one process per item and buys
the only thing that makes the loop closable.

WHAT KEEPS THIS SAFE IS NOT THIS FILE
-------------------------------------
The prompt states the tier. That is efficiency. The safety is:

  * `lib/common.tier_verdict` — the same judge `tier_check` runs on the PR diff,
    applied here to every file that actually changed. An out-of-tier edit ends
    the run at exit 9 and is never reported as fixed.
  * `claim_provenance_check` — no invented credentials (v3 §4.1)
  * `acceptance_check` — the finding must actually be gone (v3 §4.3)
  * the operator's merge

**Tier staging is per client, not per release.** A repo bootstraps at `tier: 1`
and `docs/client-config.yml` is on the deny floor, so the agent can never raise
its own authority: T2 and T3 exist in this module but are unreachable for a
client until a human raises the tier in a human PR.

CAPS
----
`--max-items` and `--max-files` are hard. Hitting one stops the run **cleanly**:
what landed stays, `changelog.json` records `stopped`, and the remaining items
keep their place in the worklist for the next run. A half-failed run must be
legible, which is the opposite of a run that silently did two thirds of a job.

This module does not commit, push, or open a PR. That path already exists with
its "never push a default branch" guard in `pipeline/dashboard/server.py`
(`GIT_ACTIONS`), and a second copy of a safety guard is a guard that drifts.

Exit: 0 nothing to do · 1 changes written · 9 REFUSED (an edit outside the tier)
      · 2 usage (no worklist, no `claude` on PATH)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from pipeline.lib.common import client_profile, load_config, tier_verdict

SCHEMA = "site-remediate-changelog/1"
REFUSED_EXIT = 9
USAGE_EXIT = 2

DEFAULT_MAX_ITEMS = 10
DEFAULT_MAX_FILES = 20
DEFAULT_TIMEOUT = 900
DEFAULT_MODEL = "sonnet"        # v3 §8: Sonnet for bulk, Opus for hard judgment

# Read-and-edit only. No Bash: a remediation run has no business running
# commands, and the narrower the tool list the smaller the blast radius of a
# prompt injection carried in the client's own page copy.
ALLOWED_TOOLS = "Read Edit Write Grep Glob"

SKILL = Path(__file__).resolve().parents[2] / "skills" / "site-remediation" / "SKILL.md"


class RemediateError(RuntimeError):
    """Usage failure — nothing to work from."""


# ── what changed, measured rather than claimed ───────────────────────────────

def _sha(path: Path):
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return None


def snapshot(project) -> dict:
    """{repo-relative path: (git status code, content sha)} for every dirty path.

    NUL-delimited so a filename with a space or a quote is read correctly; the
    quoted `--porcelain` form would need unescaping and would get it wrong on
    exactly the paths worth getting right.

    The status code is carried because it is the only thing that knows whether a
    path is NEW. A clean tracked file is absent from this snapshot, so inferring
    "absent before, present after" as a creation marks every ordinary edit as a
    create — and T1, which may not create, would refuse every fix it exists to make.
    """
    # -uall, not the default: git collapses a new untracked directory to
    # `src/content/` and never names the file inside it, so a T2 page creation
    # would be recorded — and judged — as a directory that matches no allow-list.
    r = subprocess.run(["git", "-C", str(project), "status", "--porcelain=v1",
                        "-uall", "-z"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RemediateError(r.stderr.strip() or "git status failed")
    fields = [f for f in r.stdout.split("\0") if f]
    out, i = {}, 0
    while i < len(fields):
        entry = fields[i]
        status, path = entry[:2], entry[3:]
        i += 1
        if status[0] in ("R", "C"):     # rename/copy carries the source in the next field
            i += 1
        out[path] = (status, _sha(Path(project) / path))
    return out


def touched(before: dict, after: dict) -> list:
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def op_for(before: dict, after: dict, path: str) -> str:
    """git's own verdict on the path, as a name-status letter."""
    status = (after.get(path) or ("", None))[0]
    if status == "??" or status.startswith("A"):
        return "A"
    if "D" in status:
        return "D"
    return "M"


# ── the prompt ───────────────────────────────────────────────────────────────

def allowed_summary(profile: dict) -> str:
    tier = profile.get("tier")
    lines = [f"You are operating at TIER {tier}." if tier else
             "This repo declares NO tier. You may change nothing."]
    if profile.get("text_paths"):
        lines.append("You may MODIFY existing files matching: "
                     + ", ".join(profile["text_paths"]))
    if tier and tier >= 2 and profile.get("content_location"):
        lines.append(f"You may CREATE files under: {profile['content_location']}")
        if profile.get("content_registry"):
            lines.append("You may MODIFY these registry files to wire a new page in (or it "
                         "will be an orphan and the PR will be refused): "
                         + ", ".join(profile["content_registry"]))
    if tier and tier >= 3:
        lines.append("You may modify, create and delete anything not on the deny list.")
    lines.append("You may NEVER touch: " + ", ".join(profile.get("deny") or []))
    return "\n".join(f"- {ln}" for ln in lines)


def build_prompt(item: dict, profile: dict, doctrine: str) -> str:
    return f"""{doctrine}

## This repo's authority

{allowed_summary(profile)}

Any edit outside that list is rejected by `tier_check` on the pull request and
ends the run. Do not attempt one; if the fix would require it, change nothing and
say so.

## The one work item for this invocation

```json
{json.dumps(item, indent=2, sort_keys=True)}
```

The page is `{item.get('url')}`. The finding is `{item.get('code')}`
({item.get('kind')}), measured on the live site as: {json.dumps(item.get('evidence'))}.

Find the source of that page's content inside the paths you are allowed to touch,
fix ONLY this finding, and stop. Do not fix anything else you notice — every other
finding has its own work item and its own acceptance check. Do not reformat,
reorder, or "tidy" surrounding code.

When you are done, reply with one line: either `FIXED <path>` naming the file you
changed, or `NO CHANGE <reason>` if the fix was not possible inside your authority.
"""


def read_doctrine() -> str:
    """SKILL.md without its YAML frontmatter — that block is skill metadata for a
    loader, not instructions for the writer."""
    if not SKILL.is_file():
        return ("# Site remediation\n\nDerivation only, never invent. Fix exactly the "
                "finding you were given.\n")
    text = SKILL.read_text()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    return text


# ── the agent ────────────────────────────────────────────────────────────────

def run_agent(project, prompt: str, model: str, timeout: int) -> tuple:
    """(ok, text, cost_usd). A non-zero exit or a timeout is an ERROR for this
    item, never a silent skip: the changelog records it and the item stays in the
    worklist for the next run."""
    # The prompt goes on STDIN, not argv. It begins with a markdown document and
    # the CLI's option parser reads a leading `---` as a malformed flag — caught
    # by the first live run, not by any test that stubbed this function out.
    argv = ["claude", "-p", "--model", model,
            "--permission-mode", "acceptEdits",
            "--allowedTools", ALLOWED_TOOLS,
            "--output-format", "json"]
    # The two prose references live in the ENGINE repo, not the client checkout,
    # so the agent cannot read them without being told they exist.
    if SKILL.is_file():
        argv += ["--add-dir", str(SKILL.parent)]
    try:
        r = subprocess.run(argv, cwd=str(project), input=prompt, capture_output=True,
                           text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s", 0.0
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[:400], 0.0
    try:
        doc = json.loads(r.stdout)
    except json.JSONDecodeError:
        return True, r.stdout.strip()[:400], 0.0
    return True, str(doc.get("result", ""))[:400], float(doc.get("total_cost_usd") or 0.0)


# ── the run ──────────────────────────────────────────────────────────────────

def load_worklist(project, cycle: str | None) -> tuple:
    audit = Path(project) / "docs" / "audit"
    names = sorted(d.name for d in audit.iterdir()
                   if d.is_dir() and (d / "worklist.json").is_file()) if audit.is_dir() else []
    if cycle and cycle not in names:
        raise RemediateError(f"no worklist.json in docs/audit/{cycle} — run wf-site-plan first"
                             + (f" (have: {', '.join(names)})" if names else ""))
    target = cycle or (names[-1] if names else None)
    if not target:
        raise RemediateError(f"no worklist.json under {audit} — run wf-site-plan first")
    try:
        return target, json.loads((audit / target / "worklist.json").read_text())
    except json.JSONDecodeError as exc:
        raise RemediateError(f"{audit / target}/worklist.json is not valid JSON: {exc}")


def selectable(worklist: dict, profile: dict) -> list:
    """Items this repo's tier can actually act on, worst lane first.

    REGRESSION before NEW before PERSISTING: a fix that did not hold is the most
    informative thing in the list, and with a cap on items it should not be the
    part that gets cut.
    """
    order = {"REGRESSION": 0, "NEW": 1, "PERSISTING": 2}
    items = [i for i in worklist.get("items", []) if not i.get("tier_blocked")]
    return sorted(items, key=lambda i: (order.get(i.get("lane"), 3), i.get("id", "")))


def remediate(project, cycle: str | None, max_items: int, max_files: int,
              model: str, timeout: int, dry_run: bool) -> tuple:
    """(changelog, exit_code)."""
    profile = client_profile(load_config(str(project)), str(project))
    target, worklist = load_worklist(project, cycle)
    queue = selectable(worklist, profile)

    doctrine = read_doctrine()
    results, files_map = [], {}
    stopped, refused, cost = None, False, 0.0
    seen_files: set = set()

    for n, item in enumerate(queue):
        if n >= max_items:
            stopped = f"max-items ({max_items}) reached with {len(queue) - n} item(s) left"
            break
        if len(seen_files) >= max_files:
            stopped = f"max-files ({max_files}) reached with {len(queue) - n} item(s) left"
            break

        prompt = build_prompt(item, profile, doctrine)
        if dry_run:
            print(f"\n===== {item['id']} — {item.get('code')} on {item.get('url')} =====")
            print(prompt)
            results.append(dict(_base(item), status="dry-run", files=[]))
            continue

        before = snapshot(project)
        ok, note, item_cost = run_agent(project, prompt, model, timeout)
        cost += item_cost
        after = snapshot(project)
        changed = touched(before, after)

        bad = [(p, tier_verdict(profile, p, op_for(before, after, p))[1])
               for p in changed if not tier_verdict(profile, p, op_for(before, after, p))[0]]
        if bad:
            refused = True
            status, note = "refused", "; ".join(reason for _, reason in bad)
        elif not ok:
            status = "error"
        elif not changed:
            status = "no_change"
        else:
            status = "fixed"

        for p in changed:
            files_map.setdefault(p, []).append(item["id"])
            seen_files.add(p)
        results.append(dict(_base(item), status=status, files=changed, note=note))
        print(f"[{status.upper()}] {item['id']} {item.get('code')} on {item.get('url')}"
              + (f" -> {', '.join(changed)}" if changed else "")
              + (f"  ({note})" if note and status != "fixed" else ""))
        if refused:
            stopped = "an edit outside the declared tier — the run stopped rather than " \
                      "keep writing"
            break

    changelog = {
        "schema": SCHEMA,
        "generated": date.today().isoformat(),
        "cycle": target,
        "domain": worklist.get("domain"),
        "tier": profile.get("tier"),
        "model": model,
        "cost_usd": round(cost, 4),
        "queued": len(queue),
        "attempted": len(results),
        "stopped": stopped,
        "items": results,
        "files": {k: sorted(set(v)) for k, v in sorted(files_map.items())},
    }
    if refused:
        return changelog, REFUSED_EXIT
    return changelog, (1 if any(r["status"] == "fixed" for r in results) else 0)


def _base(item: dict) -> dict:
    return {k: item.get(k) for k in ("id", "url", "code", "kind", "lane",
                                     "evidence", "acceptance")}


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-site-remediate",
        description="Hand each actionable work item to Claude Code and record what changed.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--cycle", help="YYYY-MM to remediate (default: the newest planned)")
    ap.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="sonnet for bulk copy fixes, opus for ambiguous scope (v3 §8)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per item")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the prompt for each item and write nothing")
    args = ap.parse_args()

    if not args.dry_run and shutil.which("claude") is None:
        print("[ERROR] `claude` is not on PATH — the remediator has no writer. Install "
              "Claude Code, or use --dry-run to inspect the prompts.", file=sys.stderr)
        return USAGE_EXIT

    try:
        changelog, code = remediate(args.project, args.cycle, args.max_items,
                                    args.max_files, args.model, args.timeout, args.dry_run)
    except RemediateError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return USAGE_EXIT

    if args.dry_run:
        print(f"\n[DRY RUN] {changelog['attempted']} item(s) would run. Nothing written.")
        return 0

    out = Path(args.project) / "docs" / "audit" / changelog["cycle"] / "changelog.json"
    out.write_text(json.dumps(changelog, indent=2, sort_keys=True) + "\n")

    fixed = sum(1 for r in changelog["items"] if r["status"] == "fixed")
    print(f"\n[{'REFUSED' if code == REFUSED_EXIT else 'OK'}] {fixed} fixed, "
          f"{changelog['attempted']} attempted of {changelog['queued']} queued, "
          f"{len(changelog['files'])} file(s) changed, ${changelog['cost_usd']} -> {out}")
    if changelog["stopped"]:
        print(f"[STOPPED] {changelog['stopped']}", file=sys.stderr)
    if code == REFUSED_EXIT:
        print("[REFUSED] an edit landed outside the declared tier. Nothing was committed; "
              "inspect `git status`, revert what you did not want, and raise the tier in a "
              "HUMAN pull request if the authority is genuinely needed.", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
