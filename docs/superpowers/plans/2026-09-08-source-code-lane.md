# Source-Code Lane Build-Out Implementation Plan

> **For agentic workers:** implement task-by-task, TDD, one commit each. Steps use checkbox syntax.

**Goal:** Deepen the read-only source-code audit from ~4 checks to ~15, judging code-level SEO/AEO setup the live HTML can't reveal — the differentiator Semrush can't touch (it never sees the repo).

**Architecture:** `analyze_source` stays pure (inputs in, rows out) and unit-tested offline. The fetch layer gains a **repo tree** call (one GitHub API request lists every path) so existence checks are cheap; a bounded set of key files (~12) is fetched for deep parsing. No whole-repo content scan (rate-limit + cost).

**Tech Stack:** Python stdlib (urllib, json, base64), GitHub contents + git/trees API, pytest.

## Global Constraints

- Read-only: GitHub read token, no writes. `owner/name` repos only; local paths skipped (unchanged).
- Pure core: `analyze_source(files, tree)` takes fetched files + the path list; no network in the analyzer.
- Never fake: a file we couldn't fetch is absent, not a failure invented.
- Two-operator repo: `git pull --ff-only` first; CHANGELOG under `[Unreleased]`; pytest output before push.
- Cost-free: GitHub API only, no DataForSEO.

## File Structure

- `pipeline/scanner/source_audit.py` — add `fetch_repo_tree`, extend `fetch_repo_files`, grow `analyze_source(files, tree)` with the new check groups; keep `_row`, `_gh_get`.
- `pipeline/scanner/server.py` — the Source tool passes the tree to `analyze_source`.
- `tests/test_scanner_source.py` — offline tests per check group (canned files + tree).

---

### Task 1: Repo tree + route-existence checks

**Files:**
- Modify: `pipeline/scanner/source_audit.py`
- Test: `tests/test_scanner_source.py`

**Interfaces:**
- Produces: `fetch_repo_tree(repo, token, fetch=None) -> list[str]` (every path, one `git/trees?recursive=1` call); `analyze_source(files: dict, tree: list[str] | None = None) -> list[dict]` (tree defaults to `list(files)` when None, so old callers still work).
- New checks driven by the tree: app-router vs pages-router (`app/` vs `pages/`), robots as route (`app/robots.ts|js`) or static, sitemap as route (`app/sitemap.ts|js`) or static or `next-sitemap.config.*`, `public/llms.txt` (AEO), `middleware.ts|js` presence.

- [ ] **Step 1: Write failing test** — `test_tree_route_checks`: given `tree=["app/layout.tsx","app/robots.ts","app/sitemap.ts","public/llms.txt"]` and `files={}`, `analyze_source({}, tree)` emits ok rows "Source: robots.txt", "Source: sitemap.xml" (route form) and an ok "Source: llms.txt". Given a tree with none of those and no static files, those go warn.
- [ ] **Step 2: Run — expect fail** (analyze_source takes 1 arg / no llms check).
- [ ] **Step 3: Implement** — add `tree` param; treat robots/sitemap as satisfied by static file OR route OR (for sitemap) `next-sitemap` dep/config; add llms.txt, app-vs-pages, middleware rows. Keep existing framework/rendering logic.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 2: next.config parsing

**Files:**
- Modify: `pipeline/scanner/source_audit.py`
- Test: `tests/test_scanner_source.py`

**Interfaces:**
- Consumes: whichever of `next.config.{js,mjs,ts}` was fetched. Regex/`in`-string checks (not a JS parse): `i18n` block (hreflang readiness), `async headers(` (security/caching headers), `async redirects(`, `trailingSlash`, `images:` (next/image config).

- [ ] **Step 1: Write failing test** — `test_next_config_checks`: a config string with `i18n:{locales:[...]}` and `async headers()` → ok rows "Source: i18n", "Source: HTTP headers"; a config without them → info/warn rows.
- [ ] **Step 2: Run — expect fail.**
- [ ] **Step 3: Implement** — a `_next_config_rows(cfg_text)` helper folded into `analyze_source`; only emit when a next.config was fetched.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 3: Root-layout metadata + deps signals

**Files:**
- Modify: `pipeline/scanner/source_audit.py` (add `app/layout.tsx|jsx|js` + `pages/_app.*` + `pages/_document.*` to `_FILES`), `pipeline/scanner/server.py` (pass tree)
- Test: `tests/test_scanner_source.py`

**Interfaces:**
- Consumes: root layout text + `deps` (already parsed). Checks: `metadataBase` set (canonical/OG base), a default `metadata`/`title`/`description` export, `openGraph`/`twitter` in metadata, `next/font` import (perf), analytics dep (`@vercel/analytics`, `gtag`, `react-ga`, GTM). `server.py`: `analyze_source(fetch_repo_files(...), fetch_repo_tree(...))`.

- [ ] **Step 1: Write failing test** — `test_metadata_checks`: a layout with `export const metadata = { metadataBase: new URL(...), title: "x", openGraph:{...} }` → ok rows; a layout without → warn "Source: metadataBase", warn "Source: default metadata".
- [ ] **Step 2: Run — expect fail.**
- [ ] **Step 3: Implement** — `_metadata_rows(layout_text, deps)`; wire the tree into `server.py`'s Source tool.
- [ ] **Step 4: Run — expect pass.**
- [ ] **Step 5: Commit.**

### Task 4: Thermo review + full suite + CHANGELOG

- [ ] Thermo review of the Task 1-3 diff (every-3 rule) — watch for regex brittleness, row-code collisions, file size.
- [ ] Full `pytest -q`, paste output. CHANGELOG entry. `docs/MODULES.md` if the module's line count/role changed. Commit.
