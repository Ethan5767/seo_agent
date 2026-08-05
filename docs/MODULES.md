# Pipeline Modules — the complete map

**As of 2026-08-01** · 6 packages, 55 modules, 8 workflows, 47 `wf-*` commands, 327 tests.
One line per module: what it does and why it exists. Deeper detail: `gate-reference.md`
(per-gate contracts + exit codes), `HOW-IT-WORKS.md` (the flow in plain language),
`CLAUDE.md` (the sync contract + where workflows live).

The flow these modules implement:

```
team DOCX / Drive link / Discord drop
        │  INTAKE (fleet-wide crons, this repo)
        ▼
pre-flight fix-list ──► content team fixes at handoff, not at emit
        │
        ▼  GENERATE (per-client, button-triggered)
distill → classify → brief → emit_ts ──► typed data + PR in the CLIENT repo
        │
        ▼  GATES (run on that PR, green-on-legacy via the baseline)
19 quality gates ──► Alex merges = the ONLY path to production
        │
        ▼  DEPLOY
build → capture → wrangler deploy → verify-live + cf-crawler → auto-rollback
        │
        ▼  AUDIT / OPS
cycle state, live audits, monthly loops
```

---

## `pipeline/lib` — shared foundation (4)

| Module | What it does |
|---|---|
| `common.py` | Config loader, self-describing client profile (topology, states, shape), `framework_family` + `resolve_build_dir` (Next→`out`, Vite→`dist`, stale-path tolerant), curl helpers, topology URL patterns. Everything else imports this. |
| `baseline.py` | The ratchet. Fingerprints legacy findings (stable across HTML reflow — never line numbers) so gates run **green-on-legacy, red-on-new**. Shrink-only; re-record refuses; growth needs `--accept-new`; five safety gates are hard-coded never-baselineable. |
| `cycle_state.py` | Shared cycle ledger committed in the **client** repo (`docs/cycle-logs/<YYYY-MM>/cycle-state.json`). Two operators claim/mark steps so neither redoes finished work. |
| `client_docs.py` | The client-repo docs contract (work log, cycle-logs, intake-archive) that `client_docs_check` enforces and `scaffold_client_docs` creates. |

## `pipeline/intake` — content in (14)

| Module | What it does |
|---|---|
| `discord_intake.py` | REST-polls the SEO-Team channels (no gateway daemon). DoH DNS override (some ISPs blackhole discord.com). Skips a denied channel instead of aborting. Routing never guesses a client — `unrouted/` is the floor. |
| `discord_notify.py` | Posts the pre-flight digest back into the SOURCE channel — feedback lands where the team already works. Reuses the poller's auth + DoH. |
| `drive_intake.py` | Month-scoped Drive ingest with a version-fingerprint ledger, so a bulk Drive reorg cannot make six months of old content look new. |
| `client_handoff.py` | **The last hop (the operator's 2026-08 PR-only override).** Retrieved DOCX → `cycle/<slug>-<YYYY-MM>` branch + monthly intake PR on the client repo (body = pre-flight fix list) + cycle-emit dispatch on that branch. Idempotent by content sha; never touches a default branch, never merges; inert without `CLIENT_REPOS_TOKEN`. |
| `drive_survey.py` / `drive_reorg.py` / `drive_cleanup_root.py` | Drive folder mapping, reorg planning/execution, root hygiene. |
| `link_intake.py` / `link_router.py` | The team shares LINKS, not files (78 links, zero DOCX). Ingests shared Doc links; routes by Drive folder first, then brand/domain content signature; **refuses when folder and content disagree**. |
| `preflight_docx.py` | **The handoff gate.** Turns a team DOCX into a plain-English fix-list (exact sentence, why, suggested rewrite — using each client's own phrasing rules). Contract: it must PREDICT emit-time refusals exactly, so every check is the emitter's own code. |
| `validate_docx_intake.py` / `verify_docx_coverage.py` | DOCX sanity + section-coverage checks. |
| `bootstrap_drive_oauth.py` | One-time browser OAuth for a **read-only** Drive token. |
| `roster.py` | Client roster loading (slug = `client_slug` in the client repo config — canonical per Alex 2026-07-31). |

## `pipeline/generate` — the emitter (6)

| Module | What it does |
|---|---|
| `distill.py` | DOCX → structured `PageDraft`s. Handles three authoring layouts in one document (labelled / unlabelled-after-H1 / markerless hero). Core-body distillation to the 800–1500 band. Fails LOUD: unsegmentable doc = exit 16, state-ambiguous slug on a multi-state client = block, never "confident but wrong". |
| `classify.py` | NEW / UPDATE / SKIP / INVALID per draft against the live site data — a cycle never silently duplicates or clobbers a page. `--strict-topology` rejects off-pattern URLs outright. |
| `brief.py` | §19 fan-out briefs (`docs/briefs/*.json`): ≥6 fan-out queries, capsule, semantic triples, proprietary variable from the client's allow-list (never fabricated). Reads BOTH keyword schemas — flat and Crestline's per-state `states[]` nesting. |
| `validators.py` | V1–V6 constraints (hero 25w/2s/160ch with hook extraction, title band, em-dash, Title Case, card-grid counts 3/4/5/6, alt text) + produce-by-construction §20/§21. Severity model: BLOCK (would ship harm) vs CURATE (human call — page HELD, never suppresses siblings). |
| `emit_ts.py` | Writes validated drafts into the client's REAL typed data files (anchor-spliced, byte-idempotent), wires an inbound link so no emitted page is ever an orphan, registers routes. Exit contract: 0 clean · 1 shipped-with-flags · 15 held for curation · 9 refused · 16 unsegmentable. Cross-checks `EMIT_SUMMARY` against exit status and refuses on disagreement. |
| `models.py` | `PageDraft` + `to_ts_entry` (real TS shape) + `to_brief`; the bands (standard §04/§02); `CURATION_CODES ∩ HARM_CODES = ∅` asserted at import. |

## `pipeline/gates` — the 19 quality gates

Baseline-aware unless marked ⛔ (never baselineable — legacy debt is still live liability).

| Gate | Checks | 
|---|---|
| ⛔ `forbidden_sweep.py` | The legal gate. Union of YAML regex rules + `banned-phrases.txt` (per-client), `<script>`-masked so RSC payloads can't false-positive, fails LOUD on an empty ruleset, and lints wrong-file rule placement (the "fails silently" footgun). |
| ⛔ `rules_selftest.py` | The ruleset's OWN gate: every union pattern compiles, no dead regex lines in the txt ledger (BUG-018), no plain line defeating a YAML lookahead exception (free-system class), case audit (BUG-019), and per-client `docs/rule-fixtures.yml` must_match/must_not_match proof samples run through the production matcher. |
| ⛔ `orphan_check.py` | Every sitemap URL has ≥1 inbound internal link (the original Acme bug). |
| ⛔ `parity_check.py` | sitemap == built routes == llms.txt. |
| ⛔ `fingerprint_check.py` | Invisible/zero-width/bidi characters in raw bytes (AI-clipboard fingerprints). |
| ⛔ `audit_ssr.py` | No unguarded `window`/`document` in server-rendered paths (the blank-shell disasters). |
| `capsule_check.py` | §20: interrogative H2 → answer-first → TL;DR (only >1500w, per standard §01). |
| `noncommodity_check.py` | §21: proprietary variable per page + sibling 5-gram overlap thresholds. |
| `brief_fanout_check.py` | §19 brief completeness. |
| `check_headings.py` | Title Case, no possessive contractions. |
| `em_dash_check.py` | No em dashes in public text (script/style-stripped, line-preserving). |
| `llms_sales_purge.py` | llms.txt carries no sales/CTA copy (§30). |
| `image_budget_check.py` | Per-tier image byte budgets (hero/content/thumb). |
| `lcp_hygiene_check.py` | No lazy-loaded declared hero; `<img>` width/height present. |
| `pages_are_data_check.py` | Pages are data + templates, not bespoke TSX (Lesson 1). |
| `robots_aicrawler_check.py` | robots.txt allows every CITATION crawler (training-bot blocking is fine). |
| `audit_built.py` | The 30-point per-page checklist (meta bands, schema, links, uniqueness…). Bands = the Content Team Operating Standard, config-overridable. |
| `client_docs_check.py` | The client-repo docs contract is present. |
| `validate_multistate_config.py` | Multi-state config addendum consistency. |

## `pipeline/deploy` — ship + recover (5)

| Module | What it does |
|---|---|
| `verify-live.sh` | Post-deploy: routes return 200 + expected content (retry-tolerant, WAF-aware UA). |
| `cf-crawler-check.sh` | Post-deploy: all AI **citation** bots (OAI-SearchBot, Claude-SearchBot, PerplexityBot, Bingbot, Googlebot, ChatGPT-User) reach the live edge — the silent-AEO-kill check. |
| `cf-rollback.sh` | Capture the live deployment id pre-deploy → on failed verification, promote it back and independently re-verify. Only ever promotes an EXISTING deployment — no second path to prod. |
| `proof-assert.sh` | Blocking meta-gate: the deploy proof exists and is non-empty ("no proof = it didn't happen"). |
| `indexnow_submit.py` | The one IndexNow submitter (gated on a healthy deploy, never at build time). |

## `pipeline/audit` — ops + client state (10)

`client_profile.py` (who/shape/states/build — the pipeline's front door) · `cycle_status.py` (the claim/mark CLI) · `preflight.py` (config completeness, exits 11–14) · `audit_live.py` / `poll_live.py` (live-site audits) · `gbp_baseline.py` (GBP snapshot) · `bootstrap_config.py` / `scaffold_client_docs.py` (client onboarding) · `setup_gtm_foundation.py` (GA4/GTM provisioning) · `update_sitemap_dates.py` (lastmod hygiene).

## `.github/workflows` — the runtime (8)

| Workflow | Where it runs | Trigger |
|---|---|---|
| `intake-poll.yml` | THIS repo (fleet-wide) | hourly cron — Discord drops → pre-flight → digest back to the channel; skips green until secrets exist |
| `drive-poll.yml` | THIS repo (fleet-wide) | every 3h — Drive/link ingest for every client in one run; with `CLIENT_REPOS_TOKEN` set, the HANDOFF stage then opens the monthly intake PR per client and dispatches cycle-emit (PR-only, never main) |
| `ci.yml` | THIS repo | every push/PR — the 274-test suite on 3 Pythons |
| `quality-gate.reusable.yml` | called by client repos `@tag` | every client PR — build once, run all gates with the client's baseline |
| `preview.reusable.yml` | called by client repos | client PR — Cloudflare preview + verify |
| `cycle-emit.reusable.yml` | called by client repos | **workflow_dispatch only** — started by a human or by drive-poll's handoff stage (on the cycle branch); distill→classify→brief→emit→PR; 9/16 = no PR, fail loud |
| `deploy.reusable.yml` | called by client repos | push to client main (= the operator's merge) — build, capture, deploy, verify, auto-rollback, proof, IndexNow |
| `seo-health.reusable.yml` | called by client repos | daily — live-site monitor, never blocks |

## `config/`

`client-config.starter.yml` (sanitized onboarding template) · `discord-intake.yml` (channel→slug map; canonical slugs; Pat's shared channel disambiguates by hints or refuses) · `drive-intake.yml` (per-client Drive roster, exact folder ids) · `discord-intake.example.yml`.

## The two layers that are not code

- **Client repos** — each is its own source of truth (Model A): `docs/client-config.yml`, `docs/gate-baseline.json`, cycle logs, rule ledgers, thin workflow callers pinned `@tag`.
- **The judgment layer** — operators in Claude sessions handle everything NOVEL (new doc formats, rule conflicts, misfiled content); the content team fixes copy; **the operator's PR merge is the only path to production, by design**. The modules handle the known; humans handle the new.
