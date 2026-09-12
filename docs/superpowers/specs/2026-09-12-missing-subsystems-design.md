# Design — Six Missing Subsystems (Engine, Python)

**Date:** 2026-09-12
**Branch:** feature/automation-spine
**Author:** pairing session (operator + Claude)
**Status:** awaiting user review

## Why

A gap scan of the SEO/AEO SOP document against the codebase found six things the
document sells that the engine does not do (or does differently than described):

1. Report delivery over Email / Telegram — absent entirely.
2. Backlink outreach — only DataForSEO backlink *analysis* exists; no qualifier,
   link bank, or content execution.
3. Server log parsing (Googlebot crawl budget, status distribution, byte
   overhead) — absent; Core Web Vitals "triangulation" is missing its log leg.
4. E2E gate — the SOP lists a 16th "E2E gate"; no such gate exists.
5. CSR / render detection — the SOP's headline rendering check
   ("raw HTML < 20% text → fail") is not implemented; `audit_ssr` checks a
   different thing (unguarded `window`/`document`).
6. Two client reports (Progress + Action-Needed) — only one combined
   `report.md` is rendered today.

Plus documentation drift the same commit corrects: gate count `16 → 20`,
auto-merge is tier+gate based (not "month 4+"), and Bright Data SERP is a second
data vendor the cost table omits.

## Scope and constraints

- **Language / location:** all six are **Python** in `pipeline/`. The `web/`
  Next.js frontend is NOT touched. Core logic is Python; the website is
  frontend only.
- **No new dependencies.** Standard library only (`smtplib`, `email`, `urllib`,
  `json`, `re`, `argparse`). Matches the existing dependency-light engine.
- **No secrets in this repo (CLAUDE.md §6).** Credentials are read from env by
  name only. Per-client recipients/config live in the *client* repo
  `docs/client-config.yml`. The starter template
  `config/client-config.starter.yml` gains sanitized placeholder blocks only.
- **No silent green (CLAUDE.md sharp-edge #4, #6).** Every path that cannot do
  its job — missing credential, empty input, frozen provider — returns a
  **named skip** or a "cannot judge" exit, never a false success.
- **Ships UNVERIFIED.** Per the operator's instruction this session, the code is
  written but the test suite is NOT run. Every CHANGELOG entry is stamped
  `UNVERIFIED — not run this session`, exactly as the provider network paths are
  already recorded (CLAUDE.md sharp-edge #6). This is honest disclosure, not a
  hidden gap.

## wf-command wiring

New console scripts in `pyproject.toml [project.scripts]`, each `module:main`:

| Command | Entry point |
|---|---|
| `wf-deliver` | `pipeline.audit.deliver:main` |
| `wf-logparse` | `pipeline.audit.logparse:main` |
| `wf-outreach` | `pipeline.outreach.run:main` |
| `wf-e2e-check` | `pipeline.gates.e2e_check:main` |

CSR detection is a scanner check, not its own command; two-report split rides
inside existing `wf-site-plan`.

---

## Subsystem 1 — Delivery (`pipeline/audit/deliver.py`)

**Purpose:** deliver a rendered report to the client over email and/or Telegram,
behind a human-review gate.

**Interface:**
`wf-deliver --project <client-repo> --cycle <YYYY-MM> [--report progress|action|combined] [--send]`

**Behaviour:**
- Default (no `--send`): render the message, write it to
  `<client-repo>/docs/audit/<cycle>/outbox/<channel>-<report>.txt`, print a
  preview, exit 0. This is the human-review-before-delivery step (SOP §10).
- `--send`: transmit via the configured channels, then append a receipt line to
  `outbox/delivery-log.jsonl` (channel, target, status, cycle — no message body,
  no PII beyond the target already in client config).
- **Email:** `smtplib.SMTP` (STARTTLS). Creds from env `SMTP_HOST`, `SMTP_PORT`,
  `SMTP_USER`, `SMTP_PASS`. Recipient from client config `delivery.email`.
- **Telegram:** `urllib` POST to `https://api.telegram.org/bot<token>/sendMessage`.
  Token from env `TELEGRAM_BOT_TOKEN`. Chat id from `delivery.telegram_chat_id`.
- **Missing credential or config → named skip** (`SKIP email: SMTP_PASS unset`),
  exit 0, recorded in the log. Never a silent success, never a crash.

**Client config block (starter, placeholders):**
```yaml
delivery:
  channels: []                 # ["email", "telegram"]; empty = deliver nothing
  email: "<client@example.com>"
  telegram_chat_id: "<chat-id>"
```

**Depends on:** the cycle's rendered report files (Subsystem 6). Reads config via
`pipeline/lib/common`.

---

## Subsystem 2 — Backlink outreach (`pipeline/outreach/`)

New package. Actual outreach email stays **human** (SOP §12 "requires human
outreach"); this builds everything up to that point.

- **`qualify.py`** — the 4-point safety check before a domain enters the bank:
  not penalized, real organic traffic, bounded outbound link count, in-content
  placement. Uses the existing `pipeline/scanner/dataforseo.py` client. That
  client is pay-frozen, so with no live spend the qualifier returns a **named
  skip** per domain, never a fabricated pass.
- **`linkbank.py`** — read/write the candidate store at
  `<client-repo>/docs/outreach/linkbank.json` (schema: domain, metrics, verdict,
  tier, status). Idempotent upsert keyed by domain.
- **`content.py`** — generate outreach/guest content via the `claude` CLI, reusing
  the grounding pattern in `web/app/api/content/generate` (evidence-grounded, no
  invented facts). Tier 1 = LSI keyword variations; Tier 2 = localized phrasing.
- **`run.py`** — `wf-outreach --project <repo> [--qualify <domains-file>]
  [--draft <domain>]`. Orchestrates qualify → bank → draft. Emits a summary; does
  not send.

**Client config block (starter, placeholders):**
```yaml
outreach:
  enabled: false
  tier: 1                      # 1 = basic LSI, 2 = localized/professional
  topics: []                   # target topics for fit-matching
```

---

## Subsystem 3 — Server log parsing (`pipeline/audit/logparse.py`)

**Purpose:** turn a client-supplied access log into crawl-budget findings that
feed the ratchet like any other measure output.

**Interface:** folded into measure via `wf-site-health ... --with-logs <path>`,
and standalone `wf-logparse --logs <path> --out findings-logs.json`.

**Behaviour:**
- Parse Apache/Nginx **combined** and **common** formats (regex) and Cloudflare
  **JSON** log lines. Unknown lines counted and reported, never crash.
- Emit finding rows: Googlebot visit frequency per path (money-page vs utility),
  status-code distribution (200 / 301·302 / 404 / 500), byte overhead per
  crawler visit.
- Rows use the same finding shape as `pipeline/audit/measure.py` so
  `plan.py` ratchets them across cycles.
- **Empty / unreadable log → named skip**, no rows, exit 0. Never green over
  nothing.

**Depends on:** measure's finding schema (fingerprint fields).

---

## Subsystem 4 — E2E gate (`pipeline/gates/e2e_check.py`)

**Purpose:** the missing whole-pipeline gate. Verifies the JSON handoff chain is
internally consistent before a human reviews the PR.

**Interface:** `wf-e2e-check --project <repo> --cycle <YYYY-MM>` → exit 0 pass,
exit 21 fail, **exit 4 "cannot judge"** on an empty/absent cycle.

**Checks:**
- `findings.json`, `worklist.json`, `changelog.json` exist and parse.
- Each conforms to its declared `SCHEMA` string.
- Lanes reconcile: every worklist item traces to a finding; every `changelog`
  `fixed` entry traces to a worklist item.
- The built tree referenced by acceptance exists (reuses `acceptance_check`
  helpers where possible).

**Empty-input rule (CLAUDE.md sharp-edge #4):** a cycle with no artifacts is
**exit 4**, never a pass. Registered as gate #20.

**Docs touched:** `docs/gate-reference.md` (add gate 20, update the
`8+9+2=19 → …=20` tally), `docs/MODULES.md` (gate count + new module lines),
`pyproject.toml` scripts.

---

## Subsystem 5 — CSR / render detection (`pipeline/scanner/checks.py`)

**Purpose:** the SOP's headline rendering check.

**Behaviour:**
- Fetch raw pre-JS HTML for the page. Strip `<script>`/`<style>`. Measure visible
  text.
- Heuristic classification (documented as a heuristic, not a headless render):
  - framework mount point present **and** near-empty body text
    (`<div id="__next"></div>`, `<div id="root"></div>`) **and** text ratio
    < 20% → **CSR fail** (`csr.empty_shell`).
  - text ratio > 90% → **SSR pass**.
  - between → **warn** (`csr.partial_hydration`).
- Emits a finding row into the scanner output; no separate command.

**Known limitation (goes to BUG-LEDGER):** true "on-screen text" needs a headless
render; this uses a raw-HTML heuristic and can misclassify heavily-cached SSG
shells. Recorded so it is not mistaken for a full renderer.

---

## Subsystem 6 — Two reports (`pipeline/audit/plan.py`)

**Purpose:** split the single report into the two client-facing reports the SOP
describes.

**Behaviour:**
- Add `render_progress_report(...)` — RESOLVED lane, score deltas, fixed counts
  ("what got better").
- Add `render_action_report(...)` — NEW / REGRESSION / PERSISTING plus the
  standing human-worklist items ("what needs attention / client action").
- `write_artifacts` (line 371) additionally writes `report-progress.md` and
  `report-action.md` into the cycle dir. `report.md` (combined) stays for
  back-compat and existing dashboard reads.
- `plan()` return tuple is unchanged; the two new renders derive from the same
  `doc`/`lanes` already computed, so no new inputs.

**Depends on:** existing lane partitioning in `plan.py`. Delivery (Subsystem 1)
consumes these files.

---

## Documentation debt corrected in the same push (CLAUDE.md sync contract)

- `CHANGELOG.md` — one `[Unreleased]` entry per subsystem, each stamped
  `UNVERIFIED — tests not run this session`.
- `docs/MODULES.md` — new module lines and package/module/gate counts.
- `docs/gate-reference.md` — gate 20 (E2E), updated tally.
- `docs/BUG-LEDGER.md` — CSR heuristic limitation.
- The SOP document — `16 → 20` gates, auto-merge rule wording, Bright Data added
  to the cost table.

## Build order

6 (two reports, isolated) → 4 (E2E gate) → 5 (CSR check) → 3 (log parse) →
1 (delivery) → 2 (outreach). Each is an independent unit with its own CHANGELOG
line; a stop after any step leaves `main`/branch runnable.

## Explicitly out of scope (YAGNI)

- Any `web/` frontend change.
- Live tail / streaming of logs (batch file only).
- Auto-sending outreach email to site owners.
- Running the test suite (operator instruction; disclosed as unverified).
- Vercel/Netlify or non-Cloudflare deploy paths.
