# Bug Ledger

Every bug found gets a row the moment it is found — even if you fix it in the
same commit, and even if you don't fix it at all. Fixed bugs move to the Fixed
table with proof (command + output, or test name). See `CLAUDE.md` §2.

## Open

| ID | Found | Where | Symptom | Notes |
|---|---|---|---|---|

## Fixed

| ID | Found | Fixed | Where | Symptom | Proof |
|---|---|---|---|---|---|
| B-002 | 2026-08-05 | 2026-08-05 | `pipeline/audit/bootstrap_config.py` | The last of the three config template blocks was missing its `f` prefix, so **every config `wf-bootstrap-config` has ever generated is unloadable YAML**: it emitted `framework: {framework}` verbatim and `per_service: {{}}`, which PyYAML refuses with `found unhashable key`. Every downstream `load_config` on a freshly bootstrapped repo died at line 108 — and the four `repo:` keys the build action reads (`framework`, `sitemap`, `pages_dir`, …) were placeholder text, not values. Found while verifying phase 2's tier block end to end. | `f` prefix restored (its `{{}}` escapes were already written for one); duplicate `required_phrases` / `schema_type` / `faq_seed_questions` keys removed from the same block. `main()` now parses the config it built and exits 3 rather than writing YAML nothing can load — a generator that emits a broken file must refuse, not defer the failure five commands downstream. | `tests/test_tiering.py::test_bootstrapped_config_is_loadable_yaml_carrying_the_tier` — bootstraps a fixture repo, then asserts `yaml.safe_load` succeeds, `repo.framework == "nextjs-app-router"` and `h1_format.per_service == {}`. |
| B-001 | 2026-08-05 | 2026-08-05 | `pipeline/lib/common.py` `curl` / `curl_status` | A hung host raised `subprocess.TimeoutExpired` uncaught, crashing the run with a traceback 30s in. In `wf-site-health` this bypassed the exit-19 refusal path entirely, so a total outage exited 1 with a stack trace instead of a clean REFUSED. Latent in `audit_live.py` since import, and shared by all four callers (`measure`, `poll_live`, `bootstrap_config`, `preflight`). | Guard added at both helpers, returning their existing failure signals (`""` / `0`). Fixed at the shared function, not per caller. | `tests/test_common.py::test_curl_returns_empty_on_timeout`, `::test_curl_status_returns_zero_on_timeout`. Smoke run against an unresolvable domain now prints `[REFUSED] … nothing to measure` and `exit=19`, writing no `findings.json`. Found by that same smoke run — no hermetic test could have caught it, since they all monkeypatch `curl`. |
