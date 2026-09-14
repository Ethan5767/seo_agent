# Tools Revamp — Design (2026-09-14)

Branch: `feat/tools-revamp`. Operator ask: "all this tool is not working … we need to revamp all those tools", and supply every credential the project needs today.

## 1. Where we start (verified against code, 2026-09-14)

The sidebar holds 22 tools ("Site Performance" is a group heading). Baseline before any change: `pytest -q` → 1261 passed, 2 skipped; `npm test` (web) → 408 passed.

| Defect | Evidence | Effect |
|---|---|---|
| D1. DataForSEO hard-disabled in the scanner | `pipeline/scanner/server.py:497-502` `_wanted` returns False for every `dataforseo` tool unless `PYTEST_CURRENT_TEST` is set | 13 tools can never run |
| D2. DataForSEO hard-disabled again at the call | `pipeline/scanner/dataforseo.py:61` refuses unless login/password are literally `x`/`y` | same, even if D1 is removed |
| D3. Composite cards swallow sub-call status | `rankings()` / `keywords_card()` bind the status to `_s` and drop it | a skipped or failed provider call reads as "0 rows" |
| D4. Scan refusals are invisible in the UI | `ScannerApp.tsx` `run()` never checks `res.ok`, never parses the trailing buffer; `/api/scan` answers plain JSON (no newline) for 400/401/429 and **200** for "backend unreachable / SCAN_TOKEN unset" | "nothing happens" (B-104 shape) |
| D5. Budget-skipped tools are not reported | `X-Scan-Blocked-Tools` header set by `/api/scan`, read by nobody | partial run looks complete |
| D6. Hardcoded KPIs on Page Optimizer | `ReaiDashboard.tsx` `recs.length + 8` Ideas, `+42% Lift`, `84 / 100`, unconditional "All 3 Core Web Vitals Passed" | invented numbers shown to clients |
| D7. Legacy tabs with invented data share names with real tools | `/keyword-gap`, `/keyword-magic-tool`, `/backlink-audit`, `/organic-research` competitor map, `/backlink-analytics` `refDelta`, `visibilityPoints`, `totalVolume` fallback `"8,200"` | two screens per name, one fabricated |
| D8. Report views have no URL | views set React state only | cannot link, lost on refresh |
| D9. Wrong tool behind Domain Overview | `web/lib/sectionScans.ts` `VIEW_TOOLS["domain-overview"] = ["keywords"]`; `dfs.domain_overview` is emitted by `rankings()` | scan button spends on the wrong tool |
| D10. Dead codes on Crawl Issues / Backlink Audit | `dfs.duplicate_*`, `click_depth`, `orphan_page`, `redirect`, `canonical_chain`, `image_alt_missing`, `broken_links`, `broken_page` come only from `dataforseo.site_audit`, which nothing outside tests calls | screen promises rows no scan produces |
| D11. Backlink Gap has no data source | `backlinkGapData = []` hardcoded, no scanner tool | permanently empty |
| D12. Source Code silently dropped without a GitHub token | `server.py` `source_ok` filters the tool out with no row | looks like "nothing found" |
| D13. Scan saved to `clients[0]` when no project is active | `ScannerApp.tsx` `histClient \|\| clients[0]` | findings land in the wrong project |
| D14. Core Web Vitals button runs 3 of the 4 Lighthouse categories the blurb names | `VIEW_TOOLS["core-web-vitals"]` | blurb over-claims |
| D15. `.env.example` lists 7 of ~40 variables; no `web/.env.example` | files | operators cannot tell what to provide |

## 2. Decisions

1. **Spend policy: real calls, budget-capped (option A).** A paid tool runs only when all four hold: credentials set, `DATAFORSEO_PAUSE_SPEND` is not `1`, the tool was explicitly selected, and `applyBudget` admits it. `DATAFORSEO_PAUSE_SPEND=1` stays the operator kill switch and produces a *named* skip.
2. **A skip is a row, never silence.** Any tool that cannot run emits one `info` row with code `<tool>.unavailable` whose `why` names the exact reason (`DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD unset`, `paused: DATAFORSEO_PAUSE_SPEND=1`, `no GitHub token`, `no target keywords on this project`, `budget`). Unavailable rows are ungraded (do not move the score).
3. **The tool catalog states availability.** `/tools` returns `available` and `unavailable_reason` per tool, computed from the environment without spending. The UI disables the checkbox and shows the reason.
4. **One screen per name.** Legacy fabricated tabs are deleted; their URLs route to the report view of the same name. Every view is reachable at `/tools/<view-id>`.
5. **No invented numbers survive.** A KPI that cannot be derived from the report is removed, not estimated.
6. **Paid tools stay unticked by default in the full-scan picker**; a view's own Scan button may include its paid tool, with the cost named before pressing.
7. **Out of scope:** splitting `ReaiDashboard.tsx` wholesale (only code a fix touches is extracted), new providers beyond DataForSEO, GSC/GBP panels, the CLI audit rail.

## 3. Design by phase

### Phase 1 — Foundation (D1–D5, D12, D13)

**Scanner (Python)**
- `dataforseo.call`: delete the `x`/`y` gate. Order of refusal: no credentials → `skipped: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD unset`; `DATAFORSEO_PAUSE_SPEND == "1"` → `skipped: paused by DATAFORSEO_PAUSE_SPEND=1`.
- New `dataforseo.availability() -> (bool, reason)`: the same two checks, no network. Single source for both `call` and the catalog.
- `server._wanted`: delete the `PYTEST_CURRENT_TEST` branch; a `dataforseo` tool is wanted when selected. A selected-but-unavailable tool does not call its `run`; it emits the `.unavailable` row (decision 2).
- `source` tool: selected with no usable repo/token → `.unavailable` row instead of silent filter.
- `rankings()` / `keywords_card()`: collect sub-call statuses; any `skipped:`/error status becomes an `.unavailable`/`info` row and is reflected in the card's status line. `keywords_card` with no project keywords emits `dfs.keywords.unavailable` "no target keywords on this project" for the keyword-dependent sub-tools.
- `/tools` response adds `available`, `unavailable_reason`.

**Web**
- `lib/scanStream.ts` (new, pure): `readScanStream(res, handlers)` — checks `res.ok` and content type; non-NDJSON body → parsed `{error}` handed to `onError`; parses the final buffer; malformed line → `onError`, not a thrown exception. `ScannerApp.run()` uses it; `apply` reader reuses it.
- `/api/scan`: unreachable backend / unconfigured token → **503** (not 200). Refusals keep their JSON `{error}` shape.
- `ScannerApp` reads `X-Scan-Blocked-Tools` and surfaces "Skipped by daily budget: …".
- `run()` saves only to the active project; no active project → error "Pick or create a project before scanning" (matches 61af638's precondition), never `clients[0]`.
- Tool checkboxes honour `available`; the comment "paid permanently unticked" is replaced with the real rule.

### Phase 2 — Honest screens (D6–D8, D14)

- Page Optimizer: remove `Ideas`/`Lift`/`84/100`/`1-Click Ready` tiles and the unconditional CWV banner; replace with values derived from `report` (recommendation count, on-page graded pass rate, CWV verdict from `deriveCoreWebVitals`) or nothing.
- Delete the legacy data constants and tabs listed in D7. `TAB_ROUTES` entries for those URLs open the matching view.
- Route `web/app/tools/[view]/page.tsx` → `<ReaiApp initialView=…/>`; `openNavItem` for a view pushes `/tools/<id>`. Unknown id → the directory.
- `lib/viewEmptyState.ts` (new, pure): `emptyReason(view, report, catalog, project)` → one of `not-scanned`, `unavailable(reason)`, `needs-keywords`, `needs-competitor`, `clean`. Replaces the static `emptyHint` strings.
- `VIEW_TOOLS["core-web-vitals"]` adds `lh_a11y`, `lh_bp`.
- `fabricationSweep.test.mjs` extended: literal `% Lift`, `/ 100` literals, "Passed" banners without a condition, `+N ▲` deltas.

### Phase 3 — Wiring (D9–D11)

- `VIEW_TOOLS["domain-overview"] = ["rankings"]`.
- Drop dead codes (D10) from `reportViews.ts`; delete `dataforseo.site_audit` + its `DFS_RECS` entries if nothing else uses them (verify with grep first).
- New scanner tool `backlink_gap` (group `dataforseo`, category `Links`): `dataforseo.backlink_gap(domain, competitors)` → `/v3/backlinks/domain_intersection/live`, emits `dfs.backlink_gap` rows (referring domains linking to a competitor and not to you); competitor from the project, else `.unavailable` "needs a competitor". Cost mirrored in `web/lib/budget.ts` (test enforces parity). Backlink Gap tab replaced by a report view.
- **Guard test (new):** every code prefix listed in `reportViews.ts` must be emitted somewhere under `pipeline/scanner/` (grep the Python source), and every `VIEW_TOOLS` key must exist in `TOOLS`. This is what would have caught D9/D10.

### Phase 4 — Proof and docs (D15)

- Root `.env.example` and new `web/.env.example`: every variable, grouped, names only, one line each on what it unlocks.
- `CHANGELOG.md` `[Unreleased]` entry per phase; `docs/BUG-LEDGER.md` new entries for D1–D15 with fix proof; `docs/MODULES.md` counts for `backlink_gap`, `scanStream`, `viewEmptyState`.
- Live proof: once `DATAFORSEO_LOGIN/PASSWORD` are in `.env` and the operator sets `DATAFORSEO_PAUSE_SPEND=0`, one scan per group against a project domain; paste the scanner status lines and cost into the CHANGELOG. Until then the entry says **unverified live, and why**.

## 4. Testing

- Python: `call` refuses with each named reason (monkeypatched env), and makes the request when credentials are set and not paused (mocked `urlopen`); `_wanted` admits a selected paid tool outside pytest; unavailable tool emits exactly one ungraded row; composite cards surface sub-call skips; `backlink_gap` parser over a recorded fixture; `/tools` availability fields.
- Web: `readScanStream` over non-OK JSON, no trailing newline, malformed line, normal stream; `emptyReason` matrix; view↔code↔tool guard; `/api/scan` 503 on unreachable; no-project refusal; fabrication sweep.
- Each phase ends with `pytest -q` and `npm test` run on their own lines, output read before commit.

## 5. Risks

- Removing D1/D2 re-enables spend. Mitigation: `PAUSE_SPEND=1` is currently set in `.env`, budget cap is enforced server-side, paid tools stay unticked by default.
- Another session commits to `main` concurrently; this work stays on `feat/tools-revamp` and merges by PR/fast-forward after review.
- `ReaiDashboard.tsx` is 12k lines; edits there are surgical and covered by the source-level tests already in `web/tests/`.
