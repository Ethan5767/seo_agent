# Performance analytics — stronger flow + Analytics dashboard page

**Status:** draft · **Date:** 2026-08-14

---

## 0. Why

Phase 6 added four external measurement providers (`pipeline/audit/providers.py`):
CrUX (field Core Web Vitals), Google Search Console, DataForSEO On-Page, and Bright
Data SERP. All four shipped with a caveat in their own source comments: *"this
network path has never been run against the live API — only the parser is
tested."* The 2026-08-12 handoff repeated the same caveat.

On 2026-08-14, working against a real domain (`new-wave.io`) with real credentials
supplied in a local, gitignored `.env`, all three optional providers (CrUX,
DataForSEO, Bright Data SERP) were run live for the first time and worked. That
session also surfaced two concrete gaps:

1. **No dashboard control surface.** The findings page already renders provider
   status (`pipeline/dashboard/static/page-findings.js`), but nothing in the
   dashboard can *trigger* a provider run or curate what Bright Data SERP tracks.
   The only way to run them today is the bare CLI with hand-typed flags.
2. **CrUX is not redirect-aware.** `crux_findings(domain)` queries the CrUX API
   with the literal config string as the origin. Proven live: `wikipedia.org`
   (bare) returned no record; `en.wikipedia.org` (the real serving origin)
   returned a real one. Any client whose apex redirects to `www` (or vice
   versa) risks querying an origin Chrome never recorded traffic against, and
   reads that as "too little traffic" rather than "wrong host."

This spec covers making the flow stronger and giving it a dashboard front end,
scoped to already-onboarded clients.

---

## 1. Scope

- All four providers: CrUX, GSC, DataForSEO, Bright Data SERP.
- Onboarded clients only — no bare-URL / no-repo prospecting mode. Every other
  screen in this dashboard assumes a client checkout with `docs/client-config.yml`
  already exists; this does not change that.
- Credentials stay environment-variable-only. `providers.py` already states
  *"no `.env` is read"* by design — this spec does not add a secrets store. The
  dashboard subprocess already inherits `os.environ` from whatever shell
  launched `wf-dashboard` (`server.py` `Run.__init__` passes `env=None` to
  `subprocess.Popen`, which is Python's "inherit parent env" default), so the
  operator exports credentials (or sources a local `.env`) before launching
  the dashboard, same as running any `wf-*` command by hand today.
- "How to improve" surfaces only already-typed findings (`serp.*`, `gsc.*`).
  No invented advice — the same discipline `claim_provenance_check` enforces
  on client-facing copy applies here to operator-facing guidance too.

---

## 2. Components

### 2.1 `providers.py` — CrUX origin fix

`crux_findings(domain, urls=None)` resolves the domain's real serving host with
the existing `common.curl_final_host()` (built for B-037's auth-wall refusal,
already proven in this codebase) before building the `origin` query parameter.
Falls back to the literal `domain` string if resolution fails for any reason
(timeout, non-2xx, etc.) — this is strictly additive; a resolution failure
degrades to today's exact behavior, never worse.

```python
def crux_findings(domain: str, urls=None) -> tuple:
    key = os.environ.get("CRUX_API_KEY")
    if not key:
        return [], "skipped: CRUX_API_KEY unset"
    origin_host = curl_final_host(f"https://{domain}") or domain
    ...
    targets = [("origin", f"https://{origin_host}", "/")] if not urls else ...
```

The status string names the resolved host when it differs from the configured
one, so a client's operator can see the substitution happened rather than
wondering why the domain in the report doesn't match `client-config.yml`:
`"ok: 1 record(s) (resolved to www.new-wave.io)"`.

### 2.2 New CLI: seed-queries writer

A narrow, append-only writer for `seed_queries` in `docs/client-config.yml`,
same shape as `wf-bootstrap-config --add-tier` (a human/dashboard-triggered
write, never agent-triggered, never auto-committed). Lives in
`pipeline/audit/seed_queries.py` as a new `--write` mode rather than a new
module — one file already owns this concern.

```
wf-seed-queries --project <dir> --write "Top AI agency in Cambodia" [--write "..."]
```

- Dedupes case-insensitively against the existing list.
- Refuses (exit 4, matching `bootstrap_config`'s refusal vocabulary) if the
  YAML `seed_queries:` block cannot be found/round-tripped safely — never
  silently drops to a full-file rewrite that would lose comments.
- Writes only the list; nothing else in the file is touched.
- Prints the full resulting list and reminds the operator a commit is still
  required, matching every other config-mutating command in this pipeline.

### 2.3 `pipeline/dashboard/server.py` — `COMMANDS`

```python
"site-health": {
    ...
    "args": {"limit": "int", "url": "path-list",
              "with-crux": "flag", "with-gsc": "flag", "with-dataforseo": "flag"},
    ...
},
"search-suggest": {
    "argv": ["wf-seed-queries", "--project", "{project}", "--limit", "5"],
    "args": {},
    "label": "Suggest 5 search terms (agent-grounded)",
    "exits": {2: ("error", "`claude` not on PATH"), 19: ("error", "sitemap unreachable"),
              20: ("error", "the agent reply was not usable")},
},
"search-add": {
    "argv": ["wf-seed-queries", "--project", "{project}", "--write"],
    "args": {"write": "text-list"},
    "label": "Add search term(s) to track",
    "exits": {4: ("refused", "config could not be safely round-tripped")},
},
"search-check": {
    "argv": ["wf-site-health", "--project", "{project}", "--with-serp"],
    "args": {},
    "label": "Check rank for tracked search terms",
    "exits": {},
},
```

`site-health`'s DataForSEO flag is exposed with a lower dashboard-side page
cap — the dashboard passes `--max-crawl-pages 20` by default instead of the
CLI's bare-metal default of 100, so a stray click crawls a bounded, cheap
amount (~$0.0025 at DataForSEO's $0.25/2,000-page rate) rather than the full
100-page default. The operator can still raise it — the field stays editable,
just pre-filled low.

One new arg kind, `text-list` (a list of free-text strings — the existing
`path-list` widget already renders "one per line"; `text-list` is the same
widget, differently validated server-side: no path-safety checks, ordinary
string list). `build_argv`'s kind dispatch in `server.py` gets one more
branch; `widget()` in `page-runs.js` reuses the existing multi-line textarea
rendering.

### 2.4 Frontend — new Analytics page

`pipeline/dashboard/static/analytics.html` + `page-analytics.js`, added to the
client nav (`app.js`'s nav array) alongside Findings / Worklist / Report / Git.

**Section 1 — Site Health Providers.** The provider-status-strip renderer
(`renderProviders`/`providerTone` in `page-findings.js`) moves into a small
shared module (`providers-strip.js`) so Findings and Analytics render it
identically instead of forking two copies. A "Re-check now" button launches
`site-health` with `with-crux`/`with-gsc`/`with-dataforseo` checked, using the
Runs screen's existing SSE log-streaming (`Run` class in `server.py` already
supports this — no new streaming plumbing), then reloads `findings.json` on
completion and re-renders the strip.

**Section 2 — Search Terms.** Reads `seed_queries` from
`GET /api/clients/:slug/config` (already exists, read-only, used by
`page-config.js` today) and the newest `findings.json`. One row per tracked
query: latest `serp.*` finding for that query (`context` field already
carries the query text — `parse_serp` sets it), any `gsc.*` finding whose
`location` matches the best-ranking page for that query. Three controls:

- **Add term** — text input, soft-capped at 5 manually-added terms (a distinct
  counter from agent-suggested ones); past 5 the UI asks "add anyway?" rather
  than blocking, per the requirement that the operator can always add more.
- **Suggest 5 with the agent** — runs `search-suggest`, streams
  `wf-seed-queries`'s log, then parses the printed `seed_queries:` YAML block
  from the run's captured stdout into a checklist the operator ticks before
  committing any of them (mirrors the existing human-review step the CLI
  already documents — the dashboard doesn't skip that review, it makes it a
  click instead of a copy-paste).
- **Check rank now** — runs `search-check` (SERP only, kept separate from the
  general provider recheck since it's the one that's billed per tracked term,
  so it never fires as a side effect of clicking the Section 1 button).

Both write actions (`search-add`, and ticking suggestions to keep) route
through the same commit reminder pattern `onboard.py` already prints for the
`SEO_AGENT` secret — a persistent, dismissible banner: *"N term(s) added to
seed_queries — commit `docs/client-config.yml` before the next cycle, or this
list resets to what's on disk."* The dashboard does not auto-commit; that
stays a deliberate, visible human action, same as every other config write in
this codebase.

---

## 3. Data flow

No new artifact files. `findings.json` already carries `providers` (a status
string per source asked for) and typed `crux.*`/`gsc.*`/`dfs.*`/`serp.*`
findings — this spec adds triggers and curation, not a new schema.

The only new persisted state is `seed_queries` growing inside the existing
`docs/client-config.yml`, through the new narrow writer, committed by the
operator exactly like the tier block is today.

Sequence for tracking a new term:
1. Dashboard reads current `seed_queries` + latest `findings.json`.
2. Operator types a term or accepts an agent suggestion → `search-add` appends
   to the config on disk.
3. Operator commits (banner reminds; dashboard's existing Git screen handles
   the actual commit UI — reused, not rebuilt).
4. Operator clicks "Check rank now" → `wf-site-health --with-serp` → new
   `findings.json` written, chained through the same ratchet every other
   finding goes through.
5. Page reloads and re-renders from the new file.

---

## 4. Error handling / cost guardrails

- Missing credentials: buttons stay clickable (the dashboard cannot know
  in advance without probing, and probing costs a request); the result is
  today's existing amber `"skipped: X_API_KEY unset"` in the status strip.
  No new error state needed — this already works correctly.
- Curation cap: soft, UI-level only (5 manual + 5 suggested, confirm to
  exceed) — never enforced server-side, since `--write` accepting more is a
  legitimate, requested use.
- DataForSEO cost: lower dashboard-side default page cap (§2.3), stated in
  the button's own label rather than a confirmation modal.
- Bright Data cost: button label states "1 paid request per tracked term."
- Trust boundary is unchanged: everything here runs through the dashboard's
  existing localhost-bind + per-run-token model (`server.py`), and none of it
  touches `.github/workflows/**` or the tier model — this is entirely
  operator-facing tooling, same class as the existing Runs screen.

---

## 5. Bundled fixes

- **CrUX origin resolution** (§2.1) — proven necessary today, small diff,
  reuses existing `curl_final_host`.
- **`docs/BUG-LEDGER.md` + `CHANGELOG.md`** — record that CrUX, DataForSEO, and
  Bright Data SERP were run live for the first time on 2026-08-14, closing the
  "never run against the live API" caveat carried in `providers.py`'s own
  comments and the 2026-08-12 handoff.
- **Explicitly not in scope:** turning any provider on by default inside
  `wf-onboard`. `measure.py`'s own comment is deliberate — *"measuring with
  them is a decision, not a default"* — and this spec does not reverse that.
  The dashboard makes the decision one click instead of a hand-typed flag; it
  does not make the decision for the operator.

---

## 6. Testing

- `crux_findings` origin resolution: unit test with a mocked `curl_final_host`
  seam, matching the module's existing pure-function/mocked-network test
  pattern (`_request` is already the seam every other provider test mocks).
- New `--write` mode on `wf-seed-queries`: unit tests for dedupe (case
  insensitive), refusal on an unparseable `seed_queries:` block, and that
  round-tripping preserves every other key in the file byte-for-byte —
  matching `bootstrap_config.py`'s existing round-trip test style.
- Dashboard JS (`page-analytics.js`, `providers-strip.js`): manual
  verification only. No JS test harness exists anywhere in this dashboard
  today (confirmed: no `*.test.js`, no jest/vitest in the tree) — adding one
  for a single new page would be new infrastructure this spec doesn't need.
