# Free-Lane Multi-Page Crawl Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, one commit each. Steps use checkbox syntax. NO paid/live API calls in any test — offline only.

**Goal:** Make the free lane audit **multiple pages** (homepage + top sitemap URLs), not just the one URL, running our per-page checks on each and aggregating with which-page attribution. Fixes the "too fast / not deep" gap and gives site-wide coverage of our differentiator checks (E-E-A-T, AEO, content, internal links) that DataForSEO doesn't do.

**Architecture:** A pure `discover_pages()` picks the URLs (from the sitemap, falling back to same-origin links). Each `Tool` gains a `per_page` flag; in `build_report`, `per_page` tools run on **every crawled page** and their rows merge by `code` (worst severity, affected-page URLs collected — reusing the finding shape the UI already renders). Non-per-page tools (CrUX, Lighthouse, DataForSEO, source) run once as today. Crawling is opt-in + capped, so a quick scan stays single-page and cheap.

**Tech Stack:** Python stdlib backend, Next.js frontend, pytest. No new dependency.

## Global Constraints

- **No orphan inference** — that's what produced false results before. We only run existing per-page checks on real fetched pages; we never guess "orphan" from a partial crawl (DataForSEO Site Health owns orphans).
- Same-origin only; cap the page count (default 10, hard max 25); dedup.
- Free HTTP fetches only — no paid/live API in tests (offline canned data).
- Aggregation reuses the `{code, what, why, fix, severity, detail, pages}` shape already rendered by the UI (affected-pages expandable).
- Two-operator repo: `git pull --ff-only`; CHANGELOG; offline pytest output before push.

## File Structure

- `pipeline/scanner/multipage.py` (new) — `discover_pages`, `merge_by_code`. Pure.
- `pipeline/scanner/server.py` — `Tool` gains `per_page`; `build_report` runs per-page tools across crawled pages; a `crawl_pages` opt controls how many pages.
- `tests/test_scanner_multipage.py` (new).

---

### Task 1: Page discovery (pure)

**Files:** create `pipeline/scanner/multipage.py`; test `tests/test_scanner_multipage.py`

**Interfaces:**
- `discover_pages(homepage: str, sitemap_text: str, html: str, limit: int = 10) -> list[str]` — always includes `homepage` first; then same-origin `<loc>` URLs from the sitemap; if none, same-origin `href`s from `html`; dedup preserving order; cap at `limit`; drop non-http, fragments, and off-origin.

- [ ] **Step 1: Write failing test** — sitemap with 3 same-origin + 1 off-origin `<loc>` → returns homepage + the 3, off-origin dropped, capped at limit. No sitemap → falls back to same-origin hrefs from html. Homepage always first + deduped.
- [ ] **Step 2: Run — expect fail** (module missing).
- [ ] **Step 3: Implement** — regex `<loc>` + `href=` extraction, `urlsplit` origin compare, order-preserving dedup, cap.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 2: Cross-page merge (pure)

**Files:** modify `pipeline/scanner/multipage.py`; test same file

**Interfaces:**
- `merge_by_code(per_page: list[tuple[str, list[dict]]]) -> list[dict]` — input is `[(url, rows), ...]`; output one row per `code` keeping the **worst** severity seen, with `pages` = the URLs where it was an error/warn (cap 25) and `detail` = "N page(s)". A check that passes on every page stays a single `ok` row with no pages.

- [ ] **Step 1: Write failing test** — same code `warn` on 2 pages + `ok` on 1 → one row, severity warn, `pages` = the 2 failing URLs, detail "2 page(s)". A code `ok` on all pages → one ok row, `pages` empty.
- [ ] **Step 2: Run — expect fail.**
- [ ] **Step 3: Implement** — index by code, upgrade to worst severity via a rank map, collect failing pages.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 3: Wire crawl into build_report

**Files:** modify `pipeline/scanner/server.py`; test `tests/test_scanner_server.py`

**Interfaces:**
- `Tool` namedtuple gains a trailing `per_page: bool` (True for the pure-HTML free tools: seo, tech, schema, content, video, eeat, aeo, internal, validate; False for perf/lighthouse/dataforseo/source).
- `build_report(..., crawl_pages: int = 1)`: when `crawl_pages > 1`, discover + fetch up to that many pages; run each `per_page` tool over all fetched pages and `merge_by_code`; run non-per-page tools once on the homepage. `crawl_pages == 1` = today's single-page behaviour (default, so nothing changes unless asked).
- do_POST reads `crawl_pages` from the request (default 1).

- [ ] **Step 1: Write failing test** — `build_report` with `crawl_pages=3`, a fake fetch returning 3 distinct pages (one with a missing title), `selected={"seo"}` → the "title missing" row's `pages` lists the failing URL(s); a single-page run (`crawl_pages=1`) is unchanged.
- [ ] **Step 2: Run — expect fail.**
- [ ] **Step 3: Implement** — add `per_page` to the 23 Tool rows; refactor the phase loop to run per-page tools across `ctx.pages`; keep the fetch of homepage/robots/sitemap; discover+fetch extra pages only when `crawl_pages > 1`.
- [ ] **Step 4: Run — expect pass + full offline suite green.**
- [ ] **Step 5: Commit.**

### Task 4: Frontend toggle + Thermo

**Files:** `web/app/page.tsx`

- [ ] A "Crawl N pages (free, deeper)" number input / toggle in the Measure controls; send `crawl_pages` in the scan body (default 1). Affected-pages already render (Task from earlier).
- [ ] `tsc` clean.
- [ ] Thermo review of Tasks 1-3 (every-3 rule): watch the phase-loop refactor for dropped tools / double-runs, origin-compare edge cases, cap enforcement.
- [ ] Full offline `pytest -q`, paste output. CHANGELOG. Commit.
