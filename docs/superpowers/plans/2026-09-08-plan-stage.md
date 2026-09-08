# Plan Stage Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, one commit each. Steps use checkbox syntax.

**Goal:** Turn a client's stored scan `findings` into a **prioritized, ratcheted worklist** — classify each finding vs the previous scan (NEW / PERSISTING / RESOLVED / REGRESSION), order by fix-priority, and show it as a Plan screen. This is what makes Measure's output actionable and lets us judge whether the findings are any good.

**Architecture:** Core classification is a **pure Python function** `build_plan(current, previous)` (findings in, worklist out) — tested offline, no DB. Exposed via a `POST /plan` endpoint. The frontend loads the client's latest two scans' findings from Supabase, calls `/plan`, and renders the worklist. Keeps the logic in tested Python, consistent with the rest of the scanner.

**Tech Stack:** Python stdlib backend, Next.js frontend, Supabase (existing `scans`/`findings` tables), pytest.

## Global Constraints

- Findings are identified by their stable `code` (e.g. `dfs.op.no_title`, `src.metadatabase`) — same code across scans = same issue. Classification is set-diff on codes.
- Four statuses: **NEW** (in current, not previous) · **PERSISTING** (in both, same severity) · **RESOLVED** (in previous, not current) · **REGRESSION** (in both but severity got worse, e.g. warn→error).
- Worklist excludes `ok`/`info` (not action items). Order: NEW-error + REGRESSION → PERSISTING-error → NEW-warn → PERSISTING-warn.
- No client data needed to build/test — pure logic over two findings lists; the frontend reuses the scans we already store.
- Two-operator repo: `git pull --ff-only`; CHANGELOG; pytest output before push.

## File Structure

- `pipeline/scanner/plan.py` (new) — `build_plan`, `classify`, priority ordering. Pure.
- `pipeline/scanner/server.py` — add `POST /plan`.
- `tests/test_scanner_plan.py` (new) — classification + ordering.
- `web/lib/db.ts` — `lastTwoScansFindings(clientId)` helper (read `scans` newest 2 + their `findings`).
- `web/app/page.tsx` (or a new Plan view) — Plan screen: worklist grouped by status, ordered by priority, each with the fix; RESOLVED shown as wins.

---

### Task 1: Core classification (pure)

**Files:**
- Create: `pipeline/scanner/plan.py`
- Test: `tests/test_scanner_plan.py`

**Interfaces:**
- Produces: `SEV_RANK = {"error": 2, "warn": 1, "info": 0, "ok": 0}`; `classify(cur: dict, prev: dict) -> str` (one finding's status from its current + previous row, prev may be None); `build_plan(current: list[dict], previous: list[dict]) -> dict` returning `{"worklist": [...], "resolved": [...], "counts": {...}}`. Each worklist item = the finding dict plus `status` and `priority` (int, 1 = do first). `current`/`previous` are lists of finding rows with at least `code`, `severity`, `what`, `fix`, `tool`.

- [ ] **Step 1: Write failing test** — `test_classify_statuses`: NEW (code only in current), PERSISTING (same code+sev both), RESOLVED (only in previous), REGRESSION (warn in previous → error in current). `test_worklist_order`: a NEW error sorts before a PERSISTING error before a NEW warn; `ok`/`info` excluded; RESOLVED items land in `resolved`, not `worklist`. `test_empty_previous_all_new`: `build_plan(cur, [])` → every actionable finding is NEW.
- [ ] **Step 2: Run — expect fail** (module missing).
- [ ] **Step 3: Implement** — index prev by code; `classify` compares severities via `SEV_RANK`; `build_plan` walks current for NEW/PERSISTING/REGRESSION, walks previous for RESOLVED, assigns `priority` by (status, severity), sorts worklist, tallies counts.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 2: `/plan` endpoint

**Files:**
- Modify: `pipeline/scanner/server.py`
- Test: `tests/test_scanner_plan.py`

**Interfaces:**
- `POST /plan` body `{"current": [...], "previous": [...]}` → `build_plan` result as JSON. Absent/invalid lists default to `[]`.

- [ ] **Step 1: Write failing test** — `test_plan_endpoint_shape`: call the request-handling path (or a small `handle_plan(req)` helper) with canned findings → returns dict with `worklist`/`resolved`/`counts`.
- [ ] **Step 2: Run — expect fail.**
- [ ] **Step 3: Implement** — add a `handle_plan(req)` pure helper + wire `do_POST` `/plan` to it (mirrors the `/tools` GET pattern).
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 3: Frontend Plan screen

**Files:**
- Modify: `web/lib/db.ts`, `web/app/page.tsx`, add `web/app/api/plan/route.ts`

**Interfaces:**
- `lastTwoScansFindings(clientId)` → `{current: Row[], previous: Row[]}` from the two newest `scans` and their `findings`.
- `/api/plan` proxy → Python `/plan`.

- [ ] **Step 1** — `web/app/api/plan/route.ts` proxy (POST → Python `:8765/plan`).
- [ ] **Step 2** — `lastTwoScansFindings` in `db.ts` (query newest 2 scans for the client, then their findings).
- [ ] **Step 3** — a **Plan** button/view in the Measure screen: loads last-two findings, POSTs to `/api/plan`, renders the worklist grouped **NEW / REGRESSION / PERSISTING** (ordered by priority, each with `what` + `fix` + tool badge) and a **Resolved (wins)** section.
- [ ] **Step 4** — `tsc --noEmit` clean; commit.

### Task 4: Thermo review + suite + CHANGELOG

- [ ] Thermo review of Tasks 1-3 (every-3 rule) — watch the classification edge cases (no previous scan, severity ties, code collisions).
- [ ] Full `pytest -q`, paste output. CHANGELOG. Commit.
