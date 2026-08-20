# Architecture Snapshot — seo_agent v3.1.3

**As of 2026-08-20.** This is a point-in-time technical snapshot of the whole
system: what exists, how the pieces fit, and where it currently stands. It
complements, not replaces, the living docs — `SITE-AUDIT-PIPELINE.md` (the
design doc and its history), `docs/MODULES.md` (the module map),
`docs/gate-reference.md` (per-gate contracts), `docs/HOW-IT-WORKS.md` (plain-
language walkthrough), `CLAUDE.md` (the sync contract). Read those for detail
and for how things got here; read this for a single current picture.

Every fact below was checked against the code and repo state on 2026-08-20,
not against what the other docs claim — per this repo's own rule that code
wins when the two disagree. Mismatches found in that process are called out
in [Known Doc Drift](#known-doc-drift) rather than silently fixed elsewhere.

---

## 1. What this is

Point the engine at a client's GitHub repo and their domain. It measures the
live site, ratchets this month's findings against previous months, plans the
work, hands each item to Claude Code inside the client's own checkout, and
gates everything the agent wrote before a human merges it. Deployment, if any,
is the operator's own step outside this pipeline.

```
repo + domain
   │  ONBOARD    wf-onboard        clone, config, preflight, docs, first measurement
   ▼
   │  MEASURE    wf-site-health    live site → docs/audit/<YYYY-MM>/findings.json
   ▼
   │  PLAN       wf-site-plan      RESOLVED / PERSISTING / NEW / REGRESSION → worklist.json + report.md
   ▼
   │  REMEDIATE  wf-site-remediate Claude Code edits, inside the tier → changelog.json
   ▼             ── everything above runs locally, or in the container ──
   │  GATES      19 gates on the client's PR, in Actions on the CLIENT repo
   ▼
   │  HUMAN MERGE   always. the only path to production.
   ▼             ── pipeline ends here. deployment is the operator's ──
   │  MONITOR    seo-health, daily + on demand — never blocks
```

**Model A**: this repo (`seo_agent`) holds engine code only. Every client
repo is that client's own source of truth for its config, baseline, and audit
artifacts. The engine holds no client state; the worker is swappable.

## 2. Repo layout, as it actually stands

```
seo_agent/
├── pipeline/
│   ├── audit/       12 modules — the rail: onboard, measure, plan, remediate, providers, +7 support
│   ├── gates/        19 modules — the gate suite, 1:1 with pyproject.toml's 19 wf-* gate commands
│   ├── lib/           4 modules — common.py (config+tiering), baseline.py (ratchet),
│   │                               client_docs.py, score.py
│   ├── dashboard/      server.py, review.py, state.py, static/ — wf-dashboard
│   └── deploy/         Cloudflare-only deploy helpers (exists; not named in CLAUDE.md's file table)
├── .github/
│   ├── workflows/      ci.yml + 4 *.reusable.yml (quality-gate, seo-health, preview, deploy)
│   └── examples/       thin-caller copies of the 4 reusable workflows, for client repos to adopt
├── skills/site-remediation/   the doctrine inlined into every remediation prompt
├── config/client-config.starter.yml   the client-config schema template
├── docs/                the living docs listed above, plus BUG-LEDGER, ADMIN-CHECKLIST, HANDOFF-*
├── stitch_local_operator_dashboard/   static design-tool mockups for the dashboard UI — reference
│                                       art, not runtime code; not part of the pipeline
└── Dockerfile            Python + git + gh + Claude Code, the only place all four are guaranteed
```

5 packages under `pipeline/`, 40 modules total (`.py` files excluding
`__init__.py`), 34 `wf-*` commands declared in `pyproject.toml`.

## 3. The five pipeline stages

All entry points are console scripts declared under `[project.scripts]` in
`pyproject.toml`, backed by modules in `pipeline/audit/`.

| Stage | Command | Module | Does |
|---|---|---|---|
| Onboard | `wf-onboard` | `onboard.py` | Clone, config, preflight, client docs, first measurement. Stops at the interview; re-running resumes. |
| Measure | `wf-site-health` | `measure.py` | Live site → `docs/audit/<YYYY-MM>/findings.json`. Calls `providers.py` for CrUX/GSC/DataForSEO/Bright Data SERP. |
| Plan | `wf-site-plan` | `plan.py` | Diffs this cycle against the last → RESOLVED / PERSISTING / NEW / REGRESSION, emits `worklist.json` + `report.md`. Byte-identical over an unchanged cycle. |
| Remediate | `wf-site-remediate` | `remediate.py` | Claude Code edits inside the client's declared tier → `changelog.json`. Resumes: skips items the changelog already marks `fixed`, merges into it rather than overwriting. |
| Snapshot | `wf-render-snapshot` | `snapshot.py` | For clients with no static export: crawls a rendered deployment into the tree the gates already glob. Refuses at exit 19 rather than writing an empty directory. |

Supporting modules with no `wf-*` entry of their own: `providers.py` (called
by measure), `bootstrap_config.py`, `client_profile.py`, `poll_live.py`. Two
more do have declared commands not folded into the table above:
`wf-scaffold-client-docs` and `wf-seed-queries` (the Search Terms feature
shipped 2026-08-20, per `CHANGELOG.md`).

## 4. Tiering (`pipeline/lib/common.py`)

A tier is a path + operation allow-list, declared per client in their own
`docs/client-config.yml`, enforced by `tier_check` on the PR diff.

| Tier | May do |
|---|---|
| T1 (default) | Modify files matching `text_paths`. No creates, no deletes. |
| T2 | T1 + create under `content.location`, wired into `content.registry`. Refused (`resolve_tier`) unless both fields are populated. |
| T3 | Anything not denied. |

**Deny floor, unioned in at every tier including T3** (`DEFAULT_DENY`,
`common.py:243`): `.github/**`, `docs/client-config.yml`, `package*.json`,
`wrangler.toml`, `.env*` — plus two entries not yet named in `CLAUDE.md`'s
own deny-floor bullet list:

- `docs/banned-phrases.txt` — without this, a T3 agent could delete the
  phrase ledger and turn a genuine forbidden-phrase hit into a silent skip.
  Verified exit 3 → 0 on 2026-08-10.
- the standing human worklist file (the fix-queue skip-list) — moved onto
  the deny floor the same day, for the same self-disarming reason.

The agent can never raise its own tier: `docs/client-config.yml` is itself
denied at every tier, and `wf-onboard` writes the tier as a human commit on
the client's default branch.

## 5. The gate suite

19 gates, `pipeline/gates/*.py`, exactly matching the 19 gate/`wf-*` entries
in `pyproject.toml` and the count `CLAUDE.md` and `docs/gate-reference.md`
both claim — no drift here:

`acceptance_check`, `audit_built`, `audit_ssr`, `capsule_check`,
`check_headings`, `claim_provenance_check`, `client_docs_check`,
`em_dash_check`, `fingerprint_check`, `forbidden_sweep`, `image_budget_check`,
`lcp_hygiene_check`, `llms_sales_purge`, `noncommodity_check`, `orphan_check`,
`parity_check`, `robots_aicrawler_check`, `rules_selftest`, `tier_check`.

Per-gate exit codes and baselineability: `docs/gate-reference.md`. The
running rule for every gate here: a gate that scanned nothing must never
report a pass — `forbidden_sweep` and `audit_ssr` both exit 4 for "cannot
judge" rather than green-over-empty (see `CLAUDE.md` §Known Sharp Edges, and
B-027 in the bug ledger).

## 6. Workflows and versioning

`ci.yml` runs in this repo. Everything gate/monitor/deploy-related runs
**in the client repo**, via thin ~30-line callers in `.github/examples/`
that pull the real logic in by pinned tag:

```yaml
uses: Ethan5767/seo_agent/.github/workflows/quality-gate.reusable.yml@v3.1.3
secrets: inherit
```

| Workflow | Standard? | Trigger | Does |
|---|---|---|---|
| `quality-gate.reusable.yml` | yes | every PR | build once, run the 19 gates, sticky comment. Required status check. |
| `seo-health.reusable.yml` | yes | daily + dispatch | live routes, sitemap count, AI-crawler access. Never blocks. |
| `preview.reusable.yml` | opt-in, CF only | every PR | Cloudflare preview + Lighthouse |
| `deploy.reusable.yml` | opt-in, CF only | push to main | build, deploy, verify, rollback, IndexNow |

Current tag: **v3.1.3** (`git tag --sort=-creatordate`: v3.1.3, v3.1.2,
v3.1.1, v3.1.0, v3.0.0). Pinned exact tags only, enforced by
`tests/test_pipeline_pin.py`.

## 7. Test suite — proof, not paraphrase

```
$ .venv/bin/python -m pytest -q
714 passed in 6.72s
```

Run 2026-08-20. Zero failures, zero skips. (`pytest` is not on `PATH`
outside the venv — activate `.venv` first.)

## 8. Dashboard

`pipeline/dashboard/server.py` — a 127.0.0.1 console over the artifacts the
pipeline already writes into client repos. Holds no state of its own: every
client is a checkout on disk, every artifact is a JSON file in that checkout,
and every action shells out to a `wf-*` entry point, `git`, or `gh`. No
database, no accounts, no merge action. Design spec:
`docs/superpowers/specs/2026-08-05-dashboard-design.md`.

## 9. Open bugs (from `docs/BUG-LEDGER.md`, unfixed as of 2026-08-20)

| ID | Summary |
|---|---|
| B-017 | CI render-source path for non-static-export clients never verified against a live Cloudflare preview |
| B-019 | `serp.page_two` band structurally unreachable — Google no longer returns 30 organic results |
| B-021 | Transient SERP failures churn the ratchet — a query that fails then succeeds reads as false NEW/RESOLVED |
| B-026 | `--allowedTools` doesn't actually block Bash in remediation runs — the clean-tree assertion is what actually holds |
| B-028 | Inconsistent `--project`/positional-arg CLI convention across 11 commands; `wf-preflight --help` is broken |
| B-031 | Static-export warning cites an assumed `ssr_model` default as if it were declared evidence |
| B-035 | `lee` client's `forbidden_phrases: []` silently drops the default rule too, on a never-baselineable legal gate |

Full repro + evidence for each: `docs/BUG-LEDGER.md`.

## 10. Recent state (from `CHANGELOG.md`)

Most recent, since v3.1.3:

- Analytics dashboard `/analytics` page — re-check-all-providers button, plus
  a Search Terms panel (`wf-seed-queries --write`).
- **B-041 fixed** — CrUX now resolves the real serving host via
  `curl_final_host` before querying, instead of the literal config domain.
- **First live provider verification**, 2026-08-14 — CrUX, DataForSEO, and
  Bright Data SERP all confirmed working against real credentials. This
  closes the long-standing "never run live" caveat for those three
  providers (GSC still unverified live).
- **B-040 fixed** — `gate-reference.md`'s dead authority links repointed to
  what actually exists at runtime.

## Known Doc Drift

Found while grounding this document in code rather than other docs. None of
these are code defects — they're documentation lagging reality, called out
here per the sync contract rather than fixed silently elsewhere:

1. **`docs/MODULES.md` test count is stale.** It header-claims 669 tests as
   of 2026-08-10; the suite is 714 as of this snapshot (§7). The doc even
   flags test count as "the only number that moves" — it moved again since.
2. **`pipeline/lib/score.py` and `pipeline/deploy/` aren't named in
   `CLAUDE.md`'s "Where Things Live" table.** Both are real and current.
3. **`docs/banned-phrases.txt` and the standing worklist file sit on the
   deny floor** (`common.py:243`) but aren't named in `CLAUDE.md`'s
   deny-floor bullet list (§4 above).

None of these block anything; they're small enough to leave for whoever
next touches those files, but worth knowing before trusting a count from
memory instead of a fresh `pytest -q` / `find` / `grep`.
