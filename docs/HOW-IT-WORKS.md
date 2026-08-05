# How It Works

Plain-language walkthrough of the whole pipeline, start to finish. Read this first. The detail lives in [`gate-reference.md`](./gate-reference.md), [`consuming-the-pipeline.md`](./consuming-the-pipeline.md), and the module docs in [`modules/`](./modules/).

---

## The one-line version

The content team hands over one big Word document per client per cycle. The pipeline strips it down, turns it into clean typed data, edits the client's repo, audits every page at every stage, opens a pull request — **and then stops and waits for Alex.** the operator's merge is the deploy. After deploy it tells the search engines, checks the live site, and files the proof.

---

## The flow, step by step

### 1. Team DOCX lands in Drive

GrowMinion (the content team) drops the cycle's Word document into that client's Google Drive folder. The pipeline watches the folder, detects the upload, and nudges/confirms on Discord. Nobody has to remember to kick anything off.

*Module: [`03-intake-content.md`](./modules/03-intake-content.md).*

### 2. Client profile is resolved

Before touching anything, the pipeline reads that client's `docs/client-config.yml` — the single source of truth living in the client's own repo (**Model A**). That file describes the client's shape: topology, how many sites, which states, which framework, where the build output goes, the forbidden-phrase ledger, the proprietary-variable allow-list.

Everything downstream reads from this. No client fact is ever hardcoded in a script. If a required key is missing, the run stops and asks — it never guesses.

### 3. Generate: DOCX → clean typed data

The document is parsed, segmented, and classified page by page against the live site. Each section is distilled into a **core body** (the 800–1500-word substantive block, not the whole page), enriched, and passed through a judgment ledger that records a verdict per decision. The output is **typed data files** — entries in `src/data/*.ts` — not hand-written page components.

This is the load-bearing architectural rule: **pages are data + four templates.** A hand-rolled bespoke `page.tsx` per route is drift, and there is a gate that catches it.

Four commands do this, in order, and each is a registered `wf-*` entry point:

| Command | In | Out |
|---|---|---|
| `wf-distill` | the team DOCX | structured page drafts |
| `wf-classify` | drafts + the live repo | NEW / UPDATE / SKIP / INVALID per page |
| `wf-brief` | drafts | `docs/briefs/*.json` — the §19 content contract |
| `wf-emit-ts` | drafts + decisions | typed entries in `src/data/*.ts` |

**This runs in CI, not on a laptop.** `cycle-emit.yml` lives in the **client's own repo** (thin caller; the logic is `cycle-emit.reusable.yml` here) and is started by a human with `workflow_dispatch` — never a cron. It writes with that repo's built-in `GITHUB_TOKEN`, so no cross-repo write token exists anywhere in the fleet.

Three things about it are worth knowing before you run one:

- **`dry_run` defaults to true.** The whole chain runs and nothing is written or opened. Do that first for a client you have not run before.
- **It is a safe rerun.** It claims the `emit` step in the shared cycle log first; if the other operator already ran it this cycle, the run ends green having touched nothing.
- **A refusal is red and produces a fix list.** If the emitter refuses (a blocking finding) or the document cannot be segmented, **no PR is opened**, the run fails, and `docs/briefs/_curation.md` is uploaded as a run artifact naming the offending text and a proposed fix per page. Pages *held* for curation are surfaced in the PR body and do not ship.

*Modules: [`03-intake-content.md`](./modules/03-intake-content.md), [`05-core-body-distillation.md`](./modules/05-core-body-distillation.md), [`06-template-uiux.md`](./modules/06-template-uiux.md).*

### 4. Gates: three stages of auditing

The generated changes go onto a branch and a PR opens. Twenty-one gates run in three waves:

- **PRE-build** — against the source. Is anything SSR-unsafe? Are pages still data-driven? Do the content briefs carry their fan-out, capsule, semantic triples, and a proprietary variable?
- **BUILT** — against the actual rendered output. Are there orphan pages (the original Acme bug — every sitemap URL must have something linking to it)? Does the sitemap match the built routes match `llms.txt`? Any forbidden phrases, em dashes, non-Title-Case headings, invisible tracking characters? Does every page carry an answer-first content capsule and something proprietary to this client? Are images inside their byte budget? Is the schema right?
- **LIVE** — after deploy, against the real site. Do the pages actually load? And critically: **can the AI crawlers reach us?** A silent Cloudflare "Block AI Crawlers" toggle would zero the entire AEO pillar while every build metric stayed green — that check has to run at the edge, because it is invisible in the build output.

Every gate exits with its own numbered code, so a red run names the gate that failed without anyone reading logs. Full table in [`gate-reference.md`](./gate-reference.md).

The gates are real, not aspirational: 19 of 21 were verified against a live Acme build — each one proven to pass when clean *and* to go red on a deliberately seeded violation.

### 5. Alex merges — and that is the deploy

**This is the sacred gate.** Nothing reaches production except through a pull request that Alex merges. Not the automation, not a bot, not a force-push. `main` is protected by a ruleset that requires the quality gate to be green and blocks direct pushes.

The same gate governs everything: content changes, gate-logic changes, dependency bumps, pipeline version bumps. They all arrive as a PR and they all wait for the same merge.

If the gate is red, Alex sees why on the PR before deciding.

### 6. Deploy → IndexNow → live verify → proof

Merging `main` fires the deploy workflow: build, push to that client's Cloudflare Pages account, then:

- **IndexNow** — push the changed URLs straight to Bing and the Copilot AI surfaces for near-instant pickup. (Google doesn't support IndexNow; the sitemap with accurate `lastmod` is the Google path.)
- **Live verify** — hit the real domain, confirm key routes return 200 with the expected content.
- **AI-crawler check** — confirm the citation bots get through the Cloudflare edge unchallenged.
- **Proof** — write a deploy-proof record to a tracked path in the repo and commit it.

**"No proof, it didn't happen."** The proof file is a blocking meta-gate: if it is missing or empty, the run goes red. This exists because a repo that gitignored the proof directory would silently ship to prod with no record at all — which is what "we deployed and nothing was written down" looks like from the outside.

*Modules: [`02-deploy.md`](./modules/02-deploy.md), [`08-indexing-ops.md`](./modules/08-indexing-ops.md).*

---

## The monthly Sitebulb regression loop

The cycle above is the weekly forward motion. Once a month there is a second, slower loop whose only job is to make sure the site is getting *better*, not just newer.

1. **Crawl.** Alex runs Sitebulb (manual, about five clicks) and auto-exports to that client's synced folder.
2. **Ingest and diff.** The pipeline parses the export and diffs it against last month's, classifying every finding into one of four lanes:
   - **RESOLVED** — was there, is gone. Good.
   - **PERSISTING** — was there, still there. Aging; escalates.
   - **NEW** — appeared this month.
   - **REGRESSION** — we already fixed this and it came back. The one that matters most.
3. **Route.** A config map (not code) sends each issue type to its owner: **CODE** → Robin, **CONTENT** → GrowMinion, **NOISE** → an explicit ignore-ledger. Nothing is silently dropped, and no issue type is allowed to be unmapped.
4. **Fix with proof.** Every fix is verified — grep, curl, or build output. Sitebulb findings are leads, not gospel; verify before fixing.
5. **Confirm.** A re-crawl closes the loop.
6. **Escalate to the gate.** This is the part that compounds: a **REGRESSION** on something that was previously gated gets fed back as a **blocking required check on the next PR.** Once something has been fixed, the pipeline refuses to let it come back.

**The metric is simple: the issue list shrinks every month.** If it doesn't, that is a process escalation, not a to-do item.

*Module: [`04-monthly-qa.md`](./modules/04-monthly-qa.md). Visual regression: [`07-visual-qa-autoshot.md`](./modules/07-visual-qa-autoshot.md).*

---

## Why it's built this way

**Everything is gated, nothing is trusted.** Every rule the team learned the hard way — the orphan-page bug, the em-dash rule, no dollar amounts on site, Title Case headings, no bespoke per-route pages, conversion tracking via a real `/thank-you/` page instead of a modal — became a piece of code that blocks a merge. A lesson that only lives in someone's head gets re-learned. Provenance for each one is in [`DOCTRINE-GATE-MATRIX.md`](./DOCTRINE-GATE-MATRIX.md).

**One engine, five clients, zero copies.** Client repos hold three small workflow files pointing at this repo, pinned to an exact version tag. Gate logic lives here once. Fixing a gate fixes it everywhere, and each client adopts the fix by merging a version-bump PR — through the same gate.

**A gate that can't run must refuse, not pass.** The forbidden-phrase gate and the non-commodity gate both exit with a distinct "empty ruleset" code rather than reporting green on zero rules. A silent green is worse than a red, because nobody investigates a green.

**Client config lives with the client.** Real config, credentials, and knowledge stay in each client's own repo. This shared repo ships only a sanitized starter template with placeholder values. No secrets, ever.
