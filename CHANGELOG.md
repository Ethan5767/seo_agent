# Changelog

All notable changes to this pipeline are documented here, newest first.
**Every behavior-changing commit must carry its entry in the same commit** —
see `CLAUDE.md` (the sync contract).

## [Unreleased]

### Added

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
