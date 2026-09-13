# SEO Content Pipeline

A gated, multi-client SEO/AEO content pipeline: website audit in, prioritized
triage + remediated pull requests in the client's repo out — with 16 safety gates
between audit and production and strict multi-tier change controls.

This is a sanitized template repo: all client data, credentials, IDs, and
brand references have been replaced with placeholders. The engineering —
modules, gates, workflows, tests, and the lessons encoded in them — is real.

## The SOP Flow

The pipeline executes in 4 continuous stages:

```
target domain & client repo
        │
        ▼  1. AUDIT (Measure)
        │  Runs technical, content, lighthouse, and AEO scanners.
        │  `wf-site-health` ──► docs/audit/<YYYY-MM>/findings.json
        │
        ▼  2. PLAN (Triage)
        │  4-lane ratchet: RESOLVED / PERSISTING / NEW / REGRESSION.
        │  Classifies issues into Scope Tiers (T1 Copy, T2 Content, T3 Full).
        │  `wf-site-plan` ──► worklist.json + report.md
        │
        ▼  3. REMEDIATE (Model A / Model B)
        │  - Model A: Generates actionable implementation briefs for client developers.
        │  - Model B: Claude Code autonomously patches code in client repo branch.
        │  `wf-site-remediate` ──► changelog.json + PR
        │
        ▼  4. GATES (Safety Checks)
        │  16 deterministic quality & safety checks verify PR code against baseline.
        │
        ▼  MERGE & DEPLOY
        │  - Operator Review: Standard human merge is required.
        │  - Auto-Merge: Optional, OFF by default. Strictly restricted to low-risk
        │    T1 copy changes and must be explicitly enabled per workflow.
```

### Running Tests & Verification

Run the test suite and web build locally before pushing changes:

```bash
# 1. Run Python test suite (offline unit tests, no paid API calls)
pytest -q

# 2. Run Web security unit tests (SSRF, DNS resolution, rate limiting, size limits)
cd web && npm test

# 3. Run Web app production build & typecheck
npm run build
```

## What's here

| Path | What it is |
|---|---|
| `pipeline/lib` | Config loader, baseline ratchet (green-on-legacy, red-on-new), cycle ledger |
| `pipeline/scanner` | Multi-engine local & cloud audit runner (SEO, AEO, Schema, Core Web Vitals, Crawl) |
| `pipeline/audit` | Client profile, onboarding scaffolds, and the audit rail: measure (`wf-site-health`) → plan (`wf-site-plan`) → remediate (`wf-site-remediate`) |
| `pipeline/gates` | 16 quality & safety gates (forbidden-phrase sweep, SSR hydration, orphan check, parity, rules self-test, …) |
| `pipeline/deploy` | Verify-live, crawler reachability, capture + auto-rollback, IndexNow |
| `web/` | Next.js 15 App Router dashboard, multi-tenant authenticated APIs, and SSRF-protected scanning proxy |
| `.github/workflows` | Release-quality CI (`ci.yml`), reusable workflows, and automated safety sweeps |
| `docs/` | Architecture specs, SOP guides, gate references, and security architecture (`docs/SECURITY.md`) |

Design principles baked in everywhere:

- **Agent proposes, gates dispose.** Generated content must pass deterministic
  gates; auto-merge is optional, off by default, and limited to low-risk T1 copy changes.
- **Model A vs Model B:** Model A generates client briefs for external teams;
  Model B generates branch PRs with automated verification.
- **Multi-Tenant Security & Isolation:** All data modification, scan execution, and
  tenant persistence routes are authenticated via Supabase session tokens, scoped strictly
  by `user_id`, and protected against DNS-rebinding SSRF, request bloat (413), and burst abuse (429).
  Public utility and OAuth routes remain unauthenticated by design. Full details in `docs/SECURITY.md`.
- **Rules are tested like code.** Forbidden-phrase rulesets have their own
  gate: fixtures prove every rule still fires, exceptions still hold, and a
  dead regex fails CI the day it's introduced.

## Adapting this template

1. **Engine repo (this one):** create your repo from it, install dependencies
   in `.venv`, and run `pytest -q` — the suite must be green before any change.
2. **Web Dashboard:** configure `web/.env.local` with Supabase keys, run
   `npm run dev` for local dev, and test with `npm test && npm run build`.
3. **Client repos:** add caller workflows pinned to a tag of this repo, a gate baseline,
   and the docs contract (`pipeline/audit/scaffold_client_docs.py` creates it).
4. **Secrets** (GitHub Actions, names only — set what you use):
   `ANTHROPIC_API_KEY`, `CLIENT_REPOS_TOKEN`, plus your deploy platform's token trio on each client repo.
5. Read `docs/MODULES.md` first, then `docs/SECURITY.md`, `docs/HOW-IT-WORKS.md`,
   and `docs/gate-reference.md` for per-gate contracts and exit codes.
