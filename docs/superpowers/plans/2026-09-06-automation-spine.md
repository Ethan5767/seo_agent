# Automation Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the pipeline run end-to-end without a human — auto-merge low-risk changes that pass all gates, and prove the whole cycle works with one automated E2E test. No live client involved.

**Architecture:** Add an auto-merge decision layer on top of the existing 19-gate suite: a change is auto-merged only if ALL gates pass AND it is low-risk (tier T1, no medical/legal/new-page flags). Everything else is queued for a human. Add a full-cycle E2E test that runs measure→plan→remediate→gates→merge-decision on a local fixture site.

**Tech Stack:** Python 3 (existing pipeline), pytest, GitHub Actions (existing quality-gate workflow).

## Global Constraints
- Do NOT touch any real client repo. Build + test on a local fixture only.
- Auto-merge NEVER fires unless all 19 gates pass AND risk = low.
- Follow existing repo patterns; every change needs a test; commit per task.
- Human-review path must always remain available (fallback, not removed).

---

## Prerequisites (verified 2026-09-06)

- **Python ≥3.10 required** (code uses `str | None` syntax). Mac default python3.9.6 is TOO OLD and cannot run the pipeline.
- **Working local env:** `python3.14 -m venv .venv && .venv/bin/pip install -e . -r requirements-dev.txt`
- **Run tests with:** `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q']))"` (the plain `pytest` command is intercepted by the rtk shell hook; the python-inline form bypasses it).
- **Baseline confirmed:** 714 tests pass in ~9s on 2026-09-06. Any new work must keep 714+ green.
- Stage entry points (from pyproject `[project.scripts]`): `wf-site-health`=measure, `wf-site-plan`=plan, `wf-site-remediate`=remediate, gates=`wf-<gate>-check`, `wf-onboard`=onboard.

## Requirements (what the automation spine must do)

Functional:
- FR1 — Given a change (PR), the system outputs a decision: AUTO-merge or route-to-HUMAN, with a reason string.
- FR2 — AUTO only if ALL 19 gates report pass (green) AND the change is low-risk.
- FR3 — Low-risk = tier == T1 AND no new page/file created AND no medical/legal ("YMYL") claim touched.
- FR4 — Any gate fail, any gate "cannot judge" (exit 4), OR high-risk ⇒ HUMAN.
- FR5 — No declared tier ⇒ HUMAN (deny by default).
- FR6 — Auto-merge is behind an off-by-default flag; it never fires unless explicitly enabled per client.
- FR7 — One E2E test runs the full cycle (measure→plan→remediate→gates→decision) on a local fixture and asserts each stage plus the final AUTO decision for a safe fix.
- FR8 — After an (enabled) auto-merge, the existing post-deploy verify + rollback path still triggers (preserve current behavior).

Acceptance criteria (spine is "done"):
- The E2E test is green end to end and asserts an AUTO decision for a seeded T1 fix.
- The eligibility function returns HUMAN for: any gate fail, exit-4, tier T2/T3, new-page, or YMYL claim.
- Auto-merge workflow step merges only when eligible AND flag is on; defaults off.
- 714+ existing tests still pass.

Non-goals (explicitly NOT in this plan — later phases):
- Wiring the dfs-test DataForSEO providers into measure.
- Ranking offense (cannibalization/CTR/decay fixes).
- Local SEO, citation-share, report delivery, content engine.
- Deploying to any real client.

---

## Task list (do ONE at a time, in order)

### Task 1: Auto-merge policy config
Define, in one config file, what makes a change auto-mergeable: all gates green + tier == T1 + no risk flags. Just the rules as data, no logic yet.
Done when: config file exists with the policy and a test reads it.

### Task 2: Risk-flag detector
A function that looks at a change and returns risk = high if it touches medical/legal claims, creates a new page, or is tier T2/T3. Low otherwise.
Done when: unit test passes for a safe change (low) and a risky change (high).

### Task 3: Auto-merge eligibility function
A function that takes (gate results, tier, risk) and returns AUTO or HUMAN.
Done when: test passes — all-green + low-risk = AUTO; any fail or high-risk = HUMAN.

### Task 4: Local fixture site — DONE
A tiny fake website with 2-3 seeded SEO problems (missing meta, an orphan page) for the E2E test to run against.
Done when: fixture exists and the measure step finds the seeded problems.
- [x] `tests/e2e_fixture.py`: one `/services/` page, seeded with `health.title_length` (75-char title) + `health.desc_missing`. Page is otherwise gate-clean (valid capsule, schema, canonical, og:image, >500 words). `serve()` maps URL→local file for the network-free measure; `agent_that_fixes()` is the deterministic run_agent stand-in; `commit_fix()` + `run_gates()` drive the gate step. NOTE: tier must be int `1`, not `"T1"` — `common.client_profile` reads a string as no-tier.

### Task 5: E2E test — measure stage — DONE
- [x] `tests/test_e2e_spine.py::test_measure_finds_the_two_seeded_defects` — stubs `measure.curl`/`curl_status`, runs real `measure.main()`, asserts exactly the two seeded codes.

### Task 6: E2E test — plan stage — DONE
- [x] `::test_plan_produces_two_actionable_t1_items` — runs real `plan.main()`, asserts 2 actionable T1 items, 0 tier-blocked.

### Task 7: E2E test — remediate stage — DONE
- [x] `::test_remediate_fixes_both_items_in_tier` — patches `rem.run_agent` with the fixture writer, runs real `remediate()`, asserts both items `fixed`, only the page file touched, nothing refused (in-tier).

### Task 8: E2E test — gates stage — DONE
- [x] `::test_gates_pass_on_the_fixed_fixture` — commits the fix to a PR branch, runs the content-gate set (tier_check, acceptance_check, check_headings, forbidden_sweep, noncommodity_check, capsule_check, em_dash_check) with each gate's real CLI; all exit 0. (The full 19-gate CI — TSC/SSR/LCP/etc. — needs the client's real framework build and runs in the client repo's Actions, by design; these are the gates a T1 copy edit is responsible for.)

### Task 9: E2E test — merge decision — DONE
- [x] `::test_full_cycle_ends_in_an_auto_merge_decision` — feeds real gate results into `automerge.decide()`, asserts AUTO for the safe T1 fix, and HUMAN when any single rail flips (gate fail / T2 / new page / YMYL text / policy off). The YMYL check gets the CHANGED copy (new title+meta), not the whole page.
- Also shipped: `scripts/spine_demo.py` — the same cycle as a readable before/after transcript for stakeholders.
- Baseline: 740 tests pass (was 735).

### Task 10: Wire auto-merge into the workflow (guarded, off by default) — DONE
Add the merge step to the quality-gate workflow: if eligibility == AUTO, merge; else leave for human. Behind an off-by-default flag so it never fires until switched on.
Done when: workflow test confirms AUTO merges, HUMAN does not, flag defaults off.
- [x] `pipeline/audit/automerge_gate.py` (`wf-automerge-decide`): derives tier (config) + creates + changed copy from the PR diff, calls `automerge.decide`, writes `decision=AUTO|HUMAN` to `$GITHUB_OUTPUT`, never merges, never fails the run. KEY: `public_creates()` excludes `docs/` — the audit trail (findings/worklist/changelog) ships in every remediation PR by design and must NOT count as a "new page", or every real PR is forced to HUMAN.
- [x] `.github/workflows/quality-gate.reusable.yml`: `automerge_enabled` input (boolean, default **false**) + `auto-merge` job — `needs: quality-gate`, `if: inputs.automerge_enabled && needs.quality-gate.result == 'success'`, `contents:write`+`pull-requests:write`, runs `wf-automerge-decide`, then `gh pr merge --squash` only when `decision == 'AUTO'`, else comments HUMAN+reason. Two independent guards (flag AND decision).
- [x] Tests: `tests/test_automerge_gate.py` (8) + `tests/test_automerge_workflow.py` (5): AUTO for safe T1 fix, HUMAN for red gates/disabled/new-page; input defaults off; job gated on flag AND gate success; merge step guarded on AUTO.

### Task 11: Confirm verify + rollback — DONE
Add a test that the existing post-deploy verify + rollback still trigger correctly after an auto-merge.
Done when: test passes.
- [x] Auto-merge does an ordinary `gh pr merge --squash` into the PR base (main) — the exact `push: branches:[main]` trigger `.github/examples/deploy-prod.yml` watches, so `deploy.reusable.yml`'s built-in verify-live + auto-rollback still fire. Locked by `test_auto_merge_is_an_ordinary_push_to_main_so_deploy_still_fires`. Chain intact by construction; nothing to change.
- Baseline: **753 tests pass** (was 740 after Tasks 4-9, 735 before the spine).

---

Notes:
- Each task gets its full step-by-step detail (failing test → implement → pass → commit) when we START it, so we're never juggling more than one.
- Tasks 1-3 = the decision brain. Tasks 4-9 = the E2E proof. Tasks 10-11 = wire it in safely.
