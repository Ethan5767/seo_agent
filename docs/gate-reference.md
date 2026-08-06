# Gate Reference

Every gate in the seo-content-pipeline: what it checks, when it runs, whether it blocks, and the exit code it claims.

**Authority:** the exit-code registry in [`PIPELINE-MASTER-BUILD-PLAN.md`](./PIPELINE-MASTER-BUILD-PLAN.md#exit-code-registry-keep-gates-attributable). Gate behaviour and real-world verdicts come from [`VERIFY-REPORT-RUN1.md`](./VERIFY-REPORT-RUN1.md) (full suite run against a real Acme Next 16 build, 103 HTML files / 99 sitemap URLs, 2026-07-19). Doctrine provenance for each content gate is in [`DOCTRINE-GATE-MATRIX.md`](./DOCTRINE-GATE-MATRIX.md).

---

## Stage vocabulary

| Stage | When it runs | Input it reads | Can it block the merge? |
|---|---|---|---|
| **PRE-build** | On the PR, before `npm run build` | Source tree (`src/app`, `src/data`, `docs/briefs/`, `docs/client-config.yml`) | Yes — required PR check |
| **BUILT** | On the PR, against the build output dir (`out/` for Next, `dist/` for Vite) | Rendered HTML, sitemap, robots.txt, llms.txt, image assets | Yes — required PR check |
| **LIVE** | Post-deploy, against the production URL | The live edge (Cloudflare in front of the site) | No — it runs *after* the operator's merge; it fails the deploy job and alerts |

Blocking vs advisory: **BLOCKING** gates are wired into the quality-gate Evaluate loop and turn the PR check red. **ADVISORY** gates report into the sticky PR comment and are never allowed to red a merge.

---

## Exit-code registry

Each gate claims a distinct code so the workflow can name the failing gate from the exit status alone. A new gate **must** claim a code from this registry (or add one) — never reuse another gate's code.

| Code | Claimed by |
|---:|---|
| `0` | Pass (all gates) |
| `1` | Generic gate failure — headings, llms sales-purge, LCP hygiene, image budget, orphan, parity (observed), robots-aicrawler, pages-are-data, proof-assert |
| `3` | Orphan (registry) / forbidden-sweep (observed) / rules-selftest (ruleset defects) |
| `4` | **Empty-ruleset refusal** — forbidden-sweep, rules-selftest and non-commodity refuse to silently pass with zero rules loaded |
| `5` | Parity (registry) / audit-built (observed) |
| `6` | Content capsule (§20) |
| `7` | Non-commodity (§21) |
| `8` | Fingerprint / invisible-Unicode scrub (§17) |
| `9` | Brief fan-out (§19) (registry) / audit-ssr (observed) / **data-gen emitter refusal** |
| `10` | audit-ssr / audit-built (registry) |
| `11`–`14` | `pipeline/audit/preflight.py` — 11 missing config fields · 12 unresolved TODOs · 13 homepage non-200 · 14 Cloudflare challenge |
| `15` | **data-gen emitter: pages HELD for curation** (emitted what it could; held pages did not ship) |
| `16` | **Unsegmentable DOCX** — `distill` / `preflight_docx` / the emitter chain refuse a non-empty handoff that segments to 0 pages (unrecognized page-boundary format). Never reported as "clean". First free code above the fleet. |
| `17` | **Tier violation** — `tier_check`: the PR diff changes a path or performs an operation the repo's declared tier does not permit (or no tier is declared, which permits nothing). |
| `18` | **Unsourced claim** — `claim_provenance_check`: changed text states a fact that resolves to no config field, no work-item evidence, no citation, and not to the previous version of the file. |
| `19` | **Nothing measured** — `wf-site-health`: every source was unreachable. A run that measured nothing must be red, never a green report with zero findings. |
| `20` | **A claimed fix did not land** — `acceptance_check`: a work item `changelog.json` reports as fixed still fires its finding against the build output, or has no built page to check at all. |

### `pipeline/generate/` — the data-gen emitter (not a gate; it feeds them)

The emitter is a writer, not a gate, but it exits on the same registry so an orchestrator can branch on status alone. Authority for this table is the module docstring in [`pipeline/generate/__init__.py`](../pipeline/generate/__init__.py); SPEC-emitter §7 says the same.

| Code | Meaning |
|---:|---|
| `0` | every draft emitted clean |
| `1` | emitted with curation flags — **everything shipped**. The warn flags ride along in the ledger; nothing was withheld. Safe to treat as a pass-with-notes. |
| `2` | usage / input / dependency error |
| `9` | refused to emit — at least one BLOCK finding (forbidden or legal phrase, §21 sibling duplicate, out-of-topology URL, out-of-allow-list proprietary variable, structural/TS corruption). Never waivable in `decisions.json`. Also returned by every module's `--self-test` on failure. |
| `15` | **one or more pages HELD for curation** — the emitter emitted what it could and the held pages did **not** ship. NOT green. CI must treat `15` as "requires acknowledgement", never as pass. The held pages, their offending text and a concrete proposed fix are in `docs/briefs/_curation.md`. |
| `16` | **unsegmentable input** — `distill` produced no pages, or `emit_ts` was handed a drafts file with zero entries. Refuses rather than report a clean emit that shipped nothing. Shared with `distill` (`UNSEGMENTABLE_EXIT`). |

**The orchestrator is real now:** `.github/workflows/cycle-emit.reusable.yml` branches on exactly this table — `0`/`1`/`15` commit and open a PR, `9`/`16`/`2` open none and fail the run with the curation queue as the artifact. It also cross-checks `EMIT_SUMMARY` against the process exit status and refuses if they disagree. `tests/test_cycle_emit_workflow.py` executes that workflow's own verdict script against every code here, so this table and the CI behaviour cannot drift apart silently.

Most severe wins: `9` > `15` > `1` > `0`. Every outcome owns a distinct code so an orchestrator can branch on exit status alone. Belt and braces: the emitter also prints a stable parseable line, `EMIT_SUMMARY emitted=N held=N blocked=N flagged=N exit=N`, carrying the same verdict.

> Corrected 2026-07-21 (MINOR-1): `emit_ts.py` previously returned an undocumented `3` on refusal, which collides with forbidden-sweep's observed code and contradicted `__init__.py`, SPEC §7 and `brief.py`. All four sources now read `9`.

> Corrected 2026-07-21 (M3): `1` previously meant BOTH "emitted, some warn flags" AND "one or more pages HELD and did not ship", so an orchestrator branching on exit status alone could not tell shipped from not-shipped. Held now claims its own code, `15` — the first free code in the fleet, since `1`–`10` are the gate registry's and `11`–`14` are `pipeline/audit/preflight.py`'s. `1` now means shipped-with-flags only. Same defect class as the 3-vs-9 bug above; fixed before the CI wiring landed. Registry, `pipeline/generate/__init__.py`, `SPEC-emitter.md` §0/§7 and the CLI `--help` all agree.

> **Known drift (do not "fix" without a decision):** Run #1 observed several gates exiting on a code other than the one the registry assigns them — orphan exited `1` (registry says `3`), forbidden-sweep exited `3` (registry says `4` only for the empty-ruleset case), audit-ssr exited `9` (registry says `10`), audit-built exited `5` (registry says `10`). The registry is the intended contract; the observed column below records what actually happened so nobody debugs a phantom. Reconciling the two is a code task, not a doc task.

---

## Baseline + ratchet (pre-existing debt vs new regression)

A proven gate is still unusable as a *blocking* PR check while a client's LEGACY content fails it en masse — on the Acme pilot, capsule 60/61 pages, non-commodity 31/61, image-budget 37/63, plus 132 audit-built findings. The only two settings used to be "block every PR forever" or "advisory, enforce nothing"; both enforce nothing. `pipeline/lib/baseline.py` adds the missing third setting: **record today's findings once, then block only findings that are NOT in that record.** The recorded debt stays visible and countable, and it can only shrink.

- **Recorder / ratchet CLI:** `wf-gate-baseline` (`pipeline.lib.baseline:main`).
  - `wf-gate-baseline --project DIR --out docs/gate-baseline.json` records every current finding for the baselineable gates. The baseline is **CLIENT state** (Model A) — commit it to the client repo, never to this one.
  - Each baselineable gate gains `--baseline PATH`: a finding in the baseline is reported **PRE-EXISTING** and does not fail; a finding absent from it is **NEW** and does. Output states plainly `N pre-existing (ignored), M new (blocking)`, and the gate exits non-zero only on M.
  - `wf-gate-baseline --project DIR --check` is the CI ratchet: it **fails** on new findings and **reports (does not fail)** baseline entries that have been fixed, prompting a `--refresh`. Refreshing drops fixed entries for free; **adding** an entry requires an explicit `--accept-new`, so a regression can't be laundered into the accepted set by re-running the recorder.
- **Stable fingerprints:** a finding is identified by `gate | code | location | normalized-context`, never by line number or any measured quantity (bytes, word counts, overlap ratios). Two runs over an unchanged site produce byte-identical baselines (verified: 322/322 fingerprints match across independent recordings). A finding merely *getting worse* therefore never silently reclassifies as new.

### Which gates are baselineable — and why the split is hard-coded

The exclusion list is hard-coded in `pipeline/lib/baseline.py`; attempting to baseline an excluded gate is a **loud error (exit 3)**, never a silent skip, and a baseline *file* that smuggles in an excluded-gate entry is rejected on load. Baselining is a decision to keep shipping a known-bad thing — acceptable only for *content debt* that harms nobody today, never for a live liability or a correctness/integrity failure whose damage compounds with time. **Do not widen `BASELINEABLE` casually** — see the module docstring; it is a documented human decision in a PR, not a convenience during a red build.

| Gate | Baselineable? | Reasoning |
|---|:---:|---|
| `forbidden-sweep` | **NEVER** | Legal exposure. A pre-existing banned phrase is a *live liability* that has been accruing risk the whole time — not legacy debt. Baselining it would formally sign off on shipping it. |
| `audit-ssr` | **NEVER** | Correctness. SSR-unsafe `window`/`document` is a runtime crash / blank page under static export. A "pre-existing" crash still crashes on every request. |
| `fingerprint-check` | **NEVER** | Integrity / provenance. Invisible-Unicode + generator fingerprints are authorship/tamper tells whose entire value is that the answer is always zero; a tolerated non-zero baseline destroys the signal. |
| `parity-check` | **NEVER** | Structural truth. sitemap == routes == llms.txt is a bidirectional invariant, not a defect count — a "pre-existing" mismatch means the site's own map is lying, and every downstream gate reasons off that map. |
| `orphan-check` | **NEVER** | Structural truth + the original Acme bug, highest-value gate in the suite. An orphaned URL is unreachable and uncrawlable *today*; age does not soften it. |
| `rules-selftest` | **NEVER** | Meta-integrity. This gate checks the forbidden-phrase ruleset itself (BUG-018 dead rules, BUG-019 case escapes, defeated lookahead exceptions, fixture proofs). A baselined defect here is a silently disarmed legal gate. |
| `claim-provenance-check` | **NEVER** | Legal exposure. An invented credential is a live falsehood however old the run that wrote it — the same argument as `forbidden-sweep`, arriving by a different route. |
| `tier-check` | **NEVER** | Authority. Accepting a past out-of-tier edit as debt is how the tier stops meaning anything; the whole safety argument for letting a model write files is that this line holds. |
| `acceptance-check` | **NEVER** | Proof. A fix that never landed is not fixed. Baselining it would grandfather the lie the gate exists to catch. |
| `capsule-check` | yes | Missing §20 capsule — content debt, worked down page by page. |
| `noncommodity-check` | yes | Missing §21 proprietary variable / sibling duplication — content debt. |
| `image-budget-check` | yes | Oversized image bytes — content debt (fingerprinted on the path+tier, not the size). |
| `lcp-hygiene-check` | yes | Dimensionless `<img>` / lazy-loaded declared hero — content debt (fingerprinted on file+src, not line). |
| `pages-are-data-check` | yes | Bespoke-heavy static route — architecture debt (fingerprinted on route, not line count). |
| `check-headings` | yes | Heading casing — content debt (fingerprinted on file + heading text). |
| `llms-sales-purge` | yes | CTA copy in llms.txt — content debt (fingerprinted on phrase + line text). |
| `audit-built` | yes | The 30-point per-page audit (titles, metas, alt text, FAQ, schema) — content debt (fingerprinted per page URL + check key). |

Everything not listed (em-dash, robots-aicrawler, proof-assert, the live post-deploy checks) is either already clean on the pilot or out of scope for baselining; only the eight `yes` gates carry legacy content debt and accept `--baseline`. Nine gates are now never-baselineable: the six inherited plus the three phase-4 authorship gates.

---

## The gates

### PRE-build — the agent-authorship floor (v3 phase 4, 2026-08-05)

These three exist because a model writes into client repos. They judge the **PR
diff**, not the tree, so they run on every PR regardless of who authored it — an
out-of-tier edit or an invented credential is the same risk from a human hand.
All three are **never-baselineable**: you cannot grandfather a fabricated
credential, an unauthorized edit, or a fix that never landed.

The client checkout must be `fetch-depth: 0`. A gate that cannot see the diff
refuses (exit 2) rather than reporting an unexamined PR clean.

| Gate | What it checks | Blocking? | Exit | Status |
|---|---|---|---:|---|
| `tier_check.py` | Every changed path and operation against the repo's declared tier. T1 modifies `text_paths`; T2 adds creates under `content.location` and modifies `content.registry`; T3 anything not denied, deletes included. **The deny floor (`.github/**`, `docs/client-config.yml`, `package*.json`, `wrangler.toml`, `.env*`) applies at every tier and is unioned in from `DEFAULT_DENY`, so a client config cannot shrink it.** No declared tier permits nothing. A rename is judged as delete + create. `docs/audit/**` rides along at every tier (create/modify only) because the cycle's own artifacts ship inside the PR. | BLOCKING | 17 | **WORKS** — verified against a real agent diff: in-tier edit exit 0, a `src/components/Hero.tsx` create exit 17 |
| `claim_provenance_check.py` | Every factual claim in **added** text — rating, review count, licence number, year-count, `since <year>`, warranty term, price, percentage, jobs-completed, superlative — must resolve to `docs/client-config.yml`, to a work item's `evidence`, to an explicit citation on the line, or **to the previous version of the same file** (a claim already on the site was not invented by this run). Markdown is scanned as prose; code and data files are scanned **only inside string literals**, so a bare `id: 4471` is not a claim. Empty corpus refuses. | BLOCKING | 18 · 4 (empty corpus) | **WORKS** — `4.9 stars` / `1,200 reviews` / `28 years` blocked; `since 1998` passed off `trust_signals` |
| `acceptance_check.py` | Re-runs each fix `docs/audit/<YYYY-MM>/changelog.json` **claims** (`status: fixed`) against the build output, using `measure.check_page` itself rather than a second implementation. Refuses when the finding still fires, when the claimed URL has no built page, when the `check` is unimplemented, and when the code is a phase-6 provider code that `check_page` could never emit (a vacuous pass is worse than no gate). A PR claiming nothing skips green. | BLOCKING | 20 | **WORKS** — a `len=5` description claimed as fixed went red; the real agent fix went green |

### PRE-build

| Gate | What it checks | Blocking? | Exit (registry) | Exit (observed Run #1) | Status |
|---|---|---|---:|---:|---|
| `audit-ssr.py` | No SSR-unsafe `window` / `document` in the render path of `src/app` | BLOCKING | 10 | 9 | **WORKS** — seeded module-level `window.location.href` went red |
| `pages-are-data-check.py` | Pages come from 4 templates + data, not bespoke per-route `page.tsx`. Flags a static non-whitelisted route above `--max-static-lines` (default 120). Lesson-1 gate. | BLOCKING | 1 | 1 | **WORKS** — flagged `/our-process` (175 lines) on real Acme |
| `brief-fanout-check.py` | Each `docs/briefs/*.json` has ≥6 distinct fan-out queries, a capsule, ≥1 semantic triple, a `proprietary_variable` inside the allow-list, and a valid intent enum. §19. | BLOCKING | 9 | 9 | **WORKS** — soft-skips clean when `docs/briefs/` is absent |
| `forbidden-sweep.py source` | Forbidden-phrase ledger against `src/data/*.ts` | **ADVISORY** | 4 (empty-ruleset) | 3 | **WORKS, RED IS OVER-BROAD** — `derive_word_pattern()` strips the heading anchor, so it flags body-prose contractions. Built mode is the trustworthy signal. Keep advisory. |
| `validate_multistate_config.py` | Multi-state addendum applies only when `topology_class` actually needs it | BLOCKING | 1 | 0 (bypassed) | **WORKS** — correctly bypassed on a single-state config |
| `rules_selftest.py` | The ruleset's own gate (2026-08-03): union patterns compile; no regex metachars in `banned-phrases.txt` (BUG-018 dead-rule class); no plain txt line defeating a YAML negative-lookahead exception (Crestline free-system class); case audit warns on case-sensitive rules (BUG-019 class, opt-out `case_sensitive: true`); `docs/rule-fixtures.yml` must_match/must_not_match samples proven through the production matcher, and every lookahead exception proven by a fixture. Bootstrap: missing fixtures file = warning only. | BLOCKING | 3 (defects) / 4 (empty ruleset) | — | **NEW** — regression-tested against all three shipped ruleset bugs |

### BUILT

| Gate | What it checks | Blocking? | Exit (registry) | Exit (observed Run #1) | Status |
|---|---|---|---:|---:|---|
| `orphan-check.py` | Every sitemap URL has ≥1 inbound internal `<a href>`. **The original Acme bug — highest-value gate in the suite.** | BLOCKING | 3 | 1 | **WORKS** — 99/99 clean; seeded orphan `<loc>` went red |
| `parity-check.py` | sitemap == built routes == `llms.txt` (run with `--strict-llms`) | BLOCKING | 5 | 1 | **WORKS** — seeded bogus `<loc>` went red |
| `forbidden-sweep.py built` | Forbidden-phrase ledger against rendered HTML, with `<script>`/`<style>` stripped so Next 16 RSC flight payloads don't false-positive. Union of in-config `forbidden_phrases` ∪ `docs/banned-phrases.txt`. **The legal-exposure gate.** Since 2026-07-31, `load_phrases()` also runs a **placement lint** (`[LINT]` on stderr, advisory only, never changes detection): regex constructs in the txt ledger, bare phrases in the YAML block when a txt ledger exists, and a plain txt line defeating a YAML rule's negative-lookahead exception (the Crestline free-system shape, BUG-017). | BLOCKING | 4 (empty-ruleset) | 3 | **WORKS** — 0 hits on 103 files; seeded `$5000` went red |
| `em-dash-check.py` | No em dashes in rendered output (global Meridian writing rule) | BLOCKING | 1 | 1 | **WORKS** |
| `check-headings.py` (+ `.sh` wrapper) | Headings are Title Case; acronym+number exempt; stopwords handled | BLOCKING | 1 | 1 | **WORKS** |
| `fingerprint-check.py` | Invisible-Unicode scrub on **raw bytes** (the one gate that must NOT strip `<script>`): ZWSP/ZWNJ/ZWJ, word-joiner, BOM beyond a single leading one, soft hyphen, bidi controls, the U+E0000–U+E007F tag block, `data-generated-by` attrs. §17. | BLOCKING | 8 | 8 | **WORKS** — seeded U+200B went red |
| `llms-sales-purge.py` | `llms.txt` is free of sales/CTA copy (word-boundary anchored, so `notebook` ≠ `book`). §30 — parity-check already covers existence/parity. | BLOCKING | 1 | 1 | **WORKS** |
| `robots-aicrawler-check.py` | `out/robots.txt` exists and does not `Disallow` any citation UA (OAI-SearchBot, Claude-SearchBot, PerplexityBot, Bingbot, Googlebot, ChatGPT-User). Missing robots.txt is red with a "generate robots.txt" finding. | BLOCKING | 1 | 1 | **WORKS** |
| `capsule-check.py` | Interrogative H2 → answer-first 2–3 sentence block → TL;DR on pages over `content.long_page_threshold`. §20 — the literal unit AI engines lift. | BLOCKING | 6 | 6 | **WORKS + REAL FINDING** — 60/61 Acme pages lack a capsule |
| `noncommodity-check.py` | ≥1 proprietary token from the `proprietary_variables` allow-list per page + cross-page uniqueness vs siblings (0.90 hub-spoke / 0.60 default). **Empty allow-list → exit 4**, never a silent pass. §21. | BLOCKING | 7 | 7 | **WORKS + REAL FINDING** — 31/61 pages `duplicate_of_sibling` |
| `image-budget-check.py` | Per-tier byte ceilings — hero/OG ≤200 KB, in-content ≤100 KB, thumb/icon ≤30 KB. Compensating control for `images.unoptimized: true` under static export. | BLOCKING | 1 | 1 | **WORKS + REAL FINDING** — 37/63 images over budget |
| `lcp-hygiene-check.py` | No `loading="lazy"` on a preloaded hero; every `<img>` carries non-empty `width` and `height` (SVG allow-list). CLS + LCP pre-conditions only — field CWV stays monitoring. | BLOCKING | 1 | 1 | **WORKS + REAL FINDING** — 2 pages preload a hero then lazy-load it |
| `audit-built.py` | The 30-point built-page audit: titles, meta descriptions, alt text, FAQ counts, schema subtype + `sameAs` + `areaServed` geometry, 5-gram sibling uniqueness | BLOCKING | 10 | 5 | **BROKEN AS WIRED** — (1a) `read_built()` doesn't strip scheme+host from the `<loc>` URLs the workflow feeds it → `file_not_found` on every non-root page; (1b) `28_in_sitemap_recent` reads the `.ts` sitemap *generator* instead of the built XML. Treat its RED as noise until both are fixed. |
| `proof-assert.sh` | Meta-gate: the deploy proof exists at the tracked `docs/deploy-proofs/` path and is non-empty. "No proof = it didn't happen." | BLOCKING | 1 | 1 | **WORKS** — missing proof file went red |

### LIVE (post-deploy)

| Gate | What it checks | Blocking? | Exit | Status |
|---|---|---|---:|---|
| `verify-live.sh` | Key routes return 200 with expected content on the real domain, with retries | Fails the deploy job (post-merge) | 1 | **WORKS** — verified against live prod |
| `cf-crawler-check.sh` | Citation UAs get 200 + content at the Cloudflare edge (no `Just a moment` / `cf-challenge` / `cdn-cgi/challenge`). Training bots (GPTBot, ClaudeBot, Google-Extended, CCBot) are **INFO only, never red**. Catches a silent CF "Block AI Crawlers" toggle — the highest catastrophic-miss risk, invisible in `out/`. | Fails the deploy job | 1 | **WORKS** — 12 UA×route pairs clean against live prod |

### Not gates

`indexnow-submit.py` is a submitter, not a gate — smoke-tested via `--dry-run`. Keep exactly one IndexNow submitter in the fleet.

---

## Reading the results

- **19 of 21 gates** ran clean and either pass-when-clean + catch-when-seeded, or are correctly red on genuine content.
- **1 broken** (`audit-built.py`, two wiring bugs — one-line fixes each).
- **1 over-broad** (`forbidden-sweep.py` source mode — keep advisory).
- **5 real content findings** on the hand-built Acme site (images, LCP, capsule, non-commodity, one bespoke route). These are the exact gaps the V2 emitter is meant to prevent going forward — triage them as fix / whitelist / accept-as-legacy, not as a blocked ship.

A gate going red is not automatically a bug in the gate. Always separate *gate broken* from *gate works and found a real content issue* before routing the work.
