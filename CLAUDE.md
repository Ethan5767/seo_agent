# CLAUDE.md — seo-content-pipeline V2

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

**A commit that changes behavior with no CHANGELOG entry is incomplete work.** The other side pulls and has no idea what moved.

### 3. Verify against CODE, never against docs.

Docs go stale silently. Code does not. Before you state that something is broken, missing, or blocked, **run the command and paste the output.**

This is not a style preference. On 2026-07-28 a state-audit doc listed six blocking defects; all six had already been fixed days earlier. Anyone who trusted that doc would have "fixed" working code.

```bash
# Good: a claim with evidence
$ gh api repos/your-org/acme-roofing-site/branches/main/protection
403 "Upgrade to GitHub Pro or make this repository public"

# Bad: "I think branch protection isn't set up yet"
```

**When a doc and the code disagree, the code wins — and fixing the doc is part of the job.**

### 4. Proof or it did not happen.

The gate suite is built on this principle; hold the code to it too. A fix is not done because it looks right. It is done when you have run it and can show the output. Paste real terminal output into the CHANGELOG or ledger entry. Never paraphrase a result you did not see.

**Never claim tests pass without showing the run.** If you could not verify something, say exactly that and say why.

⚠️ **Do not pipe a verification command into `tail`, `head`, or `grep` inside an `&&` chain.** The pipeline's exit status is the *last* command's, so a failing `pytest` piped to `tail` reports success and the chain continues to `git push`. This happened on 2026-07-28. Run the check on its own line, read the result, then push.

```bash
pytest -q                 # look at it
git push origin main      # separate step
```

### 5. Never break `main`.

`main` must always be pullable and runnable. Branch for anything experimental. Docs-only changes may go direct to `main`.

### 6. No secrets. No client PII. Ever.

No API keys, tokens, `.env` files, Cloudflare or Google credentials, or client data in this repo. Client config lives in the client's own repo (**Model A**). Real rosters go under `**/secrets/**`, which is gitignored. When you must reference a credential, reference it **by name only**.

---

## What This Repo Is

The **engine**. It takes the SEO content team's messy handoff, reformats it into clean pipeline-ready data, classifies each page against the live site, edits typed data files in the client's own repo, gates every step, opens a PR, waits for the operator's merge, deploys, and verifies live.

**Model A:** this repo holds engine code only. Every client repo is that client's single source of truth — its own `docs/client-config.yml`, its own `docs/banned-phrases.txt`, its own Cloudflare secrets, in the client's own Cloudflare account.

**The contract:** messy team handoff in → clean, standardized, pipeline-ready data out, rendered into the client's template architecture and gated at every step.

---

## Writing Standards (these ship to paying clients)

The gates enforce these on client sites. Match them in anything that renders publicly.

- **Title Case on every heading.** "Florida's Only Active Stone Quarry", never "Florida's only active stone quarry". Enforced by `check_headings`.
- **No em dashes in public-facing copy.** Enforced by `em_dash_check`. **This does NOT apply to internal markdown, code comments, or commit messages** — write those however reads best.
- **No possessive contractions in headings.** "Summer Is Around the Corner", not "Summer's Around the Corner".
- Proper grammar and spelling everywhere. Proofread before pushing.

---

## Before You Push — The Checklist

```bash
git pull --ff-only                 # 1. not stale
pytest -q                          # 2. tests pass (paste the output)
git diff --stat                    # 3. scope is what you think it is
#    4. CHANGELOG.md updated under [Unreleased]?
#    5. New bug found → docs/BUG-LEDGER.md?
#    6. No secrets in the diff?
git push origin main
```

Then **tell the other side what changed** — do not assume they will read the log.

---

## Where Things Live

| Path | What |
|---|---|
| `CHANGELOG.md` | **Every change, newest first.** Read this first after a pull. |
| `docs/BUG-LEDGER.md` | Open and fixed bugs, each with reproduction and evidence |
| `docs/ADMIN-CHECKLIST.md` | Human-only setup + live status table (GitHub, Cloudflare, Discord, Drive) |
| `docs/MODULES.md` | **The complete module map** — every package/gate/workflow, one line each |
| `docs/HOW-IT-WORKS.md` | Plain-language walkthrough |
| `docs/gate-reference.md` | What each gate checks |
| `pipeline/gates/` | The gate suite |
| `pipeline/intake/` | Discord + Google Drive intake |
| `.github/workflows/*.reusable.yml` | Workflows client repos call by tag |
| `.github/examples/` | Thin callers to copy into a client repo |

---

## Known Sharp Edges

Read `docs/BUG-LEDGER.md` for the live list. The ones that bite hardest:

1. **Drive intake selects by time window, not by month.** `--since-hours` is the only filter. **Moving or reorganizing files in Drive updates their `modifiedTime`**, so a bulk reorg can make six months of old content look brand new to the next run.
2. **Client callers must pin an exact tag** (`@vX.Y.Z`, latest: `v2.1.0` — verify with `git tag -l`). The old note "no tag has been cut" is obsolete; tags exist and the shared `uses:` path is live. Vendored `.pipeline/` copies in client repos are the legacy interim and drift unless re-synced.
3. **Branch protection cannot be enabled.** GitHub Free does not support it on private repos. The gate reports but cannot block. See `ADMIN-CHECKLIST.md` §2.
4. **A human collaborator grant is not Actions access.** Being a collaborator on this private repo does not let another repo's workflow check it out. That needs a `PIPELINE_REPO_TOKEN` secret.

---

## Two Operators, One Pipeline

Alex and Robin both run this and never see each other's screens. **Before you run any cycle step, ask what is already done:**

```bash
git -C <client-repo> pull --ff-only
wf-cycle-status <client-repo> --client <slug>
```

That reads `docs/cycle-logs/<YYYY-MM>/cycle-state.json` in the **client** repo — shared through git, no server involved — and reports every step, who ran it, and when.

**Wrap steps so a rerun is a safe no-op:**

```bash
wf-cycle-status "$REPO" --client "$SLUG" --claim distill || exit 0   # exit 3 = already done
run-the-step
wf-cycle-status "$REPO" --client "$SLUG" --mark distill --status done --detail "12 pages"
git -C "$REPO" add docs/cycle-logs && git -C "$REPO" commit -m "cycle: distill done" && git -C "$REPO" push
```

**The state is only as good as the push.** Marking a step and not pushing is worse than not marking it — the other side confidently redoes finished work. `wf-cycle-status` warns when your checkout is behind origin, but it cannot push for you.

---

## Where Workflows Live — Fleet-Wide vs Per-Client

There are two kinds and they live in different repos. Putting one in the wrong place is the easiest structural mistake to make here, so check this before adding any workflow.

### Fleet-wide — ONE copy, in THIS repo

```
seo-content-pipeline/.github/workflows/
  drive-poll.yml     polls Google Drive for EVERY client
  intake-poll.yml    polls Discord for every mapped channel
  ci.yml             this repo's own test suite
```

`drive-poll.yml` reads `config/drive-intake.yml`, loops over every client, and checks each one's Drive folder in a single run. **Adding a sixth client is one config entry — no new workflow anywhere.**

🔴 **Never copy `drive-poll.yml` or `intake-poll.yml` into a client repo.** Five copies would mean five jobs hammering the same Drive, five times the Actions minutes, five files drifting out of sync, and five separate ingest ledgers that each think they are the only one.

### Per-client — ONE copy in EACH client repo

```
acme-roofing-site/.github/workflows/
  quality-gate.yml   gates THIS repo's pull requests
  preview.yml        previews THIS repo's site
  cycle-emit.yml     runs a content cycle and opens a PR in THIS repo
  deploy-prod.yml    deploys THIS repo (not installed yet)
```

These **must** be per-repo: GitHub only runs a workflow on the repo that contains it. A PR against Acme can only be gated by a workflow inside Acme — and a workflow can only **write** to Acme from inside Acme without a cross-repo PAT, which is why `cycle-emit` is on this list and not the fleet-wide one.

They are ~30-line **thin callers**. All real logic lives in the `*.reusable.yml` files here, pulled in by tag:

```yaml
uses: richardnhek/seo-content-pipeline/.github/workflows/quality-gate.reusable.yml@v2.0.1
secrets: inherit
```

That is why bumping one tag upgrades every client at once, and why the callers stay tiny. Copy them from `.github/examples/` and edit **only** the `with:` values.

**Pin an exact tag. Never `@main`, never a moving `@v2`.** These workflows gate production; a mutable ref means the thing guarding a client's live site can change without a PR.

### The whole flow

```
drive-poll.yml            (HERE, every 3h)  → finds team content, routes it per client
        ↓
HANDOFF stage (same run, only when CLIENT_REPOS_TOKEN exists)
  └→ wf-client-handoff → cycle/<slug>-<YYYY-MM> branch in the CLIENT repo,
     DOCX committed to docs/intake/<YYYY-MM>/, ONE intake PR per client per
     month (body = the pre-flight fix list), then dispatches ↓ on that branch
        ↓
cycle-emit.yml            (CLIENT repo, workflow_dispatch — by a human OR by the handoff stage)
  └→ cycle-emit.reusable.yml (HERE)          → wf-distill → wf-classify → wf-brief → wf-emit-ts
        ↓
emit commits land on the SAME cycle/ branch — the intake PR ripens into the content PR
        ↓
quality-gate.yml + preview.yml  (CLIENT repo) → 18 gates + a preview URL
        ↓
Alex merges → deploy
```

**Intake is central. Gates, emit and deploy are local.** `cycle-emit` is per-client for the same reason the gates are: it **writes** into a client repo, so it runs inside that repo on that repo's own `GITHUB_TOKEN`.

**Cross-repo writes are PR-ONLY (the operator's override, 2026-08).** The original design refused any cross-repo write PAT; that left the last hop unowned and a month's delivered pages stopped at an expiring artifact. Alex explicitly overrode it for PR-mediated writes: the handoff stage in `drive-poll.yml` holds `CLIENT_REPOS_TOKEN` (fine-grained PAT, the five client repos only — mint spec in `docs/ADMIN-CHECKLIST.md` §9) and may create `cycle/` branches, commit intake DOCX, open/update PRs and dispatch `cycle-emit`. It must **never** push a client's default branch and **never** merge — the operator's merge stays the only path to production, and without the secret the stage skips green and the old artifact-only behavior stands.

`dry_run` defaults to **true**: the first run against any client runs the whole chain and writes nothing.

The emitter's exit code decides whether a PR happens, and the workflow honours it literally:

| exit | meaning | action |
|---|---|---|
| 0 | every draft emitted clean | commit + PR |
| 1 | emitted, warn flags in the ledger | commit + PR |
| 15 | some pages HELD for curation | commit + PR for what emitted; held pages are **never** green |
| 9 | REFUSED — a BLOCK finding | **no PR**, run fails, `docs/briefs/_curation.md` uploaded as the fix list |
| 16 | unsegmentable DOCX / 0 pages | **no PR**, run fails |

Step one is `wf-cycle-status --claim emit`; exit 3 (the other operator already ran it) ends the run clean having touched nothing.
