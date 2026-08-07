# Plan — one automated cycle, three human gates, and a score

**Date:** 2026-08-07
**Reads with:** `docs/HANDOFF-2026-08-07.md`, `docs/BUG-LEDGER.md` B-010 / B-013 / B-014 / B-015 / B-016

---

## The flow, stated once

Everything below serves this one sequence. If a change does not move a client
along it, it is not in this plan.

```
ADD CLIENT                        repo · domain · TIER (T1 default)
  │  clone · bootstrap config · preflight · client-profile · scaffold
  │  commit the scaffold to main            ← B-014
  ▼
GATE 1 — THE INTERVIEW          human. unavoidable.
  │  nobody can invent a licence number, hours, or a review count.
  │  preflight exits 12, the console names the file, the same button resumes.
  ▼
  │  measure → plan          automatic, chained
  ▼
ONE CLICK — REMEDIATE           shows N items and the projected spend first
  │  Claude Code edits inside the tier, one item per invocation
  ▼
GATE 2 — THE DIFF               human. per item, or approve all.
  │  approving is `git add`. the index IS the approval record.
  ▼
  │  commit → gates → push      automatic, in that order    ← B-015
  ▼
  "Open a PR?"                   asked, not assumed
  ▼
GATE 3 — THE MERGE              human, on GitHub. the only path to production.
```

Three gates. Everything between them is one button that the dashboard picks
for you.

**What the operator gets that they do not have today:** a client screen that
says which of the seven stages this client is on, what the one next action is,
how many findings are left, an SEO and an AEO score, and a graph of that score
per cycle with the projected effect of the pending PR on it.

---

## Phase 0 — onboarding: five bugs and the tier

Each bug is a hard stop on the sequence above. Fixing them is not a detour; it is
the first half of the work. Ordered by what unblocks the most.

The tier picker is grouped here rather than given its own phase because it writes
`docs/client-config.yml` — the same file B-014's scaffold commit commits. Landing
them apart means committing `tier: 1` and then amending it.

### B-010 — every new client stops before the interview

`preflight.py:24` requires a top-level `industry`. Nothing in `pipeline/` writes
it. `bootstrap_config.py:229` writes `business.trade: "TODO"` — the same fact,
in the place the interview already covers.

**The call: drop `industry` from `preflight.required` and read
`business.trade`.** One fact, one place. Verified concrete: `trade` is already
`"TODO"` on a fresh bootstrap, so preflight's existing TODO scan catches it and
exits **12** — the documented interview stop — instead of exit 11 on a field
nobody was ever asked for.

- `pipeline/audit/preflight.py:24` — drop `"industry"` from `required`
- `pipeline/audit/preflight.py:54` — print `cfg["business"]["trade"]`
- The rejected alternative: emit `industry: TODO` from bootstrap. Same exit
  code, but keeps two names for one fact, and the next person has to work out
  which is authoritative.

### B-014 — the onboarding scaffold cannot be committed

Six paths (`docs/client-config.yml` + five scaffolded docs) are creates that
`tier_check` refuses at every tier, `client-config.yml` deliberately so. Nothing
in the pipeline ever commits them, so the operator meets the deny floor as
exit 17 on their first PR instead of as an instruction.

**The call: `wf-onboard` commits them itself, on the default branch, by
explicit pathspec, and never pushes.** The ledger called this "a new class of
surprise" — correct for a general-purpose tool, wrong for the one command whose
entire job is to leave a repo in a runnable state. The constraints are what make
it safe:

- Named pathspec only — the six paths it wrote, never `git add -A`
- Refuses unless `HEAD` is the default branch, so it can never land on a cycle
  branch
- Refuses if any of the six is already tracked and modified (that is a human's
  edit, not a scaffold)
- Local commit only. Push stays a human action.

New step in `pipeline/audit/onboard.py`, after `wf-scaffold-client-docs`,
before `wf-site-health`. The exact `git add` line the handoff documents becomes
the code that runs it.

### B-013 — a capped run redoes work and destroys the first run's record

`selectable()` never reads `changelog.json`, and `main` writes it wholesale.

**The call: resume.** Both halves, because either alone is half a fix.

- `main` **merges** into an existing changelog for the cycle rather than
  overwriting: items keyed by `id`, a later attempt replaces its own earlier
  entry, everything else survives. Counters (`attempted`, `cost_usd`) accumulate.
- `selectable()` skips items already `status: "fixed"` in that changelog.

**On the authority objection**, which is the real reason this sat open: the
changelog now decides what gets *attempted*. It still decides nothing about what
is *verified*. `acceptance_check` re-measures every claimed fix against the build
output and refuses if the finding is still there, and that is unchanged. A
changelog that lies about a fix wastes one item's budget and is then caught by
the gate — it does not reach production.

Also, one word, and it unblocks the projected score in Phase 3:

- `remediate.py::_base` — add `"finding_fp"` to the carried keys. Worklist items
  already have it. Without it, mapping a fixed item back to its finding means
  matching on `(url, code)`, which is ambiguous the moment a page has two
  findings of the same code.

### B-016 — provenance refuses every client's first PR

`.md` is in `TEXT_SUFFIXES`, so `prose_from` scans `docs/audit/<cycle>/report.md`
— which `wf-site-plan` generated — as client copy, and `SUPERLATIVE_RE` catches
its own phrase "this is the first cycle".

**The call: `prose_from` skips the cycle artifacts, reusing the definition
`tier_check` already uses.** `pipeline/lib/common.py` exports `ARTIFACT_PATHS`
and `path_matches`, and `tier_verdict` already classifies these exact paths as
`cycle artifact` (`common.py:303-306`). Importing that instead of writing a
second glob list means the two gates agree by construction rather than by
coincidence — which was the actual defect, not the word "first".

- `pipeline/gates/claim_provenance_check.py::prose_from` — return `[]` for a
  path matching `ARTIFACT_PATHS`
- Not reworded in `plan.py`. Rewording fixes one sentence and leaves the class of
  bug — a gate scanning generated artifacts — waiting for the next phrase.

### B-015 — local gates report green over an uncommitted tree

`tier-check` and `claim-provenance` diff `origin/main...HEAD`. On a dirty tree
with no cycle commit the diff is empty, both exit 0, and the console prints
`Clean — every check passed` over work it never looked at.

**The call: the console refuses to launch them when there is nothing committed
to judge.** Before launching either, check `git rev-list --count
origin/<default>..HEAD`; if it is 0, refuse with *"nothing committed for these
gates to judge — commit first, then check"*. A refusal, never a vacuous pass.

The gates are not touched. `--base HEAD` would make them judge the working tree
and diverge from what CI runs, and a gate that means something different locally
is worse than one that occasionally refuses.

This is also enforced by shape in Phase 4: the review screen only offers the
gates *after* COMMIT, so the correct order is the only order the UI presents.

### The tier is declared at onboarding

Today `bootstrap_config.tier_block()` hardcodes `tier: 1` and the `content:` block
ships commented out. Raising a tier means a second manual act against the client
repo.

**The change:** the ADD CLIENT panel offers T1 / T2 / T3, defaulting to **T1**.
Picking T2 reveals `content.location` and `content.registry` and **requires
both** — refused, never silently downgraded, because `bootstrap_config.py:165`
already states the rule (`No content.location -> T2 is unavailable`) and a config
claiming T2 with nowhere to create files is the "working T1 that fixes zero
findings" shape the code comments warn about. T3 needs neither: it may change
anything not denied.

- `pipeline/audit/bootstrap_config.py` — `tier_block(project_dir, tier=1,
  content_location=None, content_registry=None)` writes the real `content:` block
  for T2+ instead of the commented template, and raises on `tier=2` without both
  fields. `--add-tier` takes the same flags, so raising a tier later uses one
  code path, not a second one.
- `pipeline/audit/onboard.py` — `--tier`, `--content-location`,
  `--content-registry` passed straight through. The tier is written *before* the
  scaffold commit, so one commit carries the finished config.
- `pipeline/dashboard/server.py::build_onboard` — `tier` must be an int in
  `{1,2,3}`; the two paths are validated with the same rules the repo and branch
  names get (must start alphanumeric, no `..`, bounded length). They join argv as
  separate tokens; nothing is interpolated into a shell.
- `static/fleet.html` + `page-fleet.js` — the radio group and the two revealed
  fields.

**What does not change, and this is the point:** `deny` still carries
`docs/client-config.yml` at every tier including T3, so the agent can never raise
its own authority. The tier now lands in the scaffold commit on the **default
branch**, which B-014's fix makes a human-authored commit by construction — the
same act CLAUDE.md already required, done at the moment the operator has the
context to make it.

A registry path that does not exist on disk is a WARN at onboarding and an ERROR
from `validate_profile`, so an incoherent T2 stops the run at the
`wf-client-profile` exit 5 seam that already exists rather than at a gate.

**Docs that become wrong and must change in the same commit:** `CLAUDE.md`'s
tiering section asserts "`wf-bootstrap-config` writes `tier: 1`. T2 and T3 exist
in the code but are unreachable for a client until a human raises that tier in a
human PR." The true statement afterwards is that the operator declares the tier
at onboarding, in a human-authored commit on the default branch, and the agent
still can never raise it. Also `docs/HOW-IT-WORKS.md` and
`docs/ADMIN-CHECKLIST.md` wherever they describe raising a tier as a separate
step.

**Phase 0 verification:** each fix lands with a test that fails without it.
`tests/test_onboard.py` for the scaffold commit (scratch repo, assert the six
paths are in `HEAD` and nothing else is), `tests/test_remediate.py` for merge +
resume, `tests/test_phase4_gates.py` for `prose_from` over
`docs/audit/2026-08/report.md`, `tests/test_dashboard.py` for the empty-diff
refusal, `tests/test_tiering.py` for T2-without-a-location being refused and for
the deny floor still holding at T3. Full suite pasted into the CHANGELOG.

---

## Phase 1 — the score

New module: **`pipeline/lib/score.py`**, ~70 lines. One definition, three
consumers (fleet card, client page, chart). Nothing in the codebase scores
anything today; this is the whole of it.

### How it is derived

A check either fires on a page or it does not. That is the unit.

```
score = 100 × (1 − failing_pairs / total_pairs)

total_pairs   = urls_checked × (codes in this family that actually ran)
failing_pairs = distinct (location, code) pairs present in findings.json
```

Two families, from the codes `measure.check_page` can emit:

| | Codes |
|---|---|
| **SEO** | `title_missing` `title_length` `desc_missing` `desc_length` `h1_count` `canonical_mismatch` `noindex_present` `og_image_missing` `img_alt_missing` `forbidden_phrase` `phone_missing` `tel_link_missing` `ga4_missing` `status_not_200` |
| **AEO** | `schema_business_missing` `schema_faq_missing` `schema_breadcrumb_missing` `thin_content` |

Three properties this shape buys, each of which a simpler formula loses:

1. **Immune to multiplicity.** B-009 emitted 1158 `img_alt_missing` findings from
   one broken regex. Counting distinct `(page, code)` pairs means one page
   contributes at most one failure per check, however many images it has.
2. **A skipped check cannot inflate it.** `tel_link_missing`, `phone_missing`,
   `ga4_missing` and `forbidden_phrase` do not run when their config field is
   unset. Those codes leave the denominator entirely and are listed by name under
   the score. Counting an unmeasured check as a pass is the "green means not
   measured" failure the whole rail is built against.
3. **Unmeasured is not 100.** `urls_checked == 0` returns `None`, and the UI
   renders "not measured", never a number.

`score(findings_doc, cfg)` returns, per family:
`{"score": 68, "failing": 41, "total": 128, "skipped": ["health.ga4_missing", …]}`

**Stated ceiling, in a `ponytail:` comment:** which checks ran is derived from
the config as it reads *now*, not as it read when the cycle was measured. Fill in
`ga4_id` after August's run and August's score shifts. The alternative is
stamping `checks_run` into `findings.json`, which is a second source of truth and
a schema change; not worth it until a cycle's score is quoted to a client.

**Also in this module**, because both screens need it and neither should compute
it: `progress(worklist, changelog)` →
`{actionable, fixed, remaining, blocked, unclassified, cost_usd}`. This is the
"how many findings are left" answer, and it is only trustworthy once B-013's
changelog merge lands.

**Verification:** `tests/test_score.py`. A clean cycle scores 100. A cycle with
one page failing one check out of ten scores 90. 1158 alt findings on one page
cost exactly one pair. An unset `ga4_id` shrinks the denominator instead of
scoring a pass. `urls_checked: 0` returns `None`.

---

## Phase 2 — the client screen says what stage this client is on

The complaint is "the dashboard and workflow is so confusing". The cause is that
every screen shows an artifact and no screen shows the sequence. There are nine
nav items and none of them is "what do I do now".

Add `next_action(client, cycle_bundle)` to `pipeline/dashboard/server.py`,
beside `fleet_entry`. Pure derivation from files already on disk — no state, no
database, consistent with the console holding none.

| Stage | Detected by | The one action |
|---|---|---|
| `ONBOARD` | no `docs/client-config.yml` | ADD CLIENT |
| `INTERVIEW` | config parses, still has TODOs | **human** — edit the config, then RESUME |
| `MEASURE` | no `findings.json` this cycle | run `site-health` |
| `PLAN` | findings, no `worklist.json` | run `site-plan` |
| `REMEDIATE` | worklist with items remaining | run `site-remediate` — shows count + projected spend |
| `REVIEW` | changelog with unapproved diffs | **human** — GATE 2, the diff screen |
| `COMMIT` | all approved, tree dirty | commit, gate, push |
| `PR` | branch pushed, no PR | "Open a PR?" |
| `MERGE` | PR open | **human** — GATE 3, on GitHub |

Rendered as a stage rail across the top of the client screen, current stage lit,
human gates marked as gates. The single primary button runs the stage's command.
`blocked_by` carries anything that makes the stage un-runnable — no write
access, no gate baseline, no build tree — as a visible reason rather than a
failure discovered mid-run.

**One piece of real chaining:** `COMMANDS["site-health"]` gains
`"then": "site-plan"`, and `Run`, on exit 0 or 1, launches the follow-on with the
same slug and cwd. Eight lines, declarative, and it removes the only genuinely
useless state in the rail — a measured cycle with no lanes, which the fleet card
today has to render as the words "not planned". Both runs appear in the console.

Chained under `RUNS_LOCK` and through the existing `busy_run` check, so the
follow-on obeys the same one-writer-per-checkout rule (B-012) as everything else.

**Verification:** `tests/test_dashboard.py` — one test per stage over a fixture
tree, plus a test that `site-health` exiting 1 launches `site-plan` and exiting 2
does not.

---

## Phase 3 — the graph

On the client screen: score per cycle, SEO and AEO as two series.

Three visually distinct states, because a claim must never render as a
measurement:

- **measured** — solid line, one point per `docs/audit/<ym>/findings.json`.
  Already on disk; the cycle folders are the time series.
- **projected** — dashed, one point, only for the open cycle. Recomputed with the
  findings whose `fingerprint` matches a `fixed` changelog item's `finding_fp`
  removed. This is what the pending PR claims it will do, labelled as a claim.
  Depends on the `finding_fp` addition in Phase 0.
- **verified** — a tick on the projected point, only once `acceptance_check` has
  exited 0 for that cycle. Absent is rendered as "not verified", never as
  verified.

**Until Phase 5 the verified leg is unavailable for SSR clients, and the graph
says so.** `acceptance_check` reads the build tree, `resolve_build_dir` falls back
to `./out`, and lee is `nextjs-16-app-router` with no `output: 'export'` in
`next.config.ts`, so it cannot run there. The graph renders "cannot verify — no
render source" for those clients, which is why the three states are visually
distinct in the first place. Phase 5 supplies the render source; nothing here
depends on it.

Implementation: `static/chart.js`, inline SVG, no dependency. Tailwind is already
on the page and there is no chart library in the repo; twelve points do not
justify adding one. `theme.css` already defines the palette. I will read the
`dataviz` skill before writing it, per its trigger.

A sparkline of the same series goes on the fleet card, so the fleet view answers
"who is getting better" without a click.

**Verification:** `tests/test_score.py` covers the series builder (the pure
function producing measured/projected points from a list of cycle bundles). The
SVG itself gets an eyeball, and I will say so rather than claim it is tested.

---

## Phase 4 — Gate 2, the diff review screen

The screen the whole plan exists to reach. New page, `/review`.

### Approving is `git add`

The dashboard holds no state, and this needs none. Staged means approved,
unstaged means pending. The index is the record: inspectable with `git status`,
survives a browser refresh, survives the server restarting, and needs no file
nobody else knows about.

- **APPROVE ITEM** → `git add --` the files that item touched
- **REJECT ITEM** → `git restore --staged --worktree --` those files
- **APPROVE ALL** → `git add -A` (the existing `stage-all` action, unchanged)

### Items are grouped into approval units, because a diff is not always separable

`changelog.json` carries `files: {path: [item_ids]}`. When two items touched the
same file their diffs cannot be split — you cannot approve one and reject the
other. So the server groups items transitively by shared file and presents each
group as one approval unit, saying plainly *"these 2 items both changed
`lib/page-meta.ts` — approve or reject together."* Pretending they are separable
is how an operator loses a fix they approved.

### Two refusals worth building

- **The pathspec is validated against the changelog.** Every path in an approve
  or reject request must appear in that cycle's `changelog.json` `files` map.
  Anything else is a 400. This is the same boundary as `COMMANDS`: without it,
  `POST /api/clients/<slug>/review` is `git add` and `git restore` over arbitrary
  paths, bound to a port.
- **Rejecting an untracked file is refused, with the reason.** `git restore`
  cannot revert a create; the honest alternative is `git clean -f`, which
  silently deletes a file. The message tells the operator to delete it
  themselves. T1 clients cannot create at all, so this only ever fires at T2/T3.

### Endpoints

- `GET /api/clients/<slug>/cycles/<ym>/review` → the units, each with its item
  ids, files, `git diff --` (pending) and `git diff --cached --` (approved) text,
  and a state of `pending` / `approved` / `partial`
- `POST /api/clients/<slug>/review` `{action, files}` → runs through the existing
  `_launch`, so it streams and is logged like every other action

Diffs render as raw unified text with `+`/`-` colouring — no diff library, and
the operator sees exactly what `git diff` said.

### And then it asks about the PR

Once no unit is pending, the screen reveals the finish panel, in this order and
no other — which is B-015's fix expressed as shape rather than as a paragraph
nobody reads:

1. **CREATE CYCLE BRANCH** — only if still on the default branch
2. **COMMIT** — message prefilled `audit: <slug> <cycle> — N fixed`
3. **CHECK** — `tier-check` and `claim-provenance`, now on a real commit, so
   green means something. Red stops here.
4. **PUSH**
5. **"Open a pull request?"** — asked. Yes runs `gh pr create --fill`; no leaves
   the branch pushed and says so.

No merge button. Gate 3 is a human reading a diff on GitHub, and that has not
changed.

**Verification:** `tests/test_dashboard.py` — a scratch repo with two items
sharing a file (asserts one unit, not two), a path outside the changelog
(asserts 400), a reject on an untracked file (asserts refusal, asserts the file
still exists), and approve-then-commit (asserts the commit carries the approved
files).

---

## Phase 5 — the gates come back online for SSR clients

Deliberately last: **nothing in phases 0-4 reads the build tree.** `measure`
crawls the live site over HTTP, and plan, remediate and the diff review are
entirely source-side. So the automated flow works end to end on lee before this
lands; what stays blocked is CI's judgment of the PR it produces.

### The actual state, which is better than the handoff implies

`.github/actions/build-site/action.yml:189-191` exits 1 when `BUILD_DIR` is
missing or empty, and every OUT gate carries
`if: steps.build.outcome == 'success'`. So on lee, CI **fails the build and skips
nine gates** — it does not report them green.

**Nine gates, not one.** `capsule_check` `check_headings` `em_dash_check`
`fingerprint_check` `forbidden_sweep` `orphan_check` `parity_check`
`noncommodity_check` read `<BUILD_DIR>/**/*.html`; `acceptance_check` reads it
via `resolve_build_dir`. Two of them are `NEVER_BASELINEABLE` for legal exposure
(`forbidden_sweep`) and structural truth (`orphan_check`, `parity_check`).

**A doc correction owed:** CLAUDE.md sharp edge #4 says a site with no route tree
"makes both gates scan nothing and report **green**." That is true only for a
directory that *exists* and holds no HTML — a missing directory is caught by the
build assertion, and `em_dash_check` and `acceptance_check` both refuse it
explicitly. The distinction matters because it rules out the fix anyone would
reach for first: pointing `build_output_dir` at `.next` produces exactly the
existing-but-empty tree that *does* report green, and only for the subset of
routes Next happened to prerender. Reword the sharp edge and add the ledger note.

### The render source

Rewriting a client's rendering architecture to suit our gates is backwards. The
rendered HTML for an SSR client already exists: the **Cloudflare preview
deployment**, which `preview.reusable.yml` resolves and exposes as `preview_url`
today.

One helper in `pipeline/lib/common.py`:

```
pages_for(profile, project, *, out_dir=None, base_url=None) -> Iterable[(route, html)]
```

- static-export client → glob `<out_dir>/**/*.html`, route derived from the path
- SSR client → crawl `base_url`, reusing `measure.discover_urls` / `curl`, which
  are already written and already tested
- neither available → raise, so the caller exits **4** ("the gate cannot run, so
  it will not pass"), a vocabulary that already exists in `EXIT_MEANING`

Then the nine gates change from globbing to calling it. `acceptance_check` and
`em_dash_check` first — the verified leg of the graph and B-008 — then the other
seven mechanically.

### The cost, stated plainly

`preview.yml` today is monitoring only and "never blocks". Wiring it into the
quality gate makes a Cloudflare outage a blocked PR. Mitigation: the gate polls
with a bound and exits **4 — refused, cannot judge** when the preview never
resolves. Never 0. A blocked PR is recoverable; a green one over an unrendered
site is not.

`quality-gate.reusable.yml` gains a `preview_url` input, and `build-site` learns
that a no-static-export client is a *named render mode*, not a build failure.
Locally, `--base-url` on the gate, and the console passes the preview URL it
already reads from `gh pr view`.

### B-008 — em dashes, with the decision it has been waiting for

`em_dash_check` is in neither `BASELINEABLE` nor `NEVER_BASELINEABLE`, so
`assert_baselineable` refuses it as "not in the allow-list".
`docs/gate-reference.md:105` already diagnoses why: it sits in a third category
"because on the pilot they were already clean. That is a property of the pilot,
not of the gates."

**The call: it is baselineable.** An em dash in the client's pre-existing copy is
legacy *content* debt, structurally identical to a non-Title-Case heading — and
`check_headings` is already in `BASELINEABLE`. The never-baselineable list is for
live falsehoods (an invented credential, a fix that never landed) and structural
invariants (sitemap parity, an orphaned route); a legacy em dash is neither.

Two parts, because the registry entry alone does nothing:

- `pipeline/gates/em_dash_check.py` — emit `Finding` objects instead of printing
  `(line_no, ctx)` tuples. This is the only reason it was never wired: the
  ratchet needs fingerprints.
- `pipeline/lib/baseline.py` — add `"em_dash_check"` to `BASELINEABLE`, beside
  `check_headings`, with the reasoning in the module docstring where the existing
  entries carry theirs.

The ratchet then does the work: legacy em dashes recorded once, the baseline may
only shrink, and an em dash in copy *we* wrote is a new finding that blocks.

**Verification:** a fixture with an em dash in legacy copy and one in a new file
— baseline recorded, the legacy one accepted, the new one blocking. Plus
`tests/test_gate_smoke.py` for `pages_for` over both a static tree and a stubbed
crawl, and an assertion that no render source exits 4 rather than 0.

---

## Order of work

Phase 0 first and whole — every later phase runs into one of those five
otherwise, and the tier picker shares its files. Then 1 (the score, which 2 and 3
both read), then 4 (the screen that is the actual ask), then 2 and 3 (the screens
that make the state legible). Phase 5 last, on its own, because it is the only
phase that touches CI.

Each phase is its own commit with its own CHANGELOG entry, its own ledger move
for the bugs it closes, and `pytest -q` output pasted in — run on its own line,
never piped into `tail` inside an `&&` chain.

`docs/MODULES.md` counts change: `pipeline/lib/score.py`, `static/chart.js`,
`static/review.html` + `static/page-review.js`.
`docs/HOW-IT-WORKS.md` gets the seven stages and the three gates.
`docs/gate-reference.md` loses its "third category" paragraph when Phase 5 moves
`em_dash_check` into `BASELINEABLE`.

---

## After Phase 0: reset lee's cycle, not lee

Once the five fixes land, lee's open PR #34 was produced under the broken gates
and its `changelog.json` was overwritten by the second run (B-013). The clean
first PR under the fixed rail is:

```bash
git -C ~/clients/lee-series-web checkout main
git -C ~/clients/lee-series-web branch -D cycle/lee-2026-08
rm -rf ~/clients/lee-series-web/docs/audit/2026-08/
```

Then re-run from the console. Costs roughly $3 in remediate and is fully
reversible up to the point the branch is deleted.

**Deleting every client and starting fresh fixes neither open problem.** The SSR
gap is a property of `nextjs-16-app-router` with no `output: 'export'`, so a fresh
client on that stack has it on day one. The em dashes are in the client's own
legacy copy, which a fresh clone carries identically. And lee is the only client
that has been driven through all six steps by an operator who did not write the
tool — it is what surfaced B-012 through B-016, and that history is worth more
than a clean slate.

---

## Not in this plan, deliberately

- **A queue, a scheduler, or a cron.** Both fleet pollers were deleted in v3 and
  that was the argument for this repo staying cheap. "Automated" here means the
  dashboard picks the next command; it does not mean a daemon runs it at 3am.
- **A merge button.** Gate 3 is the product.
- **Changing any client's rendering architecture.** Phase 5 gives the gates a
  render source that works on SSR; it does not ask a client to statically export
  to suit us.
- **A local render source for SSR clients.** Phase 5 wires the preview URL, which
  exists in CI and on an open PR. Building and serving the site locally to gate a
  pre-commit tree is a bigger lever than the flow needs — the gates run on a
  commit, and by then there is a PR.
- **A per-finding severity model.** The score is a pass rate. Weights are an
  argument every month; a pass rate is a fact.
