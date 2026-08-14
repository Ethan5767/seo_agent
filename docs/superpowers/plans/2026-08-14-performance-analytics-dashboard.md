# Performance Analytics — Stronger Flow + Analytics Dashboard Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the CrUX exact-origin bug proven live on 2026-08-14, then give the dashboard a way to trigger CrUX/GSC/DataForSEO re-checks and to curate and track Bright Data SERP search terms — all for already-onboarded clients, using credentials the operator already has in their shell environment.

**Architecture:** Backend: one bug fix in `providers.py` (reuse the existing `curl_final_host` helper), one new append-only write mode on the existing `wf-seed-queries` CLI (text-based edit, same pattern as `wf-bootstrap-config --add-tier`, never a PyYAML round-trip), and three new entries in the dashboard's `COMMANDS` allow-list. Frontend: a shared provider-status-strip module (currently duplicated nowhere, but about to be needed twice) extracted out of `page-findings.js`, and one new dashboard page (`analytics.html` + `page-analytics.js`) that triggers runs through the dashboard's existing run-launch/SSE-streaming plumbing — no new streaming, auth, or storage layer.

**Tech Stack:** Python 3.10+ (stdlib only — PyYAML is the repo's one runtime dependency), pytest, vanilla JS + Tailwind CDN (no build step, no framework — matches every existing dashboard page).

## Global Constraints

- **No secrets in the repo.** Credentials stay environment-variable-only; nothing in this plan reads or writes a `.env` file. (CLAUDE.md §"No secrets. No client PII.")
- **`docs/client-config.yml` is edited text-in-place, never via `yaml.safe_load`/`dump`.** The file is mostly hand-written comments; a full parse-and-rewrite round-trip eats them (this is why `bootstrap_config.add_tier` does the same thing).
- **Every finding a provider produces is written to `findings.json` through the existing schema.** No new artifact files.
- **A command that did nothing must say so, not read as success.** Every new dashboard command declares its real exit-code vocabulary in `COMMANDS`, matching the existing pattern.
- **`git pull --ff-only` before starting, and re-run before the final commit** — CLAUDE.md's sync contract; this repo has two operators.
- **`pytest -q` output must be pasted into the final CHANGELOG entry, not paraphrased or guessed at.** (CLAUDE.md §4, "proof or it did not happen.")
- **CHANGELOG.md `[Unreleased]` gets an entry in the same commit as the behavior change it describes** — not deferred to a later commit.
- Docs-only changes may commit directly; everything else follows the repo's ordinary "pull, test, diff --stat, push" checklist.

---

### Task 1: CrUX queries the domain's real serving origin, not the literal config string

**Files:**
- Modify: `pipeline/audit/providers.py:118-148` (`crux_findings`)
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: `pipeline.lib.common.curl_final_host(url: str) -> str` (already exists, returns `""` on an unreachable/timed-out URL — see `pipeline/lib/common.py:51-70`).
- Produces: `crux_findings(domain: str, urls=None) -> tuple[list[Finding], str]` — same public signature as today; callers (`measure.py:294`) need no change.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_providers.py`, in the CrUX section (after the existing `test_crux_*` tests, before the GSC section):

```python
def test_crux_queries_the_resolved_origin_not_the_configured_domain(monkeypatch):
    """A client configured as the bare apex whose site redirects to www must be
    queried at the host Chrome actually recorded traffic against — proven live
    2026-08-14: bare wikipedia.org had no CrUX record, en.wikipedia.org did."""
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "www.example.com")
    seen = []

    def fake(endpoint, payload=None, headers=None, timeout=45):
        seen.append(payload)
        return {"record": {}}, None

    monkeypatch.setattr(p, "_request", fake)
    findings, status = p.crux_findings("example.com")
    assert seen == [{"origin": "https://www.example.com"}]
    assert "resolved to www.example.com" in status


def test_an_unresolvable_domain_falls_back_to_the_configured_string(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "")
    seen = []

    def fake(endpoint, payload=None, headers=None, timeout=45):
        seen.append(payload)
        return {"record": {}}, None

    monkeypatch.setattr(p, "_request", fake)
    findings, status = p.crux_findings("example.com")
    assert seen == [{"origin": "https://example.com"}]
    assert "resolved to" not in status


def test_per_url_mode_does_not_resolve_the_origin(monkeypatch):
    """Per-URL queries are already absolute; resolution only applies to the
    origin-level default path."""
    monkeypatch.setenv("CRUX_API_KEY", "k")

    def boom(url):
        raise AssertionError("curl_final_host must not be called in per-URL mode")

    monkeypatch.setattr(p, "curl_final_host", boom)
    monkeypatch.setattr(p, "_request", lambda *a, **k: ({"record": {}}, None))
    findings, status = p.crux_findings("example.com", urls=["https://example.com/a/"])
    assert status.startswith("ok:")


def test_the_no_field_data_message_names_the_resolved_host(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "www.example.com")
    monkeypatch.setattr(p, "_request", lambda *a, **k: (None, "HTTP 404 from x"))
    findings, status = p.crux_findings("example.com")
    assert findings == []
    assert "www.example.com" in status
    assert "too little traffic" in status
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_providers.py -k "resolved_origin or unresolvable_domain or per_url_mode or no_field_data_message" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'curl_final_host'` (it isn't imported into `providers.py` yet).

- [ ] **Step 3: Add the import**

In `pipeline/audit/providers.py`, add to the imports (after the stdlib imports, before `from pipeline.lib.baseline import ...`):

```python
from pipeline.lib.common import curl_final_host
```

- [ ] **Step 4: Rewrite `crux_findings`**

Replace `pipeline/audit/providers.py:118-148` with:

```python
def crux_findings(domain: str, urls=None) -> tuple:
    """(findings, status). Origin-level by default; per-URL when `urls` is given.

    A 404 from CrUX means the origin has too little traffic to have field data.
    That is a fact about the dataset, not a defect in the site, so it emits no
    finding — but it is reported in the status so nobody reads the silence as a
    pass.

    Origin-level queries target the domain's REAL serving host, not the literal
    config string. CrUX is not redirect-aware: a client configured as the bare
    apex that 301s to `www` (or vice versa) has almost no Chrome navigations
    recorded against the un-redirected host, so querying it returns "no record"
    even when the real origin has field data. Proven live 2026-08-14: bare
    `wikipedia.org` had no CrUX record, `en.wikipedia.org` — the real serving
    origin — did. `curl_final_host` (built for B-037) resolves it; an
    unresolvable domain falls back to the literal string, so this is never
    worse than before the fix. Per-URL mode is untouched — those URLs are
    already absolute.
    """
    key = os.environ.get("CRUX_API_KEY")
    if not key:
        return [], "skipped: CRUX_API_KEY unset"

    endpoint = f"https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={key}"
    if urls:
        targets = [("url", u, "/" + u.split("//", 1)[-1].split("/", 1)[-1]) for u in urls]
        report_domain = domain
    else:
        report_domain = curl_final_host(f"https://{domain}") or domain
        targets = [("origin", f"https://{report_domain}", "/")]

    findings, missing, errors = [], 0, []
    for field, value, location in targets:
        doc, err = _request(endpoint, {field: value})
        if err:
            if "404" in err:
                missing += 1
            else:
                errors.append(err)
            continue
        findings += parse_crux((doc or {}).get("record") or {}, location)

    resolved_note = f" (resolved to {report_domain})" if report_domain != domain else ""
    if errors:
        return assign_ordinals(findings), \
            f"partial: {len(errors)} request(s) failed ({errors[0]}){resolved_note}"
    if missing == len(targets):
        return [], f"no field data: CrUX has no record for {report_domain} " \
                   f"(too little traffic){resolved_note}"
    return assign_ordinals(findings), f"ok: {len(targets)} record(s){resolved_note}"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_providers.py -v`
Expected: all PASS, including the pre-existing CrUX tests (they don't set `curl_final_host`, so it hits the real function — confirm none of them set `CRUX_API_KEY` in a way that reaches the network; the existing skip test explicitly unsets it, and the pure `parse_crux` tests never call `crux_findings` at all, so this is safe).

- [ ] **Step 6: Commit**

```bash
git add pipeline/audit/providers.py tests/test_providers.py
git commit -m "fix: CrUX queries the domain's real serving origin, not the config string

Proven live 2026-08-14 against wikipedia.org vs en.wikipedia.org: a bare
domain that redirects has no CrUX record even when the real origin does.
Resolves via the existing curl_final_host helper; falls back to the
configured domain if resolution fails."
```

---

### Task 2: `wf-seed-queries --write` — append search terms without touching anything else in the config

**Files:**
- Modify: `pipeline/audit/seed_queries.py`
- Test: `tests/test_seed_queries.py`

**Interfaces:**
- Produces: `write_seed_queries(target: Path, new_queries: list[str]) -> int` — `0` on success (including the idempotent "nothing new" case), `4` refused (blank input, or an existing `seed_queries:` that is not a plain block list).
- CLI: `wf-seed-queries --project <dir> --write "term one" --write "term two"` — repeatable flag, one term per occurrence, matching the dashboard's `text-list` arg kind (Task 3).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_seed_queries.py` (new section at the end, after the existing CLI-stub tests):

```python
# ── write_seed_queries: the config-editing seam ──────────────────────────────

def test_write_seed_queries_appends_a_new_block_when_the_key_is_absent(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("domain: example.com\ntier: 1\n")
    code = sq.write_seed_queries(target, ["Top AI agency in Cambodia"])
    assert code == 0
    text = target.read_text()
    assert "seed_queries:" in text
    assert "  - Top AI agency in Cambodia" in text
    assert "domain: example.com" in text
    assert "tier: 1" in text


def test_write_seed_queries_appends_to_an_existing_block(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("seed_queries:\n  - existing term\ntier: 1\n")
    code = sq.write_seed_queries(target, ["new term"])
    assert code == 0
    text = target.read_text()
    assert text.index("- existing term") < text.index("- new term")
    assert text.count("tier: 1") == 1


def test_write_seed_queries_dedupes_case_insensitively(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("seed_queries:\n  - Existing Term\n")
    code = sq.write_seed_queries(target, ["existing term"])
    assert code == 0
    assert target.read_text().count("  - ") == 1


def test_write_seed_queries_refuses_a_flow_style_list(tmp_path):
    target = tmp_path / "client-config.yml"
    original = "seed_queries: [already, here]\n"
    target.write_text(original)
    code = sq.write_seed_queries(target, ["new term"])
    assert code == 4
    assert target.read_text() == original


def test_write_seed_queries_rejects_blank_input(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("tier: 1\n")
    code = sq.write_seed_queries(target, ["   ", ""])
    assert code == 4
    assert target.read_text() == "tier: 1\n"


def test_write_seed_queries_inserts_right_after_the_last_existing_item_even_with_a_trailing_key(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("seed_queries:\n  - one\n  - two\ntier: 1\n")
    code = sq.write_seed_queries(target, ["three"])
    assert code == 0
    text = target.read_text()
    assert text == "seed_queries:\n  - one\n  - two\n  - three\ntier: 1\n"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_seed_queries.py -k write_seed_queries -v`
Expected: FAIL — `AttributeError: module 'pipeline.audit.seed_queries' has no attribute 'write_seed_queries'`.

- [ ] **Step 3: Add the `Path` import**

In `pipeline/audit/seed_queries.py`, add after the existing `from urllib.parse import urlsplit` line:

```python
from pathlib import Path
```

- [ ] **Step 4: Implement `write_seed_queries`**

Add to `pipeline/audit/seed_queries.py`, immediately before the `# ── the CLI ──` section marker:

```python
# ── write_seed_queries: append-only, text-based, same shape as add_tier ──────
_SEED_KEY_RE = re.compile(r"^seed_queries:[ \t]*\n", re.M)
_SEED_ITEM_RE = re.compile(r"^[ \t]*-[ \t]*(.+?)[ \t]*$", re.M)


def write_seed_queries(target: Path, new_queries: list) -> int:
    """Append new_queries to seed_queries: in an EXISTING docs/client-config.yml.

    Text-based, like bootstrap_config.add_tier — PyYAML round-tripping this file
    eats its comments. Refuses (4) rather than guess when seed_queries: exists
    but is not a plain block list (`seed_queries: []` or flow-style `[a, b]`):
    editing that safely needs a real parser, and this module deliberately
    doesn't carry one for this file. Appends a fresh commented block when the
    key is absent entirely, matching add_tier's append-at-end shape. Dedupes
    case-insensitively; a query already tracked is skipped, not re-added,
    because the query text is part of every SERP finding's fingerprint.
    """
    text = target.read_text()
    cleaned = [q.strip() for q in new_queries if q and q.strip()]
    if not cleaned:
        print("[ERROR] no non-blank query given", file=sys.stderr)
        return 4

    key_match = _SEED_KEY_RE.search(text)
    if key_match is None:
        if re.search(r"^seed_queries:", text, re.M):
            print(f"[ERROR] seed_queries: exists in {target} but is not a plain "
                  f"block list — refusing to edit it blind. Edit it by hand.",
                  file=sys.stderr)
            return 4
        block = ("\nseed_queries:                     # Bright Data SERP tracks "
                  "these — one paid request each per cycle\n"
                  + "".join(f"  - {q}\n" for q in cleaned))
        target.write_text(text.rstrip("\n") + "\n" + block)
        print(f"[OK] Added seed_queries: to {target} with {len(cleaned)} term(s).")
        print("[NEXT] Commit docs/client-config.yml.")
        return 0

    rest = text[key_match.end():]
    body_end = 0
    for line in rest.splitlines(keepends=True):
        if re.match(r"^[ \t]*-[ \t]*.+$", line):
            body_end += len(line)
        else:
            break
    body = rest[:body_end]
    existing = [m.group(1) for m in _SEED_ITEM_RE.finditer(body)]
    have = {q.lower() for q in existing}

    to_add = []
    for q in cleaned:
        if q.lower() in have:
            print(f"[INFO] already tracked, skipped: {q}")
            continue
        have.add(q.lower())
        to_add.append(q)
    if not to_add:
        print("[OK] Nothing new — every term given is already tracked.")
        return 0

    insert_at = key_match.end() + body_end
    addition = "".join(f"  - {q}\n" for q in to_add)
    target.write_text(text[:insert_at] + addition + text[insert_at:])
    print(f"[OK] Added {len(to_add)} term(s) to seed_queries: in {target}.")
    print("[NEXT] Commit docs/client-config.yml.")
    return 0
```

- [ ] **Step 5: Wire `--write` into the CLI**

In `pipeline/audit/seed_queries.py`, in `main()`, add the argument (after the existing `--timeout` argument, before `args = ap.parse_args()`):

```python
    ap.add_argument("--write", action="append", default=[], metavar="QUERY",
                    help="append this query to seed_queries: in docs/client-config.yml "
                         "and exit — skips the crawl and the agent entirely")
```

Then, immediately after `args = ap.parse_args()` and **before** the `shutil.which("claude")` check, add:

```python
    if args.write:
        target = Path(args.project) / "docs" / "client-config.yml"
        if not target.exists():
            print(f"[ERROR] {target} does not exist", file=sys.stderr)
            return 2
        return write_seed_queries(target, args.write)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_seed_queries.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add pipeline/audit/seed_queries.py tests/test_seed_queries.py
git commit -m "feat: wf-seed-queries --write appends terms without the crawl or the agent

Text-based, append-only edit of seed_queries: in docs/client-config.yml —
same pattern as wf-bootstrap-config --add-tier. Dedupes case-insensitively,
refuses rather than guesses on a flow-style list, never touches anything
else in the file."
```

---

### Task 3: Dashboard `COMMANDS` — expose provider flags, add search-suggest/search-add/search-check

**Files:**
- Modify: `pipeline/dashboard/server.py:48-` (`COMMANDS`), `:309-355` (`build_argv`)
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `write_seed_queries` CLI flag from Task 2 (`--write`), `--with-crux`/`--with-gsc`/`--with-dataforseo`/`--with-serp`/`--max-crawl-pages` flags on `wf-site-health` (already exist on the CLI — `pipeline/audit/measure.py:249-260`).
- Produces: `build_argv(command, project, args)` gains a `text-list` argument kind; `COMMANDS` gains `search-suggest`, `search-add`, `search-check`; `site-health`'s declared args grow. Frontend (Task 5) calls these by name via the existing `POST /api/clients/:slug/runs`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dashboard.py` (in the `build_argv` section, after the existing cycle-argument tests):

```python
def test_text_list_argument_accepts_real_terms():
    argv = build_argv("search-add", "/p", {"write": ["Top AI agency in Cambodia", "best seo phnom penh"]})
    assert argv == ["wf-seed-queries", "--project", "/p",
                     "--write", "Top AI agency in Cambodia",
                     "--write", "best seo phnom penh"]


def test_text_list_argument_must_be_a_list():
    with pytest.raises(ValueError):
        build_argv("search-add", "/p", {"write": "Top AI agency in Cambodia"})


@pytest.mark.parametrize("bad", ["", "   ", "x" * 201])
def test_text_list_argument_rejects_blank_or_oversized_terms(bad):
    with pytest.raises(ValueError):
        build_argv("search-add", "/p", {"write": [bad]})


def test_site_health_provider_flags_are_declared():
    argv = build_argv("site-health", "/p",
                       {"with-crux": True, "with-gsc": True,
                        "with-dataforseo": True, "max-crawl-pages": 20})
    assert "--with-crux" in argv
    assert "--with-gsc" in argv
    assert "--with-dataforseo" in argv
    assert "--max-crawl-pages" in argv and "20" in argv


def test_search_check_runs_serp_only():
    argv = build_argv("search-check", "/p", {})
    assert argv == ["wf-site-health", "--project", "/p", "--with-serp"]


def test_search_suggest_caps_the_agent_at_five():
    argv = build_argv("search-suggest", "/p", {})
    assert argv == ["wf-seed-queries", "--project", "/p", "--limit", "5"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k "text_list or provider_flags or search_check or search_suggest" -v`
Expected: FAIL — `ValueError: unknown argument for site-health: with-crux` and `ValueError: unknown command: search-add` (etc.).

- [ ] **Step 3: Add the `text-list` kind to `build_argv`**

In `pipeline/dashboard/server.py`, in `build_argv` (around line 342-343), insert a new branch immediately before `elif kind == "flag":`:

```python
        elif kind == "text-list":
            # Free-text terms (search queries), not paths — no path-safety
            # regex, just a length bound so one `--write` cannot smuggle a
            # multi-kilobyte string into an argv the shell never sees anyway.
            if not isinstance(value, list):
                raise ValueError(f"{key} must be a list")
            for item in value:
                stripped = item.strip() if isinstance(item, str) else ""
                if not (1 <= len(stripped) <= 200):
                    raise ValueError(f"bad {key} value: {item!r}")
                argv += [f"--{key}", stripped]
```

- [ ] **Step 4: Update `site-health` and add the three search commands**

In `pipeline/dashboard/server.py`, replace the `"site-health"` entry in `COMMANDS` (currently lines 54-60):

```python
    "site-health": {
        "argv": ["wf-site-health", "--project", "{project}"],
        "args": {"limit": "int", "url": "path-list",
                 "with-crux": "flag", "with-gsc": "flag", "with-dataforseo": "flag",
                 "max-crawl-pages": "int"},
        "label": "Measure live site",
        "exits": {},
        "then": "site-plan",
    },
```

Then add three new entries immediately after the `"site-plan"` entry:

```python
    "search-suggest": {
        "argv": ["wf-seed-queries", "--project", "{project}", "--limit", "5"],
        "args": {},
        "label": "Suggest 5 search terms (agent-grounded)",
        "exits": {
            2: ("error", "`claude` is not on PATH — nothing to generate with"),
            19: ("error", "the sitemap could not be crawled for grounding"),
            20: ("error", "the agent's reply was not a usable query list"),
        },
    },
    "search-add": {
        "argv": ["wf-seed-queries", "--project", "{project}"],
        "args": {"write": "text-list"},
        "label": "Add search term(s) to track",
        "exits": {
            4: ("refused", "REFUSED — seed_queries: is not a plain list, or every "
                           "term given was blank"),
        },
    },
    "search-check": {
        "argv": ["wf-site-health", "--project", "{project}", "--with-serp"],
        "args": {},
        "label": "Check rank for tracked search terms",
        "exits": {},
    },
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/dashboard/server.py tests/test_dashboard.py
git commit -m "feat: dashboard COMMANDS — provider flags on site-health, search-suggest/add/check

Exposes the existing --with-crux/--with-gsc/--with-dataforseo flags for the
dashboard to trigger. Adds search-suggest (wraps wf-seed-queries --limit 5),
search-add (wraps the new --write mode), and search-check (SERP-only re-run,
kept separate since it's billed per tracked term)."
```

---

### Task 4: Extract the provider-status strip into a shared module

**Files:**
- Create: `pipeline/dashboard/static/providers-strip.js`
- Modify: `pipeline/dashboard/static/page-findings.js` (remove `providerTone`/`renderProviders`, lines 47-71)
- Modify: `pipeline/dashboard/static/findings.html` (add a `<script>` tag)

**Interfaces:**
- Produces: two globals, `providerTone(status: string) -> string` (a Tailwind text-color class) and `renderProviders(providers: object) -> void` (renders into `#providers` in the current document). No module system is used anywhere in this dashboard (every helper in `app.js` is a bare global function referenced from page-specific scripts) — this file follows the same convention.
- Consumes: the global `esc(s)` helper from `app.js` (already loaded first on every page).

- [ ] **Step 1: Create the shared module**

Write `pipeline/dashboard/static/providers-strip.js`:

```javascript
// Shared provider-status-strip renderer — used by Findings and Analytics.
//
// measure.py writes a status string per external source it was asked for, for
// one reason: a provider that returned nothing because it was never asked must
// not read as a provider that returned nothing because the site is clean.
//
// Three tones, because only one of them means "this number is complete":
// green `ok:`, red `failed:`, amber for everything else (skipped, partial,
// timed out, no field data). Amber is not a warning about the site, it is a
// warning about the measurement.
function providerTone(status) {
  if (status.startsWith('ok:')) return 'text-green-400';
  if (status.startsWith('failed:')) return 'text-error';
  return 'text-tertiary';
}

function renderProviders(providers) {
  const el = document.getElementById('providers');
  const names = Object.keys(providers || {}).sort();
  if (!names.length) {
    // The empty case is the one that misleads, so it is the loudest. An
    // HTTP-only cycle is a real measurement, just not of anything a provider
    // sees — and nothing else on this screen would say so.
    el.innerHTML = `<span class="font-mono-sm text-mono-sm text-tertiary">`
      + `HTTP-only cycle — no external provider ran. CrUX, Search Console, `
      + `DataForSEO and Bright Data findings are absent because they were never `
      + `asked for, not because the site is clean.</span>`;
    return;
  }
  el.innerHTML = `<span class="font-label-caps text-label-caps text-on-surface-variant shrink-0">PROVIDERS</span>`
    + names.map((n) => `<span class="font-mono-sm text-mono-sm whitespace-nowrap shrink-0">`
        + `<span class="text-on-surface">${esc(n)}</span> `
        + `<span class="${providerTone(String(providers[n]))}">${esc(String(providers[n]))}</span>`
      + `</span>`).join('');
}
```

- [ ] **Step 2: Remove the duplicated functions from `page-findings.js`**

In `pipeline/dashboard/static/page-findings.js`, delete lines 35-71 (the `providerTone` and `renderProviders` function definitions, including their comment block). The call site at line 28 (`renderProviders(doc.providers);`) stays exactly as it is — it now resolves to the global defined in `providers-strip.js`.

- [ ] **Step 3: Load the shared module on the Findings page**

In `pipeline/dashboard/static/findings.html`, change:

```html
<script src="/static/app.js"></script>
<script src="/static/page-findings.js"></script>
```

to:

```html
<script src="/static/app.js"></script>
<script src="/static/providers-strip.js"></script>
<script src="/static/page-findings.js"></script>
```

- [ ] **Step 4: Manually verify**

Run: `wf-dashboard --clients-dir ~/clients` (or whatever `--clients-dir` this machine uses), open a client's Findings page in a browser, confirm the PROVIDERS strip still renders exactly as before (either the amber "HTTP-only cycle" message or the per-provider status line). This dashboard has no JS test harness (confirmed: no `*.test.js`, no jest/vitest anywhere in the tree) — this manual check is the verification, matching how every other dashboard screen here is tested.

- [ ] **Step 5: Commit**

```bash
git add pipeline/dashboard/static/providers-strip.js pipeline/dashboard/static/page-findings.js pipeline/dashboard/static/findings.html
git commit -m "refactor: extract the provider-status strip into a shared module

Findings and the new Analytics page (next commit) both need it; forking two
copies would let them drift. No behavior change on the Findings page."
```

---

### Task 5: Analytics page — Section 1, Site Health Providers

**Files:**
- Modify: `pipeline/dashboard/server.py:439-442` (`PAGES`)
- Modify: `pipeline/dashboard/static/app.js:42-53` (`NAV`)
- Create: `pipeline/dashboard/static/analytics.html`
- Create: `pipeline/dashboard/static/page-analytics.js`

**Interfaces:**
- Consumes: `GET /api/clients/:slug/config` (existing, returns the parsed config as JSON — used today by `page-config.js`), `GET /api/clients/:slug/cycles` and `GET /api/clients/:slug/cycles/:ym` (existing, used today by `page-findings.js` — `bundle.artifacts['findings.json']`), `POST /api/clients/:slug/runs` (existing), global helpers from `app.js` (`api`, `post`, `esc`, `requireClient`, `streamRun`, `fail`) and `providers-strip.js` (`renderProviders`, Task 4).
- Produces: page-level globals `cfg` (the parsed config) and `latestFindings` (the newest cycle's `findings.json`, or `null`) that Task 6 (Section 2) reads.

- [ ] **Step 1: Register the route**

In `pipeline/dashboard/server.py`, change the `PAGES` dict (lines 439-442) from:

```python
PAGES = {"/": "fleet.html", "/fleet": "fleet.html", "/client": "client.html",
         "/findings": "findings.html", "/runs": "runs.html", "/git": "git.html",
         "/worklist": "worklist.html", "/report": "report.html", "/config": "config.html",
         "/changelog": "changelog.html", "/review": "review.html"}
```

to:

```python
PAGES = {"/": "fleet.html", "/fleet": "fleet.html", "/client": "client.html",
         "/findings": "findings.html", "/runs": "runs.html", "/git": "git.html",
         "/worklist": "worklist.html", "/report": "report.html", "/config": "config.html",
         "/changelog": "changelog.html", "/review": "review.html",
         "/analytics": "analytics.html"}
```

- [ ] **Step 2: Add the nav entry**

In `pipeline/dashboard/static/app.js`, in the `NAV` array (lines 42-53), insert a new entry after `Findings` (report already uses the `analytics` icon, so this page uses a different one — `query_stats` — to stay visually distinct):

```javascript
  { href: '/analytics', icon: 'query_stats', label: 'Analytics', needsClient: true },
```

placed between the `/findings` and `/worklist` lines.

- [ ] **Step 3: Create the page skeleton**

Write `pipeline/dashboard/static/analytics.html`:

```html
<!DOCTYPE html>
<html class="dark" lang="en"><head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>Analytics · wf-dashboard</title>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap" rel="stylesheet"/>
<script src="/static/theme.js"></script>
<link href="/static/theme.css" rel="stylesheet"/>
</head>
<body class="font-body-md text-body-md antialiased">
<main class="md:ml-60 pt-12 h-screen flex flex-col bg-background overflow-auto">
<div class="h-12 border-b border-outline-variant bg-surface-container flex items-center gap-md px-md shrink-0">
<span class="font-label-caps text-label-caps text-on-surface-variant">Analytics</span>
</div>
<div id="providers" class="shrink-0 border-b border-outline-variant bg-surface-container-low px-md py-xs flex items-center flex-wrap gap-x-md gap-y-xs"></div>
<div class="p-md flex flex-col gap-lg max-w-4xl">

<section class="border border-outline-variant rounded bg-surface-container-low">
  <div class="px-md py-sm border-b border-outline-variant flex items-center justify-between flex-wrap gap-sm">
    <span class="font-label-caps text-label-caps text-on-surface-variant">SITE HEALTH PROVIDERS</span>
    <button id="recheck" class="font-mono-sm text-mono-sm px-sm py-xs rounded bg-primary text-on-primary hover:opacity-90">RE-CHECK NOW (CrUX + GSC + DataForSEO, up to 20 pages)</button>
  </div>
  <div id="recheck-log" class="p-md font-mono-sm text-mono-sm text-on-surface-variant/70">Not run yet this session.</div>
</section>

<section id="search-section" class="border border-outline-variant rounded bg-surface-container-low">
  <div class="px-md py-sm border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant">SEARCH TERMS</div>
  <div class="p-md font-body-sm text-body-sm text-on-surface-variant/70">Loading…</div>
</section>

</div>
</main>
<script src="/static/app.js"></script>
<script src="/static/providers-strip.js"></script>
<script src="/static/page-analytics.js"></script>
</body></html>
```

(The `#search-section` placeholder body is replaced by Task 6's `renderTerms()`; this task only needs the section present so Task 6 can find it.)

- [ ] **Step 4: Write `page-analytics.js` — Section 1**

Write `pipeline/dashboard/static/page-analytics.js`:

```javascript
// Analytics — trigger the four external measurement providers and curate the
// Bright Data SERP search-term list. Section 1 (providers) below; Section 2
// (search terms) is appended by a later change to this same file.
const slug = requireClient();

let cfg = null, latestFindings = null;

async function load() {
  try {
    cfg = await api(`/api/clients/${encodeURIComponent(slug)}/config`);
    const cycles = await api(`/api/clients/${encodeURIComponent(slug)}/cycles`);
    latestFindings = null;
    if (cycles.length) {
      const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${cycles[0]}`);
      latestFindings = bundle.artifacts['findings.json'] || null;
    }
    renderProviders((latestFindings && latestFindings.providers) || {});
  } catch (err) {
    fail(document.getElementById('recheck-log'), err);
  }
}

async function recheck() {
  const btn = document.getElementById('recheck');
  const logEl = document.getElementById('recheck-log');
  btn.disabled = true;
  logEl.innerHTML = '';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/runs`, {
      command: 'site-health',
      args: { 'with-crux': true, 'with-gsc': true, 'with-dataforseo': true, 'max-crawl-pages': 20 },
    });
    streamRun(run_id, logEl, { onExit: load });
  } catch (err) {
    fail(logEl, err);
    btn.disabled = false;
  }
}

document.getElementById('recheck').addEventListener('click', recheck);
load();
```

- [ ] **Step 5: Manually verify**

Run `wf-dashboard`, navigate to a client, click "Analytics" in the sidebar. Confirm: the page loads without a console error, the PROVIDERS strip renders (either the amber "HTTP-only cycle" message if the newest cycle never asked for a provider, or real statuses), and clicking "RE-CHECK NOW" starts a `site-health` run whose log streams live into `#recheck-log` and, on completion, refreshes the strip. If real CrUX/DataForSEO credentials are exported in the shell that launched `wf-dashboard`, confirm the refreshed strip shows real `ok:`/`no field data:` statuses rather than `skipped:`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/dashboard/server.py pipeline/dashboard/static/app.js pipeline/dashboard/static/analytics.html pipeline/dashboard/static/page-analytics.js
git commit -m "feat: Analytics dashboard page — re-check CrUX/GSC/DataForSEO with one click

New page, reusing the existing run-launch/SSE-streaming plumbing and the
shared provider-status strip. Search-term tracking (Section 2) follows in
the next commit."
```

---

### Task 6: Analytics page — Section 2, Search Terms

**Files:**
- Modify: `pipeline/dashboard/static/analytics.html` (replace the `#search-section` placeholder body)
- Modify: `pipeline/dashboard/static/page-analytics.js` (append Section 2 functions)

**Interfaces:**
- Consumes: `cfg` and `latestFindings` globals from Task 5's `load()`; `search-suggest`/`search-add`/`search-check` dashboard commands (Task 3); `GET /api/runs/:id` (existing — returns `{output: string[], ...}`, used today by `page-runs.js`'s `history()`).
- Produces: none consumed elsewhere — this is the top of the call chain.

- [ ] **Step 1: Replace the placeholder section body**

In `pipeline/dashboard/static/analytics.html`, replace:

```html
<section id="search-section" class="border border-outline-variant rounded bg-surface-container-low">
  <div class="px-md py-sm border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant">SEARCH TERMS</div>
  <div class="p-md font-body-sm text-body-sm text-on-surface-variant/70">Loading…</div>
</section>
```

with:

```html
<section id="search-section" class="border border-outline-variant rounded bg-surface-container-low">
  <div class="px-md py-sm border-b border-outline-variant flex items-center justify-between flex-wrap gap-sm">
    <span class="font-label-caps text-label-caps text-on-surface-variant">SEARCH TERMS</span>
    <div class="flex gap-sm">
      <button id="suggest" class="font-mono-sm text-mono-sm px-sm py-xs rounded border border-outline-variant hover:bg-surface-container-highest">SUGGEST 5 WITH THE AGENT</button>
      <button id="check-rank" class="font-mono-sm text-mono-sm px-sm py-xs rounded bg-primary text-on-primary hover:opacity-90">CHECK RANK NOW (1 paid request per term)</button>
    </div>
  </div>
  <div class="px-md py-sm border-b border-outline-variant flex gap-sm">
    <input id="new-term" class="flex-1 bg-surface-container-highest border border-outline-variant text-on-surface font-mono-base text-mono-base rounded px-sm py-xs focus:outline-none focus:border-primary" placeholder="Top AI agency in Cambodia"/>
    <button id="add-term" class="font-mono-sm text-mono-sm px-sm py-xs rounded border border-outline-variant hover:bg-surface-container-highest">ADD</button>
  </div>
  <div id="commit-banner" class="hidden px-md py-xs bg-tertiary-container/20 text-tertiary font-body-sm text-body-sm border-b border-outline-variant"></div>
  <div id="suggestions" class="hidden px-md py-sm border-b border-outline-variant"></div>
  <div id="terms" class="p-md"></div>
</section>
```

- [ ] **Step 2: Append Section 2 to `page-analytics.js`**

Append to `pipeline/dashboard/static/page-analytics.js`:

```javascript
// ── Section 2: Search Terms ──────────────────────────────────────────────────
// Default is 5 terms you add + 5 the agent suggests. There is no stored
// distinction between the two once they're both in seed_queries — the
// pipeline's own rule (Finding.context is fingerprinted on the query text)
// means this list must stay stable, not carry extra metadata that could drift
// from it — so the cap is a soft, total-count check, not a tagged 5-and-5.
const SOFT_CAP = 10;

function findingsFor(query) {
  const findings = (latestFindings && latestFindings.findings) || [];
  const serp = findings.filter((f) => f.code.startsWith('serp.') && f.context === query);
  const bestPage = serp.length ? serp[0].location : null;
  const gsc = bestPage
    ? findings.filter((f) => f.code.startsWith('gsc.') && f.location === bestPage)
    : [];
  return { serp, gsc };
}

function termRow(query) {
  const { serp, gsc } = findingsFor(query);
  const status = serp.length
    ? serp.map((f) => `<span class="font-mono-sm text-mono-sm ${f.code === 'serp.absent' ? 'text-error' : 'text-tertiary'}">${esc(f.code)} ${esc(f.detail || '')}</span>`).join(' ')
    : '<span class="font-mono-sm text-mono-sm text-on-surface-variant/50">not checked yet</span>';
  const improve = gsc.length
    ? gsc.map((f) => `<div class="font-body-sm text-body-sm text-on-surface-variant">${esc(f.code)} — ${esc(f.detail || '')}</div>`).join('')
    : '';
  return `<div class="border-b border-outline-variant/40 py-sm">
    <div class="font-mono-base text-mono-base text-on-surface">${esc(query)}</div>
    <div class="mt-xs">${status}</div>
    ${improve}
  </div>`;
}

function renderTerms() {
  const el = document.getElementById('terms');
  const terms = (cfg && cfg.seed_queries) || [];
  el.innerHTML = terms.length
    ? terms.map(termRow).join('')
    : '<div class="font-body-sm text-body-sm text-on-surface-variant/70">No search terms tracked yet. Add one above, or ask the agent to suggest some.</div>';
}

function showCommitBanner() {
  const el = document.getElementById('commit-banner');
  el.textContent = 'seed_queries changed — commit docs/client-config.yml before '
    + 'the next cycle, or this list resets to what is on disk.';
  el.classList.remove('hidden');
}

// Launches a command, streams it into logEl, reloads cfg/latestFindings, then
// re-renders the terms table from the fresh data. Callers await this instead
// of wiring their own onExit so a chain of two runs (e.g. suggest, then add)
// cannot race the reload.
function runAndReload(command, args, logEl) {
  return post(`/api/clients/${encodeURIComponent(slug)}/runs`, { command, args })
    .then(({ run_id }) => new Promise((resolve) => {
      streamRun(run_id, logEl, { onExit: () => load().then(() => { renderTerms(); resolve(); }) });
    }));
}

async function addTerm() {
  const input = document.getElementById('new-term');
  const term = input.value.trim();
  if (!term) return;
  const existing = (cfg && cfg.seed_queries) || [];
  if (existing.length >= SOFT_CAP &&
      !confirm(`${existing.length} terms already tracked (the default is 5 you `
        + `add + 5 the agent suggests). Add one more anyway?`)) {
    return;
  }
  await runAndReload('search-add', { write: [term] }, document.getElementById('recheck-log'));
  input.value = '';
  showCommitBanner();
}

async function suggest() {
  const btn = document.getElementById('suggest');
  const box = document.getElementById('suggestions');
  btn.disabled = true;
  box.classList.remove('hidden');
  box.innerHTML = '<div class="font-mono-sm text-mono-sm text-on-surface-variant">Asking the agent…</div>';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/runs`,
      { command: 'search-suggest', args: {} });
    await new Promise((resolve) => streamRun(run_id, box, { onExit: resolve }));
    const run = await api(`/api/runs/${run_id}`);
    const queries = (run.output.join('\n').match(/^ {2}- (.+)$/gm) || [])
      .map((l) => l.replace(/^ {2}- /, '').trim());
    box.innerHTML = queries.length
      ? queries.map((q) => `<label class="flex items-center gap-sm py-xs">
          <input type="checkbox" class="suggestion accent-primary" value="${esc(q)}" checked/>
          <span class="font-mono-base text-mono-base text-on-surface">${esc(q)}</span></label>`).join('')
        + `<button id="keep-suggestions" class="mt-sm font-mono-sm text-mono-sm px-sm py-xs rounded bg-primary text-on-primary hover:opacity-90">ADD TICKED</button>`
      : '<div class="font-mono-sm text-mono-sm text-on-surface-variant/70">No suggestions came back — see the log above.</div>';
    document.getElementById('keep-suggestions')?.addEventListener('click', async () => {
      const picked = [...document.querySelectorAll('.suggestion:checked')].map((c) => c.value);
      if (!picked.length) return;
      await runAndReload('search-add', { write: picked }, box);
      showCommitBanner();
      box.classList.add('hidden');
    });
  } catch (err) {
    fail(box, err);
  } finally { btn.disabled = false; }
}

async function checkRank() {
  const btn = document.getElementById('check-rank');
  btn.disabled = true;
  try {
    await runAndReload('search-check', {}, document.getElementById('recheck-log'));
  } finally { btn.disabled = false; }
}

document.getElementById('add-term').addEventListener('click', addTerm);
document.getElementById('suggest').addEventListener('click', suggest);
document.getElementById('check-rank').addEventListener('click', checkRank);

// load() (Task 5) runs on script load and does not know about renderTerms();
// call it once more here now that Section 2 exists, after load() resolves.
load().then(renderTerms);
```

Note: this means `load()` (defined in Task 5) now runs twice on page open — once from Task 5's own trailing `load();` call, once from this file's trailing `load().then(renderTerms)`. Remove Task 5's bare trailing `load();` call as part of this step (it is superseded by the one above) — delete the line `load();` at the very end of the Section 1 block written in Task 5.

- [ ] **Step 3: Manually verify**

Run `wf-dashboard`, open a client's Analytics page. Confirm: the Search Terms table renders (empty state if `seed_queries` is unset, or one row per tracked term otherwise). Type a term into the input, click ADD — confirm it POSTs, the commit-reminder banner appears, and (if you then check `docs/client-config.yml` in the client checkout) the term was actually appended with the rest of the file untouched. Click "SUGGEST 5 WITH THE AGENT" — confirm it requires `claude` on PATH and real page content to crawl (this will fail loudly with the Task 3 exit-code messages on a client with no sitemap or no `claude` binary — that is the expected, documented failure mode, not a bug). Click "CHECK RANK NOW" — confirm it runs `wf-site-health --with-serp` and, if `BRIGHTDATA_API_KEY`/`BRIGHTDATA_SERP_ZONE` are exported, real `serp.absent`/`serp.page_two` rows appear against the tracked terms after the run.

- [ ] **Step 4: Commit**

```bash
git add pipeline/dashboard/static/analytics.html pipeline/dashboard/static/page-analytics.js
git commit -m "feat: Analytics page Section 2 — add/suggest/track/check search terms

Add a term or accept an agent suggestion (wf-seed-queries, capped at 5
agent-grounded picks) -> commit reminder -> Check Rank Now runs Bright Data
SERP scoped to the tracked list and shows rank plus any GSC data for the
same page, using only findings the pipeline already measures."
```

---

### Task 7: Bundle the docs the sync contract requires

**Files:**
- Modify: `docs/BUG-LEDGER.md` (new Fixed entry)
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Modify: `pipeline/audit/providers.py` (two docstring updates)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Add the CrUX bug to `docs/BUG-LEDGER.md`**

In `docs/BUG-LEDGER.md`, in the `## Fixed` table, add a new row at the top (newest first, matching the existing order) using the next sequential ID (`B-041` — confirm this is still unused: `grep -oE "B-[0-9]+" docs/BUG-LEDGER.md | sort -t- -k2 -n -u | tail -1` before writing it, in case another entry landed between now and when this plan was written):

```
| B-041 | 2026-08-14 | 2026-08-14 | `pipeline/audit/providers.py:118-148` (`crux_findings`) | **CrUX queried the literal config domain, not the host Chrome actually recorded traffic against.** Any client whose apex 301s to `www` (or the reverse) risks an exact-origin miss: CrUX's dataset is keyed per exact origin and is not redirect-aware. Proven live 2026-08-14 while verifying all three optional providers for the first time against real credentials: `wikipedia.org` (bare) returned no CrUX record; `en.wikipedia.org` (the real serving origin, same site) returned a real one. `new-wave.io` returned no record under either its bare or `www` form — consistent with too little Chrome traffic either way, not proof either origin was queried correctly, which is what motivated checking the mechanism directly against a known-high-traffic site. | Origin-level queries now resolve the domain's real serving host via the existing `curl_final_host` helper (built for B-037) before building the CrUX request, falling back to the literal domain if resolution fails. Per-URL queries are untouched — those are already absolute. The status string names the resolved host when it differs from the configured one. | `tests/test_providers.py::test_crux_queries_the_resolved_origin_not_the_configured_domain` and three siblings assert the resolved host reaches the request, an unresolvable domain falls back safely, per-URL mode never calls the resolver, and the "no field data" message names the host actually queried. `.venv/bin/python -m pytest -q` → **PASTE THE REAL COUNT HERE FROM STEP 3**. |
```

- [ ] **Step 2: Update the two stale "never run live" docstrings**

In `pipeline/audit/providers.py`, in `dataforseo_findings` (the docstring currently reads, in part):

```python
    """(findings, status). Posts a crawl, polls the summary, reads the pages.

    NOTE: the network path here has never been run against the live API — it is
    written from the documented request/response shapes and only the parser is
    covered by tests. Treat the first real run as the verification, and read the
    status string, not the finding count.
    """
```

replace the `NOTE:` paragraph with:

```python
    """(findings, status). Posts a crawl, polls the summary, reads the pages.

    Run live for the first time 2026-08-14 against a real domain with real
    DataForSEO credentials: the request/response shapes documented here match
    the vendor. That one run is not exhaustive coverage of every response
    shape the API can return — the automated test suite still only covers the
    pure parser (`parse_dataforseo_pages`), which is the honest boundary; read
    the status string, not just the finding count, on every run.
    """
```

Apply the same edit to `serp_findings`'s docstring — replace:

```python
    """(findings, status). One Google SERP request per seed query.

    NOTE: like the other three providers, this network path has never been run
    against the live API — it is written from Bright Data's documented request
    shape and only `parse_serp` is covered by tests. Treat the first real run as
    the verification, and read the status string, not the finding count.
    """
```

with:

```python
    """(findings, status). One Google SERP request per seed query.

    Run live for the first time 2026-08-14 against a real domain with real
    Bright Data credentials: Bright Data's documented request shape matches
    what the vendor actually accepts. That one run is not exhaustive coverage
    of every response shape the API can return — the automated test suite
    still only covers the pure parser (`parse_serp`), which is the honest
    boundary; read the status string, not just the finding count, on every run.
    """
```

- [ ] **Step 3: Run the full suite and record the real count**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS. Copy the exact final line (e.g. `704 passed in 6.10s`) — paste it into the `docs/BUG-LEDGER.md` B-041 row from Step 1 (replacing the `PASTE THE REAL COUNT HERE FROM STEP 3` placeholder) and into the CHANGELOG entry in Step 4. Do not guess this number or carry forward the `691 passed` figure from the 2026-08-12 handoff — Tasks 1-3 added new tests.

- [ ] **Step 4: Add the `CHANGELOG.md` entry**

In `CHANGELOG.md`, under `## [Unreleased]`, add a new subsection (before any existing `### Fixed`/`### Documentation` entries already there):

```markdown
### Added

- **Analytics dashboard page — trigger and curate the four external providers
  without hand-typing CLI flags.** New `/analytics` page: a "Re-check now"
  button runs `wf-site-health --with-crux --with-gsc --with-dataforseo`
  (capped at 20 DataForSEO pages by default) and streams the live log; a
  Search Terms panel lets the operator type up to 5 terms and accept up to 5
  agent-suggested ones (`wf-seed-queries`, unchanged, still never
  auto-commits), then run Bright Data SERP scoped to just the tracked list
  and see rank plus any related GSC data — all from findings the pipeline
  already measures, no new artifact schema. New `wf-seed-queries --write`
  mode appends to `seed_queries:` in `docs/client-config.yml` (text-based,
  same pattern as `wf-bootstrap-config --add-tier` — never a PyYAML
  round-trip, which would eat the file's comments) and still requires a human
  commit, same as every other config write in this pipeline.

### Fixed

- **CrUX queried the literal config domain instead of the host Chrome
  actually recorded traffic against — B-041.** Proven live 2026-08-14: bare
  `wikipedia.org` had no CrUX record, `en.wikipedia.org` (the real serving
  origin) did. Any client whose apex redirects to `www` (or the reverse) was
  at risk of a false "too little traffic" read. Origin-level queries now
  resolve the real serving host via the existing `curl_final_host` helper
  before querying, falling back to the literal domain if resolution fails.

### Verified

- **CrUX, DataForSEO and Bright Data SERP were run live for the first time
  on 2026-08-14**, against `new-wave.io` with real credentials in a local,
  gitignored `.env`. All three worked: CrUX correctly reported no field data
  for a low-traffic site (cross-checked against `en.wikipedia.org`, which did
  return real data, to confirm the mechanism itself is sound); DataForSEO
  crawled 5 pages and found real `dfs.image_alt_missing` findings; Bright
  Data SERP measured a real query and correctly reported `serp.absent`. This
  closes the "never run against the live API" caveat both providers' source
  comments and the 2026-08-12 handoff carried.
```

- [ ] **Step 5: Commit**

```bash
git add docs/BUG-LEDGER.md CHANGELOG.md pipeline/audit/providers.py
git commit -m "docs: B-041 (CrUX origin fix) + first live verification of all three optional providers

Per CLAUDE.md's sync contract — this is the paper trail for everything
committed in this branch's preceding commits."
```

---

## Self-Review Notes

- **Spec coverage:** §2.1 (CrUX fix) → Task 1. §2.2 (writer CLI) → Task 2. §2.3 (COMMANDS) → Task 3. §2.4 (frontend, both sections) → Tasks 5-6, with the shared-strip prerequisite pulled out as Task 4 since §2.4 explicitly calls for the extraction. §3 (data flow) has no dedicated task — it's a property of Tasks 1-6 together, not a separate deliverable. §4 (cost guardrails) → the `max-crawl-pages: 20` default and button-label wording in Task 5, the `SOFT_CAP`/confirm in Task 6, the per-term cost label in Task 6's HTML. §5 (bundled fixes) → Task 1 (the fix itself) + Task 7 (the record). §6 (testing) → each task's own Steps 1-2/5-6; Task 7 covers the "paste the real pytest count" requirement explicitly.
- **Placeholder scan:** the only intentional placeholder is the `PASTE THE REAL COUNT HERE FROM STEP 3` marker in Task 7 Step 1 — it exists because CLAUDE.md forbids writing a test count that was not actually observed, so the plan cannot pre-fill it. Every other step has complete, real code.
- **Type/name consistency checked:** `crux_findings(domain, urls=None)` signature unchanged across Task 1 and its caller in `measure.py` (not modified — no task touches it). `write_seed_queries(target: Path, new_queries: list) -> int` name and signature match between Task 2's implementation and Task 3's `search-add` COMMANDS wiring (which calls the CLI, not the function, directly — no drift risk there). `cfg`/`latestFindings` globals are defined in Task 5 and consumed by name in Task 6 with no renaming. `renderProviders`/`providerTone` signatures in Task 4 match every call site in Task 5/6 and the untouched call site in `page-findings.js`.
