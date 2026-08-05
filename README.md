# SEO Content Pipeline

A gated, multi-client SEO/AEO content pipeline: team-authored DOCX in, typed
page data + a pull request in the client's repo out — with 19 quality gates
between intake and production and a hard rule that **a human PR merge is the
only path to production**.

This is a sanitized template repo: all client data, credentials, IDs, and
brand references have been replaced with placeholders. The engineering —
modules, gates, workflows, tests, and the lessons encoded in them — is real.

## The flow

```
team DOCX / Drive link / Discord drop
        │  INTAKE (fleet-wide crons, this repo)
        ▼
pre-flight fix-list ──► content team fixes at handoff, not at emit
        │
        ▼  GENERATE (per-client, button-triggered)
distill → classify → brief → emit_ts ──► typed data + PR in the CLIENT repo
        │
        ▼  GATES (run on that PR, green-on-legacy via the baseline)
19 quality gates ──► operator merges = the ONLY path to production
        │
        ▼  DEPLOY
build → capture → deploy → verify-live + crawler check → auto-rollback
        │
        ▼  AUDIT / OPS
cycle state, live audits, monthly loops
```

## What's here

| Path | What it is |
|---|---|
| `pipeline/lib` | Config loader, baseline ratchet (green-on-legacy, red-on-new), cycle ledger |
| `pipeline/intake` | Discord/Drive/link ingest, DOCX pre-flight, the PR-only client handoff |
| `pipeline/generate` | The emitter: distill → classify → brief → validate → emit typed data |
| `pipeline/gates` | 19 quality gates (forbidden-phrase sweep, orphan check, parity, capsule, rules self-test, …) |
| `pipeline/deploy` | Verify-live, crawler reachability, capture + auto-rollback, IndexNow |
| `pipeline/audit` | Client profile, cycle status, live audits, onboarding scaffolds |
| `distiller/` | The one judgment stage: repair a raw team doc to 0-BLOCK before the engine parses it |
| `.github/workflows` | Fleet crons (intake/drive polls), CI, and reusable workflows client repos call `@tag` |
| `docs/` | `MODULES.md` (the complete map), `gate-reference.md`, `HOW-IT-WORKS.md` |

Design principles baked in everywhere:

- **Agent proposes, gates dispose.** Generated content must pass deterministic
  gates; a human merge gate is sacred and never automated.
- **Model A:** every client repo is its own source of truth
  (`docs/client-config.yml`, `docs/gate-baseline.json`, cycle logs). This repo
  is the shared engine, versioned by tag.
- **Fail loud, never guess.** Unroutable content goes to `unrouted/`; an
  unsegmentable doc exits 16; a classify run that can see nothing refuses
  (exit 17) instead of emitting confident wrong verdicts.
- **Rules are tested like code.** Forbidden-phrase rulesets have their own
  gate: fixtures prove every rule still fires, exceptions still hold, and a
  dead regex fails CI the day it's introduced.

## Adapting this template

1. **Engine repo (this one):** create your repo from it, then
   `python3.12 -m venv .venv && .venv/bin/pip install -e .` and run
   `.venv/bin/python -m pytest` — the suite must be green before any change.
2. **Per-client config:** copy `config/client-config.starter.yml` into each
   client repo as `docs/client-config.yml` and fill it in. Real client data
   never lives in this repo.
3. **Intake rosters:** copy `config/discord-intake.example.yml` →
   `config/discord-intake.yml` and `config/drive-intake.example.yml` →
   `config/drive-intake.yml`; replace placeholder IDs.
4. **Client repos:** add thin caller workflows pinned to a tag of this repo
   (see `.github/workflows/*.reusable.yml` inputs), a gate baseline, and the
   docs contract (`pipeline/audit/scaffold_client_docs.py` creates it).
5. **Secrets** (GitHub Actions, names only — set what you use):
   `DISCORD_BOT_TOKEN`, `DRIVE_CLIENT_ID`, `DRIVE_CLIENT_SECRET`,
   `DRIVE_REFRESH_TOKEN`, `PIPELINE_DRIVE_PARENT_FOLDER_ID`,
   `CLIENT_REPOS_TOKEN` (fine-grained PAT, client repos only, PR-mediated
   writes), plus your deploy platform's token trio on each client repo.
6. Read `docs/MODULES.md` first, then `docs/HOW-IT-WORKS.md`,
   then `docs/gate-reference.md` for per-gate contracts and exit codes.
