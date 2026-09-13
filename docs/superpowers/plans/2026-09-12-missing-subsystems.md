# Six Missing Subsystems Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the six engine subsystems the SOP sells but the code lacks — delivery, backlink outreach, log parsing, E2E gate, CSR detection, two reports — all in Python `pipeline/`.

**Architecture:** Each subsystem is an isolated Python module (or package) exposing a `main()` wired as a `wf-*` console script in `pyproject.toml`, or a scanner check / plan render. No `web/` change. Standard library only. Secrets by env name; per-client config in the client repo. Every dead-end returns a named skip or "cannot judge" exit — never a silent pass.

**Tech Stack:** Python 3, stdlib (`smtplib`, `email`, `urllib`, `json`, `re`, `argparse`), existing `pipeline/lib/common`, `pipeline/scanner/dataforseo`, `pipeline/audit/measure` + `plan`.

## Global Constraints

- Language/location: Python in `pipeline/` only. `web/` (Next.js frontend) is NEVER touched — copied verbatim from operator: "we use python for core function but website as frontend please careful."
- No new dependencies. Standard library only.
- No secrets in this repo (CLAUDE.md §6). Credentials read from env by name. Client recipients/config in client repo `docs/client-config.yml`; `config/client-config.starter.yml` gets sanitized placeholder blocks only.
- No silent green (CLAUDE.md sharp-edge #4/#6): missing cred / empty input / frozen provider → named skip or exit 4, never a false success.
- Verification DEFERRED per operator instruction this session ("do not test"). No pytest run. Every CHANGELOG entry stamped `UNVERIFIED — tests not run this session`. Sanity per task = module imports and `--help` prints, nothing more.
- Commit after each task. Scoped commits. Never break the branch.
- Docs are part of the work (CLAUDE.md sync contract): CHANGELOG, MODULES.md counts, gate-reference.md, BUG-LEDGER, SOP doc corrections.

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `pipeline/audit/plan.py` (modify) | add `render_progress_report`, `render_action_report`; write both files | 1 |
| `pipeline/gates/e2e_check.py` (create) | E2E handoff-chain gate, exit 21 / 4 | 2 |
| `pipeline/scanner/checks.py` (modify) | CSR/render heuristic check | 3 |
| `pipeline/audit/logparse.py` (create) | access-log → crawl-budget findings | 4 |
| `pipeline/audit/deliver.py` (create) | email/telegram delivery, outbox + `--send` | 5 |
| `pipeline/outreach/{__init__,linkbank,qualify,content,run}.py` (create) | backlink outreach pkg | 6 |
| `pyproject.toml` (modify) | register `wf-deliver`, `wf-logparse`, `wf-outreach`, `wf-e2e-check` | 2,4,5,6 |
| `config/client-config.starter.yml` (modify) | `delivery:` + `outreach:` placeholder blocks | 5,6 |
| docs (modify) | CHANGELOG, MODULES.md, gate-reference.md, BUG-LEDGER, SOP | 7 |

---

### Task 1: Two reports (Progress + Action-Needed)

**Files:**
- Modify: `pipeline/audit/plan.py` (add two render fns near `render_report`:210; extend `write_artifacts`:371)

**Interfaces:**
- Consumes: existing `doc`, `lanes`, `cycle`, `prior_cycle`, `resolved` already computed in `plan()`.
- Produces: `render_progress_report(doc, cycle, prior_cycle, lanes, resolved) -> str`; `render_action_report(doc, cycle, lanes) -> str`. `write_artifacts` also writes `report-progress.md`, `report-action.md`.

- [ ] Step 1: Add `render_progress_report` — RESOLVED lane, score delta vs prior cycle, fixed count. Title Case headings, no em dashes.
- [ ] Step 2: Add `render_action_report` — NEW + REGRESSION + PERSISTING lanes, plus standing human-worklist items.
- [ ] Step 3: In `write_artifacts`, write both files into the cycle dir alongside `report.md` (keep `report.md` unchanged for back-compat).
- [ ] Step 4: Sanity — `python -c "import pipeline.audit.plan"` imports clean.
- [ ] Step 5: Commit `feat(plan): split Progress and Action-Needed reports`.

### Task 2: E2E gate (gate #20)

**Files:**
- Create: `pipeline/gates/e2e_check.py`
- Modify: `pyproject.toml` scripts (`wf-e2e-check = "pipeline.gates.e2e_check:main"`)

**Interfaces:**
- Produces: `main(argv=None) -> int`. Exit 0 pass, 21 fail, 4 cannot-judge.
- Consumes: cycle dir from `pipeline.lib.common` (same project/cycle resolution as other gates); reuse `acceptance_check` built-tree helper if importable.

- [ ] Step 1: Load `findings.json`, `worklist.json`, `changelog.json` from the cycle dir. Absent/empty cycle → print `CANNOT JUDGE` and return 4.
- [ ] Step 2: Assert each parses and its `SCHEMA` string matches the expected constant.
- [ ] Step 3: Reconcile lanes — every worklist item traces to a finding fingerprint; every changelog `fixed` traces to a worklist item. Mismatch → collect, return 21.
- [ ] Step 4: `main()` with argparse `--project`/`--cycle`, print PASS/FAIL summary.
- [ ] Step 5: Register script in `pyproject.toml`.
- [ ] Step 6: Sanity — `wf-e2e-check --help` (after `pip install -e .` already present) or `python -m pipeline.gates.e2e_check --help`.
- [ ] Step 7: Commit `feat(gates): add E2E handoff-chain gate (#20)`.

### Task 3: CSR / render detection

**Files:**
- Modify: `pipeline/scanner/checks.py` (add check fn + register in the check list it already exposes)

**Interfaces:**
- Produces: a check emitting rows `csr.empty_shell` (fail), `csr.partial_hydration` (warn), or SSR pass, using the row shape already in `checks.py`.
- Consumes: raw HTML the scanner already fetches per page.

- [ ] Step 1: Add helper `visible_text_ratio(raw_html) -> float` — strip `<script>`/`<style>`, measure text vs markup.
- [ ] Step 2: Classify: framework mount (`id="__next"`/`id="root"`) + near-empty body + ratio < 0.20 → `csr.empty_shell`; ratio > 0.90 → pass; else `csr.partial_hydration`.
- [ ] Step 3: Wire into the scanner's per-page check emission following the existing pattern in `checks.py`.
- [ ] Step 4: Sanity — `python -c "import pipeline.scanner.checks"`.
- [ ] Step 5: Commit `feat(scanner): CSR/render heuristic check`.

### Task 4: Server log parsing

**Files:**
- Create: `pipeline/audit/logparse.py`
- Modify: `pyproject.toml` (`wf-logparse = "pipeline.audit.logparse:main"`); `pipeline/audit/measure.py` (`--with-logs <path>` hook)

**Interfaces:**
- Produces: `parse_logs(path) -> list[finding_row]`; `main(argv=None) -> int`. Finding rows match `measure.py` shape (fingerprint fields).
- Consumes: measure's finding-row constructor / schema.

- [ ] Step 1: Regex parsers for Apache/Nginx combined + common; JSON-line parser for Cloudflare. Unknown lines counted, never crash.
- [ ] Step 2: Aggregate → rows: Googlebot freq per path, status distribution (200/3xx/404/500), byte overhead per crawler.
- [ ] Step 3: Empty/unreadable log → named skip, no rows, exit 0.
- [ ] Step 4: `main()` argparse `--logs`/`--out`; `--with-logs` branch in `measure.py` merges rows into findings.
- [ ] Step 5: Register script.
- [ ] Step 6: Sanity — `python -m pipeline.audit.logparse --help`.
- [ ] Step 7: Commit `feat(measure): server access-log crawl-budget parsing`.

### Task 5: Delivery (email/telegram)

**Files:**
- Create: `pipeline/audit/deliver.py`
- Modify: `pyproject.toml` (`wf-deliver = "pipeline.audit.deliver:main"`); `config/client-config.starter.yml` (`delivery:` block)

**Interfaces:**
- Produces: `main(argv=None) -> int`. `send_email(cfg, subject, body) -> str(status)`; `send_telegram(cfg, body) -> str(status)`.
- Consumes: cycle report files from Task 1; config via `pipeline.lib.common`.

- [ ] Step 1: Resolve report file (`--report progress|action|combined`) from cycle dir.
- [ ] Step 2: Default (no `--send`): write `outbox/<channel>-<report>.txt`, print preview, exit 0.
- [ ] Step 3: `send_email` via `smtplib` STARTTLS, creds from env `SMTP_HOST/PORT/USER/PASS`; missing → `SKIP email: <VAR> unset`.
- [ ] Step 4: `send_telegram` via `urllib` POST to Bot API, token from env `TELEGRAM_BOT_TOKEN`; missing → named skip.
- [ ] Step 5: `--send` writes receipt line to `outbox/delivery-log.jsonl` (channel, target, status — no body).
- [ ] Step 6: Add `delivery:` placeholder block to starter config.
- [ ] Step 7: Register script; sanity `python -m pipeline.audit.deliver --help`.
- [ ] Step 8: Commit `feat(deliver): email/telegram report delivery with outbox gate`.

### Task 6: Backlink outreach package

**Files:**
- Create: `pipeline/outreach/__init__.py`, `linkbank.py`, `qualify.py`, `content.py`, `run.py`
- Modify: `pyproject.toml` (`wf-outreach = "pipeline.outreach.run:main"`); `config/client-config.starter.yml` (`outreach:` block)

**Interfaces:**
- Produces: `linkbank.load(path)/upsert(path, entry)`; `qualify.qualify_domain(domain) -> dict(verdict, reasons)`; `content.draft(domain, tier, topics) -> str`; `run.main(argv=None) -> int`.
- Consumes: `pipeline.scanner.dataforseo` client (pay-frozen → per-domain named skip); `claude` CLI for drafts (grounded pattern).

- [ ] Step 1: `linkbank.py` — JSON store at `<client-repo>/docs/outreach/linkbank.json`, idempotent upsert keyed by domain.
- [ ] Step 2: `qualify.py` — 4-point safety (penalty / real traffic / outbound count / in-content). Frozen provider → `SKIP: no live spend`, verdict `unknown`, never fabricated pass.
- [ ] Step 3: `content.py` — Tier1 LSI / Tier2 localized draft via `claude` CLI, evidence-grounded, Title Case, no em dashes, no invented facts.
- [ ] Step 4: `run.py` — argparse `--project`/`--qualify <file>`/`--draft <domain>`; orchestrates qualify→bank→draft; prints summary; does NOT send.
- [ ] Step 5: Add `outreach:` placeholder block to starter config.
- [ ] Step 6: Register script; sanity `python -m pipeline.outreach.run --help`.
- [ ] Step 7: Commit `feat(outreach): backlink qualifier, link bank, tiered drafts`.

### Task 7: Documentation debt (sync contract)

**Files:**
- Modify: `CHANGELOG.md`, `docs/MODULES.md`, `docs/gate-reference.md`, `docs/BUG-LEDGER.md`, and the SOP doc.

- [ ] Step 1: `CHANGELOG.md` — one `[Unreleased]` entry per subsystem, each stamped `UNVERIFIED — tests not run this session`.
- [ ] Step 2: `docs/MODULES.md` — add module lines (deliver, logparse, outreach×5, e2e gate), bump package/module/gate counts.
- [ ] Step 3: `docs/gate-reference.md` — add gate #20 (E2E), update `8+9+2=19` tally to include it.
- [ ] Step 4: `docs/BUG-LEDGER.md` — record CSR raw-HTML heuristic limitation (can misclassify cached SSG shells).
- [ ] Step 5: SOP doc — correct `16 → 20` gates, auto-merge wording (tier+gate, not "month 4+"), add Bright Data SERP to the cost table.
- [ ] Step 6: Commit `docs: record six subsystems, gate #20, SOP corrections`.

---

## Self-Review

- Spec coverage: all six subsystems + doc debt mapped to Tasks 1-7. ✓
- Placeholder scan: config YAML placeholders are intentional (sanitized template); no TBD/TODO in steps. ✓
- Type consistency: `main(argv=None) -> int` across new commands; `render_progress_report`/`render_action_report` names match spec and Task 1. ✓
- Deviation from skill default (TDD) is deliberate and disclosed: operator said do not test; verification is deferred and every entry stamped unverified. ✓
