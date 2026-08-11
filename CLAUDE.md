# CLAUDE.md — seo_agent (v3)

**Read this before you touch anything. It is auto-loaded by Claude Code for every session in this repo.**

This repo is the **shared sync point between two developers who never see each other's screens**: Alex (Meridian) and Robin (the partner studio). Each of us works with Claude. Neither Claude can see what the other one did. **The only thing keeping us in sync is what gets written down here before a push.**

That is the whole reason these rules exist. Follow them even when the change feels too small to document. Especially then.

---

## The Sync Contract (non-negotiable)

### 1. Pull before you start. Always.

```bash
git pull --ff-only
```

If that fails, stop and reconcile before writing a single line. Do not start work on a stale tree. On 2026-07-28 the local clone was **five commits behind** and three status docs described problems that had already been fixed — a full session was nearly spent re-solving solved work.

### 2. Document BEFORE you push, in the SAME commit.

Every push must carry its own paper trail. Never "I will write it up after."

| You did this | You must also update |
|---|---|
| Any behavior change, fix, or new feature | `CHANGELOG.md` under `[Unreleased]` |
| Found a bug (even one you did not fix) | `docs/BUG-LEDGER.md` |
| Fixed a bug from the ledger | Move it to Fixed, add the proof |
| Changed what a human must do by hand | `docs/ADMIN-CHECKLIST.md` |
| Changed the gate suite | `docs/gate-reference.md` |
| Added/removed a module or command | `docs/MODULES.md` (including the header counts) |

**A commit that changes behavior with no CHANGELOG entry is incomplete work.** The other side pulls and has no idea what moved.

### 3. Verify against CODE, never against docs.

Docs go stale silently. Code does not. Before you state that something is broken, missing, or blocked, **run the command and paste the output.**

This is not a style preference. On 2026-07-28 a state-audit doc listed six blocking defects; all six had already been fixed days earlier. On 2026-08-06 `docs/MODULES.md` still documented 20 modules that had been deleted a release earlier, and `README.md` still drew the DOCX flow. Anyone trusting either would have "fixed" working code or looked for a package that no longer exists.

```bash
# Good: a claim with evidence
$ gh api repos/your-org/acme-roofing-site/branches/main/protection
403 "Upgrade to GitHub Pro or make this repository public"

# Bad: "I think branch protection isn't set up yet"
```

**When a doc and the code disagree, the code wins — and fixing the doc is part of the job.**

### 4. Proof or it did not happen.

The gate suite is built on this principle; hold the code to it too. A fix is not done because it looks right. It is done when you have run it and can show the output. Paste real terminal output into the CHANGELOG or ledger entry. Never paraphrase a result you did not see.

**Never claim tests pass without showing the run.** If you could not verify something, say exactly that and say why — the phase 6 provider network paths are in the CHANGELOG as unverified for exactly this reason.

**Implemented is not wired.** B-007: `lib/baseline.py` was complete, tested and called by nothing on a PR for a whole release. A green unit test proves the function works, not that anything invokes it. When you add something the CI has to call, assert the call site too.

⚠️ **Do not pipe a verification command into `tail`, `head`, or `grep` inside an `&&` chain.** The pipeline's exit status is the *last* command's, so a failing `pytest` piped to `tail` reports success and the chain continues to `git push`. This happened on 2026-07-28. Run the check on its own line, read the result, then push.

```bash
pytest -q                 # look at it
git push origin main      # separate step
```

### 5. Never break `main`.

`main` must always be pullable and runnable. Branch for anything experimental. Docs-only changes may go direct to `main`.

### 6. No secrets. No client PII. Ever.

No API keys, tokens, `.env` files, Cloudflare or Google credentials, or client data in this repo. Client config lives in the client's own repo (**Model A**). Real rosters go under `**/secrets/**`, which is gitignored. When you must reference a credential, reference it **by name only**. The container bakes in nothing: `git`/`gh` use the operator's mounted config, the model uses `ANTHROPIC_API_KEY` from the environment.

---

## What This Repo Is

The **engine**. Point it at a client's GitHub repo and their domain, and it measures the live site, ratchets this month's findings against previous months, plans the work, hands each item to Claude Code inside the client's checkout, and gates everything the agent wrote before a human merges it.

```
repo + domain
   ↓  ONBOARD    wf-onboard          clone, config, preflight, docs, first measurement
   ↓  MEASURE    wf-site-health      live site → docs/audit/<YYYY-MM>/findings.json
   ↓  PLAN       wf-site-plan        RESOLVED / PERSISTING / NEW / REGRESSION → worklist.json + report.md
   ↓  REMEDIATE  wf-site-remediate   Claude Code edits, inside the tier → changelog.json
   ───────────── everything above runs locally, or in the container ─────────────
   ↓  GATES      19 gates on the client's PR, in Actions on the client repo
   ↓  HUMAN MERGE  always. the only path to production.
   ───────────── THE PIPELINE ENDS HERE. deployment is the operator's, on the
                 client's own platform. `deploy.reusable.yml` still exists and is
                 CLOUDFLARE PAGES ONLY — opt in per client, never assumed.
   ↓  MONITOR    seo-health, daily + on demand: live routes, sitemap, AI citation
                 crawlers at the edge. never blocks. the only thing watching prod.
```

**Every arrow is a JSON file with a schema.** No stage talks to the next through memory or a prompt. That is what makes each stage re-runnable and testable offline.

**Model A:** this repo holds engine code only. Every client repo is that client's single source of truth — its own `docs/client-config.yml` (including its tier), its own `docs/gate-baseline.json`, its own `docs/audit/<YYYY-MM>/` artifacts, its own Cloudflare secrets in the client's own Cloudflare account. The audit artifacts ship **inside the PR**, so the worker holds no state and the host is swappable.

**v3 deleted the DOCX rail.** `pipeline/intake` (Discord, Drive, DOCX pre-flight), `pipeline/generate` (distill → classify → brief → emit_ts), both fleet-wide cron pollers, `cycle-emit`, and `wf-cycle-status` are all gone — see `SITE-AUDIT-PIPELINE.md` §3. **Claude Code is the only writer now.** If you find a doc describing that rail, it is stale; fix it.

---

## Tiering — the thing to understand before you touch the agent

A tier is a **path + operation allow-list**, declared per client in their own `docs/client-config.yml`, and enforced by a gate on the PR diff. It answers "what may the agent touch", never "who approves".

| | May do |
|---|---|
| **T1** copy | Modify files matching `text_paths`. No creates, no deletes. |
| **T2** content | T1 + create under `content.location`, wired into `content.registry`. Unavailable without a declared location. |
| **T3** full | Anything not denied. |

**The deny floor applies at every tier, T3 included**, and is unioned in from `lib/common.DEFAULT_DENY` so a client config can never shrink it: `.github/**` (the agent must never edit the gates that judge it), `docs/client-config.yml` (it must never raise its own tier), `package*.json`, `wrangler.toml`, `.env*`.

**The operator declares the tier at onboarding**, in the ADD CLIENT panel or via `wf-onboard --tier`. It defaults to **T1**, and **T2 is refused without `content.location` and `content.registry`** — T2 means "may create pages there and wire them in", so without both it grants authority over nowhere while claiming more.

**The agent can never raise its own tier**, and that is what the model rests on: `docs/client-config.yml` is on the deny floor at every tier including T3, and `wf-onboard` writes the tier into a commit on the **default branch** — a human commit, which is what the model always required. What a human chooses is *when* to declare it, never whether they must.

What keeps agent authorship safe is not the prompt. It is `tier_check` on the diff, `claim_provenance_check` on the claims, `acceptance_check` on the result, and the operator's merge.

---

## Writing Standards (these ship to paying clients)

The gates enforce these on client sites. Match them in anything that renders publicly.

- **Title Case on every heading.** "Florida's Only Active Stone Quarry", never "Florida's only active stone quarry". Enforced by `check_headings`.
- **No em dashes in public-facing copy.** Enforced by `em_dash_check`. **This does NOT apply to internal markdown, code comments, or commit messages** — write those however reads best.
- **No possessive contractions in headings.** "Summer Is Around the Corner", not "Summer's Around the Corner".
- **Derivation only, never invention.** A rating, review count, licence number, year-count or warranty term must trace to the client's config, a work item's evidence, a citation, or the previous version of the file. `claim_provenance_check` refuses the rest. This applies to you as much as to the agent.
- Proper grammar and spelling everywhere. Proofread before pushing.

---

## Before You Push — The Checklist

```bash
git pull --ff-only                 # 1. not stale
pytest -q                          # 2. tests pass (paste the output)
git diff --stat                    # 3. scope is what you think it is
#    4. CHANGELOG.md updated under [Unreleased]?
#    5. New bug found → docs/BUG-LEDGER.md?
#    6. Module/command added or removed → docs/MODULES.md counts?
#    7. No secrets in the diff?
git push origin main
```

Then **tell the other side what changed** — do not assume they will read the log.

---

## Where Things Live

| Path | What |
|---|---|
| `CHANGELOG.md` | **Every change, newest first.** Read this first after a pull. |
| `SITE-AUDIT-PIPELINE.md` | The v3 design doc — what was removed, the tier model, the build sequence, the open decisions |
| `docs/BUG-LEDGER.md` | Open and fixed bugs, each with reproduction and evidence |
| `docs/MODULES.md` | **The complete module map** — every package/gate/workflow, one line each |
| `docs/gate-reference.md` | What each gate checks, its exit code, and whether it is baselineable |
| `docs/ADMIN-CHECKLIST.md` | Human-only setup + live status table |
| `docs/HOW-IT-WORKS.md` | Plain-language walkthrough of the whole v3 flow, onboarding to proof |
| `pipeline/audit/` | The rail: `onboard` · `measure` · `plan` · `remediate` · `providers`, plus client bootstrap/preflight |
| `pipeline/gates/` | The 19 gates |
| `pipeline/lib/` | `common.py` (config + tiering), `baseline.py` (the ratchet), `client_docs.py` |
| `pipeline/dashboard/` | `wf-dashboard` — a 127.0.0.1 console over the client-repo artifacts. No database, no accounts, no merge action. |
| `skills/site-remediation/` | The doctrine inlined into every remediation prompt |
| `.github/workflows/*.reusable.yml` | Workflows client repos call by tag |
| `.github/examples/` | Thin callers to copy into a client repo |
| `Dockerfile` | Python + git + gh + Claude Code. The only place all four are guaranteed together. |

---

## Where Workflows Live

**There are no cron workflows.** Both fleet-wide pollers went with the intake rail, taking ~2,180 Actions minutes/month with them — which was the entire argument for making this repo public. `seo_agent` can stay private.

`ci.yml` runs here. Everything else runs **in the client repo**, because GitHub only runs a workflow on the repo that contains it: a PR against Acme can only be gated by a workflow inside Acme.

A client repo holds ~30-line **thin callers** copied from `.github/examples/`. All real logic lives in the `*.reusable.yml` files here, pulled in by tag:

```yaml
uses: Ethan5767/seo_agent/.github/workflows/quality-gate.reusable.yml@v3.1.3
secrets: inherit
```

That is why bumping one tag upgrades every client at once. Edit **only** the `with:` values.

**Pin an exact tag. Never `@main`, never a moving `@v3`.** These workflows gate production; a mutable ref means the thing guarding a client's live site can change without a PR. `tests/test_pipeline_pin.py` enforces this, plus the agreement between the stamped `PIPELINE_REF`/`PIPELINE_REPO`, the examples, and the tag. **The stamp is self-referential** — v3.0.0's copy of a file stamps v3.0.0 — so advance it *in the tagged commit*, never after.

**The standard pair is `quality-gate.yml` + `seo-health.yml`. Copy those two and stop.** The other two are Cloudflare Pages only and are opt-in per client, not part of the default rail — the pipeline is PR-terminal and the operator deploys.

| Client workflow | Standard? | Trigger | Does |
|---|---|---|---|
| `quality-gate.yml` | **yes** | every PR | build once, run 19 gates, sticky comment. Set it as a **required status check** — red gate = un-clickable Merge = prod blocked by construction. |
| `seo-health.yml` | **yes** | daily + `workflow_dispatch` | live routes, sitemap count, and AI citation-crawler access at the edge. Never blocks. **The only thing watching production**, so a client without it is gated but unwatched. Press Run workflow right after deploying. |
| `preview.yml` | opt-in, **CF only** | every PR | Cloudflare preview URL + Lighthouse. Monitoring only. Its real job was feeding `render_url` to the quality gate for a repo with no static export — that input is host-agnostic, so on another platform feed it that platform's PR preview URL instead. |
| `deploy-prod.yml` | opt-in, **CF only** | push to main (= the merge) | build, capture, `wrangler pages deploy`, verify live, auto-rollback, proof, IndexNow. Hard-depends on three `CLOUDFLARE_*` secrets; there is no Vercel or Netlify path here. |

---

## Known Sharp Edges

Read `docs/BUG-LEDGER.md` for the live list. The ones that bite hardest:

1. **A client with no `docs/gate-baseline.json` runs the gates BARE.** Record one before their first PR (`wf-gate-baseline --project <repo> --out docs/gate-baseline.json`, committed to *their* repo) or every piece of inherited debt reads as blocking. The workflow warns loudly rather than failing, which is deliberate — but "warns" is not "handled" (B-007).
2. **`em_dash_check` accepts no baseline at all.** One em dash in a client's legacy copy blocks every PR forever, with no recording that can accept it. Open as **B-008**; needs a human decision, not a workaround.
3. **A human collaborator grant is not Actions access.** Being a collaborator on this private repo does not let a client repo's workflow check it out. That needs a `SEO_AGENT` secret in the client repo.
4. **Static export is an onboarding precondition, not a footnote.** **Nine** gates derive what they judge from the built HTML tree — including `forbidden_sweep`, which is never-baselineable for legal exposure. Two failure modes, and they are not the same (B-018):
   - **No tree at all** → `build-site` exits 1 and every build-tree step is **SKIPPED**, not green. Loud, and recoverable.
   - **A tree that exists and holds no HTML** → every gate globs zero files and reports **green over nothing**. This is the dangerous one, and pointing `build_output_dir` at `.next` produces exactly it.

   The supported answer is `wf-render-snapshot`, which crawls a rendered deployment into the tree the gates already glob, and refuses at exit 19 rather than writing an empty directory. Verified on lee (no static export, SSR on Vercel): 26 routes captured plus sitemap/robots/llms.txt, after which all nine gates gave real verdicts. `wf-onboard` reports the static-export verdict; `None` means "cannot tell", not "fine".

   **The general rule this is one instance of: a gate that scanned nothing must never report a pass.** `audit_ssr` broke it until 2026-08-10 by looking only in `src/` — `create-next-app`'s default is no `src/`, so the common Next layout got a silent green from a never-baselineable gate (B-027). Both `forbidden_sweep` and `audit_ssr` now exit **4** for "cannot judge". When you add a gate, decide what its empty input means *before* you ship it, and prefer a denylist over an allowlist keyed on framework — `framework_family()` returns `None` for anything it has not met, so an allowlist silently covers nothing on the next unfamiliar client.
5. **Branch protection cannot be enabled.** GitHub Free does not support it on private repos. The gate reports but cannot block. See `ADMIN-CHECKLIST.md` §2.
6. **The DataForSEO / GSC / CrUX network paths have never run live.** Only the parsers are tested. Read the status string on the first real run, not the finding count — a provider with no credentials returns a *named skip* precisely so a silent zero can never look like a clean site.

---

## Two Operators, One Pipeline

Alex and Robin both run this and never see each other's screens. The `wf-cycle-status` ledger went with the DOCX rail, so **there is no automated claim/mark step any more.** Coordination is the sync contract above plus one habit:

```bash
git -C <client-repo> pull --ff-only     # the client repo carries the artifacts
ls <client-repo>/docs/audit/            # which cycles have been measured
```

`docs/audit/<YYYY-MM>/` in the **client** repo is the shared state: `findings.json` means it was measured, `worklist.json` means it was planned, `changelog.json` means an agent ran. All three ship inside the PR, so a `git pull` in the client repo tells you what the other side already did. Nothing is coordinated through this repo, and nothing needs a server.

**Re-running is safe by design** — `wf-onboard` resumes, `wf-site-plan` is byte-identical over an unchanged cycle, and `wf-site-remediate` **resumes**: it skips what the cycle's `changelog.json` records as `fixed` and merges into that changelog rather than overwriting it. Prefer a re-run to a guess.
