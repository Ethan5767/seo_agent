# Measure on DataForSEO — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Execute ONE task at a time — this plan exists because ad-hoc building got tangled.

**Goal:** Rebuild the scanner's **Measure** stage so every capability DataForSEO offers is served by DataForSEO, and we build our own only for the gaps DataForSEO doesn't cover. One consistent data source, per-tool result cards, exact cost.

**Architecture:** `pipeline/scanner/dataforseo.py` becomes the DataForSEO client + one pure parser per tool (parsers unit-tested offline with canned responses — the live API costs money and can't run in CI). `server.build_report` orchestrates the tools, streaming one card per tool. The free HTML crawler (`crawl.py`) is **retired for site-wide checks** — DataForSEO's crawl renders JS, so it doesn't produce the false orphans ours did. Our own code remains ONLY for the three gaps DataForSEO has no tool for.

**Tech Stack:** Python 3 stdlib (urllib, base64), existing scanner. DataForSEO endpoints + inputs are documented in `~/dfs-test/INPUTS-17-TOOLS.md` (tested live). Location `2116` (Cambodia), language `en`.

## Global Constraints
- Python ≥3.10, repo `.venv`. Run tests: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q', <args>]))"` (bare `pytest` is intercepted by the rtk hook).
- Keep 790+ tests green. Every task: failing test → implement → pass → commit.
- **The rule:** DataForSEO for anything it has a tool for; our own ONLY for gaps (robots AI-crawler allow, answer-first/entity structure, SSR-vs-CSR rendering).
- **Never fake data:** no creds / API error / no field data → an honest "skipped/none" status, never invented numbers. A tool that couldn't run must not read as a pass.
- **Cost is exact where the API reports it:** read the top-level `cost` field from each DataForSEO response and sum it; the on-page crawl (which bills per page across several calls) may show a per-page estimate, clearly labelled "est".
- Every DataForSEO parser is pure and unit-tested with a canned response; the caller takes an injectable `call`/`run` seam so tests never hit the network.
- Credentials come from the one `.env` via `pipeline.lib.env.load_env` (already wired). Never commit secrets.
- All endpoints/inputs must match `~/dfs-test/INPUTS-17-TOOLS.md` exactly.

## Capability → source (locked)
| Capability | Source |
|---|---|
| On-page + site crawl (title/meta/H1/dup/broken/orphan/redirect/canonical/non-indexable/click-depth/alt) | DataForSEO on-page (tools 1-6) |
| Page speed / CWV | Google CrUX (free field data — already built) + DataForSEO Lighthouse #7 optional later |
| Rankings (SERP #8, ranked kw #9, domain #10, historical #11) | DataForSEO |
| Keywords (volume #12, ideas #13, suggestions #14, gap #15, competitors #16) | DataForSEO |
| AI citations / LLM mentions #17 | DataForSEO |
| AEO: AI-crawler robots.txt allow | Ours (gap) |
| AEO: answer-first / entity structure | Ours (gap) |
| Rendering SSR vs CSR | Ours (gap) |

Dependency chain (so the user still only pastes a URL): run #9 ranked-keywords + #16 competitors first; feed their output into #8/#12/#14/#15.

---

## Task 1: DataForSEO client with exact cost capture

**Files:**
- Modify: `pipeline/scanner/dataforseo.py`
- Test: `tests/test_scanner_dataforseo.py`

**Interfaces:**
- Produces: `call(path, payload, timeout=60) -> (json|None, error|None)` (exists). Add `cost_of(doc) -> float` reading the top-level `cost` field (exists as `_cost`; rename/export as `cost_of`). Add `result_items(doc) -> list` (exists as `_first_result_items`; export). These are the shared primitives every tool parser uses.

- [ ] **Step 1: Write the failing test**
```python
from pipeline.scanner.dataforseo import cost_of, result_items
def test_cost_of_reads_top_level_cost():
    assert cost_of({"cost": 0.0123}) == 0.0123
    assert cost_of({}) == 0.0
def test_result_items_digs_the_nest():
    doc = {"tasks": [{"result": [{"items": [{"k": 1}]}]}]}
    assert result_items(doc) == [{"k": 1}]
    assert result_items({}) == []
```
- [ ] **Step 2: Run → fails** (`cannot import name 'cost_of'`).
- [ ] **Step 3: Implement** — rename `_cost`→`cost_of`, `_first_result_items`→`result_items` (keep behaviour), update internal callers.
- [ ] **Step 4: Run → passes.**
- [ ] **Step 5: Commit** `feat(scanner/dfs): shared client primitives (cost_of, result_items)`.

---

## Task 2: Site Health card — DataForSEO on-page site audit (replaces free crawler)

**Files:**
- Modify: `pipeline/scanner/dataforseo.py` (finish `site_audit` started ad-hoc — make it parser-tested)
- Test: `tests/test_scanner_dataforseo.py`

**Interfaces:**
- Consumes: `providers.dataforseo_findings(domain, max_pages) -> (findings, status)` (proven, ran live 2026-08-14). `DFS_RECS` code→(why,fix,severity) map (exists).
- Produces: `site_audit(domain, max_pages=25, run=None) -> (rows, status, cost)`. `run` injectable. Rows map each finding via `DFS_RECS`.

- [ ] **Step 1: Write the failing test**
```python
from pipeline.scanner.dataforseo import site_audit
from pipeline.lib.baseline import Finding
def test_site_audit_maps_findings_to_rows():
    fake = lambda d, n: ([Finding("dataforseo", "dfs.broken_links", "/a/", detail="404"),
                          Finding("dataforseo", "dfs.orphan_page", "/b/")], "ok: crawled 20")
    rows, status, cost = site_audit("x.com", run=fake)
    by = {r["code"]: r for r in rows}
    assert by["dfs.broken_links"]["severity"] == "error"
    assert by["dfs.orphan_page"]["severity"] == "warn"
    assert "est" in status
```
- [ ] **Step 2: Run → fails.**
- [ ] **Step 3: Implement** `site_audit` (already drafted): map findings→rows via `DFS_RECS`, cost = `round(0.0003*max_pages,4)` labelled est. NOTE in the code comment: on-page crawl uses `enable_javascript=False` in `providers.dataforseo_findings`; DataForSEO still renders more than our regex crawler, but a fully JS site needs `enable_javascript=True` — a follow-up flag on providers.
- [ ] **Step 4: Run → passes.**
- [ ] **Step 5: Commit** `feat(scanner/dfs): Site Health card from DataForSEO on-page audit`.

---

## Task 3: Retire the free crawler from Measure

**Files:**
- Modify: `pipeline/scanner/server.py` (build_report), `web/app/page.tsx`
- Test: `tests/test_scanner_server.py`

**Interfaces:**
- `build_report(..., crawl=..., deep=...)` → replace the `crawl` (free `crawl_site`) site-wide path with `site_audit` when the user opts into the DataForSEO site audit. The `crawl.py` module stays in the tree (still unit-tested) but is no longer called by Measure. The "Whole site" card becomes "Site Health (DataForSEO)".

- [ ] **Step 1: Write the failing test** — `build_report(..., site_audit_run=fake)` includes a `site` group sourced from `site_audit`, and does NOT call the free crawler.
- [ ] **Step 2: Run → fails.**
- [ ] **Step 3: Implement** — swap the crawl branch; inject `site_audit_run` for tests; drop `crawl_site`/`site_rows` imports from the Measure path.
- [ ] **Step 4: Run → passes** + full suite green.
- [ ] **Step 5: Commit** `refactor(scanner): Measure site-wide = DataForSEO on-page, retire free crawler`.

---

## Task 4: Rankings card (tools 8-11)

**Files:** `pipeline/scanner/dataforseo.py`, `tests/test_scanner_dataforseo.py`
**Interfaces:** extend with pure parsers + injectable callers:
- `ranked_keywords` (exists — keep) ·
- `domain_overview(domain, call=call) -> (rows, status, cost)` → `/v3/dataforseo_labs/google/domain_rank_overview/live` payload `[{target, location_code:2116, language_code:"en"}]` — parse organic `etv`/`count` into a visibility row.
- `serp_rank(keyword, call=call) -> (rows, status, cost)` → `/v3/serp/google/organic/live/advanced` payload `[{keyword, location_code:2116, language_code:"en", depth:20}]` — parse whether the client domain appears + position.

- [ ] Per parser: failing test with a canned response → implement → pass → commit. (One commit per parser, or one for the Rankings group.)
- [ ] Card assembles ranked_keywords + domain_overview into one "Rankings" group; SERP-rank runs per keyword derived from the onboard keywords or #9.

---

## Task 5: Keywords card (tools 12-16)

**Files:** `pipeline/scanner/dataforseo.py`, tests.
**Interfaces:** pure parsers + callers, endpoints exactly per the doc:
- `search_volume(keywords: list, call=call)` → `/v3/keywords_data/google_ads/search_volume/live` (field-array up to 1000 kw, one charge).
- `keyword_ideas(seeds: list, call=call)` → `/v3/dataforseo_labs/google/keyword_ideas/live`.
- `keyword_suggestions(keyword, call=call)` → `/v3/dataforseo_labs/google/keyword_suggestions/live`.
- `keyword_gap(you, competitor, call=call)` → `/v3/dataforseo_labs/google/domain_intersection/live` payload `[{target1:competitor, target2:you, intersections:false, ...}]` (terms only the competitor ranks for).
- `competitors(domain, call=call)` → `/v3/dataforseo_labs/google/competitors_domain/live`.

- [ ] Each: canned-response parser test → implement → pass → commit.
- [ ] Auto-derive: seeds/keywords come from the onboard keywords + #9 ranked-keywords; competitor for the gap comes from #16 (fallback to onboard competitors). So the user still only pastes a URL.

---

## Task 6: AI Visibility card — LLM mentions (tool 17)

**Files:** `pipeline/scanner/dataforseo.py`, tests.
**Interfaces:** `llm_mentions(brand, domain, call=call) -> (rows, status, cost)` → `/v3/ai_optimization/llm_mentions/search_mentions/live` with the documented `target` array (brand keyword partial-match in answers + domain in sources). Parse: is the brand/domain cited, how often, by which engines. Brand derived from onboard business name / domain.

- [ ] Canned-response parser test → implement → pass → commit.

---

## Task 7: Our gap checks card (only what DataForSEO lacks)

**Files:** `pipeline/scanner/audit.py` (reuse existing `aeo_rows` robots check) + `extra_checks.py` (rendering) — consolidate into a small "AEO & Rendering" group. Tests exist for these already.
**Interfaces:** a `gap_rows(url, html, robots) -> list[dict]` that returns ONLY the three gap checks: AI-crawler robots.txt allow (from `aeo_rows`), answer-first/entity structure (new small check), SSR-vs-CSR rendering (`extra_checks.visible_text_ratio`). Everything DataForSEO already covers is dropped from our code path to avoid duplication.

- [ ] Failing test for the consolidated gap set → implement (mostly re-wire existing) → pass → commit.

---

## Task 8: Onboard — keywords as multi-add

**Files:** `web/app/page.tsx`
**Interfaces:** the onboard "target keywords" field becomes an add-list: type a keyword, press Enter/Add, it appears as a removable chip; submit sends `keywords: string[]`. Backend already accepts a list (`_list` in server.do_POST). Onboard is otherwise unchanged (it's good).

- [ ] Manual UI (no unit test needed): chips add/remove; the scan request carries `keywords` as an array. Commit.

---

## Task 9: Wire-up — cards, exact cost totals, cleanup

**Files:** `pipeline/scanner/server.py`, `web/app/page.tsx`, `docs/MODULES.md`, `CHANGELOG.md`
**Interfaces:** `build_report` emits one `on_tool` card per DataForSEO tool group + the gap card, each with its exact/estimated cost; total cost summed from the real response `cost` fields. Remove the now-unused free-crawler wiring from Measure. Update MODULES/CHANGELOG (sync contract).

- [ ] Full suite green; per-tool cards stream; total cost is the sum of real DataForSEO `cost` fields; free/gap checks show "free". Commit.

---

## Self-Review (at write time)
- **Rule coverage:** every capability maps to DataForSEO except the 3 named gaps (Task 7). ✓
- **No-fake invariant:** every parser returns `[]` + a status on error/empty; costs read from real `cost` fields (Task 1). ✓
- **Testability:** every DataForSEO tool = pure parser + injectable caller, tested with canned responses; no network in CI (matches dfs-test's own boundary). ✓
- **Retire free crawler:** Task 3 removes it from Measure (kept in tree, no longer called) — resolves the JS-nav false-orphan mess. ✓
- **Dependency order:** Tasks 4→5 rely on #9/#16 output; noted so keywords auto-derive and the user still only pastes a URL. ✓
- **Endpoints:** all taken verbatim from `~/dfs-test/INPUTS-17-TOOLS.md`. ✓
- **Known estimate:** on-page crawl cost is a per-page estimate (Task 2) because the crawl spans several billed calls; flagged "est". Exact cost everywhere the response reports it.
