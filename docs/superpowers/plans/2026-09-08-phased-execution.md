# Phased Tool Execution Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, one commit each. Steps use checkbox syntax.

**Goal:** Restructure the Measure core so selected tools run in a defined, cost-aware **order** (cheap/fast first, paid last), with a live "Phase N of 4" progress indicator — instead of a flat run of 24 tools in catalog order.

**Architecture:** `build_report` walks an ordered `PHASES` list; a pure `phase_of(tool)` maps each tool to a phase from attributes it already has (group + the `lh_` key prefix), so no 24-row edit. Phase is exposed in `/tools` and streamed as a marker event. **Category (result grouping) and phase (execution order) stay separate concepts** — categories still group the results visually; phases only order execution and drive the live progress line.

**Tech Stack:** Python stdlib backend (`server.py`), Next.js frontend (`page.tsx`), pytest.

## Global Constraints

- Phases in order: **1 Page & technical (free)** → **2 Google Lighthouse (free, external)** → **3 Search data (paid)** → **4 Source code (repo)**. Money is spent last, by construction.
- `phase_of` is pure and derived — no per-tool phase field, no mass edit.
- Selection still filters (a phase with no selected tools is skipped silently).
- Result grouping stays by **category**; phase is execution-order + live progress only.
- Two-operator repo: `git pull --ff-only` first; CHANGELOG under `[Unreleased]`; pytest output before push.

## File Structure

- `pipeline/scanner/server.py` — add `PHASES` + `phase_of(tool)`; rewrite the `build_report` tool loop to walk phases and emit a `state="phase"` marker via `on_tool`; `tool_catalog` gains `phase` + `phase_label`.
- `tests/test_scanner_phases.py` (new) — ordering, markers, phase skipping, catalog shape.
- `web/app/page.tsx` — consume `phase` events into a live "Phase N of M: label" progress line during a run.

---

### Task 1: Backend phases + phase-walk in build_report

**Files:**
- Modify: `pipeline/scanner/server.py`
- Test: `tests/test_scanner_phases.py`

**Interfaces:**
- Produces: `PHASES: list[tuple[int, str]]` = `[(1,"Page & technical"),(2,"Google Lighthouse"),(3,"Search data (paid)"),(4,"Source code")]`; `phase_of(t: Tool) -> int` (source→4, dataforseo→3, key startswith `lh_`→2, else 1); `tool_catalog()` rows gain `phase` (int) and `phase_label` (str). `build_report` walks phases in order; before a phase's first tool it calls `on_tool(f"Phase {n}/{N}: {label}", "phase", [], "", 0.0)`; within a phase, tools run in catalog order; the `needs=="repo"` skip and `selected` filter are unchanged.

- [ ] **Step 1: Write failing test** — `test_phase_order`: with `selected={"seo","site","source"}`, a repo+token supplied, and DataForSEO monkeypatched, capture `on_tool` "running" labels in order → `seo` (phase 1) comes before `site` (phase 3) before `source` (phase 4). `test_phase_markers`: the `state=="phase"` events arrive in ascending phase order and only for phases that have a selected tool. `test_catalog_has_phase`: every `tool_catalog()` row has int `phase` and str `phase_label`; a `lh_` tool is phase 2, a dataforseo tool phase 3.
- [ ] **Step 2: Run — expect fail** (`phase_of`/`PHASES` missing).
- [ ] **Step 3: Implement** — add `PHASES`, `phase_of`; rewrite the `for t in TOOLS` loop as `for pn, plabel in PHASES:` → filter `[t for t in TOOLS if phase_of(t)==pn and selected-ok and repo-ok]`, skip empty, emit phase marker, then the existing per-tool run block. Extend `tool_catalog`.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 2: Live phase progress in the frontend

**Files:**
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: ndjson events `{tool, state:"phase", ...}` where `tool` is the phase label. Track `phaseLine` state; render a progress line above the result cards while `busy`. `phase`-state events must NOT create tool cards (the existing `toolMap.set` path handles `running`/`done` only).

- [ ] **Step 1** — in the stream loop, branch `ev.state === "phase"` → `setPhaseLine(ev.tool)`; leave `toolMap` untouched for those events (guard the existing `if (ev.tool)` so phase markers don't become cards).
- [ ] **Step 2** — render `{busy && phaseLine && <div>…{phaseLine}…</div>}` above the results; clear it when the run ends.
- [ ] **Step 3** — `tsc --noEmit` clean; manual check deferred (needs servers); commit.

### Task 3: Thermo review + suite + CHANGELOG

- [ ] Thermo review of the Task 1-2 diff (every-3 rule) — watch the loop restructure for a dropped tool, phase-marker double-emit, or selection/repo-skip regressions.
- [ ] Full `pytest -q`, paste output. CHANGELOG entry. Commit.
