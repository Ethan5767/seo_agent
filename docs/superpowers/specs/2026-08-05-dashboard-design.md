# `wf-dashboard` — local operator console

**Status:** draft · **Date:** 2026-08-05 · **Reverses:** `SITE-AUDIT-PIPELINE.md` §intro, row 1

A single-operator, single-machine web UI for running the pipeline and reading its
artifacts. It runs on `127.0.0.1`, stores no state of its own, and holds no credentials.

This document is the **contract for the UI**, written so screens can be designed against
it before they are built. Every screen below is specified by the data it renders and the
data shapes are the ones already on disk.

---

## 0. Why this reverses a v3 decision

`SITE-AUDIT-PIPELINE.md` opens with:

| Decision | Consequence |
|---|---|
| Internal studio tooling, repos we have access to | **No dashboard, no multi-tenant anything** |

That decision killed v2's *Vercel dashboard with a pull-based worker* — a hosted,
multi-tenant, stateful service with accounts and a database, sitting between the operator
and the repos. That is still dead and this document does not revive it.

What this builds instead is a **local view over files that already exist**. It has no
host, no accounts, no tenancy, and no database. It runs the same `wf-*` commands you
would type, in the same checkouts, as the same user. If the process is killed, nothing is
lost: every artifact it displays is a JSON file in a client repo, and every action it
takes is a `git` or `gh` invocation that leaves its own record.

The v3 row stands as written. This is a different thing wearing a similar word, and the
distinction is the absence of state.

---

## 1. No database

**Supabase is not needed, and adding it would be a regression.**

The pipeline's data model is already durable, versioned, diffable, and synced:

| Data | Lives at | Provided by |
|---|---|---|
| Findings | `<client>/docs/audit/<YYYY-MM>/findings.json` | phase 1 (shipped) |
| Work items | `<client>/docs/audit/<YYYY-MM>/worklist.json` | phase 3 |
| Human report | `<client>/docs/audit/<YYYY-MM>/report.md` | phase 3 |
| Change map | `<client>/docs/audit/<YYYY-MM>/changelog.json` | phase 5 |
| Client config | `<client>/docs/client-config.yml` | shipped |
| History | the monthly folders, in git | git |
| Sync between machines | `git pull` | git |

A database would be a **second copy** of all of it, with its own schema to migrate, its
own backups to forget, and its own opportunity to disagree with the repo. `SITE-AUDIT-PIPELINE.md`
§1 is explicit that the worker holds no state, and that "there is nothing to back up and
nothing to migrate" is what makes the host swappable.

The one feature that intuitively demands a database is **trend over time** — findings
count per client per month. It does not: the monthly folders *are* the time series, and
reading twenty-four small JSON files takes milliseconds. Read them.

**The one condition that would reopen this:** a shared hosted instance serving more than
one operator. That brings auth, secrets handling, and a server, and at that point the
question is worth reasking. It is out of scope here by the answer to "one machine".

---

## 2. Discovery, not configuration

```
wf-dashboard [--clients-dir DIR] [--port 8765]
```

`--clients-dir` defaults to `~/clients`. The dashboard scans one level deep for
directories that are git repos **and** contain `docs/client-config.yml`. Each one is a
client; its slug is the `client:` key inside that file.

There is no roster file to maintain. Adding a client is cloning it. Removing one is
deleting the checkout. A directory that does not parse is listed with its error rather
than skipped silently — a client that has vanished from the fleet view because its YAML
broke is the failure mode worth spending a line of code to avoid.

**Model A holds.** No client data is written to this repo. The dashboard reads client
repos in place and writes only inside them.

---

## 3. Architecture

```
pipeline/dashboard/
  server.py            JSON API, static file serving, subprocess runner   (~350 lines)
  static/index.html    markup
  static/app.css       ← the design surface
  static/app.js        fetch + render + SSE
```

Python standard library only. The repo's sole runtime dependency is PyYAML and this adds
none. `http.server.ThreadingHTTPServer` serves the API, the static files, and the SSE
stream; every action shells out to a `wf-*` entry point, `git`, or `gh`.

Rejected: **FastAPI + uvicorn** (two dependencies to save ~80 lines of a server that is
already simple, and auto-generated API docs are worthless to a single-page frontend that
is written against the API by hand). **Next.js + React** (a full Node toolchain in a
Python repo, plus this same Python layer underneath it anyway, because every button
still ends in a subprocess — two runtimes to maintain for one localhost tool).

**The upgrade path stays open.** The frontend talks to the server only through the JSON
API in §5. If the UI outgrows vanilla JS, swap `static/` for a Vite build; the server
does not change.

---

## 4. The safety boundary

This is a web server that runs subprocesses. Two rules are load-bearing and both belong
in the first commit.

### 4.1 The command allow-list

`POST /api/runs` accepts a command **name**, looked up in a fixed dict that maps it to an
argv list. It never accepts a shell string, and `subprocess` is never called with
`shell=True`.

```python
COMMANDS = {
    "site-health": ["wf-site-health", "--project", "{project}"],
    "site-plan":   ["wf-site-plan",   "--project", "{project}"],
    "preflight":   ["wf-preflight",   "--project", "{project}"],
    # ...
}
```

Arguments the UI may supply (`--limit`, `--url`) are declared per command with a type and
validated before they join the argv list. `{project}` resolves only to a path the scan in
§2 discovered.

Without this, the dashboard is a remote shell bound to a port.

### 4.2 Token and Origin

`127.0.0.1` is not a trust boundary. Any page open in the operator's browser can `POST`
to localhost. The server therefore:

- prints a random token at startup and requires it in an `X-Dashboard-Token` header
- rejects any request carrying an `Origin` header that is not its own

Roughly ten lines, and it closes a real hole in a tool whose endpoints start processes
and push commits.

### 4.3 No merge, ever

The dashboard may pull, branch, commit, push, and open a PR. It **may not merge**, and it
may not push a client's default branch.

`SITE-AUDIT-PIPELINE.md` §1 makes human merge the only path to production, and the entire
safety argument for letting a model write files rests on it. A merge button beside a green
checkmark is not the same act as reading a diff. The PR screen links out to GitHub; the
merge happens there.

### 4.4 No credentials

The dashboard stores no tokens and reads no `.env`. `git` and `gh` use the operator's
existing local authentication. There is nothing in this tool for a leak to take.

---

## 5. API

All responses are JSON. All mutating routes require the token from §4.2.

| Method | Route | Returns / does |
|---|---|---|
| `GET` | `/api/clients` | Fleet summary — one entry per discovered client |
| `GET` | `/api/clients/{slug}` | Client detail: config, available cycles, git state |
| `GET` | `/api/clients/{slug}/config` | Parsed `client-config.yml` |
| `PUT` | `/api/clients/{slug}/config` | Validated write-back (§7.6) |
| `GET` | `/api/clients/{slug}/cycles` | `["2026-08", "2026-07", ...]`, newest first |
| `GET` | `/api/clients/{slug}/cycles/{ym}` | Every artifact present in that folder, plus which are absent |
| `POST` | `/api/clients/{slug}/runs` | `{command, args}` → `{run_id}` |
| `GET` | `/api/runs` | Run history for this session |
| `GET` | `/api/runs/{run_id}` | Status, exit code, interpretation |
| `GET` | `/api/runs/{run_id}/stream` | **SSE.** `line` events, then one `exit` event |
| `POST` | `/api/clients/{slug}/git` | `{action}` — `pull` · `branch` · `commit` · `push` · `pr` |

### Fleet entry shape

```jsonc
{
  "slug": "acme-roofing",
  "domain": "acmeroofing.com",
  "path": "/Users/ethan/clients/acme-roofing-site",
  "tier": 1,
  "latest_cycle": "2026-08",
  "findings_total": 47,
  "findings_by_lane": { "NEW": 3, "PERSISTING": 41, "REGRESSION": 3, "RESOLVED": 12 },
  "git": { "branch": "cycle/acme-roofing-2026-08", "dirty": true,
           "ahead": 2, "behind": 0, "pr": { "number": 118, "state": "open" } },
  "error": null
}
```

`findings_by_lane` is `null` until phase 3 — phase 1's `findings.json` has no lanes.
`error` carries a parse or discovery failure and the fleet row renders in an error state
rather than disappearing.

### Run logs

Runs stream over SSE and are also written to `~/.cache/seo_agent/runs/{run_id}.log`, so a
browser refresh does not lose the output of a run that already finished. Not in the client
repo: a run log is machine noise, not an artifact. `rm -rf ~/.cache/seo_agent` is the
cleanup story.

Run history is per-process. There is no run database, and this is deliberate: the durable
record of what a run did is the artifact it wrote and the commit it produced.

---

## 6. Data shapes the UI renders

### `findings.json` — phase 1, shipped

```jsonc
{
  "schema": "site-health/1",
  "generated": "2026-08-05",
  "domain": "example.com",
  "urls_checked": 12,
  "urls_unreachable": 0,
  "findings": [
    { "gate": "site_health", "code": "health.title_length", "location": "/roofing/",
      "context": "", "detail": "len=71", "ordinal": 0, "fingerprint": "a3f9…" }
  ]
}
```

Field meanings, from `pipeline/lib/baseline.py:194`:

- **`code`** — the rule that fired. Eighteen exist; see the phase 1 spec §2.
- **`location`** — URL path. Never absolute, never a line number.
- **`context`** — stable identity of the offending thing (the `src` of an image, the
  matched rule pattern). Empty for most codes.
- **`detail`** — volatile numbers (`len=71`, `count=3`, `status=404`). **Excluded from the
  fingerprint**, so a finding cannot become "new" by getting worse.
- **`ordinal`** — disambiguates repeated identical findings on one page.
- **`fingerprint`** — the identity phase 3's ratchet compares on.

### `worklist.json` — phase 3

```jsonc
{
  "id": "wi-2026-08-0031",
  "finding_fp": "a3f9…",
  "url": "/roof-replacement-charlotte-nc/",
  "kind": "meta_description_out_of_band",
  "lane": "REGRESSION",
  "evidence": { "current": "…", "length": 71 },
  "acceptance": { "check": "meta_desc_length", "expect": { "min": 120, "max": 160 } }
}
```

The worklist carries only what the client's tier permits. Findings the tier cannot act on
appear in the report as **not actionable at your tier** — visible and counted, never
silently dropped (`SITE-AUDIT-PIPELINE.md` §4.6). The UI must preserve that distinction;
collapsing it would hide the signal that a client should move up a tier.

---

## 7. Screens

Eight screens. Phases 3–8 do not exist yet, so screens whose producer is unbuilt render an
**empty state naming the phase that ships them**. All eight can be designed now.

### 7.1 Fleet — the landing screen

One row or card per client: slug, domain, tier badge, total findings, lane breakdown, last
run date, git state, open PR number.

Git state has five renderings and they are not interchangeable: **clean** · **dirty**
(uncommitted work) · **ahead** (unpushed commits — the state that silently loses work) ·
**behind** (stale checkout) · **error** (the client failed to load).

### 7.2 Client detail

Header: domain, tier, topology class, build framework. A cycle picker (`2026-08`,
`2026-07`, …) that scopes the three artifact tabs below it.

### 7.3 Findings

The densest screen, and the one worth the most design attention. A table of `findings[]`
with:

- grouping toggle: **by code** (which rules fire most) or **by URL** (which pages are
  worst)
- filter by code, by lane, by URL substring
- `detail` shown inline; `context` shown where non-empty
- counts that stay visible while filtered, so a filter cannot be mistaken for a fix

Empty state, zero findings: distinguish **clean** from **not yet run** — they look
identical in a naive table and mean opposite things.

Two codes are known-noisy by design (`health.schema_faq_missing`,
`health.schema_breadcrumb_missing` fire on nearly every page; phase 1 spec §2). The UI
should not special-case them, but a group-by-code view makes their volume self-evident,
which is the point.

### 7.4 Worklist — phase 3

Work items with their `acceptance` criteria, split into **actionable at this tier** and
**not actionable at this tier**. Each item links to the finding it derives from.

### 7.5 Report — phase 3

`report.md`, rendered. Four lanes: RESOLVED · PERSISTING · NEW · REGRESSION.

### 7.6 Config editor — phase 2

A form over `docs/client-config.yml`, scoped to the tiering block: `tier`, `text_paths`,
`content.location`, `content.registry`, `content.format`.

- The **deny-list is shown but flagged**. It is the shortest, most load-bearing part of
  v3 (§2) and editing it needs friction, not convenience.
- **No `content.location` → T2 is unavailable.** The form enforces this rather than
  letting an invalid tier be saved.
- Writes are validated before hitting disk, and the file is round-tripped through YAML
  so comments in the starter template are not destroyed. If comment preservation proves
  awkward with `PyYAML` alone, the editor falls back to opening the file in `$EDITOR` and
  reloading — an acceptable outcome that beats silently eating a 16KB commented config.

### 7.7 Run console

Command picker, per-command argument inputs, and a live streaming log.

**Exit codes render as sentences, not numbers.** The codes are meaningful and a bare `19`
communicates nothing:

| exit | rendering |
|---|---|
| 0 | Clean — every URL passed |
| 1 | Findings written |
| 2 | Usage error — bad arguments, or a sitemap with no `<loc>` entries |
| 19 | **Refused** — every source unreachable. Nothing was written |
| 9 | **Refused** — a BLOCK finding. No PR |
| 15 | Emitted, some pages held for curation |
| 16 | **Refused** — nothing to process |

A refusal must read as a refusal. The distinction exit 19 exists to protect — a run that
measured nothing is not a clean site — is destroyed by a UI that shows a green
"completed" chip.

### 7.8 Git and PR

Branch state, changed-file summary, and the action buttons: **pull** · **create cycle
branch** · **commit artifacts** · **push** · **open PR**.

Merge is a link to the PR on GitHub. There is no merge button (§4.3).

---

## 8. Testing

One file, `tests/test_dashboard.py`, hermetic, in the style of the existing suite.

- An unknown command name is rejected; a command name is never string-interpolated into a
  shell. **The security property, and the one worth a test above all others.**
- Argument validation rejects a `--limit` that is not a positive integer.
- Discovery finds a directory with `docs/client-config.yml` and ignores one without.
- A client whose YAML fails to parse appears in `/api/clients` with `error` set, rather
  than being dropped.
- A request without the token is refused; a request with a foreign `Origin` is refused.
- The config write-back round-trips a config unchanged.
- Exit-code interpretation maps 19 to a refusal, not a success.

No fixtures beyond `tmp_path`, no network, no real client repo.

---

## 9. Documentation, per the sync contract

Shipped in the same commit as the code:

- `CHANGELOG.md` under `[Unreleased]` — the new `wf-dashboard` command and its scope
- `docs/MODULES.md` — the new `pipeline/dashboard/` package
- `SITE-AUDIT-PIPELINE.md` — a note on the §intro row, per §0 above, so the two documents
  do not disagree
- `pytest -q` output pasted into the CHANGELOG entry, not paraphrased

`docs/gate-reference.md` is untouched. The dashboard is an operator tool, not a gate.

---

## 10. Not built

- **No database.** §1.
- **No auth, accounts, or multi-tenancy.** One operator, one machine.
- **No hosting.** `127.0.0.1` only. It is never exposed, and nothing in it is designed to
  survive being exposed.
- **No websockets.** SSE is one-directional and that is the only direction needed.
- **No build step, no bundler, no state-management library.**
- **No run history beyond the session** and the log files in `~/.cache`.
- **No notifications.** The runs are seconds to minutes and you started them.
- **No merge.** §4.3.

---

## 11. Open question — when this ships

Phases 1 through 3 produce `findings.json`, `worklist.json`, and `report.md`. Today only
the first exists. A full control plane built now would render one populated screen and
five empty states.

Two defensible orders:

**Build it after phase 3** — every artifact screen has real data on day one, and the
findings table can be designed against a real month of output rather than a schema.
`SITE-AUDIT-PIPELINE.md` §7 already calls phase 3 "the highest-value stopping point".

**Build the fleet view and run console now** (§7.1, §7.7, §7.8) and add artifact screens
as their producers land. These three are useful against phase 1 alone: they replace
remembering which client repo is stale and what `--limit` does.

The second is recommended, and it costs nothing to defer: the API in §5 is shaped by the
artifact schemas, which are already fixed by the v3 doc, so the screens added later do not
disturb the ones built first.
