# How It Works

Plain-language walkthrough of the whole pipeline, start to finish. Read this first. The detail lives in [`gate-reference.md`](./gate-reference.md) (per-gate contracts and exit codes), [`MODULES.md`](./MODULES.md) (every module, one line each), and [`../SITE-AUDIT-PIPELINE.md`](../SITE-AUDIT-PIPELINE.md) (the v3 design doc and its open decisions).

---

## The one-line version

A client gives us collaborator access to their repo and their domain. The pipeline measures the live site, compares this month against every previous month, decides what is worth fixing and what the agent is even allowed to touch, hands each item to Claude Code one at a time, and opens a pull request — **then stops and waits for a human.** The operator's merge is the end of the pipeline. Deployment is theirs, on whatever platform the client is actually on; a daily monitor is what watches the live site afterwards.

---

## Three gates, and one button for everything else

The console derives which of eight stages a client is on from the artifacts already
on disk, and offers **one** next action. Three of those stages are yours; the rest
are a click.

```
ADD CLIENT                    repo · domain · TIER (T1 by default)
  │  clone · config · preflight · profile · scaffold · commit the scaffold to main
  ▼
GATE 1 — THE INTERVIEW        ← you. unavoidable.
  │  Nobody can invent a licence number, opening hours, or a review count.
  │  wf-preflight exits 12, the console names the file, the same button resumes.
  ▼
  │  measure → plan           automatic: site-health chains into site-plan, because
  │                           a measured cycle with no lanes is a useless state
  ▼
ONE CLICK — REMEDIATE         shows the item count first; a re-run RESUMES
  │  Claude Code edits inside the tier, one item per invocation
  ▼
GATE 2 — THE DIFF             ← you. per item, or approve all.
  │  Approving is `git add`. The git index IS the approval record.
  │  Items that touched the same file are one unit: those diffs are not separable.
  ▼
  │  commit → gates → push    in that order, and only that order
  ▼
  "Open a pull request?"      asked, never assumed
  ▼
GATE 3 — THE MERGE            ← you, on GitHub. the only path to production.
```

**Why commit before gating.** `tier_check` and `claim_provenance_check` diff
`origin/<default>...HEAD` — commits, not the working tree. Run either on a dirty
checkout with no cycle commit and the diff is empty, both exit 0, and you get a
green "every check passed" over work they never looked at. The console **refuses**
to start them with nothing committed, and the review screen only offers them after
the commit, so the correct order is the only order available.

**What the numbers mean.** The client screen carries an **SEO** and an **AEO** score
and a count of findings left. The score is a pass rate over *(page, check)* pairs: a
check either fires on a page or it does not. That is why 1158 alt-text findings on
one page cost one pair rather than 1158, why a check whose config field is unset
leaves the denominator instead of counting as a pass (it is listed as `not scored`),
and why a cycle nobody measured reads `not measured` rather than 100. The chart
draws a **solid** line for measured cycles, a **dashed** segment to a hollow marker
for what the pending PR *claims* it will do, and marks verification only when
`acceptance_check` can actually run — for a client with no static export it says
*cannot verify*, which is not the same as *not verified*.

---

## The flow, step by step

### 1. Onboarding: a repo and a domain

```bash
wf-onboard acme/roofing-site acmeroofing.com
```

One command runs the whole sequence: clone, generate `docs/client-config.yml`, verify the live site responds, check the config coheres, scaffold the client-repo docs contract, measure, plan.

It **stops** at the one step nothing can automate. `wf-bootstrap-config` can read a framework off disk and scrape a business name off the homepage, but it cannot invent a client's hours, their licence number, or the services they refuse to perform. It writes `TODO` and preflight refuses until a human replaces them. `wf-onboard` exits 1, names the step, and resumes from there when you run it again.

It also asks `gh` what permission we actually hold. Read access is not fatal — measuring a site you can only read still produces a report worth delivering — but it means no PR can ever be opened from that checkout, and that is better known now than after a paid agent run.

### 2. The client profile is the source of truth

Everything downstream reads `docs/client-config.yml` in the **client's own repo** (**Model A**). It describes the client's shape: topology, states, framework, where the build output lands, the forbidden-phrase ledger, the NAP block, the trust signals — and the **tier**, which decides what the agent may touch.

No client fact is ever hardcoded in a script. A missing required key stops the run rather than being guessed at.

### 3. Measure: the live site becomes typed findings

```bash
wf-site-health --project ~/clients/roofing-site
```

Fetches every URL the sitemap declares and runs 18 `health.*` checks per page — title and description bands, H1 count, canonical, noindex, OG image, business/FAQ/breadcrumb schema, forbidden phrases, tel links, GA4, image alt text, thin content. Out comes `docs/audit/<YYYY-MM>/findings.json`, one typed `Finding` per problem.

Three external providers can be switched on — CrUX for field Core Web Vitals, Search Console for impressions and cannibalization, DataForSEO for an on-page crawl. All are **off by default and credentialed from the environment only**. A provider with no credentials returns a **named skip that is written into the artifact**, because a provider that silently returned nothing would make the site look cleaner than last month and the ratchet would report the difference as RESOLVED.

### 4. Plan: four lanes and a worklist

```bash
wf-site-plan --project ~/clients/roofing-site
```

Compares this cycle's findings against the earlier monthly folders — **the monthly folders are the time series**, there is no second database — and sorts every finding into a lane:

- **RESOLVED** — was there, is gone. Good.
- **PERSISTING** — was there, still there. Aging.
- **NEW** — appeared this cycle.
- **REGRESSION** — we fixed this before and it came back. **The lane the module exists for.**

Fingerprints deliberately exclude the measured detail, so a finding that merely gets *worse* (`len=71` degrading to `len=210`) stays PERSISTING instead of masquerading as new.

Out come two files. `report.md` lists **every** finding — the tier filter never hides one. `worklist.json` carries only what the client's tier permits the agent to act on; everything else appears in the report under *Not Actionable at T1* with the tier that would unlock it, or *Needs a Human* when no acceptance criterion maps to it.

### 5. Tiering: what the agent may touch

A tier is a **path + operation allow-list**, declared per client and enforced by a gate on the PR diff — not by the prompt, and not by trust.

| | May do |
|---|---|
| **T1** copy | Modify files matching `text_paths`. No creates, no deletes. |
| **T2** content | T1 + create under `content.location`, wired into `content.registry`. |
| **T3** full | Anything not denied. |

**The deny floor applies at every tier, T3 included**, and is unioned in from the code so a client config cannot shrink it: `.github/**`, `docs/client-config.yml`, `package*.json`, `wrangler.toml`, `.env*`. The agent can never edit the gates that judge it, and can never raise its own tier.

Every repo bootstraps at `tier: 1`. T2 and T3 exist in the code but are **unreachable for a client until a human raises that tier in a human PR** — which is enforcement rather than a release schedule.

### 6. Remediate: Claude Code fixes one item at a time

```bash
wf-site-remediate --project ~/clients/roofing-site --max-items 5
```

Each work item is handed to Claude Code **in its own invocation**, inside the client checkout, with the remediation doctrine inlined into the prompt.

The obvious design hands the whole worklist over at once. Then the file→item mapping is something the model *asserts*, and `changelog.json` — the artifact the acceptance gate re-measures against — becomes a claim. One item per invocation makes the mapping a **measurement**: the files that changed between two `git status` snapshots are the files that item touched, whatever the model says it did.

- Every file the agent actually touched is judged by the **same function the PR gate runs**. An out-of-tier edit ends the run and is never recorded as fixed.
- `--max-items` / `--max-files` are hard caps that stop **cleanly**: what landed stays, what is left is named, and the remaining items keep their place for the next run. REGRESSION items are worked first, so a cap never cuts the lane that says a fix did not hold.
- It does not commit, push, or open a PR.

The container is where all four required tools are guaranteed to exist together:

```bash
docker run --rm -it -e ANTHROPIC_API_KEY \
  -v "$HOME/clients:/clients" -v "$HOME/.config/gh:/root/.config/gh:ro" \
  seo-agent wf-site-remediate --project /clients/roofing-site --max-items 1
```

### 7. Gates: 19 checks on the PR

The changes go onto a branch and a PR opens in the client's repo. `quality-gate.yml` there calls the reusable workflow here, which builds once and runs every gate in three waves:

- **PRE (the diff)** — `tier_check` refuses any path or operation the tier does not permit, judging a rename as a delete plus a create. `claim_provenance_check` refuses changed text carrying a rating, review count, licence number, year-count or superlative that traces to no config field, no work-item evidence, no citation, **and not to the previous version of the file**. That last source is what keeps the gate usable rather than flagging every reflowed paragraph.
- **PRE (the source)** — SSR-unsafe `window`/`document`, the forbidden-phrase ruleset's own self-test.
- **BUILT (the rendered output)** — orphan pages (the original Acme bug: every sitemap URL must have something linking to it), sitemap↔routes↔`llms.txt` parity, forbidden phrases, em dashes, heading casing, invisible tracking characters, content capsules, non-commodity checks, image budgets, LCP hygiene, robots access for citation crawlers, the 30-point per-page audit — and `acceptance_check`, which re-runs each *claimed* fix's criterion against the build output using the same code that produced the finding, and refuses when it still fires. **A claimed URL with no built page refuses too: silence is not proof.**

Every gate exits with its own numbered code, so a red run names the gate without anyone reading logs. Full table in [`gate-reference.md`](./gate-reference.md).

**The ratchet is what makes this usable on a site that already exists.** A client's inherited debt would fail these gates en masse — on the Acme pilot, 60 of 61 pages on capsule alone. So `wf-gate-baseline` records today's findings once, into the client's own repo, and each baselineable gate then reports a recorded finding as PRE-EXISTING and blocks only what is new. The recorded debt stays visible, countable, and can only shrink.

Eight gates accept a baseline. **Nine never can** — a legal exposure, a runtime crash, a broken invariant, a fabricated credential, an out-of-tier edit or a fix that never landed is a live liability, not aging debt, and baselining it would mean the pipeline formally signs off on shipping it.

> ⚠️ **A client with no recorded baseline runs the gates bare.** The workflow warns rather than failing, but every piece of their pre-existing debt then reads as blocking. Record one before the first PR.

### 8. A human merges — and that is the deploy

**This is the sacred gate.** Nothing reaches production except through a pull request a human merges. Not the automation, not a bot, not a force-push. The quality gate is set as a required status check, so a red run makes the Merge button un-clickable.

The same gate governs everything: content changes, gate-logic changes, dependency bumps, pipeline version bumps. They all arrive as a PR and they all wait for the same merge.

### 9. After the merge: the pipeline is done

**The pipeline is PR-terminal.** It measures, plans, writes, gates, and stops at a
pull request a human merges. It does not deploy. Deployment is the operator's job on
whatever platform the client is on, and nothing in this repo observes it.

That is a deliberate narrowing, made on 2026-08-10. The deploy rail exists and works,
but it hard-depends on `wrangler pages deploy` and three `CLOUDFLARE_*` secrets, so it
only ever fit clients on Cloudflare Pages. `deploy.reusable.yml` and
`preview.reusable.yml` are now marked **optional, Cloudflare Pages only**, and the
standard pair a client repo copies is `quality-gate.yml` + `seo-health.yml`.

**What still watches production.** `seo-health.yml` runs daily and on
`workflow_dispatch`, and it carries two things that used to fire inside the deploy job:

- **Live route verification** — the critical pages return 200 with a title, an h1, a
  canonical and JSON-LD, and the sitemap still carries the URLs it should.
- **The AI citation-crawler check** — the citation bots reach the live edge
  unchallenged. A Cloudflare "Block AI Crawlers" toggle, a Vercel bot rule or any WAF
  managed ruleset zeroes the entire AEO pillar while every build metric stays green,
  and it is invisible in build output. This has to run against the live host, forever.

The cost of the narrowing, stated plainly: detection moves from *within a minute of
deploying* to *the next scheduled run*. Press Run workflow right after you deploy and
that window closes by hand. And auto-rollback, the deploy proof record and IndexNow
submission only exist on the optional Cloudflare rail — a PR-terminal client does not
get them, and rollback becomes a thing the operator does on their own platform.

## The monthly loop

Steps 3 through 9 are the loop. Run it monthly per client and the artifacts accumulate in `docs/audit/<YYYY-MM>/`, which *is* the time series.

The metric is simple: **the finding list shrinks every month, and REGRESSION stays empty.** A regression means a fix did not hold, and it is worked before anything else. If the list is not shrinking, that is a process escalation, not a to-do item.

Because every artifact ships inside the PR and lives in the client's repo, a `git pull` there tells either operator exactly what has already been done this cycle: `findings.json` means measured, `worklist.json` means planned, `changelog.json` means an agent ran.

---

## Why it's built this way

**Every arrow is a JSON file with a schema.** No stage talks to the next through memory or a prompt. That is what makes each stage re-runnable, testable offline, and inspectable when something goes wrong.

**Everything is gated, nothing is trusted.** Every rule learned the hard way — the orphan-page bug, the em-dash rule, no dollar amounts on site, Title Case headings — became a piece of code that blocks a merge. A lesson that only lives in someone's head gets re-learned.

**The safety is in the gates, not the prompt.** The remediation prompt states the tier because that is efficient. What actually keeps agent authorship safe is `tier_check` on the diff, `claim_provenance_check` on the claims, `acceptance_check` on the result, and the human merge. Any of those failing stops the change; the prompt failing does not.

**A gate that cannot run must refuse, not pass.** The forbidden-phrase and non-commodity gates exit with a distinct "empty ruleset" code rather than reporting green on zero rules. The diff gates refuse when the checkout has no history to diff against. A silent green is worse than a red, because nobody investigates a green.

**Implemented is not wired.** `lib/baseline.py` was complete and fully tested for a release while the CI workflow called none of it, so the ratchet did nothing on any PR (B-007). A green unit test proves a function works, not that anything invokes it.

**One engine, many clients, zero copies.** Client repos hold thin workflow callers pinned to an exact version tag. Gate logic lives here once. Fixing a gate fixes it everywhere, and each client adopts the fix by merging a version-bump PR — through the same gate.

**Client config lives with the client.** Real config, credentials and knowledge stay in each client's own repo. This repo ships a sanitized starter template with placeholder values, and the container bakes in no credentials at all. No secrets, ever.
