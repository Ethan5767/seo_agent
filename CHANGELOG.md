# Changelog

All notable changes to this pipeline are documented here, newest first.
**Every behavior-changing commit must carry its entry in the same commit** —
see `CLAUDE.md` (the sync contract).

## [Unreleased]

### Fixed

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
