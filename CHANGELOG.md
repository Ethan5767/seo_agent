# Changelog

All notable changes to this pipeline are documented here, newest first.
**Every behavior-changing commit must carry its entry in the same commit** —
see `CLAUDE.md` (the sync contract).

## [Unreleased]

### Added

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
