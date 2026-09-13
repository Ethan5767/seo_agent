# URL Audit MVP — design

**Status:** approved (brainstorming), 2026-09-07
**Owner:** team@new-wave.io
**One line:** A local web app — paste a **URL + repo**, pick **Model A or B**, and watch the pipeline find issues → fix them (or write a brief) → gate → decide, all in the browser.

## Purpose

Make the pipeline **tangible and testable**. Today the only way to see it run is the terminal (`spine_demo.py`) or pytest. The MVP is a browser front end over the real engine so the operator (and their CEO) can run a real site through the whole SOP flow on one screen. It is the demo-that-is-also-a-real-test: nothing is faked except where a mode genuinely cannot act.

## Users

- **Primary:** the operator (internal), testing real sites and showing the CEO.
- Not a customer-facing self-serve product (that is the separate `seo-tool` app). No auth, no billing, no multi-tenant. Localhost only, same as `wf-dashboard`.

## The two models (the core behavior)

Both take **URL + repo**. The difference is the only thing that matters:

| | Model A (client-owned) | Model B (agency-owned) |
|---|---|---|
| Code access | **read-only — never edited** | full — edited in place |
| Claude produces | a **brief / change-file** (the fix, written for the client to apply) | the **actual code edit** |
| After remediate | show the brief; repo stays clean | gates on the diff → AUTO/HUMAN decision → show the diff |
| Engine call | `remediate(..., recommend=True)` | `remediate(...)` |

This mirrors the SOP §3 and §7 exactly, and the engine already supports both (the `--recommend` flag IS Model A). The MVP adds no new remediation logic; it wires a UI over what exists.

**Model vs tier are orthogonal.** Model A/B = *access* (may we edit the code). Tier T1/T2/T3 = *scope* (what may be touched). The MVP defaults a scaffolded repo to **T1** (copy edits) and Model B unless the operator picks A; both are surfaced in the UI. A repo that already declares a tier keeps it.

## Scope of the audit (SEO + AEO + performance)

Always run, on the live URL, regardless of model:

- **SEO** — `measure.check_page` on the fetched page: title band, meta description, single H1, canonical, og:image, schema presence, thin content, image alt, noindex. Config-gated checks (forbidden phrases, NAP, GA4) are SKIPPED with a visible note when the repo config does not declare them — never silently, never faked.
- **AEO** — fetch `robots.txt` from the URL origin and reuse `robots_aicrawler_check.parse_groups` + `root_blocked` against the citation UA set (OAI-SearchBot, ChatGPT-User, PerplexityBot, Bingbot, Googlebot); plus schema presence + answer-capsule signal already surfaced by `check_page`/`capsule` logic.
- **Performance** — `providers.crux_findings(domain)` for real field LCP/INP/CLS. Requires `CRUX_API_KEY`. **No key → the performance section renders "set CRUX_API_KEY to enable", never zeros.** A provider that could not run must never read as a clean result (repo invariant).

Every issue is mapped through `plan.ACTIONS` to a recommendation: **what / why it matters / the fix + target band**.

## Architecture

New package `pipeline/scanner/`, entry point `wf-scan-web` — same shape and constraints as `pipeline/dashboard` (stdlib `http.server`, 127.0.0.1 only, no DB, no accounts, fixed route set, no secrets on disk). The engine runs **in-process**; no rewrite, no second language.

```
pipeline/scanner/
  server.py     # wf-scan-web: http.server, routes, SSE for live progress
  audit.py      # assemble the audit: measure + robots/AEO + CrUX -> findings + recommendations (pure, testable, no HTTP)
  config.py     # ensure_config: a repo with no docs/client-config.yml gets a minimal one scaffolded (domain from URL, tier default T1, build dir detected via client_profile) so plan/remediate can run at all
  run.py        # drive a full model-A/B cycle over a repo (ensure_config -> measure -> plan -> remediate -> gates -> decide)
  static/       # one page: index.html + app.js (input form + results render)
```

Boundaries:
- `audit.py` is **pure assembly** — given fetched HTML/robots/CrUX data, returns a structured report. Unit-testable with a canned fixture, no network. This is where the SEO+AEO+recommendation logic composes.
- `run.py` orchestrates the real stages for a repo (reuses `measure`, `plan`, `remediate`, the gate CLIs, `automerge_gate.decide_pr`). It shells to the same `wf-*` entry points the CI uses, so the web path and the CI path cannot drift.
- `server.py` is HTTP only — parse the request, call `audit.py`/`run.py`, stream progress, render JSON. No engine logic in the handler.

## Data flow

```
browser: URL + repo + model
   │  POST /scan  (SSE stream back)
   ▼
server.py
   ├─ audit.py: fetch URL + robots + CrUX  → report{seo[], aeo[], perf[], recommendations}
   └─ run.py (if repo given):
        measure(URL) → plan → remediate(recommend = modelA)
        modelB: gates(diff) → decide_pr → {diff, gates[], decision}
        modelA: {brief}
   ▼
browser renders: audit report + (B) diff/gates/decision  or  (A) brief
```

Each arrow is the engine's existing JSON artifact where one exists (findings.json, worklist.json, changelog.json), so the UI reads the same files the CI does.

## UX (one screen)

1. **Input:** URL, repo (a **local folder path** for the MVP; a public GitHub URL is `git clone`d to a temp dir), Model A/B toggle, "Run". A repo with no `docs/client-config.yml` is auto-scaffolded a minimal one (see `config.py`) so it can run at all.
2. **Progress:** the 6 steps stream live (SSE), same labels as `spine_demo`.
3. **Results:**
   - **Audit** — 3 groups (SEO / AEO / Performance), each row `✓/✗ · what · why · fix`, with a score.
   - **Model B** — the real **diff**, the gate results, and the **AUTO/HUMAN** decision + reason.
   - **Model A** — the **brief** (change-file) for the client to apply.
4. **Honest banner:** "Model A: we never touch your code — we hand you the fix. Model B: we fix it, gate it, and decide." Matches the SOP.

## Error handling

- URL unreachable → the same `Unreachable`/status-0 path `measure` already uses; show "site unreachable", do not write a report.
- No repo given → audit-only mode (SEO+AEO+perf + recommendations), fix section shows "connect a repo to fix".
- `claude` not on PATH / no `ANTHROPIC_API_KEY` → remediate refuses (its existing `USAGE_EXIT` guard); the UI surfaces "set up Claude to run the fix" and still shows the audit + plan.
- CrUX key absent → performance section shows the enable-note (above).
- Long runs → SSE keeps the page alive; a hard per-run timeout mirrors `remediate --timeout`.

## Testing

- `audit.py` unit tests with a canned HTML + canned robots + canned CrUX payload (no network): assert the assembled report groups + recommendations for a known-bad and known-good page. Reuse the `tests/e2e_fixture` page.
- `run.py` covered by the existing E2E spine path (it calls the same stages); add one test that `run.py` on the fixture in Model B yields a diff + AUTO, and in Model A yields a brief and a clean tree.
- Server: a smoke test that `/scan` on the fixture returns a report JSON with the three groups. No live-URL test in CI (network-free); the operator tests live URLs on their Mac.

## Out of scope (YAGNI)

- Auth, accounts, billing, multi-tenant, hosting/deploy (localhost only for the MVP).
- GitHub OAuth (a local path or a plain `git clone` of a public repo covers the test; OAuth belongs to `seo-tool`).
- The DataForSEO / GSC / SERP / backlink / video providers — audit uses the free trio (page crawl + robots + CrUX). Paid providers are a later toggle.
- Monitoring/reporting (SOP step 7), weekly content engine, backlink add-on.

## Dependencies / preconditions

- Runs on the operator's Mac (network). The dev sandbox is offline, so the app is written here and tested live by the operator.
- Python ≥3.10 venv (existing). `wf-scan-web` added to `[project.scripts]`.
- Optional keys: `CRUX_API_KEY` (performance), `ANTHROPIC_API_KEY` + `claude` CLI (real fix). Everything degrades honestly without them.

## Success criteria

- Operator runs `wf-scan-web`, opens the browser, pastes a real URL + a repo, picks a model, and sees: real issues + recommendations, and either a real Claude fix (B, with gates + AUTO/HUMAN) or a real brief (A).
- The web path calls the same `wf-*` stages as CI (no divergence).
- Nothing is faked: absent keys/repo degrade to a truthful partial result, never invented numbers.
