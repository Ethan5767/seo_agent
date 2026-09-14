# Pipeline Modules — the complete map

**As of 2026-09-14 (v3.2.0)** · 9 packages, 84 modules, 5 workflows, 41 `wf-*` commands, **1,308 Python tests (all pass) + 459 web tests (all pass)**. Counted on 2026-09-13, not carried forward: `find pipeline -name '__init__.py' | wc -l`, `find pipeline -name '*.py' ! -name '__init__.py' | wc -l`, `ls .github/workflows/*.yml | wc -l`, the `wf-` entries under `[project.scripts]`, `pytest -q` and `npm test`. The line this replaced read "As of 2026-08-10 · 5 packages, 40 modules · 720 tests" — more than a month stale, and wrong about the package count by four. The six 2026-09-12 subsystems previously listed as UNVERIFIED are still unverified **against a live network**, which is a different claim from untested — see the CHANGELOG.
(Counted, not remembered: modules = `.py` under `pipeline/` excluding `__init__.py`;
commands = `[project.scripts]` in `pyproject.toml`; tests = `pytest -q`. Only the test
count moved on 2026-08-10 — `--recommend` is a flag on an existing command, and
`crawler-check.sh` is a rename, not a new module.)
One line per module: what it does and why it exists. Deeper detail: `gate-reference.md`
(per-gate contracts + exit codes), `HOW-IT-WORKS.md` (the flow in plain language),
`CLAUDE.md` (the sync contract + where workflows live).

**v3 deleted the DOCX rail.** `pipeline/intake` (Discord, Drive, DOCX pre-flight) and
`pipeline/generate` (distill → classify → brief → emit_ts) are gone, along with the
two fleet-wide cron workflows and `cycle-emit`. Claude Code is the only writer now.
See `SITE-AUDIT-PIPELINE.md` §3 for what was removed and why.

The flow these modules implement:

```
GitHub repo (collaborator access) + domain
        │  ONBOARD      wf-onboard ──► clone, config, preflight, profile, docs
        ▼               stops at the interview; re-run resumes
        │  MEASURE      wf-site-health ──► docs/audit/<YYYY-MM>/findings.json
        ▼
        │  PLAN         wf-site-plan ──► worklist.json + report.md
        ▼               (RESOLVED / PERSISTING / NEW / REGRESSION)
        │  REMEDIATE    wf-site-remediate ──► Claude Code edits, in tier ──► changelog.json
        ▼               ─── everything above runs locally, in a container ───
        │  GATES        20 quality gates on the client PR (green-on-legacy via the baseline)
        ▼
        │  HUMAN MERGE  Alex merges = the ONLY path to production
        ▼               ─── THE PIPELINE ENDS HERE (PR-terminal, 2026-08-10) ───
        │               deployment is the operator's, on the client's own platform
        │  MONITOR      seo-health, daily + on demand: live routes, sitemap,
        ▼               AI citation crawlers at the edge. never blocks.
        │  AUDIT / OPS  wf-dashboard, monthly cycles
```

`deploy.reusable.yml` and `preview.reusable.yml` still exist and still work, but they
are **Cloudflare Pages only and opt-in per client** — not part of the default rail.
The standard pair to copy into a client repo is `quality-gate.yml` + `seo-health.yml`.

---

## `pipeline/lib` — shared foundation (5)

| Module | What it does |
|---|---|
| `automerge.py` | **The auto-merge decision brain** (automation spine). `decide(gate_results, tier, creates, text, policy)` → `AUTO` or `HUMAN` with a reason, on the escalate-when-unsure rule: only an all-gates-green, low-risk change on an opted-in client reaches `AUTO`. Low-risk = tier `T1` AND no file created AND no medical/legal (YMYL) claim in the changed text. `AutoMergePolicy` is frozen and defaults OFF; `risk_level` and the `YMYL_TERMS` frozenset live here. The rules, as data + one pure function — the CI entry (`automerge_gate.py`) and the E2E both call it, so there is one definition of "safe to merge". |
| `common.py` | Config loader, self-describing client profile (topology, states, shape), `framework_family` + `resolve_build_dir` (Next→`out`, Vite→`dist`, stale-path tolerant), curl helpers, topology URL patterns, and the **tiering block** (v3 §2): `tier`/`text_paths`/`content.*` parsed into the profile, `DEFAULT_DENY` unioned in so a config cannot shrink the floor, `detect_static_export` for the §6 precondition. Everything else imports this. |
| `baseline.py` | The ratchet. Fingerprints legacy findings (stable across HTML reflow — never line numbers) so gates run **green-on-legacy, red-on-new**. Shrink-only; re-record refuses; growth needs `--accept-new`; five safety gates are hard-coded never-baselineable. |
| `score.py` | The SEO and AEO score, and cycle progress. A pass rate over **(page, check) pairs**, so one broken check on one page costs one pair rather than 1158 (B-009); a config-gated check that never ran leaves the DENOMINATOR rather than counting as a pass; and an unmeasured cycle is `None`, never 100. Also `progress()` — the "how many findings are left" answer — and `series()`, the one definition of the score over time that the chart and any report both read. |
| `atomic.py` | **How every cycle artifact is written.** `write_atomic` / `write_json_atomic`: sibling temp file, fsync, `os.replace`, fsync the directory. A plain `write_text` truncates to zero bytes before writing, and a truncated `findings.json` reads to the ratchet as a site with no findings (B-089). Serialises before touching the file, so an unencodable document fails with the previous artifact intact. |
| `html.py` | **The only HTML/sitemap reader.** `sitemap_locs` (every `<loc>`, case-insensitive, namespace-prefixed and CDATA forms included, entities decoded, empties dropped, order and duplicates kept), `page_title` (first `<title>`, decoded, markup left alone because a title is RCDATA; `None` and `""` stay different facts), `inner_text` (tag-stripped, for elements that really do contain markup — the `<h1>` case), `decode_entities`. Replaced eight `<loc>` regexes and four `<title>` regexes that disagreed with each other; **none of the eight decoded `&amp;`** (B-086). `tests/test_lib_html.py` fails the build if any module under `pipeline/` grows its own. |
| `client_docs.py` | The client-repo docs contract (work log, cycle-logs, intake-archive) that `client_docs_check` enforces and `scaffold_client_docs` creates. |

## `pipeline/gates` — the 20 quality gates

**16 inherited + the 3 agent-authorship gates (v3 phase 4).** `pages_are_data_check`, `brief_fanout_check` and `validate_multistate_config` were deleted with the emitter; see `SITE-AUDIT-PIPELINE.md` §3.

Baseline-aware unless marked ⛔ (never baselineable — legacy debt is still live liability).

| Gate | Checks | 
|---|---|
| ⛔ `tier_check.py` | **The gate that makes tiering real.** Walks the PR diff and refuses any path or operation the declared tier does not permit. The deny floor applies at every tier, T3 included, and is unioned in from `DEFAULT_DENY` so a config cannot shrink it. A rename is judged as a delete plus a create. Exit 17. |
| ⛔ `claim_provenance_check.py` | **Derivation only, never invent.** Refuses changed text carrying a rating, review count, licence number, year-count, warranty term, price or superlative that traces to no config field, no work-item evidence, no citation, and not to the previous version of the file. Empty corpus = exit 4, same rule as the forbidden sweep. Exit 18. |
| ⛔ `acceptance_check.py` | **The loop-closer.** Re-runs each fix `changelog.json` CLAIMS against the build output using `measure.check_page` itself, and refuses when the finding still fires. A claimed URL with no built page refuses too — silence is not proof. Exit 20. |
| ⛔ `e2e_check.py` | **The whole-pipeline handoff gate (#20).** Re-reads `findings.json → worklist.json → changelog.json` for a cycle and asserts each is a strict refinement of the last: every planned item traces to a measured finding, every remediation entry to a planned item, schemas match. A partial or empty chain is exit 4 (cannot judge), never a pass. Exit 21 on a break. `--only-if-claimed` (how CI invokes it) makes a PR with no `changelog.json` not-applicable rather than unjudgeable, while a changelog WITHOUT its findings and worklist stays a break — a fix that traces to nothing. `wf-e2e-check`. **WIRED 2026-09-13** as the `CHAIN` step, with 29 tests (`test_e2e_check.py`, `test_e2e_wiring.py`). |
| ⛔ `forbidden_sweep.py` | The legal gate. Union of YAML regex rules + `banned-phrases.txt` (per-client), `<script>`-masked so RSC payloads can't false-positive, fails LOUD on an empty ruleset, and lints wrong-file rule placement (the "fails silently" footgun). |
| ⛔ `rules_selftest.py` | The ruleset's OWN gate: every union pattern compiles, no dead regex lines in the txt ledger (BUG-018), no plain line defeating a YAML lookahead exception (free-system class), case audit (BUG-019), and per-client `docs/rule-fixtures.yml` must_match/must_not_match proof samples run through the production matcher. |
| ⛔ `orphan_check.py` | Every sitemap URL has ≥1 inbound internal link (the original Acme bug). |
| ⛔ `parity_check.py` | sitemap == built routes == llms.txt. |
| ⛔ `fingerprint_check.py` | Invisible/zero-width/bidi characters in raw bytes (AI-clipboard fingerprints). |
| ⛔ `audit_ssr.py` | No unguarded `window`/`document` in server-rendered paths (the blank-shell disasters). Scans every JS/TS file in the repo minus a **denylist** (node_modules, framework caches, build output incl. the client's configured one, public/static/vendor/docs, `*.min.js`) — never an allowlist keyed on framework, which would scan nothing for a framework the code has not met. It looked only in `src/` and exited 0 when absent until 2026-08-10, which is `create-next-app`'s default layout (B-027). Zero source files found is exit **4**, never a pass; WordPress keeps its exit-0 skip because *not applicable* ≠ *cannot judge*. |
| `capsule_check.py` | §20: interrogative H2 → answer-first → TL;DR (only >1500w, per standard §01). |
| `noncommodity_check.py` | §21: proprietary variable per page + sibling 5-gram overlap thresholds. |
| `check_headings.py` | Title Case, no possessive contractions. |
| `em_dash_check.py` | No em dashes in public text (script/style-stripped, line-preserving). **Baselineable since B-008** — a legacy em dash in the client's own copy is content debt of the same class as a heading that is not in Title Case, and it emits `Finding`s so the ratchet can hold it. Fingerprint is the offending TEXT, so a line moving does not re-block the PR. |
| `llms_sales_purge.py` | llms.txt carries no sales/CTA copy (§30). |
| `image_budget_check.py` | Per-tier image byte budgets (hero/content/thumb). |
| `lcp_hygiene_check.py` | No lazy-loaded declared hero; `<img>` width/height present. |
| `robots_aicrawler_check.py` | robots.txt allows every CITATION crawler (training-bot blocking is fine). |
| `audit_built.py` | The 30-point per-page checklist (meta bands, schema, links, uniqueness…). Bands = the Content Team Operating Standard, config-overridable. |
| `client_docs_check.py` | The client-repo docs contract is present. |

## `pipeline/deploy` — ship + recover (5)

| Module | What it does |
|---|---|
| `verify-live.sh` | Post-deploy: routes return 200 + expected content (retry-tolerant, WAF-aware UA). |
| `crawler-check.sh` | All AI **citation** bots (OAI-SearchBot, Claude-SearchBot, PerplexityBot, Bingbot, Googlebot, ChatGPT-User) reach the live edge — the silent-AEO-kill check. **Not Cloudflare-specific** despite being born there and being called `cf-crawler-check.sh` until 2026-08-10: it is curl plus a UA list against a live URL. Now runs in `seo-health.reusable.yml` on the daily schedule, since a PR-terminal pipeline has no deploy job to hang it off. |
| `cf-rollback.sh` | Capture the live deployment id pre-deploy → on failed verification, promote it back and independently re-verify. Only ever promotes an EXISTING deployment — no second path to prod. |
| `proof-assert.sh` | Blocking meta-gate: the deploy proof exists and is non-empty ("no proof = it didn't happen"). |
| `indexnow_submit.py` | The one IndexNow submitter (gated on a healthy deploy, never at build time). |

## `pipeline/audit` — measure, plan, write, onboard (15)

`onboard.py` (**the front door** — a repo and a domain in, a worklist out; sequences the six onboarding commands and translates their exit codes. Checks with `gh` what permission we actually hold rather than assuming it, because the flow is "the client adds us as a collaborator". Stops at the interview step — the TODOs no generator can invent — reports it as RESUMABLE rather than failed, and continues from there on a re-run — `wf-onboard`) · `client_profile.py` (who/shape/states/build) · `preflight.py` (config completeness, exits 11–14) · `measure.py` (live-site measurement, returns typed Findings — `wf-site-health`) · `plan.py` (the ratchet over the monthly cycle folders: RESOLVED / PERSISTING / NEW / REGRESSION, `worklist.json` + `report.md` — `wf-site-plan`) · `remediate.py` (**the writer** — hands each work item to Claude Code one at a time so the file→item map in `changelog.json` is a measurement rather than a claim; judges every touched file with the same `tier_verdict` the PR gate uses; hard `--max-items` / `--max-files` caps that stop cleanly. **`--recommend`** is the same loop with the opposite assertion — the tree must come back CLEAN — writing a brief for a human to paste into a CMS instead of a fix, into the standing `docs/audit/human-worklist.md`; a briefed fingerprint leaves the fix queue for good, which is what closes B-025's pay-for-the-same-refusal-every-cycle leak — `wf-site-remediate`) · `providers.py` (CrUX field CWV, Search Console CTR + cannibalization, DataForSEO on-page crawl, Bright Data SERP rank/absence over the config's `seed_queries` — the one thing GSC cannot see, since it reports only queries that already have impressions; credentials from the environment only, and a provider with no credentials returns a **named skip** that is written into the artifact so a skip is never mistaken for a clean measurement) · `seed_queries.py` (**the query list** — crawls the client's own titles and h1s, hands those facts to Claude Code with an expansion-and-intent recipe adapted from `AgriciDaniel/claude-seo` (MIT), prints a YAML block a human pastes, or (`--write`) appends specific terms directly — same human-commit requirement either way. Deliberately NOT a flag on `wf-site-health`: `Finding.context` is fingerprinted, so a list regenerated each cycle re-files every SERP finding as NEW and makes RESOLVED unreachable — this is also why `--write` only appends, never regenerates. Drops the bare brand name — you always rank first for your own name, so that entry buys a permanently green finding at full price — `wf-seed-queries`) · `poll_live.py` (post-deploy polling) · `bootstrap_config.py` / `scaffold_client_docs.py` (client onboarding) · `snapshot.py` (**the render source** — crawls a rendered deployment into the `<dir>/index.html` tree the nine build-tree gates already glob, so a client with no static export can be gated at all. v3 sharp edge #4: `lee-series-web` emits no route tree, `build-site` exits 1, and all nine were SKIPPED — including `forbidden_sweep`, never-baselineable for legal exposure. Refuses at exit 19 and writes nothing when no page answered, because an empty build dir makes every gate glob zero files and report green — `wf-render-snapshot`) · `update_sitemap_dates.py` (lastmod hygiene) · `automerge_gate.py` (**the CI-side auto-merge decision** — `wf-automerge-decide`. Derives the risk inputs from the real PR diff: declared tier from the config, created files and changed copy from `git diff base..head`, then runs `lib/automerge.decide`. Writes `decision=AUTO|HUMAN` to `$GITHUB_OUTPUT`; never merges, never fails the run. Two scopings that keep it honest: the YMYL check reads the ADDED copy, not the whole page, so an incidental word can't block a safe edit; and `public_creates()` drops `docs/`, because the audit trail ships in every remediation PR by design (Model A) and must not read as a new page. The `auto-merge` job in `quality-gate.reusable.yml` reads its output and runs `gh pr merge` only on `AUTO`, only when `automerge_enabled` is set — off for the fleet by default) · `logparse.py` (**crawl-budget from the access log** — parses Apache/Nginx combined and Cloudflare JSON into `log.crawl_error` / `log.byte_overhead` Findings attributed to known crawler UAs; standalone `wf-logparse` or folded into `wf-site-health --with-logs`; a missing/empty/unattributable log is a named skip, never a green. UNVERIFIED 2026-09-12) · `deliver.py` (**the report leaves the pipeline** — renders a cycle report to an outbox preview for human review, and only `--send` transmits over email/telegram; SMTP/Telegram creds by env name, recipients in the client config `delivery:` block, every unconfigured path a named skip — `wf-deliver`. UNVERIFIED 2026-09-12).

Also this cycle (2026-09-12, UNVERIFIED): `plan.py` now writes `report-progress.md` + `report-action.md` beside `report.md` (SOP §10 two-report split); `measure.py` gained `health.csr_empty_shell` (CSR shell detection ported from the scanner) and the `--with-logs` hook.

## `skills/site-remediation` — the doctrine the writer is given

`SKILL.md` is inlined into every remediation prompt: derivation only (never invent a rating, a licence, a year-count or a superlative), fix exactly one finding, stay inside the tier, where content actually lives, the per-finding definition of "fixed", the house writing standards, and the T2/T3 rules. `references/anti-slop-prose.md` and `references/serp-title-meta-craft.md` are the ported distiller doctrine; `references/page-type-shapes.md` gives the section shape of a service, location, blog, hub, FAQ or case-study page for the T2 agent that has to write one, with the provenance-risk sections named. All three are reachable by the agent through `--add-dir` on the skill directory.

## `pipeline/dashboard` — the local operator console (3 + static)

`server.py` (`wf-dashboard`) — the command allow-list, the `Run` class and the HTTP handler; `state.py` — what the console KNOWS, derived from files on disk (discovery, git state, the cycle bundle, the score, and `next_action`'s eight stages), with no HTTP in it; `review.py` — GATE 2 and the git actions, where approving is `git add`. Together: a `127.0.0.1` web UI over the artifacts client repos already hold. Stdlib only; holds no state, and stores no credential — the optional GitHub token on the Add Client form is passed to that one `wf-onboard` subprocess as `GH_TOKEN` and is never written to argv, the run log or disk. Clients are discovered by scanning `--clients-dir` for git repos containing `docs/client-config.yml`, so there is no roster to maintain; **Add Client** on the fleet screen runs `wf-onboard <owner/name> <domain>` into that directory, which is the only run that has no client yet. Runs are launched from a **fixed command allow-list** (never a shell string) and streamed over SSE; git actions stop at the PR — there is no merge action to call. The fleet card carries each client's baseline state, because a client with no `docs/gate-baseline.json` runs the gates bare. The client screen carries a **stage rail** — the eight stages and the three human gates, derived from the artifacts on disk — so one screen answers "what do I do now" instead of nine screens each showing an artifact; plus the SEO/AEO score and a chart of it per cycle (measured solid, projected dashed, verified only when `acceptance_check` can actually run). **Review Diff** is Gate 2: per-item diffs where approving is `git add`, so the git index IS the approval record and there is no parallel state to drift. Items that touched the same file are one approval unit, because those diffs are not separable. `static/` holds the ten screens (fleet · client · findings · worklist · **review** · report · changelog · runs · git · config) as plain HTML + `app.js` + `chart.js`, no build step.

## `pipeline/scanner` — the URL-audit web MVP (8)

The backend behind `wf-scan-web`: paste a URL (+ optional repo, + Model A/B), get an SEO + AEO + performance + technical + site-wide + DataForSEO audit and — with a repo — a Model A brief or a Model B fix + auto-merge decision. Same rails as `pipeline/dashboard` (127.0.0.1, stdlib `http.server`, no DB, no accounts, no secrets on disk). **Measure rule: DataForSEO for anything it has a tool for; our own only for gaps.** Streams one card per tool over ndjson, each with exact cost.

| Module | What it does |
|---|---|
| `recommendations.py` | `RECOMMENDATIONS` — a plain-English *why it matters / how to fix* per finding code, with a safe generic fallback. Advisory copy only. |
| `audit.py` | Pure row assembly (no HTTP/network): `seo_rows` (full checklist via `measure.check_page`, passes shown too), `aeo_rows` (robots citation-crawler + LocalBusiness schema + answer-first structure — the gap DataForSEO has no tool for), `perf_rows` (from `providers.crux_metrics`, honest disabled/no-data rows), and `assemble(groups: dict)` → report keyed by `GROUP_KEYS` + a 0-100 score. |
| `extra_checks.py` | `tech_rows` — the technical checklist DataForSEO's per-page audit doesn't front (HTTPS, viewport, lang, Open Graph, Twitter card, favicon, **SSR-vs-CSR rendering** via `visible_text_ratio`, sitemap, structured-data inventory). |
| `crawl.py` | Free HTML crawler (BFS + sitemap) + `site_rows` — **retired from Measure** (couldn't see JS menus → false orphans; DataForSEO's crawl replaced it). Kept + tested for reference/fallback. |
| `dataforseo.py` | The DataForSEO client + one pure parser per tool: `cost_of`/`result_items`/`_tool` primitives; `site_audit` (on-page crawl → Site Health), `ranked_keywords`/`domain_overview`/`serp_rank`/`rankings` (Rankings), `search_volume`/`keyword_ideas`/`keyword_gap`/`competitors`/`keywords_card` (Keywords), `llm_mentions` (AI Visibility). Parsers unit-tested offline with canned responses; exact cost from each response's `cost` field. |
| `progress.py` | Live scan progress without threading callbacks through providers: `reporting(sink)` (a context variable, safe on the threaded server) around each tool, `emit(text, **detail)` from inside it. `dataforseo.call` reports each request's start, finish (ms, cost) or error; `crawl_onpage` reports DataForSEO's real `pages_crawled` / `pages_in_queue` from the free summary poll. Streamed as `{tool, state: "progress"}` events to the web live panel. |
| `config.py` | `ensure_config` — scaffolds a minimal `docs/client-config.yml` for a repo that has none (folds in the Onboard profile: business, keywords→seed_queries, competitors, goal). Existing config untouched. |
| `run.py` | `run_cycle(repo, url, model)` — Model A brief / Model B fix→commit→diff→`automerge_gate.decide_pr`. |
| `server.py` | `wf-scan-web` — `http.server`; `GET /`+`/static/*` (zero-dep fallback page), `POST /scan` streams ndjson (one `{tool}` card event per tool, then `{result}`). `build_report` runs a `TOOLS` descriptor table in a loop (adding a tool = one row); auto-loads `.env`; the same JSON the Next.js front end (`web/`) calls. |

## `pipeline/seed` — the brand-mention seed engine (5)

The complement to `scanner/mentions.py` (which *measures* where a brand is cited): given a `gaps.json` from the measure agent, it *creates* brand-mentioning topics — auto-posting to safe platforms, queuing strict ones for human approval, never Wikipedia. Same discipline as `providers.py`: one flat module per concern, pure parse/build functions with an injectable side-effecting caller, every skip loud. Generation runs on the operator's `claude` CLI subscription (no API key). MVP posts via a stub (no external accounts). CLI: `wf-seed --gaps gaps.json [--out-dir .] [--drafts-dir ./drafts] [--live]`. Design: `docs/superpowers/specs/2026-09-07-brand-seed-engine-design.md`.

| Module | What it does |
|---|---|
| `tiers.py` | The safety rule as data. `GREEN` (medium/devto/hashnode/tumblr/blogger/**reddit**, auto-post) · `YELLOW` (quora, draft→approve) · `RED` (wikipedia, never) · `tier_of()` returns `green/yellow/red/unknown`. Unknown is NOT green on purpose — a typo or new platform must fall through to a loud skip, never to auto-posting. Reddit is green by operator opt-in (brand-mention reach) but keeps its own draft-first gate in the poster given shadowban risk. |
| `gaps.py` | `Gap` dataclass + `parse_gaps(rows)` → `(gaps, dropped)`. Pure. A row missing/blank on any of the six required fields is dropped WITH a `_reason`, never silently — a silent drop would make a run look complete when it seeded fewer gaps than it was handed. Optional fields (`subreddit`, the reddit target) are carried through when present. |
| `generate.py` | `Gap` → `Draft` via the `claude` CLI (`claude -p … --output-format json`) on the user's subscription. `build_prompt`/`parse_result` pure (parse survives bare and ```json-fenced output); the subprocess is injectable as `run` so the suite is offline. |
| `posters.py` | `PostResult` + `slugify` + `write_draft_file` (real yellow action: writes `<platform>-<slug>.md` for human review) + `stub_post` (green stand-in: NO HTTP, records what it *would* post). **Real Dev.to poster**: `build_devto_payload` (pure), `post_devto` (env `DEVTO_API_KEY`, injectable HTTP, loud skip; explicit UA — Dev.to's Cloudflare 403s `Python-urllib`, B-042; draft-first, `published=False`). **Real Reddit poster**: `build_reddit_submit` (pure), `post_reddit` (OAuth2 script-app creds from env `REDDIT_*`, two injectable HTTP calls token→submit, loud skip on missing creds / api-errors / HTTP; draft-first — `--live` posts to the account's own profile `u_<username>`, `--publish` to the gap's `subreddit`; offline-verified, live UNTESTED = no creds). `green_poster(live, publish, ...)` routes green platforms to their real poster, stub fallback for those without one — adding a platform is one branch. |
| `run.py` | `wf-seed`. `dispatch(drafts, dir, poster)` routes by tier; `run_seed(...)` reads gaps.json → skips red/unknown before generation (no wasted claude call, no refusal) → drafts green/yellow → dispatches → writes `seed-log.json` (`mode`, `counts`, `results`, `dropped`). `--live` reserved until real posters land. |

## `pipeline/outreach` — backlink outreach (4)

The SOP §12 add-on, built up to (not including) the send — the outreach email to a site owner is a human step by design, so nothing here transmits. Off unless the client config declares `outreach.enabled: true`. New 2026-09-12, UNVERIFIED (no tests yet).

| Module | What it does |
|---|---|
| `qualify.py` | The 4-point safety check (not-penalized · real-traffic · outbound-links · in-content). The first two derive from DataForSEO's organic footprint; the last two are page-level and marked `manual`. With DataForSEO credentials exported and the kill switch off it makes one paid call per domain (no budget yet, B-124); without them every check is `unknown` and the verdict is a named skip carrying the provider's own status — never a fabricated pass. `qualify_domain(domain, call=)`. |
| `linkbank.py` | The candidate store in the CLIENT repo, `docs/outreach/linkbank.json`. Idempotent `upsert` keyed by domain; `load`/`save`/`bank_path`. |
| `content.py` | Tier-1 (basic LSI) / tier-2 (localized) outreach drafts via the `claude` CLI. `build_prompt` pure, subprocess injected as `run`. Held to the house copy rules (derive-never-invent, Title Case, no em dashes). |
| `run.py` | `wf-outreach --project <repo> [--qualify FILE] [--draft DOMAIN]`. Orchestrates qualify → bank → draft; prints a summary; never sends. |

## `.github/workflows` — the runtime (5)

**No cron workflows.** v3 deleted both fleet-wide pollers with the intake rail, which
took ~2,180 Actions minutes/month with them — the entire argument for making this repo
public. Everything below the PR line still runs in the client repo, on that repo's own
`GITHUB_TOKEN`.

| Workflow | Where it runs | Trigger |
|---|---|---|
| `ci.yml` | THIS repo | every push/PR — the test suite on 3 Pythons |
| `quality-gate.reusable.yml` | called by client repos `@tag` | every client PR — build once, run all 20 gates (plus `tsc --noEmit`) with the client's baseline. `fetch-depth: 0`, because the two diff gates cannot judge a diff they cannot see |
| `preview.reusable.yml` | called by client repos | client PR — Cloudflare preview + verify |
| `deploy.reusable.yml` | called by client repos | push to client main (= the operator's merge) — build, capture, deploy, verify, auto-rollback, proof, IndexNow |
| `seo-health.reusable.yml` | called by client repos | daily — live-site monitor, never blocks |

`.github/actions/build-site` is the composite build step the reusable workflows share;
it shells out to `wf-client-profile` to resolve framework and build dir.
`.github/examples/` holds the thin callers to copy into a client repo.

## `config/`

`client-config.starter.yml` — the sanitized onboarding template `wf-bootstrap-config`
writes from. The Discord and Drive rosters went with the intake rail.

## The container

`Dockerfile` — Python + git + `gh` + Claude Code, the only place all four are guaranteed together. Installed `pip install -e .` deliberately: `package-data` declares `pipeline.deploy/*.sh` and nothing else, so a regular install ships neither `pipeline/dashboard/static/` (resolved via `Path(__file__).parent`) nor `skills/site-remediation/SKILL.md` (resolved via `parents[2]`, outside the `pipeline*` packages entirely). Without `-e` the dashboard 404s every page and remediate silently drops its doctrine.

`run.sh` — runs any engine command inside it with the operator's credentials: `./run.sh wf-onboard acme/site acme.com`. It passes `GH_TOKEN` from `gh auth token` rather than mounting `~/.config/gh` (on macOS the token is in the login keyring, so the mount carries config and no credential), hands plain `git` the same token through `GIT_CONFIG_*` + `gh auth git-credential`, and persists `~/.claude-docker` so a subscription login survives `--rm`. `./run.sh wf-dashboard` is the only form that publishes a port: `-p 127.0.0.1:8765:8765` with `--host 0.0.0.0` bound inside the container.

## The two layers that are not code

- **Client repos** — each is its own source of truth (Model A): `docs/client-config.yml` (including the tier block), `docs/gate-baseline.json`, `docs/audit/<YYYY-MM>/` (findings, worklist, report, changelog — the artifacts ship *inside* the PR), `docs/audit/human-worklist.md` (**standing, deliberately not per-cycle**: pages whose copy lives in a CMS are a fact about the site, not about the month it was measured), rule ledgers, thin workflow callers pinned `@tag`.
- **The judgment layer** — a human raises a client's tier, and does it in a human PR, because `docs/client-config.yml` is on the deny floor and the agent can never raise its own authority. Operators handle everything NOVEL (findings with no acceptance mapping, ambiguous scope, rule conflicts); **the operator's PR merge is the only path to production, by design**. The modules handle the known; humans handle the new.
