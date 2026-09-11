# Plan — Remediate dry-run bridge (web MVP → wf-site-remediate)

**Date:** 2026-09-09
**Goal:** Prove the web Remediate worklist can drive the real Claude Code fixer
(`wf-site-remediate`, on the Claude subscription) end-to-end **without editing any
file** — via `--dry-run`, which streams the exact per-item fix prompts.

## The two-rails reality (why a bridge is needed)

- Web Plan worklist item: `{code, what, why, fix, severity, priority, status, pages?}`.
- Pipeline worklist item (`plan.work_item`): `{id, finding_fp, url, kind, code,
  min_tier, tier_blocked, evidence, acceptance}`.
- `wf-site-remediate` only acts on codes in `plan.ACTIONS` (machine-checkable
  acceptance). `ACTIONS` keys are `health.*` — the **same** codes the web scanner
  emits for on-page findings. So the on-page subset bridges faithfully; other web
  codes (`src.* / lh.* / crux.* / aeo.*`) have no `ACTIONS` entry and are honestly
  reported as "not machine-fixable on this rail", not forced through.

## Approach — reuse, don't duplicate

`bridge_worklist(web_items, scan_url, tier, cycle)`:
- For each web item, synthesize the `finding` dict `plan.work_item` expects
  (`code`, `fingerprint`, `location`, `context`, `detail`) and call
  `plan.work_item()` — the pipeline's OWN item builder → no schema drift.
- `location` = item `pages[0]` if present else `scan_url`.
- `fingerprint` = stable `f"{code}|{location}"` so resume keys line up.
- Items whose code ∉ `ACTIONS` (work_item returns None) → collected as
  `unbridged` and surfaced separately.
- Returns `{worklist: {schema, cycle, items}, unbridged: [...]}`.

## Steps

1. **`pipeline/scanner/remediate_bridge.py`** + `tests/test_scanner_remediate_bridge.py`
   (pure, offline): bridge maps health.* → pipeline items, drops/reports the rest,
   stable fingerprints, tier gating passes through `work_item`. ← THIS COMMIT
2. **Backend `/remediate/dryrun`**: body `{repo, url, worklist, tier?, cycle?}`.
   Validate `repo` is a local dir. Write bridged worklist to
   `docs/audit/<cycle>/worklist.json`. Run `wf-site-remediate --project <repo>
   --dry-run` (NO claude, NO edits), capture stdout, return `{items, prompts, log,
   unbridged}`. Reject remote-only repos (name the gap).
3. **Web `/api/remediate/dryrun` + UI**: "Preview fixes (dry-run)" in the auto
   lane → shows each item's fix prompt + the unbridged list. Real edit-run later,
   behind an explicit confirm (drop `--dry-run`).

## Guards

- Dry-run edits nothing (verified: `remediate()` `dry_run` branch prints prompt,
  never calls `run_agent`).
- No `claude` needed for dry-run.
- No live/paid anything — safe under the cost/hold rule.
