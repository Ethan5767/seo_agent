# Measure Tool Selection Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, one commit each. Steps use checkbox syntax.

**Goal:** Replace the two blunt `crawl`/`deep` checkboxes with a per-tool checklist so the operator selects exactly which Measure tools run, sees each tool's cost, and a running total.

**Architecture:** Backend `TOOLS` becomes a catalog carrying display metadata (label, group, cost). A `GET /tools` endpoint exposes it as the single source of truth. `build_report(selected=...)` runs only selected tools. Frontend fetches the catalog, renders a grouped checklist (all ticked by default), sends the selected keys.

**Tech Stack:** Python stdlib `http.server` backend (`pipeline/scanner/server.py`), Next.js frontend (`web/app/page.tsx`), pytest.

## Global Constraints

- DataForSEO-first: tools already built; this only changes *selection*, not check logic.
- Never fake data: an unselected tool is simply absent; a selected tool with no credential returns its honest "skipped" status (unchanged).
- Default selection = **all tools ticked**.
- Catalog source of truth = backend `/tools` (frontend never hardcodes the list).
- Two-operator repo: `git pull --ff-only` before starting; CHANGELOG under `[Unreleased]`; run pytest and paste output before any push.

---

## File Structure

- `pipeline/scanner/server.py` — `TOOLS` catalog rows gain metadata; add `Tool` namedtuple; `build_report` gains `selected`; add `do_GET` `/tools`; `do_POST` reads `tools` from request.
- `tests/test_scanner_selection.py` (new) — selection filtering + catalog shape.
- `web/app/page.tsx` — fetch `/tools`, render checklist, send `tools`.
- `web/app/api/scan/route.ts` / a `/api/tools` proxy — pass-through to Python `/tools`.

---

### Task 1: Backend catalog + selection

**Files:**
- Modify: `pipeline/scanner/server.py` (TOOLS, build_report, do_GET)
- Test: `tests/test_scanner_selection.py`

**Interfaces:**
- Produces: `Tool = namedtuple("Tool", "label key group cost cost_num needs run")`; `TOOLS: list[Tool]`; `tool_catalog() -> list[dict]` (`{key,label,group,cost,cost_num}`); `build_report(..., selected: set[str] | None = None)` runs a tool when `selected is None or key in selected`, still skipping `needs=="repo"` tools without a repo.

- [ ] **Step 1: Write failing test** — `test_selection_filters` asserts `build_report(url, selected={"seo"}, fetch=fake)` returns a report whose groups contain only `seo`; `test_catalog_shape` asserts every `tool_catalog()` row has `key,label,group,cost`.
- [ ] **Step 2: Run — expect fail** (`Tool`/`selected`/`tool_catalog` missing).
- [ ] **Step 3: Implement** — convert `TOOLS` rows to `Tool(...)` with `group` in {free,dataforseo,source}, a display `cost` string and numeric `cost_num`, `needs` ("repo" for source else None). `build_report` loops `for t in TOOLS: if selected is not None and t.key not in selected: continue; if t.needs=="repo" and not source_ok: continue`. Add `tool_catalog()`. Add `do_GET`: path `/tools` → JSON catalog.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 2: Backend request wiring

**Files:**
- Modify: `pipeline/scanner/server.py` (`do_POST`)
- Test: `tests/test_scanner_selection.py`

**Interfaces:**
- Consumes request `tools`: a list of keys, or absent → all.

- [ ] **Step 1: Write failing test** — `test_post_reads_tools` posts `{"tools":["seo"]}` through the request parse helper and asserts `selected == {"seo"}`; absent `tools` → `selected is None`.
- [ ] **Step 2: Run — expect fail.**
- [ ] **Step 3: Implement** — in `do_POST`, `tools = req.get("tools"); selected = set(tools) if isinstance(tools, list) else None`; pass to `build_report`. Drop `crawl`/`deep` params.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 3: Frontend checklist

**Files:**
- Modify: `web/app/page.tsx`
- Add: `web/app/api/tools/route.ts` (proxy to Python `/tools`)

- [ ] **Step 1** — add `/api/tools` proxy route (GET → Python `:8765/tools`).
- [ ] **Step 2** — on mount, fetch `/api/tools` into `catalog` state; `selected` state = Set of all keys (all ticked).
- [ ] **Step 3** — render grouped checkboxes (Free / DataForSEO / Source), each row `label · cost`; group select-all/none; footer running total from `cost_num` of selected.
- [ ] **Step 4** — replace the `crawl`/`deep` booleans in the scan body with `tools: [...selected]`.
- [ ] **Step 5** — manual check in browser (servers running); commit.

### Task 4: Thermo review + persist

- [ ] Run thermonuclear review of Tasks 1-3 diff (every-3 rule).
- [ ] `saveScan` records `tools` (which ran) instead of `{crawl,deep}`.
- [ ] Full `pytest -q`, paste output. CHANGELOG entry. Commit.
