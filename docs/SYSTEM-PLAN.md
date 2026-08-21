# System Plan — seo_agent v3

A working plan for how each pipeline stage runs in practice, built
stage-by-stage. This is a planning doc, not a spec — it captures decisions
and process, not code. For the technical snapshot see `docs/ARCHITECTURE.md`;
for the code-level flow of any one stage see the module itself
(`pipeline/audit/*.py`) — this doc restates neither, it plans around them.

Update this file in the same commit as any change to the process it
describes (`CLAUDE.md` §2). Each part below is worked out in order, one
pipeline stage at a time.

Stages: **1. Onboard → 2. Measure → 3. Plan → 4. Remediate → 5. Gates →
6. Human Merge → 7. Monitor**

---

## Part 1 — Onboard

### 1a. Client intake checklist

What to collect from a new client, and in what order, before running
`wf-onboard`.

**1. Domain URL**

Just the live site. Business facts (legal name, services, service area,
NAP, trust signals) get discovered by fetching the domain's homepage
(`wf-bootstrap-config`) rather than asked of the client directly — faster,
doesn't wait on client response time. (`wf-seed-queries --crawl-max` goes
deeper across multiple pages when that's worth the extra time; the initial
bootstrap fetch is a single page.)

`wf-onboard` hard-stops on the TODO placeholders `wf-bootstrap-config`
writes until those facts are filled in, crawled or not. Verify what the
crawl found against the client's actual GBP / site before treating it as
fact — a crawler infers "years in business" and license numbers, it doesn't
certify them, and `claim_provenance_check` will refuse anything that doesn't
trace to a source.

**2. GitHub access**

Collaborator access on their repo, write permission. `wf-onboard` checks
this itself (`gh repo view --json viewerPermission`) and warns rather than
fails if it's read-only — but read-only means no PR can ever open from that
checkout, so get this before the first remediation run, not after.

**3. Google Search Console + Google Analytics access**

Not currently required by `wf-onboard` — nothing stops the pipeline if this
is missing, it just silently skips the data those sources feed. Ask for it
anyway: without it the whole cycle runs on crawl-based heuristics instead of
real search behavior.

- **Search Console**: add the pipeline's identity as a user on the property
  (or hand over credentials to mint an OAuth token) — read-only is enough.
  Feeds `GSC_ACCESS_TOKEN` / `GSC_SITE_URL`.
- **Analytics (GA4)**: viewer access, if they have a property set up. The
  `ga4_id` tag string, once filled in, is checked for *presence* on the live
  site (§2a) — GA4's own Analytics Data API (sessions, conversions,
  engagement) is not consumed by any provider today; collected for context
  and future use.

**4. Strategy input**

- Their own top 10-20 search terms — what they believe people type to find
  them. Rough is fine; it's a seed, not a survey.
- 3-5 named competitors.
- Any existing keyword research or rank-tracking they already pay for.

These map to `target_keywords`, `seed_queries`, and `competitors` in
`docs/client-config.yml` — all empty by default, none enforced.
`wf-seed-queries` can turn a rough term list into the seed-query format the
pipeline expects.

**Not from the client: DataForSEO, Bright Data**

`DATAFORSEO_LOGIN`/`DATAFORSEO_PASSWORD` and `BRIGHTDATA_API_KEY`/
`BRIGHTDATA_SERP_ZONE` are pipeline-side credentials — one subscription per
operator, shared across every client, set as environment/secrets on the
engine side. Never ask a client for these. (Bright Data is on a path out —
see §2c.)

**Summary table**

| # | Ask for | Required by `wf-onboard` today? | Feeds |
|---|---|---|---|
| 1 | Domain | Yes | crawl → business facts in `client-config.yml` |
| 2 | GitHub access | Checked, warns if read-only | remediation PRs |
| 3 | Search Console access | No | `GSC_ACCESS_TOKEN` — real query/CTR data |
| 3 | Analytics access | No | GA4 Data API not consumed yet — `ga4_id` tag presence is checked (§2a) |
| 4 | Top search terms, competitors | No | `seed_queries`, `target_keywords`, `competitors` |

Rows 3-4 are the real gap: nothing in `wf-onboard` currently asks for them,
so a client can be fully onboarded and cycling through gates green with all
of that data silently absent. This checklist is the forcing function until
that's built into the tool itself.

### 1b. GSC vs. GA4 — reference

Different questions, both worth having, neither substitutes for the other.

| | Google Search Console | Google Analytics (GA4) |
|---|---|---|
| **Answers** | "What did people search, and did they click?" | "What did people do once they landed?" |
| **Data starts** | Before the click — impressions, position, query text | After the click — sessions, pageviews, conversions, time on page |
| **Granularity** | Per search query + per URL | Per user/session, event-based |
| **Good for** | Which queries you rank for but show up poorly on (low CTR), keyword cannibalization, which pages Google indexes | Which pages convert, where users drop off, whether traffic from a query does anything once it lands |
| **In this pipeline** | Wired in (`providers.py`): feeds low-CTR findings and query cannibalization checks, when `GSC_ACCESS_TOKEN` is set | `ga4_id` tag presence is checked (§2a); GA4's own metrics (sessions, conversions) are not consumed by any provider today — context only |

Short version: Search Console tells you if you're *findable*; Analytics
tells you if the page *works* once found. SEO/AEO work leans on Search
Console because it's query-level and pre-click.

### 1c. Open items for this stage

- No forcing function in `wf-onboard` for GSC/GA/strategy-input collection —
  currently process discipline only, per §1a.

---

## Part 2 — Measure

Grounded in `pipeline/audit/measure.py` and `pipeline/audit/providers.py`,
both read in full. One contract note that applies to every "scoped change
list" table below, stated once rather than repeated per table: every such
list implies its own `CHANGELOG.md` / `docs/MODULES.md` entry once actually
built, per the sync contract (`CLAUDE.md` §2) — that requirement isn't
restated as a table row each time.

### 2a. What `wf-site-health` does

17 built-in finding codes, always on, no credentials, pure HTTP+regex:
page-not-200, title presence/length, meta description presence/length, h1
count, canonical mismatch, noindex presence, missing og:image, schema type +
BreadcrumbList, forbidden phrases, phone/tel link presence, GA4 tag
presence, missing image alt text, and thin content.

Four of those are skipped (not failed) and **named on stderr** when their
config input is unset (`_CONFIG_GATED` in `measure.py`): `nap.phone_tel`,
`nap.phone`, `ga4_id`, `forbidden_phrases`. One more config-driven check does
**not** skip — `schema_type` defaults silently to `LocalBusiness` when
unset and measures against that default, which is the one place an
unconfigured input still produces a real finding rather than a named skip.

Then four optional enrichments, each its own CLI flag
(`--with-crux`/`--with-gsc`/`--with-dataforseo`/`--with-serp`), each needing
its own credential, off by default:

| Enrichment | Credential | Who it depends on |
|---|---|---|
| CrUX (`crux_findings`) | `CRUX_API_KEY` | **pipeline-side** — operator's Google Cloud key |
| DataForSEO On-Page (`dataforseo_findings`) | `DATAFORSEO_LOGIN`/`PASSWORD` | **pipeline-side** — operator's paid account |
| Bright Data SERP (`serp_findings`) | `BRIGHTDATA_API_KEY`/`BRIGHTDATA_SERP_ZONE` | **pipeline-side** — operator's paid account |
| Google Search Console (`gsc_findings`) | `GSC_ACCESS_TOKEN`/`GSC_SITE_URL` | **client-dependent** — needs that specific client's own property access |

GSC is the one enrichment that literally cannot run without that specific
client granting access; the other three are a one-time operator setup cost
that benefits every client — the same split §1a already draws.

Output: `docs/audit/<YYYY-MM>/findings.json`, with a `providers` block
recording each enrichment's status string — `ok:`/`partial:`/`skipped:`/
`failed:`/`no field data:`/`timed out:`, six prefixes in total — so "never
asked" and "asked and found nothing" are always distinguishable. Two
guardrails worth knowing: refuses at exit 19 if every URL was unreachable
rather than writing an empty report; warns if one finding code makes up
≥50% of a run (the B-009 false-positive smell test — 1,158 of 1,272
findings, 91%, from one broken regex, once, for real).

### 2b. CrUX → Lighthouse fallback for low-traffic sites — scoped, not implemented

CrUX is real-Chrome-user field data. A brand-new site has ~0 recorded
navigations, so `crux_findings` returns a status starting `no field data:`
and the cycle produces **zero** Core Web Vitals findings — not wrong, just
silent, forever, until the site earns enough traffic.

Lighthouse (lab data, no traffic threshold, works day one) is the fallback,
and it **already exists in this system** — `preview.reusable.yml`'s
`lighthouse-monitor` job already installs and runs it (`npm install -g
lighthouse@12`, then `lighthouse "$url" --quiet --chrome-flags="--headless=new
--no-sandbox --disable-gpu --disable-dev-shm-usage" --only-categories=performance
--output=json`) — but only against a Cloudflare preview URL, opt-in, scoped
to PR previews. The plan below reuses that exact invocation, not a
different one, as a fallback inside `providers.py` itself.

**Detection signal already exists — no new plumbing needed for it.**
`crux_findings()` already returns a status string with the distinguishing
prefix `"no field data:"` when every target 404s (the full string also
appends a `(resolved to <host>)` suffix when the domain resolves to a
different serving host — match the prefix, not the whole string). That
prefix is the trigger; nothing new has to be invented to detect the
low-traffic case.

**Two design decisions to settle before writing the parser**, both easy to
get wrong by accident:

1. **INP has no lab equivalent.** `CWV_CODES`/`CWV_GOOD` cover exactly three
   metrics — LCP, CLS, INP — and Lighthouse produces LCP and CLS directly
   but has no INP (INP requires a real user interaction, which a lab run
   can't produce). Pick one: (a) map Lighthouse's Total Blocking Time to
   `crux.inp_above_good` as a documented proxy — TBT's own "good" cutoff
   happens to be 200ms, the same number as INP's, which is a coincidence
   worth naming in the finding's `detail`, not treated as equivalence — or
   (b) skip INP entirely on the lab path and say so in the status string.
2. **Findings must reuse the same `"crux"` source tag** `parse_crux` already
   uses — not a separate `"lighthouse"` source. Fingerprints are
   `gate | code | location | context`, not source-qualified, so a separate
   source tag would make every lab finding vanish and a `"crux"` one appear
   for the same metric the moment a low-traffic site finally earns real
   CrUX data — `plan.py`'s ratchet would report RESOLVED + NEW for a site
   where nothing on the site actually changed. Keep the source tag
   identical; carry the lab/field distinction in `detail`
   (`"(lab data via Lighthouse fallback, no CrUX field data)"`) instead.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/providers.py` | New `lighthouse_findings(domain, urls=None)` function: shells out to the `lighthouse` CLI per target URL (same flags as `preview.reusable.yml`'s existing invocation), parses LCP/CLS (and INP per the decision above) into `Finding("crux", CWV_CODES[metric], ...)` — same source tag as `parse_crux`, per the design decisions above. `crux_findings()` itself is untouched — it stays pure/unchanged; the fallback is a separate function, called only when needed. |
| 2 | `pipeline/audit/measure.py` | At the `--with-crux` call site inside `main()` (where `crux_findings(cfg["domain"])` is called): when the status starts with `"no field data:"`, call `lighthouse_findings()` and use its result instead — automatic fallback, no new CLI flag. Combined status string makes the swap visible, e.g. `"ok (lighthouse fallback): N record(s) — no CrUX field data for {domain}"`. |
| 3 | `Dockerfile` | Add `RUN npm install -g lighthouse@12` — the image already installs `nodejs npm` for Claude Code's own install step, so this is one more global npm package, not a new runtime dependency. |
| 4 | `tests/test_providers.py` | New tests: `lighthouse_findings()` parses a sample Lighthouse JSON payload into findings tagged with the `"crux"` source; the `--with-crux` fallback in `measure.py` triggers only on a `"no field data:"` status and not on `"partial:"` or `"failed:"` (a real API error should surface as an error, not silently swap to lab data). |
| 5 | `CHANGELOG.md`, `docs/MODULES.md` | per the sync-contract note above |

Cost/complexity note: Lighthouse is a free, open-source CLI — no new API key
or vendor relationship. The tradeoff is honesty about what it actually
gives: a single lab run per URL (no percentile distribution across real
users, no traffic threshold to clear) — "something over nothing," not
CrUX-equivalent data. It's also slower (spins up headless Chrome per URL),
which matters more once this also runs on a cron (§2e) than it does once a
month.

### 2c. Bright Data → DataForSEO SERP swap — scoped, not implemented

The operator wants to drop Bright Data as a vendor entirely and do
rank-checking through DataForSEO's own `serp/google/organic/live/advanced`
endpoint instead, reusing the `DATAFORSEO_LOGIN`/`PASSWORD` credentials
`dataforseo_findings` already needs — one fewer vendor, one fewer credential
pair for the whole system.

Confirmed via DataForSEO's own docs:
`POST https://api.dataforseo.com/v3/serp/google/organic/live/advanced`,
body `[{"keyword", "location_code", "language_code", "device"}]`, response
`tasks[0].result[0].items[]` where organic results carry `type: "organic"`,
`rank_group` (organic-only position — the direct analogue of Bright Data's
old `rank` field), `rank_absolute` (position including ads/features — not
used, matches why the old code preferred `rank` over `global_rank`),
`domain`, `url`.

**Two editorial decisions this swap should make explicitly, not by default:**

- **Take B-021's fix in the same change, don't just repoint the vendor
  name.** The ledger's own stated minimum fix for B-021 (transient SERP
  failure churns the ratchet) is a bounded retry in the per-query loop —
  the exact loop this swap already rewrites. Carrying a known bug forward
  under a new vendor name, in a change that's already touching that loop,
  has no upside; fix it here and move B-021 to Fixed.
- **`serp_findings()`'s own docstring currently claims the request shape was
  verified live against real Bright Data credentials** — that provenance
  statement is about to become false the moment the function is rewritten
  for a different vendor. Replace it with the DataForSEO verification note
  instead of leaving a stale claim inside the rewritten function.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/providers.py` | `parse_serp()` rewritten for the DataForSEO shape above instead of Bright Data's `brd_json=1` shape (`organic[]`, `rank`/`global_rank`/`link`). `serp_findings()` points at the DataForSEO endpoint, drops `BRIGHTDATA_API_KEY`/`BRIGHTDATA_SERP_ZONE` entirely, reuses `DATAFORSEO_LOGIN`/`PASSWORD`, takes the B-021 bounded retry, and replaces its own docstring's stale Bright-Data verification claim. Module docstring/env-var table updated. |
| 2 | `pipeline/audit/measure.py` | `--with-serp` help text — update required env vars |
| 3 | `pipeline/audit/seed_queries.py` | 4 comments/print strings reference "one paid Bright Data request" — reword to DataForSEO. One of these is the `seed_queries:` block `wf-seed-queries --write` appends into a client's own `docs/client-config.yml` — already-onboarded client repos will carry the stale vendor name in a comment already committed there; no auto-migration, just don't be surprised it isn't purely an in-repo fix. |
| 4 | `config/client-config.starter.yml` | 1 comment near `seed_queries` mentioning Bright Data |
| 5 | `pipeline/dashboard/static/analytics.html`, `app.js`, `page-analytics.js` | Three dashboard files render or reference a hardcoded "Bright Data" string (including a user-visible button label) — source files, not just the test that covers them. |
| 6 | `tests/test_providers.py` | Rewrite ~18 SERP tests (`:248-390`) to the DataForSEO shape; drop 3 that only existed for Bright Data's rank-vs-global_rank ads/features quirk (`:303`, `:310`, `:319`) — DataForSEO already separates organic from ads via `type`, so that failure class can't recur under the new vendor. Also update the parametrized credential-skip test (`:21-32`) — after the swap, its `serp` and `dataforseo` rows would assert the same credential name and stop discriminating between the two checks. |
| 7 | `tests/test_dashboard.py` | 1 skip-status string assertion (~line 1144) |
| 8 | `CHANGELOG.md`, `docs/BUG-LEDGER.md` (B-021 → Fixed, per the decision above), `docs/ADMIN-CHECKLIST.md` (drop the Bright Data secret row; leave the historical "ran live 2026-08-07/2026-08-14" verification entries as history — true statements about what happened under the old vendor, add a note rather than rewriting them), `docs/MODULES.md`, `docs/ARCHITECTURE.md`, this doc's §1a "Not from the client" line | — |

This table is the starting point if the operator says "go" on this swap in
a future session.

### 2d. Measurement flow improvements — researched, not yet implemented

Measure is not a once-a-cycle checkbox — a fix shipped in Remediate is only
proven if Measure re-checks it before the next monthly cycle rolls around.
Researched against SEMrush (named as a candidate to check), DataForSEO's own
API surface, and published data-freshness/cadence norms. Ranked by "can we
tell if a fix worked", not novelty:

**1. Weekly rank-tracking, not monthly.** The §2c DataForSEO SERP swap is
already scoped — the gap here is *cadence*, not the vendor. Rankings are
the most direct fix-worked signal there is; monthly is too coarse to catch
a regression before the next cycle. Reuses `DATAFORSEO_LOGIN`/`PASSWORD`,
cheap per-call.

**2. CrUX History API instead of a one-shot query.** Same `CRUX_API_KEY`,
zero new cost — `chromeuxreport.googleapis.com`'s History endpoint returns
~40 weeks of rolling data instead of one point-in-time snapshot. Fixes the
"no historical trend storage for CWV" gap (§2b) without building any new
storage layer — a CWV fix becomes a before/after curve instead of two
monthly snapshots compared by hand.

**3. DataForSEO Backlinks API — not SEMrush.** The one real structural gap:
no backlink/domain-authority data exists anywhere in this repo today.
Checked SEMrush as requested — its Backlink Analytics needs the **Business
plan, $499.95/mo minimum**, just for API access. DataForSEO Backlinks is
pay-per-call (~$0.05/1K rows, $50 deposit, no subscription) and reuses the
credential pair already pipeline-side. Backlink profiles move slowly —
weekly/monthly polling is enough; don't over-poll a per-call API for a
weeks-not-days signal.

**4. Wire GA4's own metrics into an actual check.** `ga4_id` tag *presence*
is already checked (§2a); GA4's Analytics Data API (sessions, conversions,
engagement) is not consumed anywhere. Without it there's no link between
"rankings went up" / "CWV improved" and whether a user actually did
anything differently — the missing outcome metric. Client-side credential
already asked for at intake, so this is zero new intake work. Monthly
cadence is fine — slower-moving signal.

**5. Pull GSC weekly, not monthly.** GSC's own lag is 2-3 days, so a
monthly pull wastes 3+ weeks of freshness the API already has available. A
weekly low-CTR/cannibalization delta surfaces a fix's impact — or an
unnoticed regression — much sooner than waiting for the next cycle.

**Net:** 3 of 5 reuse credentials already in the system (DataForSEO, CrUX
pipeline-side; GA4 client-side) — no new vendor needed. SEMrush's own
capabilities are already covered cheaper by DataForSEO; the one thing
SEMrush would add (backlinks) is better filled by DataForSEO's own
Backlinks API than by a second vendor relationship.

**Architecture constraint that shapes all five:** `seo_agent` itself has no
cron (`CLAUDE.md` — "There are no cron workflows"); any schedule has to live
in a client repo's own Actions, the same way `seo-health.yml` already does.
§2e below designs the actual mechanism — a **new** reusable workflow rather
than a branch inside `seo-health.yml`, since that file is deliberately
scoped to presence checks and carries none of the provider credentials this
needs. See §2e for the design and its GSC token blocker.

Nothing in this section is scoped to files yet beyond the cron workflow
itself (§2e) — item priority, cadence, and vendor choice are decided; which
of #1/#2/#3/#4/#5 gets file-level scoping next is the operator's call.

### 2e. A proper cron job system for Measure — scoped, not implemented

The architectural fact that has to be dealt with head-on: **`wf-site-health`
has never run inside GitHub Actions at all.** It is an operator CLI command,
run locally or inside the Docker container, once per monthly cycle —
credentials (`CRUX_API_KEY`, `GSC_ACCESS_TOKEN`, `DATAFORSEO_LOGIN`/
`PASSWORD`) come from the operator's own shell environment when they run it
by hand. The only thing that already runs on a schedule in a client repo is
`seo-health.reusable.yml` (daily + `workflow_dispatch`), and it is
deliberately scoped to presence/citation-crawler checks only — its own
comments say so explicitly ("Numbers here are presence signals, not CWV")
and its `secrets:` block carries only `CHAT_WEBHOOK_URL` + `SEO_AGENT`,
nothing provider-related. Bolting §2d's provider re-checks onto that file
would blur a scope it documents on purpose, and would need secrets it
deliberately doesn't have today. So: a **new** reusable workflow, not a
branch inside the existing one — built to the same pattern as the other
four (`harden-runner` first, `PIPELINE_REF` stamping, version-locked
pipeline checkout, `workflow_call` + `workflow_dispatch`, `secrets:
inherit`, monitoring-only / never blocks).

**Proposed: `.github/workflows/measure-cron.reusable.yml`**

| Aspect | Design |
|---|---|
| Trigger | Per-client caller supplies `schedule: - cron: '0 14 * * 1'` (weekly, Monday) + `workflow_dispatch`, same pattern as `seo-health.yml`'s caller block. |
| Checkout | **Two** checkouts, unlike `seo-health.reusable.yml` (which checks out only the pipeline, never the client repo): the version-locked pipeline (for `wf-site-health` itself) **and** the client repo, read-only — `wf-site-health --project` needs the client's own `docs/client-config.yml` for `domain`/`seed_queries`. |
| Command | `wf-site-health --project <checkout> --with-crux --with-gsc --with-serp` — deliberately **omits** `--with-dataforseo` (the on-page crawl). §2d's own reasoning applies: on-page/backlink-style data moves slowly and a 100-page crawl is heavier; that stays on the monthly cycle. Rank tracking, CWV, and CTR/cannibalization are the three that actually benefit from a week's-not-a-month's freshness. |
| Output | **No repo write-back, no commit** — matches `seo-health.reusable.yml`'s `permissions: contents: read` model, avoiding a commit-back/PR flow for a monitoring job. This makes delta-based alerting ("a tracked query dropped out of top 10", "CWV flipped good→poor") impossible with no previous run to compare against. **Decision: alert on absolute thresholds only** — a tracked query missing from the response at all, a CWV metric outside `CWV_GOOD` directly — which needs no previous-run comparison and ships with this design as-is. Persisting weekly snapshots so delta-based alerting becomes possible is a genuinely separate, later decision — a prerequisite for that kind of alert, not a nice-to-have on top of it — and isn't scoped here. |
| Secrets | `CRUX_API_KEY` + `DATAFORSEO_LOGIN`/`PASSWORD` are pipeline-side (the operator's own, shared across every client). GitHub Organization-level secrets would be the natural one-time home for these, but this repo's own sharp edge #5 (`CLAUDE.md`) already establishes GitHub Free on private repos — org-level secrets need Team or above. Until the plan changes, hand-copy them into each client repo's secrets like any other; revisit if the operator upgrades. `GSC_ACCESS_TOKEN`/`GSC_SITE_URL` stay client-side/per-repo, as today. |

**⚠️ Named blocker, not glossed over: `GSC_ACCESS_TOKEN` is a short-lived
OAuth access token (~1 hour — already flagged in `docs/ADMIN-CHECKLIST.md`).
A weekly unattended cron cannot use a 1-hour token as-is; it will work the
first run and then fail silently forever after.** This means weekly GSC
checks need a refresh-token exchange added — `gsc_findings()` (or a thin
wrapper around it) has to mint a fresh access token from a stored
`GSC_REFRESH_TOKEN` + `GSC_CLIENT_ID`/`GSC_CLIENT_SECRET` at job start. That
is new code in `providers.py`, not just a new workflow file, and it's a
prerequisite for §2d item 5 (weekly GSC) specifically — CrUX and SERP
have no equivalent token-expiry problem and aren't blocked by this.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `.github/workflows/measure-cron.reusable.yml` | New file, per the design above. |
| 2 | `.github/examples/` | New thin per-client caller example (~30 lines, matching the existing four). |
| 3 | `pipeline/audit/providers.py` | `gsc_findings()` gains the refresh-token exchange (blocker above) — needed before weekly GSC can actually run unattended. |
| 4 | `pipeline/audit/measure.py` | Add an `--out <path>` override (or `--no-write`) — `measure.py` writes `<project>/docs/audit/<YYYY-MM>/findings.json` unconditionally today, and a weekly run using that same default path would clobber the artifact the monthly cycle's ratchet (`plan.py`) reads. This is a hard prerequisite for the workflow above, not an optional nicety. |
| 5 | `docs/ADMIN-CHECKLIST.md` | New secrets row (`GSC_REFRESH_TOKEN`/`GSC_CLIENT_ID`/`GSC_CLIENT_SECRET`), new "Standard workflows" row alongside `quality-gate.yml`/`seo-health.yml`. |
| 6 | `docs/MODULES.md`, `CHANGELOG.md` | per the sync-contract note above |

Most likely bundled with whichever of §2d's five items ships first, since
this workflow is their shared prerequisite.

### 2f. Three new DataForSEO products — scoped, approved to build

Beyond On-Page (already used) and SERP/Backlinks (already scoped in §2c/§2d),
DataForSEO sells five more product lines. The operator approved the top
three for this repo; ranked by fit, not novelty:

1. **LLM Mentions API** — closes the AEO citation loop. `seo-health.yml`'s
   crawler-check already proves AI crawlers can *reach* the site; it has
   never proven anything is actually *cited*. This is the first data source
   in the whole pipeline that measures citation itself.
2. **Labs API — domain intersection / keyword gap** — `docs/client-config.yml`
   has collected a `competitors` list since onboarding (§1a) and it is
   consumed by **nothing**. This is the first real use of that field.
3. **Keywords Data API — search volume** — `seed_queries`/`target_keywords`
   get rank-tracked today with no idea whether a term has 10,000 monthly
   searches or 10; this lets Plan prioritize by demand instead of tracking
   blind.

All three reuse the existing `DATAFORSEO_LOGIN`/`PASSWORD` pair — no new
vendor, no new credential.

**Confidence note, updated.** The `domain_intersection` and `search_volume`
request/response shapes come from DataForSEO's stable, versioned endpoint
docs — the same confidence level as §2c's SERP endpoint. **LLM Mentions'
response schema is now confirmed too** (pulled from DataForSEO's
`ai_optimization/llm_mentions/target_metrics/live` doc page directly — a
documented contract, not a live authenticated call: no
`DATAFORSEO_LOGIN`/`PASSWORD` exists anywhere accessible to actually test
against the live endpoint, so this is "verified against their published
docs," one notch below "verified against a real response payload" the way
§2c's SERP shape was). Request: `target` (array, up to 10 entries, each a
`domain` or `keyword`), `platform` (`"chat_gpt"` or `"google"`),
`location_code`/`language_code`. Response, per task:
`result[].aggregated_metrics` — grouped by `location`, `language`,
`platform`, `sources_domain`, `search_results_domain`,
`brand_entities_title`, `brand_entities_category`, each group an array of
`{key, mentions, ai_search_volume}`, plus a flat `total: {mentions,
ai_search_volume}`. The field is `mentions`, not the `citation_count` this
doc guessed earlier — corrected below. `sources_domain`/
`search_results_domain` are the "who's actually being cited instead"
breakdown — the direct analogue of §2f/§3f's competitor-gap pairing,
applied to citations instead of rank.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/providers.py` | Three new functions, same shape as existing ones (`(findings_or_data, status)` tuple, named skip when credentials are unset): `llm_mentions_findings(domain, brand)` — `POST https://api.dataforseo.com/v3/ai_optimization/llm_mentions/target_metrics/live`, `target=[{"domain": domain}]`, reads `result[].aggregated_metrics.total.mentions`/`.ai_search_volume` — surfaces a finding when `mentions` is zero or dropping cycle over cycle, and separately surfaces the `sources_domain` breakdown as context (who is cited instead) for §3f's follow-on brief. `competitor_gap_findings(domain, competitors)` — `POST https://api.dataforseo.com/v3/dataforseo_labs/google/domain_intersection/live`, body `{target1: domain, target2: competitor, location_name, language_name, limit}` per competitor in `cfg["competitors"]`, surfaces keywords a competitor ranks for that the client doesn't. `keyword_volume_findings(keywords)` — `POST https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live`, up to 1000 keywords per call (well above any realistic `seed_queries`/`target_keywords` list size, so one call covers a whole client), attaches search volume/CPC/competition as context on existing SERP findings rather than a new finding code — this is enrichment of what §2c's rank-tracking finds, not a new check. |
| 2 | `pipeline/audit/measure.py` | Three new CLI flags: `--with-llm-mentions`, `--with-competitor-gap` (only runs when `cfg["competitors"]` is non-empty — else a named skip, same convention as every other config-gated check), `--with-keyword-volume`. |
| 3 | `docs/client-config.yml` schema / `config/client-config.starter.yml` | No new fields needed — `competitors` and `seed_queries`/`target_keywords` already exist (§1a); this is the first code that reads them. |
| 4 | `tests/test_providers.py` | New tests per function: credential-unset named skip, a sample success payload parsed correctly, `competitor_gap_findings` skips cleanly (not an error) when `competitors` is empty. |
| 5 | `docs/ADMIN-CHECKLIST.md`, `docs/MODULES.md`, `CHANGELOG.md` | note these three reuse `DATAFORSEO_LOGIN`/`PASSWORD` (no new secret), plus the sync-contract note above |

These are natural candidates for the weekly cron (§2e) once it exists — LLM
Mentions and search volume are exactly the kind of "did our fix move the
needle" signal §2d's cadence argument is about — but nothing above requires
§2e to ship first; they can land against the existing monthly
`wf-site-health` cycle on their own.

### 2g. Open items for this stage

- CrUX → Lighthouse fallback for low-traffic sites (§2b) — scoped to files,
  awaiting operator go-ahead. Two design decisions (INP proxy-or-skip,
  reusing the `"crux"` source tag) are settled in the plan; not yet coded.
- Bright Data → DataForSEO SERP swap (§2c) — scoped, awaiting operator
  go-ahead. Now includes taking B-021's bounded-retry fix in the same
  change rather than carrying the bug forward under a new vendor name.
- Measurement cadence upgrades (§2d, items 1-5) — prioritized, awaiting
  operator go-ahead on which to build first; none scoped to files yet
  beyond the cron workflow itself (§2e).
- The `measure-cron.reusable.yml` workflow (§2e) is the shared prerequisite
  for §2d items 1, 2, and 5 — the first piece of file-level scoping needed
  regardless of which measurement item ships first. It also needs a
  `measure.py --out` override before it can run safely (§2e change 4) so a
  weekly run doesn't clobber the monthly cycle's `findings.json`.
- `gsc_findings()`'s refresh-token exchange (§2e blocker) is a hard
  prerequisite specifically for weekly GSC (§2d item 5) — the other
  cadence items (SERP, CrUX/Lighthouse) aren't blocked by it.
- Three new DataForSEO products (§2f: LLM Mentions, Labs domain intersection,
  Keywords search volume) — scoped to files, **approved to build**. LLM
  Mentions' response schema is now confirmed against DataForSEO's published
  docs (not yet a live authenticated call — no `DATAFORSEO_LOGIN`/`PASSWORD`
  exists anywhere accessible to make one); worth one real sandbox/live call
  before `parse_llm_mentions()` ships, same as any third-party contract, but
  no longer a guess.

## Part 3 — Plan

Grounded in `pipeline/audit/plan.py`, `pipeline/gates/acceptance_check.py`,
and the `read_briefs`/`refused_in_cycle`/`--recommend` machinery in
`pipeline/audit/remediate.py`, all read in full. Same sync-contract note as
Part 2: every "scoped change list" below implies its own `CHANGELOG.md` /
`docs/MODULES.md` entry once built — not restated per table.

### 3a. What `wf-site-plan` does, and the gap that shapes everything below

Four lanes (`REGRESSION`/`NEW`/`PERSISTING`/`RESOLVED`) from a fingerprint
set comparison across `docs/audit/<YYYY-MM>/` folders — no separate baseline
file, the monthly folders *are* the time series. `ACTIONS` maps finding
codes to `(kind, min_tier, expect)`; every one of the 17 `health.*` codes
(§2a) has an entry — T1 for copy-level fixes, T3 for template/layout/routing,
no T2 entries (the one that existed, `schema_faq_missing`, was deleted per
B-022). A finding with an entry becomes a worklist item; everything else
lands in `unclassified` → the report's "Needs a Human" section. A
tier-blocked item stays visible, tagged rather than dropped — that's how the
report tells an operator a client should move up a tier. Every acceptance
criterion is the same generic shape, `{"check": "code_absent", "code": ...}`
— re-measure, refuse if it still fires — implemented once in Stage 4's
`acceptance_check.py` rather than per-code.

**Confirmed gap: none of the provider-enrichment codes have an `ACTIONS`
entry.** `crux.*`, `gsc.*`, `dfs.*` (eleven codes across broken pages, click
depth, duplicate title/description/content, redirects, canonical chains,
orphan pages, broken links, oversized pages, missing alt — see
`DFS_CHECK_CODES` in `providers.py`), and `serp.*` all fall into
`unclassified` today, indistinguishable from a finding that structurally can
never be machine-fixed.

**Confirmed cross-stage guard that constrains the fix:** `acceptance_check.py`'s
`verify_item()` already, deliberately, refuses any code that doesn't start
with `"health."` — its own comment: a provider finding "is measured against
Google's field dataset or a paid crawl, neither of which exists in a build
directory... a vacuous pass is worse than no gate." **Simply adding a
provider code to `ACTIONS` with the standard acceptance shape would make
every PR claiming that fix fail Stage 4's gate outright** — this is the
central constraint item 3b below has to design around, not just a Plan-stage
concern.

### 3b. Wire the machine-fixable provider codes into `ACTIONS`, via a next-cycle acceptance type — scoped

Not every provider code qualifies. `gsc.low_ctr`/`gsc.no_impressions`,
`crux.*_above_good`, and `serp.*` need real strategy work a text edit can't
satisfy on its own — those stay unclassified/strategic on purpose (item 3e
below gives `serp.*` a better home than a bare unclassified line, without
making it agent-fixable). The DataForSEO on-page codes are the clear
candidates: `dfs.broken_page`, `dfs.broken_links`, `dfs.duplicate_title`,
`dfs.duplicate_description`, `dfs.redirect`, `dfs.canonical_chain`,
`dfs.image_alt_missing` all mirror an existing `health.*` counterpart
closely enough to plan the same way. `dfs.click_depth`, `dfs.orphan_page`,
and `dfs.large_page_size` are murkier — fixing them usually means
restructuring internal linking sitewide, which is more strategic than a
single-file edit even though it's T3-machine-checkable in principle; decide
per-code at implementation time rather than blanket-including them.

The blocker from 3a means these can't use the existing `{"check":
"code_absent", ...}` acceptance shape — `acceptance_check.py`'s own refusal
message already names the right fix: *"Verify it in the next cycle's
measurement, not here."* So: a **second acceptance check type**,
`{"check": "next_cycle", "code": ...}`, that `acceptance_check.py` treats as
"not verifiable now, by design" — it passes through at Stage 4 without
re-measuring, and the actual verification is Stage 3's own ratchet the
following month (RESOLVED means it held, REGRESSION means it didn't). This
reuses machinery that already exists instead of bolting a paid-API re-check
onto the PR gate.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/plan.py` | New `ACTIONS` entries for the qualifying `dfs.*` codes, each with `acceptance = {"check": "next_cycle", "code": ...}` instead of `code_absent`. `min_tier` per code, following the same T1-copy/T3-template split the `health.*` entries already use (e.g. `dfs.duplicate_title`/`dfs.duplicate_description` are T1; `dfs.broken_page`/`dfs.redirect`/`dfs.canonical_chain` are T3). |
| 2 | `pipeline/gates/acceptance_check.py` | `SUPPORTED_CHECKS` gains `"next_cycle"`; `verify_item()` branches — a `next_cycle` item logs `"deferred to next cycle's measurement — not re-checked here"` and counts as passed, without touching the build output. |
| 3 | `pipeline/audit/plan.py`'s `render_report()` | Worklist/report rendering distinguishes `next_cycle` items from `code_absent` ones (e.g. a `(verified next cycle)` suffix) so a reader isn't confused about why some claimed fixes skip Stage 4 verification. |
| 4 | `tests/test_plan.py`, `tests/test_acceptance_check.py` (or wherever each currently lives) | New tests: a `dfs.broken_page` item gets a `next_cycle` acceptance shape; `acceptance_check.py` passes a `next_cycle` claim without reading the build output and still refuses an unimplemented check type. |
| 5 | `CHANGELOG.md`, `docs/MODULES.md`, `docs/gate-reference.md` | per the sync-contract note above |

### 3c. Impact-weighted worklist ordering — scoped

Items within a lane sort by URL alphabetically today (`_lines()`'s sort key)
— a homepage title fix and an orphaned page's title fix count identically.
Once GSC impressions/clicks (already wired, per-URL via `gsc_findings`) and
keyword search volume (§2f, once built) exist, Plan can rank by actual
traffic/demand instead of alphabetical order.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/plan.py` | `work_item()` gains an optional `impact` field: looked up by URL against GSC impression data for `health.*`/`dfs.*` items, and by keyword `context` against search-volume data (§2f) for `serp.*` items. Missing data (GSC/DataForSEO not enabled, or the URL/keyword has no match) leaves `impact` unset — sorts last, never crashes, matches every other config-gated check's fallback behavior in this codebase. |
| 2 | `pipeline/audit/plan.py`'s `render_report()`/`_lines()` | Sort by `impact` descending within each lane/code group when present, falling back to the current alphabetical-by-location order when absent. |
| 3 | `tests/test_plan.py` | New tests: an item with impact data sorts before one without; an all-missing-impact worklist produces byte-identical output to today's (no regression on a client with no GSC/DataForSEO enabled). |
| 4 | `CHANGELOG.md`, `docs/MODULES.md` | per the sync-contract note above |

### 3d. REGRESSION paper trail from `changelog.json` — scoped

A `REGRESSION` item today just says "seen before, fixed, and back. The fix
did not hold" — no reference to which cycle claimed it fixed, or what PR.
Every past cycle's `changelog.json` already records exactly that
(`{finding_fp, status: "fixed", ...}` — same shape `already_fixed()` in
`remediate.py` already reads). Plan can look this up itself.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/plan.py` | New helper, alongside `assign_lanes()`: for each `REGRESSION` fingerprint, scan earlier cycles' `changelog.json` (newest first) for the most recent one recording that fingerprint as `"fixed"`, and attach `{"regressed_after_cycle": ..., "regressed_after_item": ...}` to the work item. |
| 2 | `render_report()` | The `REGRESSION` section's note grows the cycle/item reference when found (falls back to the current generic note when not — e.g. the regression predates any changelog, or the fix was a `--recommend` brief rather than a code change). |
| 3 | `tests/test_plan.py` | New test: a synthetic two-cycle fixture where cycle 1's changelog marks a fingerprint fixed and cycle 2's findings bring it back — asserts the annotation is attached and correct. |
| 4 | `CHANGELOG.md`, `docs/MODULES.md` | per the sync-contract note above |

### 3e. A Claude advisory pass over the finished worklist — scoped

This repo is explicit that `wf-site-plan` must stay byte-identical over an
unchanged cycle (`CLAUDE.md`) — fingerprinting and lane assignment are pure
set comparisons on purpose, and that guarantee is not something to trade
away for an LLM call. So: Claude runs **after** `worklist.json`/`report.md`
are written, as a separate, optional, best-effort step whose output never
feeds back into fingerprints, lanes, or the worklist items themselves.

Two things it can safely add, both purely advisory:

1. **Root-cause clustering** — e.g. "these 40 `og_image_missing` findings
   are probably one missing default in a shared layout," surfaced as
   grouping hints a human (or Remediate) can use to batch fixes, not as a
   claim the ratchet reads.
2. **A short prose summary** naming the 2-3 highest-value items (using
   3c's impact data once it exists) at the top of the output, for a human
   skimming rather than reading every lane.

Written to a **separate file** — `docs/audit/<YYYY-MM>/insights.md` — never
merged into `report.md`/`worklist.json`, so it can never be mistaken for the
deterministic artifact and a failed/flaky Claude call never blocks
`wf-site-plan` itself (same "advisory, never blocks" posture as
`seo-health.yml`'s monitoring checks).

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/plan.py` | New `--with-insights` flag (off by default, same convention as `measure.py`'s provider flags). When set, calls Claude once with the finished `worklist.json` and writes `insights.md`; a failed call logs a warning and exits 0 — it never fails the `wf-site-plan` run. |
| 2 | `docs/ADMIN-CHECKLIST.md` | Note the flag needs an `ANTHROPIC_API_KEY` (already present for Remediate) — no new credential. |
| 3 | `CHANGELOG.md`, `docs/MODULES.md` | per the sync-contract note above |

### 3f. Keyword-rank briefing — pairing `serp.absent`/`serp.page_two` with competitor-gap data — scoped

The direct answer to "how does Plan help rank for a specific keyword": today
it doesn't. `serp.absent`/`serp.page_two` have no `ACTIONS` entry, so they
never enter `worklist.items` at all — they land in `unclassified`, same as
every other provider code, with no keyword-specific detail.

**This cannot simply reuse `--recommend`'s existing brief loop.**
`remediate.py`'s `refused_in_cycle()` — the candidate pool `--recommend`
drafts briefs for — only pulls fingerprints already in `worklist.items` that
a normal remediate run attempted and marked `"no_change"`. A `serp.*`
finding is never in `worklist.items` today (no `ACTIONS` entry) and was
never attempted by a normal run in the first place, so it can't reach that
pool no matter how `--recommend` is invoked. This needs its **own**
selection path — it can still reuse `read_briefs()`/`render_briefs()` as
the output mechanism (both are keyed purely by fingerprint, format-agnostic
about what kind of finding produced it), just not the `--recommend` queue
that feeds them today.

**Depends on §2f's `competitor_gap_findings` existing** — the whole point
is pairing "you don't rank for X" with "competitor Y ranks #3 for X with a
page about Z," not just restating the keyword is absent.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | `pipeline/audit/plan.py` | New function, called from `plan()` alongside `build_worklist()`: for each `serp.absent`/`serp.page_two` finding in `unclassified`, match its `context` (the keyword) against `competitor_gap_findings` results for the same keyword. A match produces brief text (keyword, absence/page-two status, the competing domain and its ranking page); no match still gets a brief, minus the competitor detail. |
| 2 | `pipeline/audit/remediate.py` | `render_briefs()`'s header prose currently says every entry exists "because the copy does not live in this repository" — no longer true once a second brief category exists. Split into two sections in `human-worklist.md` (CMS-copy briefs vs. keyword-targeting briefs) rather than let the file's own stated reason become inaccurate. |
| 3 | New CLI entry point (e.g. `wf-site-plan --with-keyword-briefs`, or a small new script) | Since this isn't `--recommend`, it needs its own trigger — deciding which is the right home (`plan.py` vs. a new `remediate.py` mode) is an open call, not decided here. |
| 4 | `tests/test_plan.py` or `tests/test_remediate.py` | New tests: a `serp.absent` finding with a matching `competitor_gap_findings` result produces a brief naming the competitor; one with no match still briefs, without a competitor reference; `human-worklist.md`'s two sections don't collide on the same fingerprint. |
| 5 | `CHANGELOG.md`, `docs/MODULES.md` | per the sync-contract note above |

Natural follow-on once §2f's `llm_mentions_findings` ships: the same pattern
(pair a "not cited" finding with competitor-gap-style evidence) applies to
AEO citation drops, not just SERP rank — §2f's `sources_domain`/
`search_results_domain` breakdown is the exact "who's cited instead" data
this needs. Named here, not scoped to files yet — the schema question that
used to block this is resolved (§2f), the file-level plan isn't written.

### 3g. Open items for this stage

- Items 3b-3f above are scoped, none built. 3b (`next_cycle` acceptance
  type) is the one with a real cross-stage dependency — it changes
  `acceptance_check.py`, not just `plan.py`.
- Per-code `min_tier` decisions for `dfs.click_depth`/`dfs.orphan_page`/
  `dfs.large_page_size` (3b) are explicitly deferred to implementation time,
  not decided in this doc.
- 3f's CLI entry point (new flag on `plan.py` vs. a new `remediate.py` mode)
  is an open design call.
- LLM Mentions findings (§2f) have no Part 3 consumer yet — the natural
  extension of 3f once `llm_mentions_findings` is actually built (schema is
  now confirmed against docs, per §2f; not built yet, and not scoped to
  files here).
- Architectural note, not a defect: the weekly cron (§2e) never writes back
  to the repo, so it never updates Plan's ratchet — "faster cadence" (§2d)
  produces an alert, not a re-planned worklist. Plan still only reasons
  monthly, over the cycle folders. Worth keeping in mind so "weekly
  checks" isn't read as "Plan replans weekly."

## Part 4 — Remediate

Grounded in `pipeline/audit/remediate.py` and `skills/site-remediation/SKILL.md`,
both read in full. Same sync-contract note as Parts 2-3: every improvement
below that gets built implies its own `CHANGELOG.md`/`docs/MODULES.md` entry,
not restated per item.

### 4a. What `wf-site-remediate` does

Reads Plan's `worklist.json` and hands each actionable item to Claude Code
**one subprocess at a time** — not one prompt for the whole worklist. That
is deliberate: it turns the file→item mapping into a *measurement*
(`git status` before/after each item) rather than a claim the model makes.

The safety is not in this file — it is four things layered on top:
`tier_verdict` (the same judge the PR gate runs, applied here to every file
that actually changed — an out-of-tier edit ends the run at exit 9, never
reported as fixed), `claim_provenance_check` (no invented ratings/
credentials), `acceptance_check` (the finding must actually be gone), and
the operator's merge.

Two modes: normal fix mode (`Read Edit Write Grep Glob`, no Bash — narrows
the blast radius of a prompt injection hidden in the client's own page
copy) and `--recommend` mode (writes a brief instead of code, only for
items the changelog already recorded as `no_change` — any file change here
is itself treated as a refusal, since this mode holds no write tool at
all). Resumable by design: a re-run skips only what is marked `fixed`
(matched by `finding_fp`, never positional `id` — B-013/B-020), and merges
into the changelog rather than overwriting. `--max-items`/`--max-files`
stop a run cleanly, not silently. Queue order is worst-lane-first
(REGRESSION → NEW → PERSISTING) so a cap never cuts the most informative
items. B-025's fix: a page whose copy lives in a CMS gets a brief instead
of endlessly re-attempting and refusing, and `docs/human-worklist.md` sits
on `DEFAULT_DENY` so the agent itself can never write there in a normal run
— only `--recommend`, which holds no write tool, can.

### 4b. Six improvements, ranked — grounded in the code and in 2026 practice for this class of pipeline

**1. One refused item halts the entire run, and a chronically-refused item
has no escape valve.** If any changed file fails `tier_verdict`, the whole
run stops (`stopped` set, loop breaks) — every other queued item, even
unrelated ones, goes unattempted this run. Each item already runs in its
own fresh subprocess (no shared context to protect), so there is no
structural reason a bad item should block the other nine. Worse: unlike
`no_change` (which eventually reaches `--recommend`'s brief queue), a
refused item has no equivalent off-ramp — it gets retried and refused
again, forever, repaying for the same mistake every cycle. This is the
exact pattern B-025 already fixed once, for a different trigger. Fix:
skip-and-continue on a single refusal; after N refusals for the same
fingerprint across cycles, route it to a brief or a "needs a tier
decision" flag instead of retrying indefinitely.

**2. Tool-allowlisting is a narrowing, not a boundary — and the code
already proved it.** `RECOMMEND_TOOLS`/`ALLOWED_TOOLS` deliberately exclude
Bash, but the module's own comment records a live run (2026-08-10) where
the writer reached for Bash anyway despite it being absent from the list
(B-026) — caught, but only because `snapshot()`'s `git status` diff happened
to reveal it, not because anything blocked the attempt. Checked current
practice for this exact threat class (an agent reading untrusted content —
here, the client's own page copy — with tool access): the 2026 consensus is
that tool-allowlisting alone is not a boundary; enforcement has to sit at
the infrastructure level (an isolated container/sandbox around the
subprocess itself) so a restriction holds regardless of what the model was
told or convinced to do. Today `run_agent()`'s `subprocess.Popen(["claude",
...], cwd=str(project), ...)` runs directly on the host with no such
isolation. This is the one item on this list with a **confirmed live
incident already in the ledger**, not a hypothetical.

**3. No cost cap, and model selection never escalates.** `cost_usd` is
tracked and printed but never checked against a limit — a `--max-cost`
flag, stopping cleanly the same way `--max-items`/`--max-files` already do
(same resumable/merge machinery, no new plumbing), closes half of this.
The other half: `DEFAULT_MODEL = "sonnet"  # v3 §8: Sonnet for bulk, Opus
for hard judgment` names a policy the code never implements — every item in
a run gets the same `--model`, full stop. Checked current practice: 2026
production systems don't pick a model per task ahead of time so much as
**cascade** — try the cheap model, escalate to the expensive one only on a
failure/low-confidence signal — which fits this pipeline better than a
static kind→model table would, since an item's real difficulty often isn't
knowable until the cheap model actually tries it. Concretely: an item that
comes back `error` (or a `--recommend` brief a human rejects) gets one
automatic retry on a stronger model before the run gives up on it, still
inside the existing per-item budget/cap accounting.

**4. No parallel execution.** Every item runs sequentially, one subprocess
at a time. Checked current practice: git worktrees are the 2026 consensus
isolation primitive for exactly this "one task, one full checkout"
execution shape — a fresh worktree per item gives complete filesystem
isolation without duplicating the repo, and would let this pipeline run N
items concurrently without corrupting each other's `git status` diffs (the
reason execution is sequential today, though the code doesn't say so
explicitly — parallel writers sharing one working tree would make
`snapshot()`'s before/after diff attribute the wrong changes to the wrong
item). A worktree-per-item model preserves the exact measurement guarantee
this file is built around while unlocking real throughput — a cited
benchmark for this pattern showed a 63% wall-clock reduction on a
comparable parallel-CI workload.

**5. `no_change`'s reason is unstructured free text — the code's own
docstring admits it.** `refused_in_cycle()`, the entire candidate pool for
`--recommend`, says outright: *"Which one it was is free prose in `note`
today, so the operator picks from this pool rather than the code
guessing."* Requiring the agent's `NO CHANGE <reason>` line to pick from a
small enumerated set (`ALREADY_FIXED` / `COPY_NOT_IN_REPO` / `OTHER`) would
let `--recommend` (and any future automation) select reliably instead of
depending on a human reading prose.

**6. No per-client style customization hook.** The doctrine (`SKILL.md`)
is one shared file for every client. A client with an unusual brand-voice
rule or a banned-word list beyond the shared `forbidden_phrases` health
check has no way to inject that without editing the shared skill — which
changes behavior for every other client too. Checked
`client-config.starter.yml`'s full field list — no `remediation_notes`-style
field exists today. A single optional client-config field, appended to the
doctrine at prompt-build time, would close this without forking anything.

Items 1, 5, and 6 are cheap, self-contained changes to `remediate.py` alone.
Items 2 and 4 are real infrastructure work (a sandboxing layer, a
worktree-orchestration layer) — bigger lifts, and the two most likely to
need an explicit operator decision on how much complexity to take on before
being scoped to files. Item 3's cost cap is cheap; its cascade-retry half
depends on item 1's "escape valve" plumbing existing first (an
escalation retry and a give-up-and-brief path are the same piece of
machinery, triggered differently).

### 4c. Open items for this stage

- None of 4b's six items are scoped to files yet — this section is
  priority + rationale, the same stage §2d's cadence list was before §2e
  gave the cron workflow a concrete design.
- Items 2 (sandboxing) and 4 (worktree parallelism) need an operator
  decision on complexity/cost before file-level scoping is worth doing —
  named here as the two to discuss first, not to build first by default.
- Item 3's retry-on-failure half and item 1's chronic-refusal escape valve
  are the same underlying mechanism (an item that keeps failing needs
  somewhere to go besides "retry forever") — scope them together, not as
  two separate features, when the time comes.

## Part 5 — Gates

Grounded in all 19 files under `pipeline/gates/`, `pipeline/lib/baseline.py`,
and `.github/workflows/quality-gate.reusable.yml` (the actual wiring, not
just `docs/gate-reference.md`'s prose — that doc itself warns some of its
content is a dated 2026-07-19 report and needs re-checking against code,
which is what this section does). Same sync-contract note as Parts 2-4.

### 5a. What Gates does

19 checks run on the client's PR, in the client's own GitHub Actions (a
GitHub Actions workflow can only gate a PR on the repo it lives in — this
is why gates can't just run on an operator's laptop instead: only a check
that reports back to GitHub's own PR status API can make the Merge button
un-clickable, "by construction" rather than by discipline). Three tiers —
**PRE-build** (source tree), **BUILT** (rendered HTML output), **LIVE**
(post-deploy, never blocks a merge, alerts only). Three gates
(`tier_check`, `claim_provenance_check`, `acceptance_check`) exist purely
because a model writes into client repos, judge the PR diff regardless of
who authored it, and are permanently **never-baselineable** — along with
six more (forbidden-sweep, audit-ssr, fingerprint-check, parity-check,
orphan-check, rules-selftest) where "it's been broken a while" is not an
acceptable state. The other 8 gates (BASELINEABLE) can be blocking on *new*
findings while a client's pre-existing legacy debt is recorded once and
never re-flagged, via `pipeline/lib/baseline.py`'s ratchet.

### 5b. Are all 19 needed? — one confirmed real duplication, one doc error, one unused capability

**`noncommodity_check.py`'s `duplicate_of_sibling` check is a verbatim copy
of `audit_built.py`'s `14b_uniqueness_vs_siblings`** — `noncommodity_check.py`
says so itself ("reuse audit-built.py's 5-gram overlap engine verbatim...
identical to audit-built check 14b, so the two gates never disagree").
Confirmed: both files independently implement the same 5-gram-overlap
threshold logic, copy-pasted rather than shared. The same check runs twice
per PR, in two gates, under two different pass/fail contracts (`audit_built`
folds it into a 30-point composite; `noncommodity_check` treats it as one
of two dedicated checks). Real overhead — worth extracting into one shared
function both gates call, not two gates duplicating one algorithm.

**`docs/gate-reference.md`'s BUILT-tier table lists `proof-assert.sh` as one
of the 19 — it isn't.** It lives in `pipeline/deploy/`, not `pipeline/gates/`,
and is only invoked from `deploy.reusable.yml` (Cloudflare-only, opt-in,
post-merge) — zero references in `quality-gate.reusable.yml`. This resolves
last session's open question about whether a deploy-time check quietly
gates PR-terminal clients with no deploy job: it doesn't, because it was
never actually part of the PR gate suite. The 19-file count in
`pipeline/gates/` (and `CLAUDE.md`) is the correct, current number; the doc
conflated a deploy-time check with the PR gate suite.

**`forbidden_sweep.py`'s `source` mode is coded but not wired into CI.**
`quality-gate.reusable.yml` only ever calls `wf-forbidden-sweep built ...`
— no `source` invocation anywhere in the file. The module's own stated
purpose ("catches violations BEFORE build") isn't happening today; only
built-mode, post-build, actually blocks a merge. Not a live bug (built mode
still catches everything that matters), but a real, currently-unrealized
capability sitting in the codebase unused.

### 5c. Upgrades required by what Parts 2-4 already planned

- **`acceptance_check.py` needs the direct change §3b already scoped.**
  Confirmed against current code: `SUPPORTED_CHECKS = {"code_absent"}` and
  `verify_item()`'s hard `code.startswith("health.")` refusal are exactly
  the blocker §3b identified — nothing here has drifted since that section
  was written.
- **`tier_check.py` needs no change for §4b's worktree parallelism.** It
  diffs `{base}...HEAD` against the final branch state — base-independent
  of how the commits reaching that state were produced, as long as
  parallel worktrees merge to one branch before the PR opens.
- **`tier_check.py` needs no change for §4b's chronic-refusal escape
  valve either** — it only re-judges the final committed diff via the same
  `tier_verdict` function `remediate.py` already calls; how remediate
  *decided* what to attempt doesn't reach this gate.
- **No gate touches §2f's three new DataForSEO finding codes** (LLM
  Mentions, competitor gap, keyword volume) — they're Measure/Plan-side
  only and never appear in a PR diff a gate reads.

### 5d. Ten edge cases not currently accounted for

1. **The baseline fingerprint algorithm has no independent version tag** —
   only the file's `schema` string is checked. If the fingerprint formula
   itself ever changes without a schema bump, every legacy-debt entry
   silently stops matching and a client's whole inherited backlog reports
   as new regressions overnight, with no error.
2. **An empty-but-present `gate-baseline.json` behaves like no baseline**
   (every finding "new") but skips the loud warning the absent-file path
   gives — same failure mode, no signal that something's wrong.
3. **Two PRs both running `--refresh` concurrently** — the baseline file is
   fully replaced on write, so whichever merges last can silently re-add
   debt the other had already paid down.
4. **`tier_check.py`'s base-resolution fallback chain** (`origin/main` →
   ... → `HEAD~1`) succeeds even in a shallow clone, silently diffing only
   the last commit instead of refusing — the "fetch-depth:0 or refuse"
   guarantee only holds if none of the fallbacks resolve.
5. **§3b's `next_cycle` acceptance merges a PR as "verified" for a finding
   never actually re-measured this run** — the gap only closes at next
   month's `wf-site-health`, and nothing today flags a merged PR as
   pending confirmation in the meantime.
6. **Plan-time `tier_blocked` can go stale if a human bumps tier mid-cycle**
   — `selectable()` reads the flag `plan.py` baked in at Plan time, not a
   fresh `tier_verdict`, so a newly-permitted item stays excluded until the
   next `wf-site-plan` run.
7. **`forbidden_sweep` source-mode's absence from CI (§5b) means a banned
   phrase in `src/data/*.ts` isn't caught until after a full build**, not
   pre-build the way the module's own docstring says it should be.
8. **`rules_selftest`'s blocking status depends on every client caller
   actually including it** — a client repo copying an older
   `.github/examples/` caller could run `forbidden_sweep` without the
   meta-gate that catches a dead rule making it vacuously pass.
9. **The weekly-signal `surfaced_early` item id shape**
   (`wi-{cycle}-weekly-{idx}`, from this session's own work) is unverified
   against any assumption a gate or the dashboard might make about
   work-item id format.
10. **No gate re-derives tier from a live config re-read mid-run** —
    `tier_check.py` reads config once at the start of `main()`; a config
    edit mid-run (unlikely in a normal build, not impossible in a long
    one) wouldn't be picked up.

### 5e. A silent-but-auditable quality pass — scoped design

The ask: run something like this session's own thermo-nuclear review
against Claude's remediation edits before merge, auto-fix what it finds,
and don't interrupt a human to do it. This fits this repo's safety model
better than it might first sound, because that model was never "trust the
writer" — it's `tier_check`/`claim_provenance_check`/`acceptance_check`
judging **the final diff, regardless of who produced it**. An auto-fixer is
just another writer subject to the same three never-baselineable gates
everything else already goes through; it doesn't open a new hole.

Two things still need resolving deliberately, not left implicit:

1. **"Doesn't report to the user" cannot mean "leaves no trace."** This
   repo's sync contract runs on "proof or it did not happen" — even the
   fully autonomous parts of this system (the daily monitor, the ratchet)
   always write something inspectable after the fact, even though nobody
   watched it happen live. So: no interactive prompt, no blocking
   question — but it still writes a record (its own entry in
   `changelog.json`, or a sibling `quality-review.json`) so it is
   auditable later even though nobody was asked to approve it in the
   moment.
2. **Running a full ambitious review on every PR is real, avoidable cost.**
   Most Stage 4 items are a three-word title fix — there is no abstraction
   to over-engineer in a string change. The value concentrates in T3/
   structural edits. Scope the trigger to diff size/tier rather than every
   PR, the same way this repo already scales effort by task
   (`DEFAULT_MODEL` comment: "Sonnet for bulk, Opus for hard judgment").

Design: a new early step in the quality-gate workflow (client's own
Actions, before the 19 existing checks run), triggered only above a
diff-size/tier threshold — runs a maintainability/simplification review
against the diff, auto-applies fixes it is confident about, using the
exact same `snapshot()`/`tier_verdict` measurement `remediate.py` already
uses per item, so an out-of-tier "fix" still refuses at exit 9 like any
other edit would. Anything found but not safely auto-fixable still surfaces
as a normal gate finding, visible in the PR comment — "don't report" only
covers what it actually resolved, not what it couldn't.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | New file, e.g. `pipeline/gates/quality_autofix.py` | Reads the PR diff, runs the review, applies safe fixes via the same measured-diff pattern as `remediate.py` (`snapshot()` before/after, `tier_verdict` on every changed file), writes a record of what it touched and why. |
| 2 | `.github/workflows/quality-gate.reusable.yml` | New early step, gated on diff size/tier, before the 19 existing gate steps — so anything it fixes is what the rest of the suite then judges. |
| 3 | `docs/audit/<YYYY-MM>/changelog.json` schema (or a sibling file) | Where the auditable-but-silent record lands — an open question named here, not decided: reuse `changelog.json`'s existing shape (another set of `_base`-like entries) vs. a dedicated file, so it doesn't get confused with `remediate.py`'s own attribution. |
| 4 | `docs/gate-reference.md`, `docs/MODULES.md`, `CHANGELOG.md` | per the sync-contract note above |

Not scoped: the diff-size/tier threshold's exact numbers, and which
specific simplification patterns it's allowed to auto-fix vs. only flag —
both are operator judgment calls, not code-derivable.

### 5f. Open items for this stage

- 5b's duplication (`noncommodity_check`/`audit_built`'s shared 5-gram
  logic) is a real, scoped-able cleanup — extract to one shared function,
  not built yet.
- 5b's unwired `forbidden_sweep` source-mode is a decision point: wire it
  into CI (catches violations earlier, pre-build) or delete the unused
  mode (less code to maintain) — either is defensible, neither is decided.
- `docs/gate-reference.md` itself needs a correction pass: drop
  `proof-assert.sh` from the BUILT-tier table (5b), and its own staleness
  warning about the missing 2026-07-19 report should probably point
  readers here instead, once this section is committed.
- 5d's ten edge cases are named, none scoped to fixes — most concerning are
  #1 (silent fingerprint drift) and #5 (a `next_cycle`-verified PR with no
  "pending confirmation" marker), since both fail by looking clean rather
  than by erroring loudly, which is exactly the failure shape this whole
  pipeline is built to avoid elsewhere.
- 5e's quality auto-fix pass is scoped at the design level; the diff-size/
  tier trigger threshold and its allowed fix vocabulary are explicitly
  open operator decisions, not resolved here.

## Part 6 — Human Merge

Grounded in `pipeline/dashboard/review.py` (read in full) and
`docs/ADMIN-CHECKLIST.md` §§2-3. Same sync-contract note as Parts 2-5.

### 6a. What this stage is

A human, on GitHub's own UI, is the only thing that can actually merge.
`merge` is deliberately absent from the dashboard's `GIT_ACTIONS` dict, and
the code says why: *"human merge is the only path to production... a
button beside a green checkmark is not the same act as reading a diff."*
The dashboard (its own "Gate 2") gets a change *to* that point — reviewing
the diff, pushing, opening the PR — and stops there on purpose.

**Approving is `git add`.** Staged means approved, unstaged means pending
— the git index itself is the approval record, so there is no separate
approvals file that could drift out of sync with the tree; `git status`
shows an operator the same thing the dashboard screen does. Items that
touched the same file are one inseparable approval unit (a union-find over
shared files), because approving one edit and rejecting another to the
same file isn't a coherent operation. Every path in an approve/reject
request must appear in that cycle's `changelog.json` file map — without
that check, the endpoint would be `git add`/`git restore` over any path a
browser happened to name. Rejecting a **created** file is refused rather
than silently deleted, since `git restore` has no way to undo a create.

### 6b. The central gap: "red gate = un-clickable Merge" is not actually true for most clients

`docs/ADMIN-CHECKLIST.md` contradicts itself across two adjacent rows, and
both halves are correct in isolation — the contradiction is the finding:

- **Row 5**: "`quality-gate` set as a required status check... Red gate =
  un-clickable Merge = production blocked **by construction**."
- **Row 6**: "Branch protection... **cannot be enabled on GitHub Free for a
  private repo.** The gate reports but cannot block."

Row 5's guarantee depends entirely on Row 6's precondition — and Row 6
admits that precondition fails for the single most common client shape
(a small business's private repo on the free tier). **Checked: CODEOWNERS-
required-review has the same dependency** — GitHub's own docs confirm
"Require review from Code Owners" is itself a branch-protection setting,
so it inherits the identical Free-tier limitation rather than offering an
escape hatch.

**Confirmed by grep: nothing in this codebase checks or surfaces actual
branch-protection status anywhere** — not `onboard.py`, not the dashboard's
`state.py`/`server.py`. It exists only as a checklist row a human has to
remember, with the same silent-failure shape this project's own sharp
edges keep warning about elsewhere (a missing `gate-baseline.json` at
least gets a loud `::warning::`; missing branch protection gets nothing).
**For any client on GitHub Free with a private repo, Stage 6's entire
safety model rests on an operator's discipline, not a technical
guarantee** — a human genuinely can click Merge on a red PR today, and
nothing in this system stops them.

### 6c. Improvements — five, two of them ruling out dead ends worth not re-chasing later

1. **Make branch-protection status a code-checked, surfaced fact, not a
   checklist row.** `wf-onboard` (or the dashboard's client screen) should
   call `gh api repos/<owner>/<repo>/branches/<default>/protection` once
   and print/display a persistent warning when it's absent — the same
   loud-warning treatment `docs/gate-baseline.json` already gets, applied
   to the gap that actually matters more.
2. **Name the concrete fix, not just "a paid plan."** The checklist today
   says "needs a paid plan, or a public client repo" with no next step.
   GitHub Team (~$4/user/month) is the minimum paid tier that actually
   unlocks branch protection on a private repo — naming it removes the
   ambiguity between "upgrade something" and an actual, priced action.
3. **An auto-revert bot, not just an alert — and it needs no paid plan.**
   The obvious "detection backstop" idea was to alert when a red PR merges
   anyway; research turned up something stronger and just as cheap: a
   GitHub Actions workflow triggered on `push` to the default branch,
   checking whether `quality-gate`'s last run for that commit's PR was
   green, and if not, **committing an automatic revert** — using nothing
   but Actions' own default write access, which every repo gets regardless
   of plan. This isn't prevention (a human already clicked Merge), but it
   closes the window to seconds instead of leaving a bad merge live
   indefinitely, without costing anything.
4. **Checked and ruled out: GitHub's newer "repository rulesets" (the
   modern successor to classic branch protection) have the identical
   free-tier limitation.** Confirmed against GitHub's own docs: rulesets
   are available on free-tier **public** repos and organizations, but
   private-repo rulesets need GitHub Pro at minimum — same wall, different
   feature name. Worth stating plainly so nobody spends time re-checking
   this path later expecting a newer feature to have quietly fixed it.
5. **Checked and ruled out: third-party merge bots (Mergify, Kodiak) are
   not an independent workaround either.** Both explicitly depend on
   GitHub's native branch-protection settings to know what "required"
   means — Mergify's own docs say it *reads and injects* branch-protection
   rules as merge conditions, and Kodiak's merge decision is "largely
   driven by GitHub Branch Protection." Neither bypasses the limitation;
   both inherit it. "Just install a merge bot" is a dead end, not a
   cheaper alternative to GitHub Team.
6. **Surface the gap in the dashboard itself, not just at onboarding.** A
   client's branch-protection state is checked once (item 1) but never
   revisited — the dashboard's client screen could carry a persistent
   banner ("merge is not technically enforced for this client — you are
   the only safeguard, until item 3's revert bot exists") on the push/PR
   screen specifically, rather than staying silent about a fact from
   onboarding day that nobody re-checks after.

### 6d. Open items for this stage

- None of 6c's items are scoped to files yet.
- Item 3 (the auto-revert bot) is the one genuinely new piece of
  infrastructure here — a new `.github/workflows/*.reusable.yml`, not a
  code tweak to an existing file. It belongs conceptually to Part 7
  (Monitor) as much as here, since it's a post-merge watcher; named in
  this part because the gap that motivates it is Stage 6's.
- Items 4 and 5 are closed questions now (both ruled out), not open ones —
  kept in the numbered list because they're worth reading, not because
  anything remains undecided about them.

## Part 7 — Monitor

Grounded in `.github/workflows/seo-health.reusable.yml`, `pipeline/deploy/
crawler-check.sh`, and `pipeline/lib/score.py` (all read in full). Same
sync-contract note as Parts 2-6.

### 7a. What this stage is, and how it relates to Measure (Part 2)

Daily + `workflow_dispatch`, in the client's own GitHub Actions, **the only
thing watching production** — the pipeline is PR-terminal, so nothing else
observes what happens after a human merges. Checks: critical pages return
200 with real content and the presence of title/h1/canonical/JSON-LD
schema; the sitemap has a minimum URL count; and (`crawler-check.sh`) AI
citation crawlers (OAI-SearchBot, ChatGPT-User, PerplexityBot, Bingbot,
Googlebot, Claude-SearchBot) get a real 200 with no WAF/bot-rule challenge
— the failure mode a static build can never reveal, since an edge-level
block is invisible in `./out`. It never blocks a merge (it runs after one)
and writes nothing — confirmed: `permissions: contents: read`, pure bash,
no JSON artifact, an optional chat-webhook alert on failure and nothing
else persists.

**Not the same job as Measure, and shouldn't be merged into it** — different
cadence (daily vs. monthly), different cost profile (must stay free/fast
enough to run forever; Measure can afford paid enrichments), different
consumer (an alert now vs. a curated work queue for later). But there is a
real, confirmed overlap worth fixing on its own: Monitor's bash re-implements
a stripped-down version of checks `measure.py`'s `check_page()` already has
— `grep -qi '<title'`/`'<h1'`/`'rel="canonical"'`/`'application/ld+json'`
duplicate `health.title_missing`/`h1_count`/`canonical_mismatch`/
`schema_business_missing`, in bash instead of shared Python. Same class of
problem as Part 5's `audit_built`/`noncommodity_check` duplication — the
fix is sharing one implementation, not merging the two stages.

### 7b. Five improvements

1. **Share the duplicated check logic with Measure, and feed Monitor's
   findings into the same `weekly_signal` mechanism (Part 3) instead of a
   dead end.** Today a failure here is a chat ping that vanishes — nothing
   persists, so a site-down event never reaches the actual work queue.
   Pulling a lightweight presence-only mode out of `check_page()` for
   Monitor to call, and writing its result in the same shape
   `apply_weekly_signal()` already consumes, would mean "the site was down"
   shows up as a `surfaced_early` item in `worklist.json`, not just an
   alert nobody structurally follows up on. Honest trade-off: it adds a
   Python dependency and a JSON-writing step to a script whose main virtue
   today is pure-bash simplicity — worth deciding deliberately.
2. **SSL/TLS certificate expiry monitoring — currently zero coverage.**
   Checked current practice: 30/14/7/1-day-before-expiry alerting is
   standard, and a `curl` 200-check structurally cannot catch this early —
   by the time a cert has actually expired and breaks the 200 check, the
   warning window that matters (weeks before) is already gone. One
   `openssl x509 -noout -enddate` call per critical domain, cheap, no new
   credential.
3. **A real-user-data signal — Monitor is 100% synthetic today.** Every
   check here is a robot fetching a page; none of them can tell "the page
   loads fine but conversions quietly collapsed" (a broken tracking tag, a
   redirect loop invisible to one curl, an algorithm hit). GA4 access is
   already collected at intake (§1a) and unused everywhere in this pipeline
   — a genuinely new use for it. Checked current practice for the false-
   positive problem real-time traffic alerting has: compare against same-day-
   last-week, same-day-4-weeks-ago, and a 30-day rolling average, and
   require at least 2 of 3 to read as anomalous before alerting — the
   pattern that avoids flagging every seasonal dip or one-off event as a
   crisis.
4. **Security headers (HSTS, X-Content-Type-Options, etc.) — not checked
   anywhere, pre-build or live.** Cheap to add alongside the existing curl
   calls; catches a redeploy that silently drops a header a prior
   configuration set, which is a trust/compliance regression a "page
   returns 200" check has no way to see.
5. **One flat alert channel for every severity.** A site fully down and a
   certificate expiring in 30 days currently reach the operator the same
   way (the same optional chat webhook, or GitHub email if unset). Site-
   down deserves a louder, harder-to-miss channel than "check Slack
   eventually"; a 30-day cert warning is a digest item, not a page. Worth
   tiering by severity once item 2 exists to actually generate a
   non-urgent class of alert.

### 7c. A weekly client-facing report — scoped design

No client-facing report exists anywhere in this codebase today — checked:
`pipeline/dashboard/static/report.html` renders `report.md`, but the
dashboard is explicitly a `127.0.0.1` operator console, never something a
client sees directly. What already exists and is ready to reuse:
`pipeline/lib/score.py`'s `score()` (SEO/AEO score per cycle), `series()`
(the score trend, already computed once for the dashboard's chart so a
report never becomes a second implementation of "the score over time"),
and `projected()` (what the score would be if this cycle's claimed fixes
hold) — exactly the "here's the improvement" data a client report needs,
sitting unused outside one internal chart.

**Same derivation-only rule that governs Remediate's writing governs this
too**: every number in a client report must trace to code-computed data
(the score functions above, `worklist.json`'s RESOLVED/NEW/REGRESSION
counts, `changelog.json`'s fixed-item count) — an LLM pass may turn those
facts into readable prose for a non-technical reader, but never invent or
adjust a number itself. Same boundary as §3e's Plan-stage advisory pass:
Claude writes prose around code-computed facts, on a separate file, never
feeding back into anything the ratchet reads.

**Where it lives and who sends it**: `docs/audit/<YYYY-MM>/client-report.md`
(or a dated weekly variant once §2e's cron exists), committed to the
**client's own repo** (Model A — consistent with every other artifact in
this pipeline). This system does not contact the client directly anywhere
today (PR-terminal, human-merge, human-deploys) — the operator is the one
who actually sends or pastes this, same as everywhere else a human is the
last step.

**Cadence reuses infrastructure already scoped, not a fourth schedule.**
§2e's `measure-cron.reusable.yml` is already the weekly-run home; a client
report is a natural additional consumer of that same run rather than a
new cron surface.

Scoped change list:

| # | File | Change |
|---|---|---|
| 1 | New file, e.g. `pipeline/audit/client_report.py` (`wf-client-report`) | Reads the latest cycle's `findings.json`/`worklist.json`/`changelog.json` (+ Monitor's history, once 7b item 1 lands), computes score/delta/fixed-count/uptime-% in code, writes the plain-language file. Optional `--with-prose` Claude pass, off by default, writes only the narrative wrapper around already-computed numbers. |
| 2 | `.github/workflows/measure-cron.reusable.yml` (§2e) | New step calling `wf-client-report` after the weekly measure run, so the report reflects the same cadence rather than a new one. |
| 3 | `tests/test_client_report.py` | New tests: numbers in the output match `score.py`'s own functions exactly (no drift, no second implementation); the prose pass never appears without `--with-prose`; missing Monitor history degrades gracefully (no crash, just an omitted section) — same config-gated-check convention this codebase uses everywhere. |
| 4 | `CHANGELOG.md`, `docs/MODULES.md`, `docs/ADMIN-CHECKLIST.md` | per the sync-contract note above; note this is the first artifact in this pipeline explicitly written for a non-technical reader, so it is also subject to `CLAUDE.md`'s Writing Standards (Title Case headings, no em dashes) the same as any other public-facing copy. |

Not scoped: whether Gates/Human-Merge activity (PRs reviewed and merged
this period) belongs in the same report — a reasonable addition, left out
here to keep this pass's scope to what was actually asked.

### 7d. Open items for this stage

- None of 7b's five items or 7c's report are scoped to files beyond the
  tables above.
- 7b item 1 (shared check logic + `weekly_signal` feed) is the one that
  most directly answers "should Measure and Monitor be combined" — the
  answer stayed "no, but connect them," consistent with the discussion
  that preceded this section.
- 7c depends on §2e's cron workflow existing to reach weekly cadence
  cleanly; it can also run monthly against the existing cycle in the
  meantime, degrading gracefully rather than waiting on §2e.
- This is the last of the seven stages — Parts 1-7 are all now written at
  the same level of grounding. Nothing across any part has been built
  except the weekly-signal feature (Parts 2-3), which is implemented,
  tested, and verified live against `leeserie.com`.
