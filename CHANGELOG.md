# Changelog

All notable changes to this pipeline are documented here, newest first.
**Every behavior-changing commit must carry its entry in the same commit** —
see `CLAUDE.md` (the sync contract).

## [Unreleased]

_Nothing yet._

---

## [v3.1.0] — 2026-08-11

**The first engine release since v3.0.0, and the one that makes a client's pin
worth bumping.** v3.0.0 shipped 2026-08-06; `git log --oneline v3.0.0..HEAD | wc -l`
reports **37** commits accumulated on `main` since, which meant lee — the only
onboarded client — was being gated by code more than a month of work old. Three
of those fix gates that were **wrong about a real client**, and one adds the
input that turns nine skipped gates on.

Verified against the tag rather than assumed: `git show v3.0.0:pipeline/gates/claim_provenance_check.py | grep -c ARTIFACT_PATHS`
→ `0` (no B-016 fix), and `git show v3.0.0:pipeline/gates/audit_ssr.py | grep '"src"'`
→ `candidates = [project / "src"]` (the B-027 allowlist, intact).

**To upgrade a client:** change the `@v3.0.0` on each `uses:` line to `@v3.1.0`
and nothing else. Then read the two notes below, because two of these changes
require action in the client repo, not just a bumped tag.

| Ships | What it unblocks |
|---|---|
| **B-016** — provenance no longer scans `docs/audit/**` | Every client's **first** PR. The gate was refusing `wf-site-plan`'s own sentence *"this is the first cycle"* as an unsourced superlative |
| **B-027** — `audit_ssr` looks outside `src/` | `create-next-app`'s default layout is *no* `src/`, so the common Next repo got a silent `[SKIP]` from a never-baselineable gate |
| **B-034** — provenance stopped reading page diagnostics as business facts | The gate against invented ratings, review counts and year-counts actually refusing them |
| **B-022** — `health.schema_faq_missing` deleted | A permanently-unactionable finding per page, per cycle, forever |
| **B-032 / B-033** — `--tier` is applied, and T3 can be onboarded | Any client above T1 |
| **`render_url`** (new input) | The nine OUT gates on a client with no static export |

> ⚠️ **`PIPELINE_REPO_TOKEN` is renamed `SEO_AGENT`.** A client carrying the old
> name must add the new one **before** bumping, or every gate fails at the
> pipeline checkout. In practice this bites nobody today: no client carries the
> old name. And since `seo_agent` went public the secret is optional either way —
> see the entry under Changed.

> ⚠️ **`render_url` is opt-in and does nothing until a client passes it.** Adding
> the input to the engine does not turn the nine gates on; a caller has to supply
> a URL, and something has to resolve that URL. On Cloudflare that is
> `preview.reusable.yml`'s `preview_url` output. On any other host the caller
> feeds that platform's PR preview URL — the input is host-agnostic by design.
> **Untested against a live preview in CI (B-017)**; `wf-render-snapshot` itself
> is verified end to end, the *workflow wiring* around it is not.

### Removed

- **`health.schema_faq_missing` is deleted — closes B-022.** Google retired FAQ
  rich results on **2026-05-07**: they stopped appearing in Search that day, the
  Rich Results Test and Search Console report followed in June 2026, the API data
  in August. `FAQPage` is still valid Schema.org and harmless to carry, so any
  that exists is left alone — but the markup can no longer earn a search feature,
  which made the finding **unfixable by value**. A client with a perfect site
  collected one per page, every cycle, forever, and the ratchet re-filed them all
  as PERSISTING.

  Option (a) of the three the ledger listed, and the one it called the honest
  default. Four call sites: the emit in `measure.py` (lines 88-89 — the `if` AND
  its body, since removing 89-90 would have left an empty `if` and made
  `schema_breadcrumb_missing` unconditional), the `min_tier: 2` row in `plan.py`
  (the last T2 entry there), the code in `score.py`'s `AEO_CODES`, and the
  remediation doctrine.

  **Dropping it RAISES existing AEO scores, which is the correct direction.**
  Those pages were never actually worse for answer engines; the metric was
  scoring compliance with a dead feature. On lee: `114 -> 95` findings, exactly
  the 19 predicted, and AEO `61 -> 72` (failing 41 -> 22, denominator 104 -> 78).

  > **The real cost was not the wasted spend.** This was estimated at ~$9/cycle
  > while the finding sat above T1 and unreachable. Once lee went to T3 it became
  > actionable, and the agent's "fix" was not markup at all — it rendered the
  > entire `<Faq>` accordion onto `/about-us/`, **a visible design change to a
  > client's site**, to satisfy a check for a feature that no longer exists. A
  > finding that cannot be fixed by value does not stay harmless when the tier
  > rises; it converts into unrequested edits. Reverted, and the changelog entry
  > corrected from `fixed` to `no_change`.

### Changed

- **`Ethan5767/seo_agent` is now PUBLIC, and `SEO_AGENT` is therefore optional.**
  The two entries below this one describe the secret as the thing without which
  *"every gate fails to start"*. That was true while the repo was private; it is
  no longer. All four reusable workflows already declare it `required: false` and
  fall back to `token: ${{ secrets.SEO_AGENT || github.token }}`, and a client
  repo's `GITHUB_TOKEN` can read any public repo.

  ```
  $ gh repo view Ethan5767/seo_agent --json isPrivate,visibility
  {"isPrivate":false,"visibility":"PUBLIC"}

  $ git ls-remote https://github.com/Ethan5767/seo_agent refs/tags/v3.0.0   # no credentials
  ff2fb5221fa8132061dca89e65b2c63ecd24b198	refs/tags/v3.0.0
  ```

  Same SHA lee's run 31458064499 resolved. **What this actually retires is sharp
  edge #3** — "a human collaborator grant is not Actions access" — whose only
  workaround was a PAT with an expiry date living in someone else's repo. That is
  a poor fit for a client in a different account: `lee-wave` is not `Ethan5767`,
  and the operator who owns the token may not administer the repo it goes into.

  > **Unverified at the Actions layer.** lee has `SEO_AGENT` set and every run to
  > date used it, so the fallback is proven at the git layer and inferred above
  > it. The first client onboarded without the secret settles it.
  > `ADMIN-CHECKLIST.md` §1a says the same rather than rounding it up.

- **The `PIPELINE_REPO_TOKEN` secret is renamed `SEO_AGENT`**, after the repo it
  opens, so a client's secret list says what the key is for without a trip to
  `ADMIN-CHECKLIST.md`. Renamed in all four `*.reusable.yml` (declaration and
  `token:` fallback), all four `.github/examples/` callers, `CLAUDE.md` and
  `ADMIN-CHECKLIST.md`. **CHANGELOG history is deliberately left alone** — those
  entries are dated records of what was true when written.

  GitHub secret names are case-insensitive and stored uppercase, so an operator
  typing `seo_agent` into the UI produces the `SEO_AGENT` the workflows reference.

  > **This is a breaking change for any client already carrying the old secret.**
  > Nothing is broken today: the reusable workflows are consumed by pinned tag, so
  > a client on `@v3.0.0` keeps the old file and the old name until it bumps. No
  > client currently has the workflows installed at all — lee, the only onboarded
  > client, has zero secrets. Anyone adopting a tag that carries this rename must
  > re-add the secret under the new name **before** bumping, or every gate fails
  > at the pipeline checkout.

- **Onboarding now states the one step it cannot perform for itself.** The
  `SEO_AGENT` requirement is printed in the `[READY]` block of every `wf-onboard`
  run and shown in the dashboard's ADD CLIENT panel, with the token type spelled
  out: fine-grained, scoped to `Ethan5767/seo_agent`, `Contents: Read-only`, not
  a classic token whose only option is read/write over every repo the operator
  owns.

  It is said at creation time because of how the failure presents. Without the
  secret, a client repo's `GITHUB_TOKEN` cannot read this private repo, so **every
  gate fails at the checkout step** — which looks like a broken pipeline rather
  than a missing key, and is the most expensive possible moment to learn it.

  The dashboard's existing `GITHUB TOKEN — OPTIONAL` field is relabelled `— FOR
  THIS CLONE ONLY`, because two different credentials were one ambiguous word
  apart: that field is ephemeral and passed to a single run's environment, while
  `SEO_AGENT` is a durable secret on the client's repo.

### Fixed

- **`claim_provenance_check` accepted invented numbers, because page diagnostics
  were being read as facts about the business — B-034.** The gate's numeric half
  was close to inert. Two independent holes, both fixed:

  **(a) A work item's `evidence` contributed its numerals to the corpus.**
  Evidence is a measurement *of the page* — `len=106`, `words=478`, `count=12`.
  Doctrine admits it as a source, and rightly: it is real. But it is never a fact
  *about the business*, and as bare integers in a flat corpus it sourced anything
  that happened to share a digit string. Evidence now contributes its **words but
  not its numerals** (digits → `#`), so it still feeds the superlative check and
  can no longer act as a numeric alibi. The `[CORPUS]` line says so:
  `worklist.json (words only, digits redacted)`.

  **(b) A scoped claim matched anywhere in the config.** `rating`, `reviews`,
  `years` and `license` now resolve against `trust_signals.rating`,
  `.reviews`, `.years_in_business` and `.licenses` **alone** — not the config at
  large. A number is not a source because it exists somewhere; it has to be the
  number that *means* the thing claimed. A blank or placeholder field yields no
  source, which is the point: a client who has not told us their rating cannot
  have one written for them. `<x.x>`-style starter placeholders are treated as
  the unanswered questions they are.

  `warranty` is the fifth kind CLAUDE.md names but has **no config field
  anywhere**, so it stays on the general corpus. Scoping it to a key that does
  not exist would refuse every warranty term unconditionally — a different
  decision, and a human's.

  Measured on the real client (`lee-series-web`, 2026-08 cycle, 95 items / 190
  evidence strings / 38 distinct integers, 25 of them below 200):

  ```
  # BEFORE — the same diff, gate as shipped at v3.0.0
  $ wf-claim-provenance-check --project ~/clients/lee-series-web \
      --diff-file b034b.diff --cycle 2026-08
  [CORPUS] 148 words from: docs/client-config.yml, docs/audit/2026-08/worklist.json
  [OK] claim-provenance: every claim in 1 changed file(s) resolves to a source.
  exit=0
  ```

  The line it passed was `"106% more hydration, 478 customers served, from $12."`
  — `len=106` and `words=478` from page diagnostics, and a stray 12.

  ```
  # AFTER
  [CORPUS] 148 words from: docs/client-config.yml, docs/audit/2026-08/worklist.json (words only, digits redacted)
  [BLOCKED] 3 unsourced claim(s).
  exit=18
  ```

  And on the year-count case, which needed **(b)** rather than (a) — lee's
  `option_full_threshold_pages: 10` (an architectural escalation threshold) was
  sourcing `"Trusted for over 10 years"` for a client whose `years_in_business`
  is blank. Before: 2 unsourced, the year-count passed. After: 3 unsourced,
  `[UNSOURCED] 'over 10 years' (years)`.

  **Narrowed, not disarmed.** The prior version of the file is still checked
  *without* the scope — a claim already published is not being invented by this
  diff, and refusing inherited copy on every reflow is how a gate gets switched
  off. Removing legacy unsourced claims is a separate job.

  `tests/test_phase4_gates.py::test_evidence_numerals_cannot_source_a_business_claim`,
  `::test_a_year_count_needs_years_in_business_not_any_stray_number` (asserts both
  that the stray 10 *is* in the general corpus and that it no longer sources the
  claim, plus that a client who **has** declared 28 years keeps it and 30 is still
  refused), `::test_a_placeholder_is_not_a_source`. 677 passed.

- **Tier 3 could not be onboarded at all, and asking for a tier raise silently
  did nothing — B-033 and B-032, both found raising a real client to T3.**

  Neither is exotic. They are what you hit the first time you try to move an
  existing client off T1, which is the ordinary second act of every onboarding.

  **B-033 — the T2 precondition was applied to T3.** `validate_profile` read
  `if tier >= 2 and not content_location:` and raised an **ERROR**, so a T3
  client with no declared content home failed config validation and
  `wf-onboard` stopped at *"the config parses but does not cohere"* (exit 5).
  But T3 never uses that key: `tier_verdict` returns `True` on its `tier >= 3`
  branch at `common.py:400`, twelve lines **before** `content_location` is read
  at `:409`. The rule in CLAUDE.md is about T2 specifically — *"T2 is refused
  without `content.location` and `content.registry`"* — and `>= 2` quietly
  extended it to the one tier that is governed by the deny floor alone. The
  error message gave the game away: it told a T3 operator that **T2** was
  unavailable, explaining a tier they had not asked for. Now `tier == 2`.

  **B-032 — `--tier` was dropped on any client that already had a config.**
  Two causes in series. `onboard.py` passed `--tier` but not `--add-tier`, and
  `bootstrap_config.main()` only reads the tier for an existing config inside
  `if args.add_tier:`; otherwise it prints `[OK] Config already exists` and
  exits **0**. Behind that, `add_tier` is append-only — it declines a config
  that already declares a tier and *also* returns 0. So the request evaporated
  twice over and the run printed `[READY]`.

  Measured on `lee-series-web`: `wf-onboard … --tier 3` exited **0** with the
  full success banner while `docs/client-config.yml` still said `tier: 1` and
  the worklist still reported `78 above tier`. Nothing in the output said the
  tier had not moved.

  The append-only behaviour is **kept**. A tier raise being a reviewed human
  commit is the model (CLAUDE.md §Tiering: the agent can never raise its own
  tier, and `docs/client-config.yml` is on the deny floor at every tier). The
  defect was never the refusal, it was reporting success while refusing. So
  onboard now passes `--add-tier` (inert on a fresh config) and a post-bootstrap
  guard compares the on-disk tier against an explicitly requested one, stopping
  at exit **1** with the hand-edit instruction rather than measuring and
  planning at a tier the operator did not ask for. `--tier` defaults to `None`
  instead of `1`, so an omitted flag stays distinguishable from `--tier 1` and
  re-running a T2/T3 client with no flag never trips the guard.

  This is the same rule the gates already follow, applied to a pipeline stage:
  **a step that did not do the thing must not report success.** A worklist
  planned at the wrong tier is worse than no worklist, because it reads as an
  answer — the operator sees "78 above tier" and concludes the client needs a
  raise they just performed.

  Verified end to end on the real client: before, exit 0 and `tier: 1`; after,
  exit 1 and `[STOPPED] you asked for tier 3, but docs/client-config.yml still
  declares tier 1`; then, once the config was edited by hand,
  `worklist: 114 actionable, 0 above tier` at `Tier: T3`. **673 passed**
  (was 669: +3 onboard guard tests, +1 T3 validation test).

- **`audit_ssr` scanned nothing and reported a pass on every repo that took
  `create-next-app`'s default layout — closes B-027.** It looked for a folder
  named `src/` and exited **0** when it found none. That prompt defaults to *no*,
  so "no `src/`" is not an edge case, it is the common Next.js shape. A
  never-baselineable correctness gate — the one standing between a client and a
  blank-shell deploy — was reporting success over entire codebases.

  The scanner itself was never wrong. It masks strings and comments, tracks
  brace-scoped function depth, and honours `typeof` guards. Only the directory
  lookup was, so this replaces the lookup and touches no detection logic.

  **A denylist, not an allowlist, and that is the design decision.** The tempting
  fix derives roots from the framework: `app/` for Next app-router, `pages/` for
  pages-router, `src/` for Vite. Don't. `framework_family()` returns `None` for
  anything that is not next/vite/wordpress, so an allowlist scans **nothing** for
  the next client on a framework this repo has not met — B-027 again wearing a
  different hat. A denylist degrades safely: an unknown framework is over-scanned,
  never under-scanned. `tests/test_audit_ssr_roots.py` asserts that directly with
  an `islands/` layout and `framework_family("qwik") is None`.

  Excluded: `node_modules`, `.git`, framework caches, build output, `public`,
  `static`, `vendor`, `docs`, plus **the client's own configured
  `build_output_dir`**, so a repo emitting to `.output/` does not get its
  generated bundles reported as violations in files nobody wrote. Minified
  bundles committed into source are skipped too.

- **Scanning zero files is now a refusal (exit 4), not a pass.** This is the half
  that generalises. It does not care about layouts: any repo, any framework, if
  the gate found no source it says so instead of implying a clean bill of health.
  Same code and same meaning the forbidden sweep gives an empty ruleset. The
  WordPress skip stays exit 0 — *not applicable* is a different claim from
  *cannot judge*, and collapsing the two is what caused this bug.

  Measured after the fix: lee (`app/` layout, no `src/`) goes from
  `[SKIP] No src/ directory · rc=0` to `[FAIL] 4 files have SSR-dangerous
  patterns · rc=9` over 165 scanned files. A repo with no JS at all goes from a
  silent pass to `[REFUSED] ... rc=4`.

  > ⚠️ **Rolling this out needs a per-client look before the tag.** This gate can
  > never be baselined, so any client carrying pre-existing SSR issues outside
  > `src/` goes red on their next PR with no recording that accepts the debt.
  > lee's four says nothing about anyone else's count. Run `wf-audit-ssr <repo>`
  > against each client checkout and read the numbers **before** cutting the tag
  > clients adopt — same discipline as recording a gate baseline before a first PR.

  Also corrected: the caller comment in `quality-gate.reusable.yml` documented the
  bug as intended behaviour (*"Skips WordPress + repos with no src/"*), listing a
  real not-applicable case and a silent green as if they were the same thing.


### Security

- **Two fail-open holes closed before this ever shipped, both found by review of
  the diff below rather than by the diff's own tests.** They are the same shape:
  a feature whose safety argument was written down correctly and implemented
  against a different boundary than the one the argument named.

  - **B-029 — the agent could write its own skip list.** `docs/audit/human-worklist.md`
    sits inside `ARTIFACT_PATHS = ["docs/audit/**"]`, which `tier_verdict` waves
    through *before* it looks at the tier. Fix mode holds `Write`. So a T1 run
    could have invented a brief, had it recorded `fixed`, sailed past `tier_check`
    as a routine cycle artifact, and permanently dequeued that finding. Moved to
    `docs/human-worklist.md` and onto `DEFAULT_DENY`.
  - **B-030 — `forbidden_phrases: []` could be manufactured by deletion.** The
    ledger is the union of the config block and `docs/banned-phrases.txt`, but the
    declaration read only the config and only the config was on the deny floor.
    Measured: `exit=3 [BLOCKED]` on a real hit, then `rm docs/banned-phrases.txt`
    → `exit=0 [SKIP]`. The predicate now reads both halves, and the ledger joined
    `DEFAULT_DENY` so no tier can delete it.

  `DEFAULT_DENY` grew two entries, and `bootstrap_config.tier_block` emits both —
  caught by the pre-existing `test_emitted_block_parses_and_carries_the_deny_floor`,
  which is precisely the drift that test exists for. Neither hole was reachable on
  any live client: no client repo carries `forbidden_phrases: []` (the starter and
  the bootstrap both ship populated blocks) and no brief file existed anywhere yet.

  Both are now asserted across T1/T2/T3 rather than argued in a docstring, because
  the docstring was right and the code was wrong for the length of one review.

### Changed

- **The pipeline is PR-terminal by default. It is no longer a Cloudflare rail.**
  Measure → plan → remediate → 19 gates → human merge, and it stops. Deployment
  is the operator's job on whatever platform the client is actually on. The
  Cloudflare coupling was only ever in two files, and both are now marked
  **OPTIONAL — CLOUDFLARE PAGES ONLY** in their own headers and in their example
  callers: `deploy.reusable.yml` (hard-depends on `wrangler pages deploy` plus
  three `CLOUDFLARE_*` secrets) and `preview.reusable.yml` (reads Cloudflare's
  Pages deployments API).

  Nothing else needed changing, which is the point. `quality-gate.reusable.yml`
  already took a host-agnostic `render_url` — *"Rendered deployment to crawl when
  the repo has no static export (e.g. the CF preview URL)"* — where Cloudflare
  was an example, never a requirement. On another platform, feed it that
  platform's own PR preview URL; Vercel and Netlify both post one as a GitHub
  deployment status.

  Standard pair for a new client is now `quality-gate.yml` + `seo-health.yml`.
  A client on Vercel copies neither of the other two. **Verified against
  `lee-wave/lee-series-web`:** `gh api .../contents/.github` → 404 and
  `.../actions/runs` → `total_count: 0`, so that client has never had the thin
  callers at all and its 19 gates have never run in Actions. Its config says
  `deploy_platform: vercel`, so the deploy rail would never have worked there.

  **What a PR-terminal client gives up**, recorded rather than quietly dropped:
  auto-rollback (the captured Cloudflare deployment id), the deploy proof record
  (the merge commit is the record instead), IndexNow submission, and immediate
  post-deploy verification. The last of those moved rather than died — see below.

- **`pipeline/deploy/cf-crawler-check.sh` → `crawler-check.sh`, and it moved into
  the daily monitor.** The `cf-` prefix claimed a Cloudflare dependency it never
  had: the script is curl plus a list of citation user agents against a live URL,
  and works identically against Vercel, Netlify, Fastly or a bare origin. The
  name was one of the reasons the whole rail read as Cloudflare-bound.

  With no deploy job to hang it off, the check now runs in
  `seo-health.reusable.yml` on the daily schedule and on `workflow_dispatch`.
  An edge block — a Cloudflare "Block AI Crawlers" toggle, a Vercel bot rule, any
  WAF managed ruleset — zeroes the entire AEO pillar while every build metric
  stays green, and it is invisible in `./out`, so it has to be checked against the
  live host forever. Detection degrades from "within a minute of deploying" to
  "next scheduled run"; press Run workflow after deploying to close that window.

- **`em_dash_check` count corrected in `gate-reference.md`.** It said *"**Seven**
  gates accept `--baseline`"* while `pipeline/lib/baseline.py:147` has listed
  eight since `em_dash_check` moved in on 2026-08-07 (B-008). Counted, not
  remembered: 8 baselineable + 9 never-baselineable + 2 in neither list = 19.

### Added

- **`wf-site-remediate --recommend` and the standing human worklist — closes
  B-025.** A `no_change` for a *structural* reason was retried on every future
  run, at full cost, forever. On `lee-series-web` nine of fifteen `thin_content`
  items are product pages whose body copy is fetched from Firestore at request
  time by `lib/catalog.ts`; it is in the repository at no path, so **no tier can
  fix them** — not T1, not T2, not T3. Each cycle paid for nine investigations
  and got nine correct refusals.

  Recommend mode turns that spend into a deliverable instead of suppressing it.
  It is the same loop with the same before/after `git status` measurement and the
  **opposite assertion**: the tree must come back clean, and a run that modified a
  file is refused and stopped exactly like an out-of-tier edit. The agent's reply
  is written to `docs/audit/human-worklist.md` for a person to paste into the CMS.

  Two design decisions worth the ink:

  - **The worklist is NOT under `docs/audit/<cycle>/`.** A page whose copy lives
    in a CMS is a fact about the site's architecture, not about the month someone
    measured it. Filed per-cycle, next cycle's empty folder re-queues all nine and
    the leak reopens.
  - **The brief file IS the list.** `selectable()` skips any fingerprint that
    carries a brief, so no `unfixable:` config block is needed and no operator
    hand-maintains fingerprints. The agent cannot suppress its own work with it
    either: writing a brief only happens in recommend mode, which an operator
    invokes, and that mode has to finish with a clean tree.

  The brief carries the derivation rule *harder* than a file edit does, because a
  file edit lands in the diff where `claim_provenance_check` refuses an invented
  rating or licence number, and a brief lands in markdown no CI reads and reaches
  production by hand. So the prompt draws the line explicitly: write out only what
  traces to a source you actually read, and emit `[NEEDS FROM CLIENT: ...]` for
  every gap. The file says so in its own header too.

  A briefed item leaves the agent's queue and **does not leave the report** —
  `plan.py` stamps `human_edit` on it and gives it its own *Briefed for a Human
  Editor* heading, because the page is still thin whether or not we can reach the
  copy. Trading a money leak for a blind spot would not have been a fix.

  **Ran live**, not only against a stub, on `www.leeserie.com`
  `/product/rice-cake-cleanser/` (`thin_content`, `words=442`):

  ```
  [BRIEFED] wi-2026-08-0101 health.thin_content on /product/rice-cake-cleanser/
  [OK] 1 brief(s) written, $0.6464 -> .../docs/audit/human-worklist.md
  [NOTE] nothing in that file has passed a gate.
  ```

  `git status` after the run showed no source file touched, so the clean-tree
  assertion held against the real writer. The brief restructured the existing
  paragraph into a benefits list (free — same sentences) and emitted two
  `[NEEDS FROM CLIENT: ...]` blocks for the usage instructions and FAQs, naming
  that those are what actually move 442 words past 500 and cannot be filled from
  anything in the repo. That is the intended shape.

- **`.github/examples/seo-health.yml` — the thin caller that never existed.**
  `CLAUDE.md` flagged its absence while the monitor was a nice-to-have. Now that
  the pipeline is PR-terminal it is the **only** thing that ever looks at the live
  site, and it carries the crawler check, so a client running the quality gate
  without it is gated but unwatched.

### Fixed

- **`fingerprint_check` no longer fails a Khmer client for writing Khmer
  correctly.** Khmer has no spaces between words and uses `U+200B` to mark where a
  line may break. `lib/i18n.ts` on `lee-series-web` carries **28** of them inside
  Khmer sentences — correct, deliberate i18n work — and this gate is
  **never-baselineable**, so the first Khmer page rendered would have blocked that
  client's every PR forever with no recording that could accept it.

  The exemption is deliberately narrow: `U+200B` only, and only when a
  neighbouring character is Khmer (`U+1780..U+17FF`). Judged on the immediate
  neighbours rather than the paragraph, because that is exactly the claim being
  made. `U+200C`, `U+200D`, the bidi controls and the tag block still fire in
  every context including inside Khmer, and a `U+200B` in a Latin sentence three
  lines down is still a hit — which is where the AI-clipboard signal actually is.

  Only Khmer is listed. Thai, Lao and Myanmar belong there the day one is
  onboarded; an over-broad list would quietly re-open the hole the gate exists to
  close. Measured on lee's real files: `lib/i18n.ts` 28 hits → **0**, and the
  genuine `U+200D` in an empty Webflow paragraph in
  `app/(site)/privacy-policy-and-terms-of-service/page.tsx` still → **1**.
  `tests/test_fingerprint_check.py`, 7 tests.

- **A client with no banned-phrase ledger can now declare that, instead of being
  blocked forever.** `forbidden_sweep` and `rules_selftest` both exited 4 on an
  empty ruleset, which is right as a default — a silent green over zero rules is
  the failure this suite exists to prevent — but left no way to say "this client
  genuinely has none". There are now three states, and the middle one is the point:

  | config | behaviour |
  |---|---|
  | `forbidden_phrases: []` | a DECISION. Both gates SKIP, and say so by name. |
  | key absent | nobody decided. Both gates still exit **4**. |
  | `forbidden_phrases: [..]` | rules. The gates run them. |

  Only a literal empty **list** counts. A bare `forbidden_phrases:` key parses to
  `None`, which reads as a config someone started and abandoned rather than a
  decision anyone made, so it stays in the refusing state.

  What makes this safe to offer at all is *where* the declaration lives:
  `docs/client-config.yml` is on the deny floor at every tier including T3, so the
  agent can never disarm the gate that judges its own copy. The skip requires a
  human commit, exactly like the tier does — `tests/test_declared_empty_ruleset.py`
  asserts that property directly rather than trusting it.

  Verified on lee: both gates went from `rc=4` to `[SKIP] ... rc=0` after adding
  the declaration. `tests/test_declared_empty_ruleset.py`, 12 tests.

- **`skills/site-remediation/references/page-type-shapes.md` — the section shape
  of a page, for the T2 agent that has to write one.** Until now the entire
  instruction for writing a new page was §7's six bullets plus the `thin_content`
  row's *"write real content that answers the query"*. That says what not to do
  (don't pad, don't invent, don't orphan it) and nothing about what a service
  page or a location page actually owes its reader, so the shape of the page was
  left to whatever the model reached for.

  The new reference gives six shapes — service, location, blog, category/hub,
  FAQ, case study — each a section table of *purpose + format + length*, plus a
  short note on homepage/about, which the agent expands rather than creates.
  Adapted from `skills/seo-content-brief/references/page-type-templates.md` in
  [AgricIDaniel/claude-seo](https://github.com/AgricIDaniel/claude-seo) (MIT,
  © 2026 agricidaniel), with the competitive-brief framing removed: at
  remediation time there is no SERP scrape and no competitor set, so the
  upstream's competitor-derived word counts and gap scoring had nothing to
  stand on.

  What was **added** rather than adapted is the provenance layer, because the
  upstream has no equivalent of `claim_provenance_check`. Three of its rows —
  "Why choose [brand]", "Outcomes and results", "Awards and recognition" — are
  precisely where an invented licence number or star rating appears, so the file
  opens with a table naming them and one rule: **a section you have no sourced
  material for gets left out, not filled.** The case-study shape carries an
  explicit "there is almost never enough in `client-config.yml` to write one
  honestly — `NO CHANGE` is the right answer" note.

  **Every gate assertion in the file is stated once, at the top, and was
  verified against `pipeline/gates/` rather than written from memory** — the
  first draft did the opposite (a claim per page-type section, from recall) and
  four of them were false, which a review caught before this shipped. What the
  file now says, with citations: `capsule_check` selects every route fitting the
  client's `topology` plus `/blog/*`, not just blog posts, so a service or
  location or case-study page needs an interrogative H2 and a **40–80 word**
  opening block after it — and that band measures the first `<p>` *or `<li>`*,
  which is why a section that opens with a bulleted list fails. `orphan_check`
  models no hub→child relationship whatever (it walks the sitemap and counts
  self-links from global nav as inbound), so enumerating a hub's children is
  entirely on the agent, and the gate that catches an unwired page is
  `parity_check`. `noncommodity_check` measures whole-page 5-gram overlap at
  **0.90** on hub-spoke, and its token allow-list is built from the client's own
  city names — so naming the city passes it. The house "true of this city, false
  of its siblings" standard is kept, now labelled as stricter than the gate
  instead of attributed to it. Schema is one block rather than six lines:
  `measure.py:82-91` demands the configured `schema_type` **and**
  `BreadcrumbList` on *every* URL unconditionally, and measures none of
  `Service` / `Article` / `WebPage`.

  Also stated: T2 grants `content.location` plus the registry paths, so a hub
  page living in a component outside those paths is a T3 edit and `tier_check`
  refuses the run — `NO CHANGE` is the answer, not a workaround. And
  `claim_provenance_check`'s patterns are numeric, so bare "licensed and
  insured" carries no digit and the gate will not stop it; §1 of the skill still
  does. Naming where the gate stops being a floor is the point.

### Fixed

- **`wf-site-remediate --only <ITEM_ID>`, repeatable.** `--max-items` cuts from
  the *front* of the queue, so reaching one item means paying for everything
  sorted ahead of it. On lee the single actionable `title_out_of_band` sorted
  fifth, behind four Firestore PDPs that had already refused once — so getting
  to it would have re-run and re-paid for four refusals already on record.
  Filtering by id costs three lines and does not touch the ordering, the tier
  check, or the resume. Built because the run needed it, not in advance.

- **First live `thin_content` run — B-024 verified against a real client, and it
  found what the tier model cannot see.** `lee-series-web`, 2026-08 cycle, T1,
  `--model sonnet`, 10 items attempted (the default `--max-items`), **$7.38**:

  ```
  runs 4  attempted 30  queued 15  stopped max-items (10) reached with 5 item(s) left
  thin_content: 6 fixed, 4 no_change
  ```

  The six fixes are the repo-backed pages, and the tier held on every one —
  `lib/learn-guides.ts` for the three `/learn/*` guides, `lib/i18n.ts` and
  `app/(site)/**/page.tsx` for `/app/`, `/contact-us/` and the `/product/`
  listing. All inside `text_paths`, no `[REFUSED]`, exit 0. `/learn/stretch-marks/`
  went 404 → 553 words. Before B-024 every one of these was filed unactionable.

  **The four refusals are the finding.** All four are `/product/[slug]` PDPs and
  all four gave the same correct reason: the body copy — `description`,
  `benefits`, `instruction`, `faqs`, which is the bulk of the word count — is
  fetched at request time from **Firestore** via `lib/catalog.ts`'s
  `getProductSetBySlug`. It is not in the repository at any path, so **no tier
  can fix it.** Not T1, not T2, not T3. Nine of lee's fifteen `thin_content`
  items are these Firestore-backed PDPs.

  The agent did exactly what §3 tells it to — changed nothing, said `NO CHANGE`,
  named the file and the allow-list it was measured against, and did not invent
  copy to hit a word count. That is the doctrine working. **The engine is what
  has no memory of it:** `already_fixed` records only `status == "fixed"`, so all
  nine will be re-queued, re-investigated and re-refused on every future run, and
  re-filed as PERSISTING by every future plan. Logged as **B-025**, unfixed —
  it needs a way to say "real, but not fixable from here", which the finding
  model does not currently have. Same end state as B-022 by a different route,
  and worth solving once for both.

  The remaining five queued items are all Firestore PDPs, so they were **not**
  run — five guaranteed refusals is not worth the spend. One genuinely
  actionable item is left in the queue (`wi-2026-08-0105`, `title_out_of_band`,
  whose copy is in `lib/page-meta.ts`).

- **`thin_content` is T1, not T2 — B-024.** `plan.py`'s tier map keyed off the
  finding kind and assumed thin content means "write a new page". It does not:
  `measure.py` only measures **live URLs**, so a page cannot be measured as thin
  unless it already exists, and the fix is always "expand the copy that is
  there". `min_tier` 2 → 1, with the reasoning in a comment at the call site so
  it does not get corrected back.

  Found by trying to act on it. On `lee-series-web`'s 2026-08 cycle this blocked
  **15 of 114** items — three `/learn/*` guides, nine `/product/*` PDPs,
  `/app/`, `/contact-us/` and the `/product/` listing, all measured at 336–496
  words against `min_words: 500` — and **every one of their target files was
  already in lee's `text_paths`**. A T1 agent was permitted to edit all of them
  and was told not to try.

  Raising the client to T2 would not have fixed it, which is the part worth
  remembering: T2 grants *creates* under `content.location`, and lee has nowhere
  to create. Its guides are a typed array in a single 180-line file with a
  union-typed slug (`lib/learn-guides.ts:6`) behind a dynamic
  `app/(site)/learn/[slug]/page.tsx` route. Declaring a `content.location` to
  unblock the work would have been precisely the "grants authority over nowhere
  while claiming more" failure `CLAUDE.md` warns about. **The tier model's
  file-per-page assumption does not hold on a data-driven repo, and the tier map
  is where that leaked.**

  The safety did not move: `tier_check` still judges the real diff, so a client
  whose thin page's copy is *not* in `text_paths` is still refused — at the
  diff, which is where the tier model puts that judgement, rather than by a
  guess made at plan time about what the fix will touch.

  `tests/test_plan.py::test_thin_content_is_actionable_at_t1` is the regression.
  The pre-existing `test_tier1_blocks_content_work_but_keeps_it_visible` used
  `thin_content` as its T2 example, so it was rewritten around `health.h1_count`
  (T3 template work, which genuinely stays blocked) and renamed
  `..._blocks_structural_work_...`. `.venv/bin/pytest -q` → `621 passed in
  5.31s`. `schema_faq_missing`, the other `min_tier: 2` entry, is untouched —
  that is B-022 and a separate call.

- **The doctrine caught up with B-024 before the run, not after.** Moving
  `thin_content` to T1 left `SKILL.md` §5 still labelling the row **(T2)**. A
  `--dry-run` of the rebuilt prompt showed the contradiction in place: the
  authority block said `TIER 1`, the work item said `min_tier: 1`, and the
  fix table said the finding needed T2. An agent reading its own prompt would
  have been entitled to answer `NO CHANGE — needs T2` on all 15 items. The row
  now says what the job actually is: the page exists, expand the copy that is
  there, create nothing. And `page-type-shapes.md` is re-scoped from "T2 only"
  to whole-page work at any tier, with a paragraph on the difference — expanding
  a thin page means finding the section it is *missing*, not rebuilding it to
  match a table row for row, because §2's one-finding rule still binds.

  Worth noting how it surfaced: `--dry-run` prints the exact assembled prompt
  and writes nothing. Reading it before a paid run is cheap and it is the only
  place a doctrine/tier-map disagreement is visible at all.

- **The same gate claims, corrected everywhere else they were stated.** Having
  written the contract down once from the source, the other copies were checked
  against it rather than left to drift:

  - `SKILL.md` §7 carried the same false `orphan_check` claim ("a page linked
    from nowhere is an orphan, and `orphan_check` refuses the PR"). It now says
    what is true: T2 *permits* a registry edit and nothing asserts you made one,
    `orphan_check` counts a global-nav self-link as inbound, `parity_check` only
    fires if the page built without reaching the sitemap — so an unwired page
    can clear both, and wiring it in is on the agent.
  - §7's capsule line and `serp-title-meta-craft.md` both described the capsule
    without its word band ("2-3 sentence answer"), which is a *latent* conflict,
    not a live one: a crisp two-sentence answer can land under 40 words and fail
    a gate neither file mentions. Both now name 40–80 words / ≤3 sentences and
    point at `page-type-shapes.md` §1 as the single place those numbers live.
  - `docs/gate-reference.md`'s `capsule-check` row had the same gap, plus no
    mention of which routes the gate selects; and its `orphan-check` row, while
    accurate, omitted the two scope facts that make the gate weaker than it
    reads (self-links count, sitemap-driven). Both now state them.

- **`docs/gate-reference.md`: three gates deleted in `79b0b5b` were still
  documented as BLOCKING, with green results — B-023.**
  `pages-are-data-check.py`, `brief-fanout-check.py` and
  `validate_multistate_config.py` went with the DOCX rail a release ago;
  `brief-fanout-check` reads `docs/briefs/*.json`, which does not exist. The doc
  contradicted itself — line 103 already called `pages-are-data-check`'s entry
  dead while line 144 listed it as live. An operator would have counted 22 gates
  against the 19 that exist. Found by listing every gate filename in the doc and
  testing each against `pipeline/gates/`, which is worth doing periodically:
  `MODULES.md` was already correct at 19, so nothing else flagged the drift.
  The rows are struck through and marked **REMOVED** naming `79b0b5b`, not
  deleted — the table carries an "observed Run #1" column and is partly a
  verification record.

  Pointed to from §5 (alongside the title/meta and anti-slop references) and §7
  of `SKILL.md`. **No code change was needed to ship it:** `remediate.py` already
  passes `--add-dir` on the skill's parent directory, so the whole `references/`
  tree is readable by the agent. Its comment said "the two prose references" and
  now says the directory, so the next one needs no edit either.

  Not taken from the same upstream, and why: its `keyword-density.md` meta rules
  (50–60 char titles, 130–150 char metas) contradict our gate bands (30–60,
  120–160) and are weaker than `serp-title-meta-craft.md`; its `seo-drift`
  SQLite snapshots duplicate `plan.py`'s ratchet statelessly-in-the-PR; its
  E-E-A-T scorer is a subjective 1–10 audit, which is the opposite of a measured
  finding and nothing downstream could gate on it; and its 18 agents / 32 slash
  commands are an interactive consultant with no tier to obey and nothing
  re-measuring the output.

  While adapting it, the upstream's dated note on Google retiring FAQ rich
  results led to **B-022**: `measure.py:89` emits `health.schema_faq_missing` on
  every page lacking `FAQPage`, for a feature Google deprecated on 2026-05-07
  (confirmed against Google's own notice, not the upstream's claim). It is
  unfixable-by-value — it PERSISTS through the ratchet forever and points a T2
  agent at markup for a dead feature. Logged, not fixed; the fix is a decision
  (delete / gate behind config / demote to informational), not a patch, and it
  moves `docs/gate-reference.md` and any client baseline with it.

- **`wf-seed-queries` — the SERP query list, grounded in the client's own pages
  instead of typed from memory.** `--with-serp` measures exactly the queries in
  `docs/client-config.yml` and nothing else, so that list *is* the measurement.
  `lee-series-web` had five, hand-typed, and one of them was `lee serie` — the
  brand name. They rank #1 for it, so a fifth of the paid budget bought a
  finding that can never be actionable.

  New module `pipeline/audit/seed_queries.py`. It crawls the sitemap (capped at
  `--crawl-max`, default 40 pages), pulls `<title>` and `<h1>` off each page
  that answered, and hands those facts to Claude Code with an expansion recipe:
  related searches and PAA via WebSearch, long-tail and intent modifiers,
  question mining, then intent classification that drops navigational terms. The
  recipe is adapted from `AgriciDaniel/claude-seo` (MIT), skill `seo-cluster`
  steps 1 and 3. The agent gets `--allowedTools WebSearch` and nothing else — it
  reads the web and writes no files, and a test asserts the argv rather than
  trusting the prompt, because the allow-list is what bounds an agent's
  authority (`CLAUDE.md`) and every other test stays green when it widens.

  **The agent is asked for a JSON array and the reply is `json.loads`-ed.** The
  first draft asked for one query per line and recovered structure with
  heuristics — strip bullets, over ten words is prose, a trailing colon is a
  heading. A review killed it, and correctly: each rule was simultaneously too
  loose and too tight. `stderr` was merged into stdout, so a single `claude` CLI
  warning line passed every filter and would have been pasted into a client
  config as a paid, permanently-fingerprinted query. And the `>10 words` rule
  deleted exactly the eleven-word People Also Ask questions the recipe exists to
  produce. A malformed reply is now a loud exit 20 carrying the raw text, never
  a partial guess, and every drop is named on stderr.

  **Two design constraints drove the shape, and both are load-bearing:**

  1. **It is a separate command, not a flag on `wf-site-health`.**
     `Finding.context` is fingerprinted and the query is the context. A list
     regenerated every cycle re-files every SERP finding as NEW forever and
     makes RESOLVED unreachable — the ratchet would silently stop meaning
     anything. Generation happens once, into a human-reviewed commit, the same
     shape as the tier.
  2. **It prints; it never writes `docs/client-config.yml`.** That path is on
     `DEFAULT_DENY` at every tier including T3. The paste step is also the
     review: these queries are derived from the site's vocabulary but are not
     volume-ranked, so a query nobody searches would produce a real
     `serp.absent` finding that reads like a site defect.

  The pure seam is `page_facts` (html → title + h1s), `brand_names` (config →
  every spelling of the client's own name), `parse_reply` (JSON → validated
  queries) and `unwrap_envelope`, so the whole suite runs offline.

  **The brand drop reads four fields, not one.** `business.legal_name` is the
  *legal* name and carries entity suffixes; the query people type is the trade
  name in `nap.name`. Matching only `legal_name` meant that on a client called
  "Lee Serie Co., Ltd." the drop silently did nothing to `lee serie` — failing
  on the exact case that motivated the feature. It now unions `client_name`,
  `business.legal_name`, `business.trade`, `nap.name` and the de-slugged
  `client_slug`. The match stays exact on the whole normalized query, never a
  substring: `lee serie` is navigational, but `lee serie stretch mark cream
  review` is commercial and worth tracking — a substring check kills both.

  Exits: 2 no `claude` on PATH (checked *before* crawling 40 pages), 19 the
  sitemap was unreachable or no page answered, 20 the agent failed or returned
  no JSON array.

  32 new tests, including a `main()`-level run with the network and agent
  stubbed — B-007, a green test on `parse_reply` proves the parser works, not
  that anything calls it.

  ```
  $ .venv/bin/python -m pytest -q
  620 passed in 5.01s

  $ .venv/bin/wf-seed-queries --project /tmp/sqtest      # unreachable domain
  [REFUSED] https://no-such-host-xyz-12345.example/sitemap.xml is unreachable
  and no --url was given: nothing to measure
  EXIT=19
  ```

  **First live run, `lee-series-web`, 2026-08-07.** Grounded in 26/26 sitemap
  pages, 39 queries, `lee serie` correctly absent. Every query traces to a
  product page on the site or to `primary_metro` / `service_areas` in the
  config. Measured with all four providers:

  ```
  [crux]       no field data: CrUX has no record for www.leeserie.com
  [dataforseo] failed: HTTP 403 from .../on_page/task_post
  [serp]       partial: 31/39 queries measured (8 failed)
  [OK] 26 URLs measured, 145 findings -> docs/audit/2026-08/findings.json
  [OK] 145 new, 0 persisting, 0 regression, 0 resolved
       worklist: 21 actionable, 93 above tier, 31 needing a human
  ```

  All 31 measured queries came back `serp.absent` — the site ranks for its own
  name and nothing else, which is a coherent result for a young DTC brand and
  exactly the gap the queries were chosen to expose. The 31 route to a human
  rather than the agent because `acceptance_check`'s allowlist is
  `code.startswith("health.")`; no change was needed for that to hold at 31
  findings instead of 3.

  The run surfaced **B-021**: the 8 SERP failures are transient, not
  deterministic. Re-probed two by hand minutes later — one returned a
  `JSONDecodeError`, the other succeeded with `organic=9`. Because the query is
  the fingerprint, a query that fails one cycle and succeeds the next reads as
  NEW, and one that succeeds then fails **reads as RESOLVED** — a fix that never
  happened. Logged, not fixed; the structural fix needs `plan.py` to distinguish
  "not measured" from "no longer a problem". Do not read a SERP RESOLVED as a
  win until it lands.

  **Not done, and deliberately:** no volume data. Google Ads Keyword Planner is
  the correct source for ranking candidate queries by real demand, but it needs
  an Ads Manager account plus a developer token with Basic-access approval, and
  returns bucketed ranges ("1K-10K") rather than numbers without active ad
  spend. Heavier than GSC, which is itself still ungranted.

  Also corrected while in the file: `client-config.starter.yml` documented the
  flag as `wf-site-measure --with-serp`. No such command exists; it is
  `wf-site-health`.

- **`measure.urls_or_refuse` — `discover_urls` now ships with its exit codes.**
  `discover_urls` raises `Unreachable` / `UsageError`, and `measure.main` mapped
  them to 19 / 2 inline. `wf-seed-queries` borrowed the function bare, so an
  unreachable sitemap — the single most likely first-run failure, and what
  sharp edge #4 is about — produced a traceback and exit 1. The mapping is the
  contract, not a detail, so it moved into `urls_or_refuse` next to the function
  it guards and both CLIs call it. Behaviour for `wf-site-health` is unchanged.

- **`serp_findings`' empty-list skip now names the command that fixes it.** It
  said "there is nothing to look up" and stopped there. It now says to run
  `wf-seed-queries`. A named skip that does not say what to do next is only half
  a named skip.

### Fixed

- **B-020 — `wf-site-remediate` resumed on a positional id, so any re-measure
  mis-resumed.** B-013 taught it to skip what the cycle's `changelog.json`
  records as `fixed`, keyed on the work item `id`. But ids are
  `f"wi-{cycle}-{idx:04d}"` (`plan.py:151`) — an enumeration index over the
  sorted findings. Gain or lose one finding, re-plan, and every later id shifts
  onto a different finding.

  Found on `lee-series-web` while re-running 2026-08 with the new SERP provider.
  Three `serp.absent` findings entered the set and **19 of 20 fixed ids landed
  on unrelated work; zero stayed aligned**:

  ```
  wi-2026-08-0009  changelog fixed: health.title_length @ /about-us/
                   that id now is : health.schema_breadcrumb_missing @ /about-us/
  ```

  The next run would have skipped nineteen untouched items as done. Caught at
  the plan step, before any spend.

  `already_fixed` now returns `finding_fp` values and `selectable` filters on
  the item's fingerprint. `remediate.py:476` already said `finding_fp` "is the
  only exact link from a fixed item back to the finding it fixed" — the resume
  path just never used it. An item with no fingerprint is never skipped:
  attempting twice costs money, skipping a real finding and recording it fixed
  puts a falsehood in the artifact.

  On the real cycle, post-renumbering: 20 fingerprints recorded fixed, **21
  actionable, 1 queued, 20 correctly skipped.**

  ```
  588 passed in 5.03s
  ```

### Added

- **The dashboard now shows provider statuses** (`findings.html`,
  `page-findings.js`). `measure.py` has always written a status string per
  external source into `findings.json` under `providers`, for one reason: a
  provider that returned nothing because it was never asked must not read as a
  provider that returned nothing because the site is clean. **The dashboard
  never read it** — `grep -rn "providers" pipeline/dashboard/` returned nothing
  before this change.

  So the screen a human actually looks at dropped the exact signal the artifact
  carries it for. A cycle where all four providers skipped rendered identically
  to a cycle where all four ran clean, and the empty state said, in words,
  *"This site was measured and passed."*

  Three states, because only one of them means the count below is complete:
  green `ok:`, red `failed:`, amber for everything else (`skipped:`, `partial:`,
  `timed out:`, `no field data:`). Amber is not a warning about the site — it is
  a warning about the measurement.

  The no-provider case gets a full-width amber sentence rather than an empty
  strip, since that is the case that misleads: an HTTP-only cycle is a real
  measurement, just not of anything CrUX, Search Console, DataForSEO or Bright
  Data can see.

  The strip wraps rather than scrolls. Verified in the browser first: with
  `overflow-x-auto` the fourth provider fell off the right edge, and the one
  clipped was the `skipped:` — a skip pushed off-screen defeats the only reason
  the strip exists.

  No server change was needed; `_cycle` already shipped the whole
  `findings.json`. Wiring is asserted rather than assumed
  (`test_the_findings_screen_actually_renders_the_provider_strip`), because
  there is no JS test harness here and a helper nothing calls is B-007 again.

  ```
  586 passed in 5.02s
  ```

- **Bright Data SERP as a fourth optional provider** (`wf-site-measure
  --with-serp`, `pipeline/audit/providers.py`). One Google request per entry in
  the client config's `seed_queries`, firing `serp.page_two` (rank 11–30) and
  `serp.absent` (rank > 30, or not in the result set at all).

  It exists for one gap and no other: **Search Console only reports queries that
  already have impressions**, so it is blind by construction to "we rank nowhere
  for this". Everything GSC can already answer is left to `gsc_findings`.

  Rank and the ranking URL are carried in `Finding.detail`, which the fingerprint
  excludes, so ordinary rank movement stays PERSISTING instead of churning
  RESOLVED + NEW every cycle. `location` is `/` for the same reason CrUX measures
  at origin level — which page ranks is Google's choice and moves without the
  site changing.

  An empty `organic` array emits **nothing**. A broken response is not evidence
  that the client ranks for nothing, and inventing `serp.absent` there would be
  the invention `claim_provenance_check` exists to refuse.

  `parse_serp` collects every hit for the client's host and bands the **best**
  one. Banding inside the scan made the verdict depend on the order `organic[]`
  happened to arrive in — a site ranking #4 read as `serp.absent` when a #61 hit
  for the same host was listed first — and made the absent-case detail contradict
  its own payload ("not in the top 1 organic results" about the only result).
  Both are covered: `test_the_best_rank_wins_regardless_of_array_order`,
  `test_ranking_far_down_reads_as_absent_and_says_the_rank`.

  Proof (`.venv/bin/python -m pytest -q`):

  ```
  583 passed in 4.90s
  ```

  Reuses the existing `seed_queries` config key, which had been declared in
  `client-config.starter.yml` and only ever counted. No new config key, no new
  module, no new dependency — `_request` and stdlib `urllib` throughout.

  The call site is asserted, not assumed
  (`test_with_serp_passes_the_configs_seed_queries_to_the_provider`): it drives
  `measure.main()` and checks both that the provider receives the config's real
  query list and that its status string lands in `findings.json`. B-007 was a
  fully-tested module that nothing called; a green test on `serp_findings` alone
  would have proved the same nothing here.

  `acceptance_check` needed no change — its guard is an allowlist
  (`code.startswith("health.")`), so `serp.*` codes are already refused as
  unverifiable against a build directory.

  **Not implemented, deliberately:** SERP-feature findings (AI overview,
  featured snippet, local pack). Only `organic[]` with
  `rank`/`global_rank`/`link`/`title`/`description` is confirmed in Bright Data's
  public docs; the feature field names are not. Capture a real payload on the
  first live run and add them against the observed shape rather than a guessed
  one.

- **An SEO score and an AEO score, and a graph of them per cycle**
  (`pipeline/lib/score.py`). Nothing in the codebase scored anything before; the
  operator could see a finding count and nothing else.

  It is a **pass rate over (page, check) pairs** — a check either fires on a page
  or it does not:

  ```
  score = 100 × (1 − failing_pairs / total_pairs)
  total_pairs   = urls_checked × (codes in this family that actually ran)
  failing_pairs = distinct (location, code) pairs in findings.json
  ```

  Three properties, each of which a simpler formula loses. **One page cannot be
  counted many times:** B-009 emitted 1158 `img_alt_missing` findings from one page
  and one broken regex — 91% of that run — and a per-pair score charges it one
  pair. **A check that never ran cannot inflate it:** the four config-gated checks
  leave the *denominator* and are listed under the number as `not scored`, because
  scoring an unmeasured check as a pass is the "green means not measured" lie the
  whole rail is built against. **Unmeasured is not 100:** `urls_checked == 0`
  returns `None`, and every caller renders it as "not measured".

  Weighted severity was considered and rejected: the weights would be invented
  here and every weight becomes an argument later. A pass rate is a fact about
  what was measured.

  The chart (`static/chart.js`, inline SVG, no dependency) draws three visually
  distinct states so a claim can never render as a measurement: solid for measured
  cycles, dashed to a hollow marker for the score this cycle's changelog *claims*
  it will reach, and a verification chip only when `acceptance_check` can actually
  run. Its two hues are the dashboard's own primary/tertiary ramps stepped into
  the dark-mode mark band and validated with the dataviz six-check validator
  against surface `#0b1326` — lightness, chroma, CVD separation (worst adjacent
  ΔE 24.6 under deuteranopia), normal-vision floor (28.4) and contrast all pass.
  `tests/test_score.py` (24 tests).

- **The client screen says which of eight stages a client is on, and offers one
  next action.** The complaint was that the console is confusing; the cause was
  that nine nav items each showed an artifact and no screen showed the sequence.
  `next_action()` derives the stage from files already on disk — the console still
  holds no state — and marks the three human gates as gates whether or not you are
  standing on one. The fleet card carries the same thing, so the fleet view answers
  "who needs me" without a click.
  `tests/test_dashboard.py::test_a_config_with_todos_is_the_interview_gate` and
  seven siblings, one per stage.

- **`site-health` chains into `site-plan`.** A measured cycle with no lanes is the
  one genuinely useless state in the rail — the fleet card had to render it as the
  words "not planned" — and nobody has ever wanted to stop there. Declared as
  `"then": "site-plan"` in `COMMANDS` rather than as a second orchestrator, fired
  on exit 0 or 1 only, and launched before `exit_code` is published so the chain
  cannot race the one-writer-per-checkout rule (B-012). Only a name already in
  `COMMANDS` can be chained, and `test_the_chain_is_acyclic_and_only_reaches_declared_commands`
  pins both properties.

- **GATE 2: a diff review screen** (`/review`). Per-item diffs from
  `changelog.json`, with **approving implemented as `git add`** — the git index IS
  the approval record. No approvals file, no server-side state: `git status` shows
  it, it survives a refresh and a restart, and there is nothing to drift out of
  sync with the tree.

  **Items that touched the same file are one approval unit.** Their diffs are not
  separable — you cannot approve one and reject the other when both edited
  `lib/page-meta.ts` — so the screen groups them transitively and says so, rather
  than offering a choice it cannot honour.

  Two refusals worth the code. **Every path is validated against that cycle's
  `changelog.json` file map**, which is the security boundary: without it
  `POST /review` is `git add` and `git restore` over any path a browser names,
  bound to a port. And **rejecting a create is refused** — `git restore` cannot
  revert one and the honest alternative (`git clean -f`) silently deletes a file,
  so it says so instead and leaves the file alone.

  Once nothing is pending the finish panel reveals commit → gate → push → **"Open
  a pull request?"**, in that order and no other. The order is the B-015 fix
  expressed as shape rather than as a sentence in the docs. No merge button.

  Driven end to end against a fixture client before shipping. Approving staged both
  files and flipped the unit to `approved`; `tier_check` then exited **17** on the
  T1 client's created file — proof that approval does not bypass the gates —
  and `claim-provenance` exited 0 on the real commit.
  `tests/test_dashboard.py::test_items_that_share_a_file_are_one_approval_unit`,
  `::test_a_path_outside_the_changelog_is_refused`,
  `::test_rejecting_a_new_file_is_refused_rather_than_deleting_it`, and 12 more.

- **`wf-render-snapshot` — a render source, so a client with no static export can
  be gated at all** (v3 sharp edge #4). Nine gates read `<BUILD_DIR>/**/*.html`:
  `acceptance_check`, `em_dash_check`, `check_headings`, `capsule_check`,
  `noncommodity_check`, `fingerprint_check`, `forbidden_sweep`, `orphan_check`,
  `parity_check`. `lee-series-web` is `nextjs-16-app-router` with no
  `output: 'export'`, so `./out` never exists, `build-site` exits 1, and **all nine
  were skipped** — including `forbidden_sweep`, which is `NEVER_BASELINEABLE` for
  legal exposure.

  Rather than teach nine gates a second way to find a page, this **crawls a
  rendered deployment into the tree they already glob** — `<route>/index.html`,
  plus `sitemap.xml` / `robots.txt` / `llms.txt`, which `parity_check` and
  `robots_aicrawler_check` read and a crawl has to ask for by name.
  `quality-gate.reusable.yml` says every OUT gate is deliberately FRAMEWORK-BLIND
  ("it scans whatever BUILD_DIR points at") and this keeps that true.

  It **exits 19 and writes nothing** when no page answered: an empty `--out` would
  let all nine gates glob zero files and report PASS, which is worse than not
  running them. The sitemap is read from the LIVE domain while pages are fetched
  from the candidate, so a PR that dropped a route cannot also drop it from the set
  of routes being judged.

  The fifteen OUT steps now key on `steps.tree.outputs.ready` instead of
  `steps.build.outcome`, because a crawled tree is not a successful build — wiring
  the crawl without rewiring the guards would have produced the tree and then
  skipped every gate that reads it.

  Proven against a local HTTP server standing in for a deployment: 3 routes +
  `sitemap.xml` captured, then `em_dash_check` found both legacy em dashes,
  `check_headings` scanned 3 files and passed, and `parity_check` reported
  `sitemap=3 built-routes=3` / `PASS: sitemap == built routes` — on a client with
  no static export, where none of the three could previously run.
  `tests/test_snapshot.py` (13 tests) + `tests/test_ratchet_wiring.py`.
  **The CI wiring itself has not run against a live Cloudflare preview — see
  B-017.**

  Full suite for everything above:
  `.venv/bin/python -m pytest -q` → `564 passed in 4.87s`.

### Verified live

- **The Bright Data network path has been run against the live API** — the first
  provider in this repo for which that is true (`CLAUDE.md` sharp edge #6 still
  stands for CrUX, GSC and DataForSEO). Two request shapes were probed against a
  real SERP zone:

  ```
  {"zone":Z,"url":"…/search?q=…&brd_json=1","format":"raw"}      → organic[] present
  {"zone":Z,"url":"…/search?q=…","format":"json",
                                 "data_format":"parsed"}          → {body,headers,status_code}
  ```

  The second is **Bright Data's own generated sample** for the zone, and it is
  the wrong shape for this parser: it wraps the SERP in an HTTP envelope, so
  `parse_serp` would find no `organic`, return `[]`, and the run would report a
  clean site. The shipped `format:"raw"` + `brd_json=1` returns the parsed SERP
  directly. Anyone "fixing" our request to match the vendor snippet would
  silently break the provider — hence this note.

  The live payload also corrected a real defect. A #1 organic result returns:

  ```
  organic[0]  rank=1  global_rank=4
  ```

  `global_rank` counts the ads and SERP features stacked above the result;
  `rank` is the organic position. The bands (`SERP_TOP_PAGE`,
  `SERP_REACHABLE_MAX`) are organic positions, so the original
  `global_rank`-first read would have fired `serp.page_two` at a site ranking
  **first** on any SERP carrying eleven features above it. Now `rank` wins and
  `global_rank` is the fallback — `test_organic_rank_beats_global_rank`.

  Confirmed field names on the live response: `organic[]` with `rank`,
  `global_rank`, `link`, `title`, `description`, `display_link`, `source`,
  `snippet_highlighted_words`, `icon`. Top-level keys also include `general`,
  `pagination`, `people_also_ask`, `popular_products`, `related` and
  `navigation` — the observed shape to build SERP-feature findings against, if
  those are ever added.

### Changed

- **Single-definition cleanup across the changes above**, after a review found nine
  copy-paste sites in them — each one annotated with a comment naming the file it
  was copied from, which is documentation of a defect rather than a rationale. This
  repo's contract is single-definition (`ARTIFACT_PATHS` is deliberately shared
  between two gates for exactly this reason), and the first pass applied that rule
  once and broke it eight more times.

  - `common.safe_path()` and `common.resolve_tier()` are now the only definitions of
    "a repo-relative path we will accept" and "T2 needs both content fields". They
    replaced three copies of the path regex (`bootstrap_config`, the onboard
    endpoint, `build_git_argv`) and two copies of the T2 refusal written in
    different words.
  - `score.CONFIG_GATED` is **derived** from `measure._CONFIG_GATED` rather than
    re-typing its four lambdas. measure decides what runs and score decides what
    counts; two copies agree until someone moves `nap.phone`, and then the score
    silently keeps scoring a check that no longer fires.
  - `state.has_todos()` calls `preflight.todo_paths()`. The rail's whole promise is
    that the stage it shows matches what the command will do, so a second definition
    of "unresolved TODO" is a rail that sends the operator to a button that refuses.
  - `app.js` gained `streamRun`, `runLine` and `cycleBranchName`. There were **four**
    identical EventSource blocks (runs, git, fleet, review) and only `page-runs.js`
    coloured its log lines — so a `[REFUSED]` on the diff review screen, where a
    refusal matters most, rendered in the same grey as everything else. Now one call
    site, and it returns the exit so the review screen can stop at the first red gate.
  - `em_dash_check` derives its rule names from the glyph lists instead of a parallel
    dict. Adding a form without touching the dict would have filed it as `"other"`,
    collapsing two rules into one fingerprint — in a gate that is now baselineable,
    that is a baseline entry accepting more than it was recorded for.
  - `bootstrap_config` uses `argparse`, like every other entry point in the package
    and like `onboard.py`, which declares these same three flags in three lines. The
    40-line hand parser existed only because the module's old style could not handle
    a flag that takes a value — which is a reason to stop matching that style.

- **`pipeline/dashboard/server.py` split at the two seams it already marked**, after
  this work pushed it past 1300 lines. `state.py` is what the console KNOWS (pure
  derivation from disk: discovery, git state, the cycle bundle, the score,
  `next_action`) and `review.py` is Gate 2 plus the git actions. `server.py` is back
  to what its docstring claims — the allow-list, the `Run` class and the HTTP
  handler — at 781 lines.

- **Fewer redundant git subprocesses.** `fleet_entry` read every artifact and then
  called `next_action`, which read all of them again plus `git_state` twice more and
  a third time inside `commits_to_judge` — about 20 sequential `git` spawns per
  client on `GET /api/clients`, for data the caller already had. `cycle_bundle()`
  reads once and is passed down. `review_units` likewise spawned one
  `git ls-files --error-unmatch` **per file** to re-derive the `??` its single
  `git status` already reported.

### Fixed

- **`blocked_by` on the stage rail is populated, not just declared.** It was
  hardcoded `None` on all eleven return paths, with a comment on the REMEDIATE
  branch asserting *"Read access is a fact to check, not assume"* — a comment
  describing intent as if it were behavior, on the line that did not have it. It now
  reports, before any money is spent, that a client has no gate baseline (so the
  gates will run bare and inherited debt reads as blocking) and that
  `acceptance_check` cannot run (so the fixes ship unverified). Both are exactly
  what happened to `lee-series-web`'s 2026-08 cycle, and both were discoverable on
  disk beforehand.

- **The PR summary says when the HTML came from a crawl.** `FAMILY=crawl` was
  written to `$GITHUB_ENV` and then overridden by a step-level `env:` that reads
  `steps.build.outputs.framework_family` — empty on a crawl client, because the
  build failed. So on precisely the SSR client the render source exists for, the
  summary rendered a blank framework and a blank build dir and never mentioned the
  crawl. `steps.tree.outputs.source` was computed for this and wired to nothing;
  the BUILD row now reads `**crawled** <url> -> <dir> (no static export)` with the
  snapshot step's own outcome. `snapshot.py` insists this distinction is
  load-bearing — a crawl of a deployment and a local build are not the same
  evidence — so the artifact that a human actually reads has to carry it.

- **The operator declares the client's tier at onboarding.** The ADD CLIENT panel
  offers T1 / T2 / T3 defaulting to **T1**, and `wf-onboard` / `wf-bootstrap-config`
  take `--tier`, `--content-location` and `--content-registry`. Raising a tier used
  to be a second manual act against the client repo after onboarding finished.

  **T2 is REFUSED without both content fields**, in all three places that could
  say so (the form, `build_onboard`, `tier_block`). T2 means "may CREATE under
  `content.location` and wire it into `content.registry`" — the rule is not new
  (`bootstrap_config.py` already carried `No content.location -> T2 is
  unavailable`), but it now fails loudly instead of writing a config that claims
  T2 and behaves as T1. A location with no registry is the worse half: the agent
  creates a page, nothing links to it, and `orphan_check` refuses the PR after the
  money is spent. T3 needs neither — it may change anything not denied.

  **This is not a relaxation of the tier model.** `docs/client-config.yml` stays on
  the deny floor at every tier including T3, so the *agent* still can never raise
  its own authority; and the tier is written into a commit on the **default
  branch**, which is the human commit the model always required. What changed is
  *when* the human declares it, not whether one has to.
  `tests/test_tiering.py::test_t2_is_refused_without_a_content_location`,
  `::test_the_deny_floor_is_written_at_every_tier`,
  `tests/test_dashboard.py::test_t2_without_its_fields_is_refused_at_the_form_not_after_a_clone`,
  `tests/test_onboard.py::test_the_declared_tier_is_passed_to_bootstrap`.
  Full suite: `.venv/bin/python -m pytest -q` → `467 passed in 3.50s`.

  `CLAUDE.md`'s tiering section is updated in this commit: it asserted
  "`wf-bootstrap-config` writes `tier: 1`. T2 and T3 exist in the code but are
  unreachable for a client until a human raises that tier in a human PR." The
  enforcement is unchanged; the sentence describing it was no longer true.

### Fixed

- **`em_dash_check` is baselineable, so a legacy client's PRs are no longer
  permanently red (B-008).** It was in neither `BASELINEABLE` nor
  `NEVER_BASELINEABLE`, so `assert_baselineable` refused it as "not in the
  allow-list" — one em dash in a client's inherited copy blocked every PR forever,
  with no recording that could accept it.

  **The call, which is what B-008 was waiting for:** an em dash in pre-existing copy
  is legacy *content* debt, structurally identical to a heading that is not in Title
  Case — and `check_headings` was already baselineable. `NEVER_BASELINEABLE` is for
  live falsehoods (an invented credential, a fix that never landed) and structural
  invariants (sitemap parity, an orphaned route); a legacy em dash is neither.
  `gate-reference.md` had already diagnosed it: that third category existed
  "because on the pilot they were already clean. That is a property of the pilot,
  not of the gates."

  Three parts, because the registry entry alone does nothing (B-007 — *implemented
  is not wired*): the gate emits `Finding`s instead of printing tuples (the only
  reason it was never wired — the ratchet needs fingerprints), `gate_argv` learned
  to invoke it, and the workflow passes the baseline arg. **That last one was caught
  by an existing test**, `test_every_baselineable_gate_receives_the_baseline`, which
  went red the moment the gate joined the set. Fingerprint is the offending TEXT
  with the line number in `detail`, so an unrelated edit above a legacy em dash does
  not turn it into a new finding.

  ```
  $ wf-gate-baseline --project ./scratch/ssrclient --out docs/gate-baseline.json
    total entries: 2
      em_dash_check          2
  $ wf-em-dash-check --out ./out --baseline docs/gate-baseline.json
    em_dash_check: 2 pre-existing (ignored), 0 new (blocking)
  PASS: no new em dashes (2 pre-existing accepted as legacy debt).     exit=0

  # then a third em dash, in copy we wrote:
    services/index.html: line 2: [—] …Repair and replacement — fast, clean…
    em_dash_check: 2 pre-existing (ignored), 1 new (blocking)
  FAIL: 1 NEW em dash(es) in public text across 1 file(s).             exit=1
  ```

- **`wf-preflight` no longer stops every new client before the interview (B-010).**
  It required a top-level `industry` that nothing in `pipeline/` ever wrote —
  `bootstrap_config` emits the same fact as `business.trade` — so the very first
  `wf-onboard` on any client exited **11** ("missing required fields") instead of
  the documented **12** ("has TODOs, this is the interview"). `industry` is out of
  `required` and the summary line reads `business.trade`. One fact, one place; the
  rejected alternative (emit `industry: TODO`) reaches the same exit while keeping
  two names for one thing.

  ```
  $ cat docs/client-config.yml     # a fresh bootstrap, business.trade: "TODO"
  $ wf-preflight ./scratch/b010
  [STOP] Config has unresolved TODOs: ['.business.trade']
  exit=12
  ```

- **`wf-onboard` commits the scaffold it writes (B-014).** Six paths
  (`docs/client-config.yml` + five scaffolded docs) are creates that `tier_check`
  refuses at every tier — `client-config.yml` deliberately so — and nothing in the
  pipeline ever committed them, so the operator met the deny floor as **exit 17**
  on their first PR instead of as an instruction. `commit_scaffold` now lands them
  on the default branch under four constraints, which are what make a tool
  committing on your behalf something other than a surprise: **named pathspec
  only** (never `git add -A`), **refuses off the default branch** (committing these
  on a cycle branch IS the bug), **refuses when a scaffold path is tracked and
  modified** (that is the operator resolving the interview TODOs, not our
  scaffold), and **never pushes**.

  Found while testing: `_git_out` called `.strip()`, which eats the leading space
  of ` M path` in `git status --porcelain` and turned a human's unstaged edit into
  a staged one — so their uncommitted work read as ours to commit. `_git_status`
  reads those lines unstripped, because column 1 is the index and column 2 is the
  worktree and they are not interchangeable.
  `tests/test_onboard.py::test_the_scaffold_commit_takes_nothing_it_did_not_write`,
  `::test_the_scaffold_is_never_committed_on_a_cycle_branch`,
  `::test_a_humans_edit_to_a_scaffold_path_is_not_committed_for_them`,
  `::test_a_second_onboarding_does_not_fail_on_the_first_ones_commit`.

- **A capped `wf-site-remediate` run now resumes, and no longer destroys the first
  run's record (B-013).** The module docstring promised "the remaining items keep
  their place in the worklist for the next run" and `CLAUDE.md` repeated it;
  neither was true. `selectable()` rebuilt the queue from `worklist.json` alone, so
  run two re-attempted the same first N items, while `main` wrote
  `changelog.json` wholesale, so run two's record replaced run one's — the
  reviewed evidence for the items that were actually fixed was gone.

  `selectable()` now skips items the cycle's changelog records as `fixed`, and the
  changelog is **merged**: prior entries survive, a fresh attempt of the same id
  replaces its own earlier entry, `cost_usd` and `runs` accumulate. A `--dry-run`
  merges nothing — it wrote no code, so it must not touch the record of runs that
  did. An unparseable changelog is a named WARN, not a silent full redo.

  **On the authority question that kept this open:** the changelog now decides what
  gets *attempted*. It decides nothing about what is *verified* —
  `acceptance_check` re-measures every claimed fix against the build output and
  refuses if the finding is still there. A changelog entry that lies about a fix
  costs one item's budget and is then caught by the gate.

  `_base` also carries `finding_fp` now. It is the only exact link from a fixed
  item back to the finding it fixed; matching on `(url, code)` instead is ambiguous
  the moment one page carries two findings of one code, which is the common case
  (`img_alt_missing`), not the exotic one.
  `tests/test_remediate.py::test_a_rerun_skips_what_the_changelog_records_as_fixed`,
  `::test_the_second_run_merges_rather_than_destroying_the_first`,
  `::test_a_dry_run_never_touches_the_record_of_runs_that_wrote`,
  `::test_a_status_other_than_fixed_is_retried`.

- **`claim_provenance_check` no longer refuses every client's first PR (B-016).**
  `.md` is in `TEXT_SUFFIXES`, so the gate read `docs/audit/<cycle>/report.md` —
  which `wf-site-plan` generates — as client copy, and `SUPERLATIVE_RE` caught its
  own sentence `- Compared Against: nothing — this is the first cycle`. That is
  exit 18 on every client whose cycle has no prior to ratchet against, i.e. every
  first PR, forever. It blocked `lee-series-web` PR #34.

  `prose_from` skips `ARTIFACT_PATHS`, **imported from `lib/common`** — the same
  list `tier_verdict` already classifies as `cycle artifact`. The defect was not
  the word "first"; it was two gates disagreeing about what `docs/audit/**` is, so
  the fix is one shared definition rather than a second glob that drifts.
  Rewording `plan.py` would have fixed one sentence and left the class of bug.

  Proven against the real gate on a scratch repo carrying that exact line:

  ```
  $ wf-claim-provenance-check --project ./scratch/b016
  [CORPUS] 4 words from: docs/client-config.yml
  [OK] claim-provenance: every claim in 1 changed file(s) resolves to a source.
  exit=0
  ```

  Negative control, same repo, one page of real client copy added — the gate is
  narrowed, not disarmed:

  ```
  [UNSOURCED] src/content/about.mdx: '4.2 star' (rating) — '4.2' appears in no config field…
  [UNSOURCED] src/content/about.mdx: 'first' (superlative) — 'first' appears in no config field…
  [BLOCKED] 2 unsourced claim(s).
  exit=18
  ```

- **The console refuses to run a gate that would judge an empty diff (B-015).**
  `tier-check` and `claim-provenance` diff `origin/<default>...HEAD` — the
  **three-dot** form, which compares commits and is blind to the working tree. Run
  either on a dirty checkout with no cycle commit and the diff is empty, both exit
  0, and the console printed `Clean — every check passed` over work they never
  looked at. That is precisely the failure the exit vocabulary exists to prevent.

  Both now carry `needs_commit`, and `_start_run` refuses with **409** and the
  reason when `commits_to_judge` is 0. The gates themselves are untouched:
  `--base HEAD` would make them judge the working tree and diverge from what CI
  runs, and a gate that means something different locally is worse than one that
  occasionally refuses. "Cannot tell" (no remote-tracking ref) lets the gate run
  and speak for itself — reading it as "nothing to judge" would refuse every
  local-only checkout.
  `tests/test_dashboard.py::test_an_uncommitted_tree_has_nothing_for_those_gates_to_judge`,
  `::test_no_remote_ref_is_cannot_tell_not_nothing_to_judge`,
  `::test_only_the_three_dot_gates_carry_needs_commit`.

- **The dashboard refuses a second run against a client that already has one
  going (B-012).** `_launch` created a `Run` unconditionally, so clicking RUN
  twice started two `wf-site-remediate` processes in the same checkout — two
  Claude Code agents editing the same files, with the loser's edits overwritten
  and nothing said about it. Observed live on 2026-08-07 against
  `lee-series-web`: two remediate runs 18 minutes apart, the first producing
  706KB of agent output and dying without writing `changelog.json`.

  `busy_run(slug)` now returns the live run for that client and `_launch`
  refuses with **409** while holding `RUNS_LOCK` — check-and-insert under one
  lock, because `ThreadingHTTPServer` answers two POSTs at once and a bare
  check lets both through. Keyed on **slug**, not cwd: onboard's cwd is the
  shared clients dir, and one client's slow measure must not serialise the
  fleet.

  Scope, stated plainly: `RUNS` is per-process, so this covers the console and
  **not** a `./run.sh wf-site-remediate` in a terminal. A lockfile in
  `remediate.py` is the upgrade if that path bites.
  `tests/test_dashboard.py::test_a_live_run_makes_that_client_busy`,
  `::test_a_finished_run_does_not_block_the_next_one`,
  `::test_another_clients_run_does_not_block`.
  Full suite: `.venv/bin/python -m pytest -q` → `419 passed in 2.65s`.

### Changed

- **The run console opens on `site-remediate`.** The dropdown selected whatever
  `COMMANDS` happened to list first (`site-health`), and an operator arriving
  from the Client screen's RUN button is nearly always there to remediate. The
  arguments pane still renders empty and RUN is still a click, so the
  destructive default costs a keystroke, not a safety property — `--dry-run`
  and `--max-items` are one click away in the same pane.

- **The dashboard's Git page stages the remediator's code edits, not just the
  audit JSON (B-011).** `stage-audit` ran `git add docs/audit` and `commit` runs
  `git commit -m <msg>` — no `-a`, no pathspec — so an operator who did the whole
  branch → stage → commit → push → PR sequence in the dashboard opened a PR
  carrying `changelog.json` claiming N fixes and none of the fixed files. The
  action is now `stage-all` → `git add -A`, and the button reads
  `STAGE ALL CHANGES`. It is not a second button beside the old one: two
  near-identical staging buttons is the same footgun with a longer name.
  Staging everything is safe because it is not the last word — `tier_check`
  judges the whole PR diff, so an out-of-tier file fails the gate rather than
  reaching production.

  Reproduced first, in a scratch repo holding one edited `src/page.tsx` and one
  `docs/audit/2026-08/changelog.json`. Old sequence:

  ```
  $ git add docs/audit && git commit -qm "audit: acme cycle artifacts"
  $ git show --stat --name-only --format="" HEAD
  docs/audit/2026-08/changelog.json
  $ git status --porcelain
   M src/page.tsx                     # the fix, left behind
  ```

  With `git add -A` the same commit carries `src/page.tsx` and `git status
  --porcelain` comes back empty.
  `tests/test_dashboard.py::test_staging_covers_the_remediators_code_edits_not_just_the_audit_json`.
  Full suite: `.venv/bin/python -m pytest -q` → `415 passed in 2.69s`.

- **`wf-site-remediate` streams Claude's live output instead of a blank pane.**
  `run_agent` used `subprocess.run(..., capture_output=True)` with
  `--output-format json`, so the dashboard (and any piped terminal) showed
  `RUNNING..` with an empty log until each item finished — often minutes. Now
  it runs Claude with `--output-format stream-json --verbose`, tees every
  NDJSON event to stdout as it arrives (`flush=True` + line-buffered stdout),
  and still parses the final `type: result` event for cost / note. Item banners
  print before the agent starts, dry-run included.
  `tests/test_remediate.py::test_the_prompt_goes_on_stdin_not_argv` (Popen stub,
  asserts stream-json + live tee) and `::test_a_streamed_error_result_is_not_ok`.
  Verified: `.venv/bin/pytest -q tests/test_remediate.py` → `19 passed in 0.76s`.
  Full suite before push: `.venv/bin/pytest -q` → `414 passed in 2.78s`.

- **`wf-onboard` puts its own `sys.executable` bindir on PATH before shelling out.**
  Invoking `.venv/bin/wf-onboard` without activating the venv meant the first
  step died with `FileNotFoundError: 'wf-bootstrap-config'` — the console
  scripts live next to the interpreter, not on the ambient PATH. `run()` now
  prepends that directory so every `wf-*` child resolves.

- **`health.img_alt_missing` no longer fires on `alt=""` (B-009).** The test was
  `re.search(r'\salt="[^"]+"', img)`, which an EMPTY alt fails — so every
  decorative image marked the way WCAG asks for was reported as a defect. First
  live run against `www.leeserie.com` (a Webflow-exported Next.js site):
  **1158 of 1272 findings**, 91% of the report, all false. Verified against the
  live homepage before changing anything: 76 `<img>`, 38 with real alt text, 38
  with `alt=""`, **zero with no alt attribute at all**. Now only an absent
  `alt=` is a finding. Re-measured after the fix: `26 URLs measured, 114
  findings`.

  `tests/test_measure.py::test_decorative_alt_is_not_a_missing_alt` — a page
  with one decorative image, one described image and one genuinely missing alt
  yields exactly the last one. Full suite `413 passed in 2.59s`.

### Added

- **`wf-site-health` warns when one code owns half a run.** B-009 was invisible
  in the output: the run printed `1272 findings` and nothing said that 91% of
  them came from a single check. `warn_dominant_code` prints a `[WARN]` naming
  the code and its share whenever one code is ≥50% of a run of 20 or more. It
  does not judge the check and it does not suppress anything — it refuses to let
  one code hide inside a total. Tests: `::test_a_dominant_code_is_warned_about`,
  `::test_a_mixed_run_is_not_warned_about`.

- **`wf-dashboard` findings: group headers are now collapsible.** GROUP BY CODE
  and GROUP BY URL rendered every row under every header, so a real cycle opened
  as a 1272-row scroll with the second code below the fold. Headers now collapse
  by default and carry a chevron, a preview of the first finding in the bucket
  and the count, so the whole shape of a site is 8 rows. A group filtered down
  to one bucket auto-expands, since choosing it is the same as opening it.

### Changed

- **`wf-dashboard` fleet: cards carry their own border.** The grid used
  `bg-outline-variant` + `gap-gutter` to fake hairlines between cards, which
  only looks right when the columns are full — one client in a 3-column grid
  rendered as a card next to a large grey slab. The container background is
  gone and each card has `border border-outline-variant rounded-sm`.

- **`run.sh` — one entry point for running any engine command in the
  container.** `./run.sh wf-onboard acme/site acme.com`, `./run.sh
  wf-site-health --project /clients/site`, `./run.sh bash`. It exists because
  three credential facts are easy to get wrong one at a time:

  - **`GH_TOKEN`, not the `-v ~/.config/gh` mount the Dockerfile documents.** On
    macOS the `gh` token lives in the login keyring, so that mount carries the
    config and no credential, and every `gh` call inside the container 401s.
  - **`GH_TOKEN` authenticates `gh` but not plain `git`**, so a clean
    `wf-site-remediate` would still fail on the push. `GIT_CONFIG_COUNT=1` +
    `credential.https://github.com.helper=!gh auth git-credential` hands git the
    same token.
  - **`remediate.py` only shells out to `claude`; it never reads
    `ANTHROPIC_API_KEY`.** So either auth works — a key in the environment, or a
    subscription login persisted in `~/.claude-docker`. The script warns when
    neither is present rather than letting the remediation step discover it.

  `wf-dashboard` is the only command that needs a port, so the publish is
  conditional on it: `-p 127.0.0.1:8765:8765` plus `--host 0.0.0.0`. The bind
  address is the CONTAINER's interface; the exposure on the operator's machine
  stays host loopback only, behind the per-run token.

- **`wf-dashboard`: Add Client on the fleet screen.** Repo, live domain and an
  optional GitHub token in three boxes, `POST /api/onboard`, and `wf-onboard`
  streams into the panel. It is the one run with no client to attach to, so it
  is a route of its own rather than a `COMMANDS` entry — every entry there is
  per-project and gets offered on the run console, where this one has no
  `{project}` to resolve.

  Both fields are normalised to the shape `wf-onboard` documents, because an
  operator pastes the browser URL, not an `owner/name` slug. The domain goes
  through `urlparse().hostname` rather than a hand-rolled scheme-stripper, which
  is both shorter and accepts the port and path a real clipboard carries:

  ```
  https://github.com/acme/roofing-site.git      → acme/roofing-site
  http://AcmeRoofing.com:8080/index.html?utm=x  → acmeroofing.com
  ```

  A repo path segment must **start alphanumeric and contain no `..`** — the same
  two rules `build_git_argv` applies to a branch name. A leading `-` is read by
  argparse as a flag, and `..` escapes `--clients-dir` *without cloning
  anything*: `onboard.py` names the checkout `slug.split("/")[-1]`, so
  `owner/..` resolves to the PARENT of the clients directory, finds it already
  exists, skips the clone and scaffolds client docs into it.

  ```
  {"repo": "owner/.."}        → 400 "repo must be owner/name or a GitHub URL"
  {"repo": "--clients-dir/x"} → 400  (a bare "--clients-dir" fails the shape check
                                      for lack of a slash, which is NOT the same
                                      invariant — the test asserts the dash case)
  ```

  **The token goes to the environment and nowhere else.** argv is written to
  `~/.cache/seo_agent/runs/<id>.log`, listed in the run history and streamed to
  the browser, so a credential there is a credential on disk. `Run` gained an
  `env` parameter; the token rides as `GH_TOKEN`/`GITHUB_TOKEN` for that one
  subprocess, the browser clears the field on submit, and nothing persists it —
  re-enter it next time. Verified against a real run:

  ```
  $ cat ~/.cache/seo_agent/runs/19fd6361cef-02b5e1.log
  $ wf-onboard nobody-here-9x/nope example.com --clients-dir /…/clients
  HTTP 401: Bad credentials (https://api.github.com/graphql)
  [ERROR] could not clone nobody-here-9x/nope — check the collaborator invite was accepted
  $ grep -rl "ghp_aaa" ~/.cache/seo_agent/runs/
  $ echo $?
  1
  ```

  **What that 401 proves, and what it does not.** It proves the token reached
  `gh` and was used against the API — without it, that run reports "Try
  authenticating with: gh auth login" instead. It does **not** prove a *private*
  repo clones on `GH_TOKEN` alone, because the git transport goes through the
  credential helper, not the variable. **That path is unverified** and is
  recorded here as unverified for the same reason the phase 6 provider network
  paths are. Related: `onboard.py` falls back to `git clone git@github.com:…`
  when `gh` is not on PATH, and `GH_TOKEN` means nothing to SSH — in that one
  configuration the operator supplies a credential that is silently unused.

  The browser reads the token field and clears it **before** the request, not
  after: clearing on the success path only left it in a live DOM node on every
  400, which is the likely path (mistype the repo). The input is
  `autocomplete="new-password"`, not `off` — Chrome and Safari ignore `off` on a
  password input and will offer to save the value to the keychain, which is the
  opposite of "never stored".

  `wf-onboard`'s exit vocabulary is its own, so `interpret_exit` gained a table
  for it. **Exit 1 is the interview step, not a failure**: it means bootstrap
  wrote TODOs a human must fill and the same command resumes from there. The
  rail reads 1 as "findings written" and git reads it as "the run failed" —
  both would be a lie here, so it renders as a warn chip that says to edit
  `docs/client-config.yml` and run it again, and the panel and its log stay open
  on exit rather than collapsing the instructions.

  Covered by 22 new cases in `tests/test_dashboard.py` (URL normalisation, the
  leading-dash and `..` refusals, the escape-the-clients-dir case with the
  `Path` arithmetic that makes it real, token-never-in-argv, exit-1 semantics).
  `test_every_command_states_which_exit_vocabulary_it_speaks` now asserts
  `ONBOARD_EXITS` too, so the one command outside `COMMANDS` is not the one
  command that invariant cannot see.

  ```
  $ .venv/bin/python -m pytest -q
  410 passed in 2.63s
  ```

### Changed

- **`wf-dashboard --host`, and the Origin check that made it useless.** The
  container has to bind `0.0.0.0` — `docker -p` reaches the container's external
  interface, not its loopback — so the flag exists. But `_authorized` compared
  `Origin` against a set hardcoded to `http://127.0.0.1:<port>`, and browsers
  send `Origin` on every same-origin POST. Reaching that dashboard by any other
  address 403'd **every** action while the pages still rendered: a console that
  looks fine and cannot do anything.

  `Origin` is now compared to the request's own `Host` header, which is the
  same-origin test and needs no list at all — the hardcoded set is deleted, not
  extended. A forged Origin still fails: the browser sets `Host` to whatever it
  connected to, and an attacker's page cannot make the two agree.

  ```
  $ # server bound 0.0.0.0, reached over the LAN address
  $ curl -o /dev/null -w '%{http_code}\n' -H "X-Dashboard-Token: $T" \
      -H "Origin: http://192.168.1.46:8797" -d '…' http://192.168.1.46:8797/api/onboard
  202                       # was 403 before this change
  $ curl … -H "Origin: http://evil.com" http://127.0.0.1:8797/api/onboard
  403                       # still refused
  $ curl … (no token) http://127.0.0.1:8797/api/onboard
  403
  ```

  The startup banner also printed `http://127.0.0.1:<port>` unconditionally.
  `0.0.0.0` is a bind address, not a URL, so it now prints the address you can
  actually browse to and names the bind separately:

  ```
  $ wf-dashboard --host 0.0.0.0 --port 8798
  wf-dashboard  http://127.0.0.1:8798   (bound 0.0.0.0)
  ```

- **`Dockerfile`: `pip install -e .`, deliberately.** A regular install copies
  only what package-data declares, and two things resolve through
  `Path(__file__)` from the source tree: the dashboard's `static/*.html` and
  `skills/site-remediation/SKILL.md`. Without `-e` the dashboard 404s every page
  and remediate silently drops the doctrine — `if SKILL.is_file()` skips, it
  does not fail, which is the worst of the two. The source is already in the
  image via `COPY . /engine`.

- **`docs/ADMIN-CHECKLIST.md` rewritten against the code.** Four of its eight
  rows were secrets for the intake rail v3 deleted — `DISCORD_BOT_TOKEN`,
  `DRIVE_*`, `PIPELINE_DRIVE_PARENT_FOLDER_ID`, `CLIENT_REPOS_TOKEN` — and
  nothing outside `docs/` has referenced any of them since:

  ```
  $ grep -rln "DISCORD_BOT_TOKEN\|DRIVE_\|CLIENT_REPOS_TOKEN" \
      --include="*.yml" --include="*.py" --include="*.sh" .
  $ echo $?
  1
  ```

  Worse, it omitted `PIPELINE_REPO_TOKEN`, the one secret whose absence stops
  every gate on every client repo from starting: the thin caller's second
  checkout reads this private repo, and a client repo's `GITHUB_TOKEN` cannot.
  It was written down only in `CLAUDE.md` §"Known Sharp Edges" and the
  workflows' own `secrets:` blocks, so a human working the checklist would not
  have found it. The new file lists each secret against the workflows that
  consume it (verified by grepping `.github/`), the per-client one-time setup
  including the gate-baseline and static-export preconditions, the operator's
  `ANTHROPIC_API_KEY`, the three optional measurement credentials that return
  named skips, and a closing section naming the dead secrets so nobody mints
  them again. Docs-only.

### Fixed

- **`bootstrap-local.sh` could not complete on a clean machine.** Its verify
  loop checked five commands that v3 deleted with the DOCX rail —
  `wf-distill`, `wf-classify`, `wf-emit-ts`, `wf-preflight-docx`,
  `wf-cycle-status` — so the script installed the engine correctly and then
  killed itself on the line after, under `set -e`:

  ```
  ── verify engine commands ──
  FATAL: wf-distill not on PATH after install
  ```

  It also `FATAL`ed on a missing `pandoc`, which nothing in v3 uses
  (`grep -rn pandoc --include=*.py --include=*.yml --include=Dockerfile .`
  returns nothing), and copied a `distiller/` skill directory that no longer
  exists in the repo, so the run always ended with a `WARN` about it. Verify
  loop now names one command per stage of the live rail; the `pandoc` gate is
  replaced by a `claude` check, which is what
  `pipeline/audit/remediate.py:362` actually requires; the distiller block is
  gone. Full run on a machine with no existing venv:

  ```
  $ bash bootstrap-local.sh
  ── checks ──
  gh: authed
  claude: on PATH
  ── engine venv ──
  using: /opt/homebrew/bin/python3.11
  ── verify engine commands ──
  engine commands: OK

  READY. Activate with:  source /Users/ethan/.wf-pipeline-venv/bin/activate
  ```

- **`wf-dashboard`: picking a cycle was silently dropped the moment you changed
  screen.** Five selects (Client, Findings, Worklist, Report, Changelog) changed
  what was rendered without touching the URL, and the sidebar builds every link
  from `location.search` once at page load. Choose 2026-07 on Worklist, click
  Changelog, land on 2026-08 — with nothing to indicate the choice had been
  thrown away. `setCycle()` now writes the selection back with `replaceState`
  and re-points the nav; `cycleScreen()` in `app.js` replaces the three
  copy-pasted bootstraps that carried the defect. Verified in a browser: the
  Changelog link goes `/changelog?client=acme` → `/changelog?client=acme&cycle=2026-07`,
  and Fleet correctly stays parameter-free.

- **`wf-dashboard`: one malformed `gate-baseline.json` blanked the whole fleet.**
  `baseline_state` caught `JSONDecodeError` and `AttributeError`, so a file
  containing `{"entries": 5}` raised `TypeError` out of `/api/clients` and every
  client vanished from the console. `discover_clients` twenty lines above already
  states the rule — a client that will not load is returned WITH its error rather
  than dropped — and the new code did not honour it. Now `except Exception`, and
  the `BASELINE BAD` chip renders it.

  ```
  $ echo '{"entries": 5}' > acme-site/docs/gate-baseline.json
  $ curl -s -o /dev/null -w "%{http_code}" localhost:8793/api/clients
  200      # was: 500, fleet empty
  ```

- **`wf-site-remediate` exit 0 rendered as "Clean — every check passed".**
  `remediate.py:339` returns 0 when it fixed *nothing* — a `--dry-run`, or a run
  where every item errored. The rail's exit vocabulary was applied to it by
  default, so the console's most destructive command reported its emptiest
  outcome in green. Every entry in `COMMANDS` now declares `exits` (an empty
  dict being the deliberate statement "this speaks the rail's vocabulary"), and
  `test_every_command_states_which_exit_vocabulary_it_speaks` makes the silence
  impossible.

  ```
  $ POST /api/clients/acme/runs {"command":"site-remediate","args":{"cycle":"2026-08","dry-run":true}}
  exit: {'code': 0, 'kind': 'warn', 'text': 'Ran, fixed nothing — a dry run, or every item errored. Read the changelog'}
  ```

- **`gate-baseline` was one allow-list entry wearing two commands' exit codes.**
  Check mode reads; record mode WRITES the accepted-debt file into the client
  repo — and exit 1 and exit 2 mean different things in each. The single entry's
  table told an operator running `--check` against a client with *no baseline*
  (the exact state the new `NO BASELINE` chip exists to surface) that a baseline
  already existed. Worse, record mode was the flagless default: three unticked
  checkboxes and EXECUTE wrote to a client repo. Split into
  `gate-baseline-check` (no arguments at all — it cannot be made to write) and
  `gate-baseline-record`, each with an exit table that is true.

- **`wf-dashboard`: the Runs console could not run any command that takes a
  `--cycle`.** `renderArgs()` rendered exactly two widgets — a number input for
  `int` and a text input for everything else — and `collect()` split every
  non-`int` value on whitespace before sending it. So a `cycle` left as
  `["2026-08"]` and a `flag` left as `["true"]`, and the server refused both on
  arrival. Every phase 3-5 command was affected: `site-plan`, `site-remediate`,
  `claim-provenance`, `acceptance-check`. Four of the nine allow-listed commands
  were unreachable from the screen built to reach them.

  The widget is now chosen from the declared type — `cycle` is a `<select>` of
  the cycles that actually exist in the client repo, `flag` is a checkbox that
  sends `true` or nothing — and an undeclared type renders a visible refusal
  instead of falling through to the path-list input that caused this.

  ```
  $ curl -X POST .../api/clients/acme/runs -d '{"command":"site-plan","args":{"cycle":["2026-08"]}}'
  {"error": "cycle must be YYYY-MM"}            # what the old UI sent

  $ curl -X POST .../api/clients/acme/runs -d '{"command":"site-plan","args":{"cycle":"2026-08"}}'
  argv : ['wf-site-plan', '--project', '.../acme-site', '--cycle', '2026-08']
  exit : {'code': 1, 'kind': 'findings', 'text': 'Findings written'}
  out  : [OK] 1 new, 0 persisting, 0 regression, 0 resolved
  ```

- **Exit 1 read as success for git actions and for the ratchet.** `EXIT_MEANING`
  is global, and exit 1 means "it wrote what it found" for the rail commands. It
  means the opposite for `git pull --ff-only` (could not fast-forward) and for
  `wf-gate-baseline` (findings that are NOT in the baseline — regressions). Both
  rendered as a blue *Findings written* chip. `interpret_exit` now takes the
  command and overrides those two:

  ```
  $ POST /api/clients/acme/git {"action":"pull"}       # repo has no upstream
  exit: {'code': 1, 'kind': 'error', 'text': 'git/gh refused — read the output'}
  ```

- **The argv preview lied about `claim-provenance`.** It guessed `wf-<name>`;
  the binary is `wf-claim-provenance-check`. `/api/commands` now returns the
  real argv template and the preview renders that, so the line above the EXECUTE
  button is the command that runs.

- **Stale phase copy across four screens.** Worklist, Report, the Client
  artifact cards and the Fleet lane cell all said an artifact "ships in phase 3
  / phase 5". Phases 3 and 5 shipped: `wf-site-plan` and `wf-site-remediate` are
  in `pyproject.toml` and on the rail. An absent artifact now names the command
  that produces it, which is a thing an operator can act on.

### Added

- **`wf-dashboard`: a Changelog screen.** `wf-site-remediate` writes
  `docs/audit/<YYYY-MM>/changelog.json` — the agent's own record of what it
  touched — and the console had no view of it at all; the Client page listed the
  artifact with a `null` link. `/changelog` renders per-item status
  (`fixed` · `no_change` · `error` · `refused`), the file→item map, cost, model,
  and the `stopped` reason as a blocking banner. `queued` and `attempted` are
  shown separately and never summed: a run that attempted ten items and fixed
  none is not a quiet success.

- **`wf-dashboard`: the gate baseline is visible and recordable.** Sharp edge #1
  — a client with no `docs/gate-baseline.json` runs the gates BARE, so every
  piece of inherited debt reads as blocking on their first PR, and the CI
  workflow only warns. The fleet card now carries `NO BASELINE` / `BL <n>` /
  `BASELINE BAD` (present-but-unparseable is a third state, not a synonym for
  absent), and `gate-baseline` joins the command allow-list with its
  `--check` / `--refresh` / `--accept-new` flags.

- **`test_every_declared_argument_type_has_a_builder`** — walks every argument
  every command declares and asserts `build_argv` handles the type. The bug
  above existed because a type could be declared with nothing on either side
  knowing how to carry it.

- **`test_every_declared_argument_type_has_a_widget`** — the sibling that covers
  the half that actually broke. The server could always build `cycle` and
  `flag`; the *screen* could not ask for them. A grep of `page-runs.js`,
  deliberately: the type vocabulary lives in Python and in no-build-step JS, and
  sharing it means generating a constant — more machinery than a four-value enum
  is worth. Mutation-checked (rename the `cycle` branch, the test fails).

- **`wf-onboard` — a repo and a domain in, a worklist out.** Onboarding was six
  commands in a specific order, each with its own exit-code vocabulary, and the
  order lived in nobody's head but the operator's. `wf-onboard <repo> <domain>`
  runs them: clone → `wf-bootstrap-config` → `wf-preflight` → `wf-client-profile`
  → `wf-scaffold-client-docs` → `wf-site-health` → `wf-site-plan`.

  `repo` takes any form a client will actually send — a checkout path, an
  `owner/name` slug, or a git URL, `.git` and trailing slash included.

  - **The interview is a stop, not a failure.** `bootstrap_config` cannot invent
    a client's hours or licence number; it writes TODOs and `preflight` exits 12
    until a human replaces them. `wf-onboard` exits **1**, names the step in the
    imperative, and resumes from there on a re-run — every underlying step was
    already idempotent. Exit 3 is reserved for a checkout that genuinely failed,
    so the two cases a new operator will hit constantly are never confused.
  - **Access is checked, not assumed.** The flow this serves is "the client adds
    us as a collaborator", so step 2 asks `gh` for `viewerPermission` and prints
    it. READ is a **warning, not a stop** — measuring a repo you can only read
    still produces a report worth delivering — but it says out loud that no PR
    can ever be opened from this checkout. Finding that out at onboarding beats
    finding it out after a remediation run has spent money.
  - **A stop stops everything after it.** Tested per step: an onboarding that
    carries on past a failed preflight measures a site it was just told not to
    trust.
  - `wf-site-plan` exits 1 when it writes a worklist. That is the success case
    and `wf-onboard` reads it as one — treating it as a failure would stop every
    client that has findings, which is every client.
  - The static-export precondition (v3 §6) is reported inline from
    `detect_static_export`, because `orphan_check` and `parity_check` derive
    routes from the built HTML tree and report green when there is not one.

  ```
  $ .venv/bin/python -m pytest -q
  ........................................................................ [ 66%]
  ........................................................................ [ 88%]
  ......................................                                   [100%]
  326 passed in 2.41s

  $ wf-onboard . example.com --dry-run
  [ok] checkout: /Users/…/seo_ai
  [ok] access: ADMIN — we can open a PR
  [DRY RUN] would bootstrap, preflight, scaffold, measure and plan /Users/…/seo_ai

  $ wf-onboard /tmp/nope acme.com --skip-clone
  [ERROR] /Users/…/clients/nope does not exist and --skip-clone was given   exit=3

  $ wf-onboard "not a repo!" acme.com --skip-clone
  [ERROR] cannot read 'not a repo!' as a path, an owner/name slug, or a git URL
                                                                            exit=3
  ```

  `README.md` gains the onboarding quick start and loses its pre-v3 flow diagram
  (the DOCX rail, deleted in v3 §3) — the other half of the `SITE-AUDIT-PIPELINE.md`
  §10 doc debt. `HOW-IT-WORKS.md` still describes the old rail and is untouched.

  **Not verified:** the two `docker run` invocations added to `README.md` and the
  `Dockerfile` comment. The Docker daemon was not running on this box, so the
  image was never built and the mounts were never exercised. The flags are read
  off the CLIs they invoke, which are tested; the container path is not.

- **Phases 4 through 8 — the safety floor, the writer, and the external
  providers** (`SITE-AUDIT-PIPELINE.md` §4.1–4.3, §4.7, §5, §7). This closes the
  v3 build sequence: phases 1–3 measured a site and planned the work; these five
  let something act on the plan and prove that it did.

  **Phase 4 — three gates, and the reason they come before authorship.**
  Shipping agent writes against the previous 16 gates would have meant shipping
  unvalidated model claims to client sites.

  - `wf-tier-check` (exit **17**) walks the PR diff and refuses any path or
    operation the declared tier does not permit. **The deny floor applies at
    every tier, T3 included**, and is unioned in from `lib/common.DEFAULT_DENY`
    so a client config cannot shrink it — the agent can never edit the gates that
    judge it, and never raise its own tier. A rename is judged as a delete plus a
    create, because collapsing it to "modify" is exactly how a T1 agent would
    move a file out of its allow-list and keep editing it.
  - `wf-claim-provenance-check` (exit **18**, exit **4** on an empty corpus)
    refuses changed text carrying a factual claim — a rating, a review count, a
    licence number, a year-count, a warranty term, a superlative — that resolves
    to no config field, no work-item evidence, no citation, and **not to the
    previous version of the file**. That last source is what keeps the gate
    usable: without it, every reflowed paragraph would be reported as a fresh
    fabrication and the gate would get switched off. Scanning is narrow on
    purpose — prose in markdown, quoted string literals only in code — because a
    gate that flags `id: 4471` gets ignored.
  - `wf-acceptance-check` (exit **20**) re-runs each *claimed* fix's acceptance
    criterion against the build output and refuses when the finding still fires.
    It reuses `measure.check_page` verbatim; a second implementation of "what
    does a bad meta description look like" would drift from the one that produced
    the finding, and then the loop proves nothing. **Silence is not proof**: a
    claimed URL with no page in the build output, an unimplemented `check`, and a
    provider code that `check_page` could never emit all refuse rather than pass.
  - All three are in `NEVER_BASELINEABLE`. You cannot grandfather a fabricated
    credential, an out-of-tier edit, or a fix that never landed.
  - `quality-gate.reusable.yml` gains the three steps, their rows in the summary
    table and sticky comment, and their entries in the Evaluate registry. The
    client checkout moves to `fetch-depth: 0` — the two diff gates cannot judge a
    diff they cannot see, and a gate that cannot run must refuse (exit 2), not
    report an unexamined PR clean. **The gate count is 19 again**, which makes
    `README.md` correct for the first time since the v3 deletion.

  **Phase 5 — `wf-site-remediate`, the writer.** Reads `worklist.json`, hands
  each actionable item to Claude Code in the client checkout, writes
  `changelog.json` mapping every changed file to the item that changed it.

  - **One item per invocation.** Handing the whole worklist over in one prompt
    makes the file→item map something the model asserts; running one item at a
    time makes it a **measurement** — the files that changed between two
    `git status` snapshots are the files that item touched, whatever the model
    says. `changelog.json` is what `acceptance_check` re-measures, so it has to
    be an observation.
  - Every file the agent actually touched is judged by `lib/common.tier_verdict`
    — the *same* function `tier_check` runs on the PR — and an out-of-tier edit
    ends the run at exit 9 and is never recorded as fixed.
  - `--max-items` / `--max-files` are hard caps. Hitting one stops **cleanly**:
    what landed stays, `stopped` names what is left, and the remaining items keep
    their place for the next run. REGRESSION items are worked first, so a cap
    never cuts the lane that says a fix did not hold.
  - It does not commit, push, or open a PR. That path already exists with its
    "never push a default branch" guard in `pipeline/dashboard/server.py`, and a
    second copy of a safety guard is a guard that drifts. This is a deliberate
    deviation from §4.7's "the CLI commits and opens the PR".
  - `skills/site-remediation/SKILL.md` — the doctrine, inlined into every prompt,
    with the ported prose references reachable via `--add-dir`.
  - `Dockerfile` — 20 lines, the four tools v3 §5 names, no credentials baked in.

  **Phases 7 and 8 — T2 and T3 — ship in the same commit, and the staging is
  per client rather than per release.** `bootstrap_config` writes `tier: 1`, and
  `docs/client-config.yml` is on the deny floor, so an agent can never raise its
  own authority: T2 and T3 exist in the code but stay unreachable for a client
  until a human raises the tier in a human PR. That is a stronger guarantee than
  a release gate, and it is enforced rather than scheduled.

  **Phase 6 — `pipeline/audit/providers.py`**, wired into `wf-site-health`
  behind `--with-crux` / `--with-gsc` / `--with-dataforseo`, all off by default.
  One module and three functions, not a `providers/` package with an ABC — the
  abstraction waits for a second vendor in a category. Credentials come from the
  environment only. **A provider with no credentials returns a named skip, and
  the skip is written into `findings.json` under `providers`**: a provider that
  silently returned nothing would make a site look cleaner than last month, and
  the ratchet would report the difference as RESOLVED. Named `providers.py`
  rather than §5's `dataforseo.py`, because CrUX and GSC needed a home too.

  **Not verified, and named as such:** the DataForSEO network path has never run
  against the live API — it is written from the documented request/response
  shapes, and only the parser is covered by tests. Same for the GSC and CrUX HTTP
  calls. Treat the first real run as the verification and read the status string,
  not the finding count. Everything else below was run.

  ```
  $ .venv/bin/python -m pytest -q
  ........................................................................ [ 23%]
  ........................................................................ [ 46%]
  ........................................................................ [ 69%]
  ........................................................................ [ 92%]
  .......................                                                  [100%]
  311 passed in 2.36s

  # A REAL end-to-end run against a fixture client repo: plan -> agent -> gates.
  $ wf-site-remediate --project <fixture> --max-items 1 --model sonnet
  [FIXED] wi-2026-08-0001 health.desc_length on /roofing/ -> src/data/services.ts
  [OK] 1 fixed, 1 attempted of 1 queued, 1 file(s) changed, $0.4054 -> .../changelog.json

  $ git -C <fixture> --no-pager diff HEAD~1 -- src/data/services.ts
  -  description: "Roofing services.",
  +  description: "Professional roofing services in Charlotte, NC from a licensed
  +  contractor serving the area since 1998. Schedule your roof inspection today.",

  $ wf-tier-check --project <fixture> --base HEAD~1
  [ok] docs/audit/2026-08/changelog.json: cycle artifact
  [ok] src/data/services.ts: matches text_paths
  [OK] tier-check: 2 changed path(s), all within T1.                    exit=0

  $ wf-claim-provenance-check --project <fixture> --base HEAD~1
  [CORPUS] 16 words from: docs/client-config.yml, docs/audit/2026-08/worklist.json
  [OK] claim-provenance: every claim in 2 changed file(s) resolves to a source.
                                                                        exit=0
  $ wf-acceptance-check --project <fixture> --out <fixture>/out
  [ok] wi-2026-08-0001: health.desc_length is gone from /roofing/       exit=0
  ```

  The same three gates, probed with the failures they exist for:

  ```
  # an edit outside T1
  $ wf-tier-check --project <fixture> --base HEAD~1
  [REFUSED] src/components/Hero.tsx: create not permitted at T1 — it matches no
            text_paths glob.
  [BLOCKED] 1 of 3 changed path(s) exceed T1.                          exit=17

  # invented credentials in a copy edit ("since 1998" IS in trust_signals and passes)
  $ wf-claim-provenance-check --project <fixture> --base HEAD~1
  [UNSOURCED] src/data/services.ts: '4.9 stars' (rating) — '4.9' appears in no
              config field, no work-item evidence, and not in the previous
              version of this file.
  [UNSOURCED] src/data/services.ts: '1,200 reviews' (reviews) — …
  [UNSOURCED] src/data/services.ts: '28 years' (years) — …
  [BLOCKED] 3 unsourced claim(s).                                      exit=18

  # a fix the changelog claims but the build output disproves
  $ wf-acceptance-check --project <fixture> --out <fixture>/out
  [FAILED] wi-2026-08-0001: health.desc_length STILL FIRES on /roofing/ (len=5)
           — the fix did not land
  [BLOCKED] 1 of 1 claimed fix(es) did not clear the finding.          exit=20
  ```

  Four defects were found and fixed during the build; all four are in
  `docs/BUG-LEDGER.md` (B-003 … B-006). The one worth repeating here: the
  remediation prompt is a markdown document, and passing it as an argv positional
  made the CLI's option parser read its leading `---` as a malformed flag. Every
  hermetic test stubbed that function out, so **only the live run could find it**
  — the same lesson B-001 taught. The prompt now goes on stdin.

- **Phase 3 — the ratchet: four lanes, a typed worklist, and `report.md`**
  (`SITE-AUDIT-PIPELINE.md` §4.6, §7 phase 3). `wf-site-plan --project <dir>
  [--cycle YYYY-MM]` reads `docs/audit/<YYYY-MM>/findings.json`, compares it
  against the earlier monthly folders, and writes `worklist.json` + `report.md`
  beside it.

  - **The monthly folders ARE the time series** — there is no second baseline
    file and no second ratchet. Fingerprints come from `lib/baseline.py`
    unchanged, so a finding cannot become "new" merely by getting worse
    (`detail` is excluded from the fingerprint; a `len=71` that degrades to
    `len=210` stays PERSISTING).
  - **REGRESSION is the lane that earns the module.** Absent from the previous
    cycle but present in an earlier one means the fix did not hold. A naive
    "in last month? no → NEW" implementation loses exactly this signal, so it
    has its own test.
  - **The tier filter never drops a finding.** The report lists every finding;
    the worklist carries only what the tier permits, and the rest appear under
    *Not Actionable at T1* with the tier that would unlock them. No declared
    tier means no authority, so every item is reported blocked.
  - **A code with no acceptance mapping never enters the worklist.** `ACTIONS`
    maps each of the 18 `health.*` codes to a kind, a minimum tier, and an
    acceptance criterion; anything absent from it lands in the report under
    *Needs a Human*. Every acceptance is the same one check
    (`{"check": "code_absent", "code": …}`) so phase 4's `acceptance_check`
    implements one thing, not eighteen.
  - **Lanes are stamped back onto `findings.json`** — the dashboard's fleet view
    reads `findings[].lane`, and re-running the planner over an unchanged cycle
    is byte-identical rather than a noise diff (tested).
  - The dashboard gains a `site-plan` command in the allow-list with a new
    `cycle` argument type (`\d{4}-\d{2}`, nothing else). `build_argv` now
    **refuses** an argument type it has no branch for; it used to drop it
    silently, and a silently ignored argument is a run that did not do what the
    operator asked.

  ```
  $ .venv/bin/python -m pytest -q
  ........................................................................ [ 31%]
  ........................................................................ [ 62%]
  ........................................................................ [ 94%]
  .............                                                            [100%]
  229 passed in 1.86s

  $ wf-site-plan --project <fixture>      # 3 cycles: a fix that did not hold
  [REGRESSION] 1 finding(s) were fixed before and are back
  [OK] 2 new, 1 persisting, 1 regression, 0 resolved -> <fixture>/docs/audit/2026-08
       worklist: 2 actionable, 1 above tier, 1 needing a human
  $ echo $?
  1

  $ head -18 <fixture>/docs/audit/2026-08/report.md
  # Site Health Report: 2026-08

  - Domain: `acmeroofing.com`
  - Measured: 2026-08-05 (3 URLs checked, 0 unreachable)
  - Compared Against: 2026-07
  - Tier: T1

  ## Summary

  | Lane | Count |
  |---|---|
  | REGRESSION | 1 |
  | NEW | 2 |
  | PERSISTING | 1 |
  | RESOLVED | 0 |

  4 current findings. 2 in the worklist, 1 not actionable at T1, 1 needing a human.

  $ md5 -q docs/audit/2026-08/*.json docs/audit/2026-08/*.md   # before / after a re-run
  88baa0b52fb702678e3f55b0adb65b41  4393ac9bb8c16cff5c8b134c4225e26e  f0ced5d9de82646b68e0933edb71eeb2
  88baa0b52fb702678e3f55b0adb65b41  4393ac9bb8c16cff5c8b134c4225e26e  f0ced5d9de82646b68e0933edb71eeb2
  ```

  Exit codes: `0` no current findings · `1` worklist written · `2` nothing
  measured yet, or a `findings.json` that will not parse.

- **Phase 2 — tiering: a repo now declares what the agent may touch**
  (`SITE-AUDIT-PIPELINE.md` §2, §6, §7 phase 2). `wf-bootstrap-config` writes the
  tier block into the config it generates, and `wf-bootstrap-config <dir> <domain>
  --add-tier` **appends** it to a config that already exists — appending rather
  than round-tripping through PyYAML, because a 16KB starter file is mostly
  comments and `safe_load`/`dump` eats every one of them. `text_paths` is seeded
  only from directories that are actually on disk: a glob matching nothing is an
  allow-list that permits nothing, which reads as a working T1 that fixes zero
  findings.

  `client_profile()` parses the block (`tier`, `text_paths`, `content.*`, `deny`)
  and `validate_profile()` judges it:

  - **`deny` is a union with `DEFAULT_DENY`, never a replacement.** A client repo
    that omits or empties the key still cannot let the agent edit `.github/**` or
    raise its own tier. The floor is not a config option.
  - **An absent tier WARNs; an incoherent one is fatal.** `wf-client-profile`
    exits 5 on ERROR and runs inside `build-site/action.yml` for every client, so
    making the pre-phase-2 fleet's missing tier an ERROR would break five builds.
    Absent = no authority, which is the safe default. `tier: 2` with no
    `content.location` is ERROR — v3 §2 says T2 is unavailable without a declared
    content home, and the config must not be able to claim it anyway.
  - **The static-export precondition is checked, not assumed** (v3 §6).
    `detect_static_export()` reads `output: 'export'` out of a `next.config.*`,
    treats a Vite build as static only when the framework string says `ssg` (a
    plain SPA emits one `index.html`, not a route tree), and WARNs — with the
    reason spelled out — when a repo is SSR or cannot be confirmed. This is the
    condition under which `orphan_check` and `parity_check` scan nothing and
    report **green**, which is the failure mode worth naming out loud.

  `wf-client-profile` prints a tier section (tier, static export, `text_paths`,
  content home). The dashboard's config screen drops its "phase 2" placeholder
  copy; the tier block now exists, so an empty one is a real finding rather than
  an unbuilt feature.

  ```
  $ .venv/bin/python -m pytest -q
  ........................................................................ [ 33%]
  ........................................................................ [ 67%]
  ....................................................................     [100%]
  212 passed in 1.91s

  $ wf-bootstrap-config <fixture> acme.com --add-tier
  [OK] Appended the tier block to <fixture>/docs/client-config.yml (tier: 1)
  $ wf-client-profile <fixture>
    5. Tier         : T1   (static export: yes)
       text_paths   : src/data/**/*.ts
       content home : — (T2 unavailable)   registry: —

  $ sed -i '' 's/^tier: 1$/tier: 2/' <fixture>/docs/client-config.yml
  $ wf-client-profile <fixture>; echo "exit=$?"
    [ERROR] tier 2+ requires content.location — no declared content home means T2
            is unavailable and the agent does structural SEO only (v3 §2).
  exit=5
  ```

  Not built: `tier_check` itself. The declaration is what phase 2 ships; the gate
  that enforces it against a PR diff is phase 4, deliberately ahead of any agent
  authorship (v3 §7).


- **`wf-dashboard`** (`pipeline/dashboard/`) — a local operator console on
  `127.0.0.1`: a web UI over the artifacts client repos already hold. Python
  standard library only, no new dependencies, no build step, **no database**.
  Eight screens (fleet · client · findings · worklist · report · runs · git ·
  config); the four whose producers ship in later phases render an empty state
  naming the phase rather than a blank table. Design doc:
  `docs/superpowers/specs/2026-08-05-dashboard-design.md`.

  Clients are **discovered**, not configured: the server scans `--clients-dir`
  one level deep for git repos containing `docs/client-config.yml`, so adding a
  client is cloning it. A client whose YAML fails to parse is listed carrying its
  error rather than dropped — vanishing from the fleet view reads as "no problems
  here", which is the opposite of the truth.

  Three safety properties, all tested:

  - **Runs come from a fixed command allow-list.** `POST /api/runs` takes a
    command *name* mapped to an argv list; arguments are validated against a
    declared type before joining it. Nothing is ever joined into a shell string
    and `shell=True` is never used. Without this the dashboard is a remote shell
    bound to a port.
  - **A token plus an Origin check.** `127.0.0.1` is not a trust boundary — any
    page in the operator's browser can POST to localhost. The token is injected
    into the served HTML, which CORS stops a cross-origin page from reading.
  - **No merge, and no push from a default branch.** There is no merge action to
    call, so no frontend change can reintroduce one alone. Human merge stays the
    only path to production (`SITE-AUDIT-PIPELINE.md` §1).

  Exit codes render as sentences, not numbers: a run that exits 19 shows
  *"REFUSED — every source unreachable. Nothing was written"*. A green
  "completed" chip there would destroy the distinction exit 19 exists to protect.

  Verified end to end against fixture client repos: browser → allow-list →
  subprocess → SSE → exit 19 rendered as a refusal. 55 new tests in
  `tests/test_dashboard.py`, hermetic (no network, no bound socket, every client
  built under `tmp_path`).

  ```
  $ .venv/bin/pytest -q
  ........................................................................ [ 77%]
  ..........................................                               [100%]
  186 passed in 1.83s
  ```

- **`wf-site-health`** (`pipeline/audit/measure.py`) — measures a live site and
  writes `docs/audit/<YYYY-MM>/findings.json` in the client repo as typed
  `lib/baseline.py` `Finding`s. Phase 1 of `SITE-AUDIT-PIPELINE.md`. URLs come
  from the live sitemap, or from `--url`; `--limit` caps the run. Exits 0 clean,
  1 findings, 2 usage, **19 when every URL was unreachable** (writes nothing —
  a run that measured nothing must be red, not a green report with zero findings).

  Ports `audit_live.py`'s 13 check groups to 18 finding codes, with four
  deliberate behavior changes: `health.img_alt_missing` is per-image and a page
  with zero images no longer reports a violation (a false positive in
  `audit_live.py`); `health.forbidden_phrase` is per-rule; missing and
  out-of-band are mutually exclusive (an absent title emits `health.title_missing`
  only, never also `health.title_length`); and a check whose config input is unset
  is skipped with a named `[WARN]` on stderr rather than failing on every page.
  That last one also fixes a latent `KeyError` — `audit_live.py:62` read
  `cfg["nap"]["phone_tel"]` unguarded and crashed on any config omitting it.

  42 new tests in `tests/test_measure.py`, hermetic (`check_page` takes
  already-fetched HTML; `curl` is monkeypatched everywhere else).

  ```
  $ .venv/bin/pytest -q
  ........................................................................ [ 55%]
  .........................................................                [100%]
  129 passed in 0.74s
  ```

### Fixed

- **`docs/HOW-IT-WORKS.md` walked through a pipeline that no longer exists.**
  The last doc still describing the DOCX rail: a team Word document landing in
  Drive, a Discord nudge, `wf-distill → wf-classify → wf-brief → wf-emit-ts`,
  `cycle-emit.yml`, "twenty-one gates", and a monthly regression loop built on a
  manual Sitebulb crawl routed to named humans. **Twelve of its links were dead**
  — ten `modules/*.md` files, `consuming-the-pipeline.md` and
  `DOCTRINE-GATE-MATRIX.md` — none of which are in the repo.

  Rewritten as the v3 walkthrough: onboarding from a repo and a domain, the 18
  `health.*` checks, the four ratchet lanes and why a finding getting *worse*
  stays PERSISTING, the tier table and the deny floor, one-item-per-invocation
  remediation and why the file→item map has to be a measurement, the three gate
  waves, and deploy through rollback to proof. Deploy is unchanged from v2 and
  is described as it still runs — verified against `deploy.reusable.yml`'s steps
  rather than carried over on trust.

  Two sections earned their place and are new: **the ratchet**, without which
  these gates cannot be pointed at a site that already exists, carrying the
  warning that an unrecorded baseline runs them bare; and **implemented is not
  wired** in "Why it's built this way", so B-007 is written down where the next
  person designing a CI step will read it.

  Every remaining relative link was checked to resolve, and the two numbers
  quoted (18 health checks, capsule 60/61 on the pilot) were read out of
  `measure.py` and `gate-reference.md`. `CLAUDE.md` loses the ⚠️ stale flag it
  carried in the file map — no doc in the repo describes the old rail now.

- **`CLAUDE.md` documented the pipeline v3 replaced.** It is auto-loaded into
  every Claude session in this repo, so it was not merely stale — it was
  actively instructing both operators and every agent from a map of a deleted
  system. It described `pipeline/intake` and `pipeline/generate`, told you to
  run `wf-cycle-status --claim` before any step (that command has not existed
  since v3 §3), warned at length about a Drive-intake `modifiedTime` footgun in
  a module that is gone, drew a flow through `drive-poll → handoff → cycle-emit`
  where none of the three workflows exist, and closed with the emitter's exit-code
  table. Rewritten against the code.

  The Sync Contract is unchanged — it was the part that was still true, and it is
  what caught all of this. Added to it: **implemented is not wired** (B-007's
  lesson — a green unit test proves the function works, not that anything calls
  it), a `docs/MODULES.md` row in the documentation table, and derivation-only as
  a writing standard that binds operators the same way `claim_provenance_check`
  binds the agent.

  New sections for what actually exists: the tier model and why the deny floor
  cannot be shrunk, the five client workflows and what each does, and six sharp
  edges that are current rather than historical — an unrecorded gate baseline,
  B-008, `PIPELINE_REPO_TOKEN`, the static-export precondition, branch protection,
  and the unverified provider network paths. `docs/HOW-IT-WORKS.md` is flagged
  in the file-map as still describing the old rail; it is the last doc that does.

- **Every workflow pointed a client at a different organisation's engine.** All
  four reusable workflows stamped `PIPELINE_REPO: "richardnhek/seo-content-pipeline"`
  / `PIPELINE_REF: "v2.1.0"`, and all three example callers pinned
  `richardnhek/seo-content-pipeline/...@v2.1.0`. That is the repo v3 was
  *imported from* and the engine it was imported *at* — so a client copying an
  example verbatim would have been gated by the v2 DOCX-era suite (16 gates, no
  tiering, no authorship floor) while every doc here said 19. Repointed to
  `Ethan5767/seo_agent@v3.0.0`, **the first tag this repo has ever carried**
  (`git tag -l` was empty).

  `tests/test_pipeline_pin.py` holds the three sources together: the stamps in
  the four workflows, the `uses:` lines in the three examples, and semver on
  both. It also refuses `@main` and a moving `@v3` — these workflows gate
  production, and a mutable ref means the thing guarding a client's live site
  can change without a PR — and fails on any surviving mention of the import
  source.

  ```
  $ .venv/bin/python -m pytest -q
  371 passed in 2.51s

  # the negative control
  $ python -c "…rewrite the example's pin to @main…"
  $ .venv/bin/python -m pytest tests/test_pipeline_pin.py -q
  FAILED …::test_every_example_pins_an_exact_tag_at_the_stamped_repo[quality-gate.yml]
  1 failed, 9 passed in 0.02s
  ```

  This closes open decision #2 in `SITE-AUDIT-PIPELINE.md` §9. The stamp stays
  self-referential — v3.0.0's copy of a file stamps v3.0.0 — so advance it *in
  the tagged commit* at every cut, never after.

- **B-007 — the ratchet was implemented, tested, and called by nothing.** Not
  one of the 7 baselineable gates in `quality-gate.reusable.yml` was invoked
  with `--baseline`, and `add_baseline_args` defaults it to `None` with no
  auto-discovery of `docs/gate-baseline.json`. Every gate ran bare and reported
  the client's *inherited* debt as blocking, so the first PR against any real
  site was red across the board — and the two ways out of that are "fix the
  whole site before we start" and "switch the gate off", the second of which
  always wins. `lib/baseline.py` was complete and correct the whole time. Being
  correct was not the property that mattered.

  - A `Resolve the gate baseline` step decides once, by asking whether the file
    exists, and each of the 7 gates takes `${{ steps.baseline.outputs.arg }}`.
  - **No file means no flag, not a failure.** A client onboarding before their
    first recording runs bare — the old behaviour exactly — with a `::warning::`
    naming the command that fixes it. Running bare is legitimate on day one and
    illegitimate on day ninety, and the annotation is what keeps it from
    becoming permanent.
  - **A `--baseline` pointing at a file that is not there stays a hard refusal**
    (exit 3, `Baseline.load`). Not passing the flag and passing a bad path are
    different things: if a missing file degraded to "no baseline", one typo
    would silently disarm the ratchet across the fleet and every gate would go
    quietly green. That is a worse bug than the one being fixed.
  - No `NEVER_BASELINEABLE` gate is offered one. They refuse at exit 3 anyway;
    the point is that the workflow never even asks.
  - `pages_are_data_check` dropped from `BASELINEABLE` and `gate_argv` — it went
    with the emitter in v3 §3 and had sat in both since. Passing it would have
    surfaced as "produced no findings file" rather than a clean refusal.

  ```
  $ .venv/bin/python -m pytest -q
  ........................................................................ [ 99%]
  .                                                                        [100%]
  361 passed in 2.54s

  # the negative control — the wiring test earns its place
  $ python -c "…strip the flag off wf-capsule-check…"
  $ .venv/bin/python -m pytest tests/test_ratchet_wiring.py -q
  FAILED tests/test_ratchet_wiring.py::test_every_baselineable_gate_receives_the_baseline[capsule_check]
  1 failed, 34 passed in 0.02s
  $ git checkout .github/workflows/quality-gate.reusable.yml
  $ .venv/bin/python -m pytest tests/test_ratchet_wiring.py -q
  35 passed in 0.01s
  ```

  `tests/test_ratchet_wiring.py` reads the workflow as text, because text is the
  artifact the defect lived in. It also catches the two ways this rots: a new
  baselineable gate added without the flag, and a gate named in `BASELINEABLE`
  that no longer exists on disk.

  **Found while tracing what a client actually has to merge, and it turned up a
  second one.** `em_dash_check` is in neither set — it takes no baseline at all,
  so this fix cannot reach it, and a legacy site with em dashes in its existing
  copy is blocked forever with no recording that can accept it. Logged as
  **B-008**, unfixed: adding a gate to `BASELINEABLE` is a documented human
  decision and this one has a real argument on both sides.

- **`docs/MODULES.md` described a repo that no longer exists.** It still carried
  the header counts from before the v3 deletion (6 packages, 55 modules, 8
  workflows, 47 commands, 327 tests), a flow diagram routing through
  `distill → classify → brief → emit_ts`, full sections for `pipeline/intake`
  (14 modules) and `pipeline/generate` (6), a `lib/cycle_state.py` row, and
  three workflows — `intake-poll`, `drive-poll`, `cycle-emit` — that were
  deleted with the rail they served. All of it is gone; the counts are now the
  measured ones (5 packages, 38 modules, 5 workflows, 31 `wf-*` commands, 311
  tests) and the diagram is the v3 §1 flow. `SITE-AUDIT-PIPELINE.md` §10 named
  this debt; this closes the `MODULES.md` half of it.

  ```
  $ ls pipeline/
  __init__.py  audit  dashboard  deploy  gates  lib
  $ grep -c '^wf-' pyproject.toml
  31
  ```

- **B-002 — every config `wf-bootstrap-config` generated was unloadable YAML.**
  The last of the three template blocks was missing its `f` prefix, so it wrote
  `framework: {framework}` verbatim and `per_service: {{}}`, and PyYAML refused
  the whole file with `found unhashable key`. The four `repo:` keys the build
  action reads were placeholder text, not values. Fixed, duplicate
  `required_phrases` / `schema_type` / `faq_seed_questions` keys dropped from the
  same block, and `main()` now parses the config it just built and exits 3 rather
  than writing one nothing can load — a generator that emits a broken file must
  refuse, not defer the failure five commands downstream. Found while verifying
  the phase 2 tier block end to end. See `docs/BUG-LEDGER.md` B-002.

- **B-001** — `curl` and `curl_status` in `pipeline/lib/common.py` let
  `subprocess.TimeoutExpired` escape, so a hung host crashed the run with a
  traceback 30s in instead of being reported unreachable. In `wf-site-health`
  that bypassed the exit-19 refusal path: a total outage exited 1 with a stack
  trace. Both helpers now return their existing failure signals (`""` and `0`)
  on timeout. Fixed at the shared function, so all four callers (`measure`,
  `poll_live`, `bootstrap_config`, `preflight`) are covered. See
  `docs/BUG-LEDGER.md` B-001.

### Removed

- `pipeline/audit/audit_live.py` and the `wf-audit-live` entry point, superseded
  by `wf-site-health`. Nothing imported it.

- `python-docx` dropped from `requirements-dev.txt`. It was a test dependency of
  the distill/segmentation/emitter suites, all deleted in `79b0b5b`; no test path
  imports `docx` any more. Verified by `grep -rn docx --include="*.py" .` returning
  nothing outside the requirements file itself. `pytest -q` → `87 passed in 0.70s`.

- **Backfill for `79b0b5b`** (which shipped without its entry): DOCX intake, the
  emitter, and emitter-bound gates removed. `pipeline/intake/` (16 files),
  `pipeline/generate/` (11), `distiller/` (4, with `anti-slop-prose.md` and
  `serp-title-meta-craft.md` ported to `skills/site-remediation/references/` first).
  Gates 19 → 16: `pages_are_data_check`, `brief_fanout_check`, and
  `validate_multistate_config` deleted. Also removed `cycle_status.py`,
  `lib/cycle_state.py`, `gbp_baseline.py`, `setup_gtm_foundation.py`, the
  `intake-poll` / `drive-poll` / `cycle-emit` workflows, and 15 test files.
  133 files → 73, 354 tests → 87. See `SITE-AUDIT-PIPELINE.md` §3.

## [0.1.0] — template extraction

- Initial template: extracted from a production multi-client pipeline with all
  client data, credentials, IDs, and brand references replaced by placeholders.
  Engineering content (modules, 19 gates, workflows, tests, encoded lessons)
  preserved intact; full test suite green at extraction time.
