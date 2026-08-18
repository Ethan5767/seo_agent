# Performance Analytics — Stronger Flow + Analytics Dashboard Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the CrUX exact-origin bug proven live on 2026-08-14, then give the dashboard a way to trigger CrUX/GSC/DataForSEO/SERP re-checks and to curate and track Bright Data SERP search terms — all for already-onboarded clients, using credentials the operator already has in their shell environment.

**Architecture:** Backend: one bug fix in `providers.py` (reuse the existing `curl_final_host` helper, with a same-registrable-domain guard), one new append-only write mode on the existing `wf-seed-queries` CLI (line-based edit, same pattern as `wf-bootstrap-config --add-tier`, never a PyYAML round-trip) plus a `--format json` mode for structured output, and one new entry point in the dashboard's `COMMANDS` allow-list (`site-health` grows a `with-serp` flag; no second command). Frontend: the provider-status-strip renderer moves into `app.js` (this codebase's one established home for cross-page render helpers — no new script file), and one new dashboard page (`analytics.html` + `page-analytics.js`) that triggers runs through the dashboard's existing run-launch/SSE-streaming plumbing via a single exit-aware helper, reused by every button on the page.

**Tech Stack:** Python 3.10+ (stdlib only — PyYAML is the repo's one runtime dependency), pytest, vanilla JS + Tailwind CDN (no build step, no framework — matches every existing dashboard page).

**Revision note (2026-08-18):** This plan was thermo-nuclear reviewed before implementation started and returned a **BLOCK** verdict — four blockers, all only visible by reading the code the first draft cited rather than trusting its own description of that code. Every task below already incorporates the fix; nothing here needs re-deriving. The blockers were: (1) the first draft's config-editing regex could never re-parse its own output, so a client's *second* tracked term always failed; (2) the "how to improve" panel joined GSC data on a field `parse_serp` hardcodes to `"/"` by design, so it would have shown unrelated homepage findings labeled as query-specific; (3) a term ranking on page one rendered identically to a term never checked — the exact "measurement vs. clean" ambiguity `providers.py`'s own doctrine exists to prevent; (4) a separate "check rank only" run would have silently overwritten `findings.json` with a narrower provider set than the last full check, discarding paid results and feeding the ratchet false RESOLVEDs. All four are structural, not cosmetic — see each task's inline notes for exactly what changed and why.

## Global Constraints

- **No secrets in the repo.** Credentials stay environment-variable-only; nothing in this plan reads or writes a `.env` file. (CLAUDE.md §"No secrets. No client PII.")
- **`docs/client-config.yml` is edited in place, line-based, never via `yaml.safe_load`/`dump`.** The file is mostly hand-written comments; a full parse-and-rewrite round-trip eats them (this is why `bootstrap_config.add_tier` does the same thing).
- **A measurement that returned nothing must never look like a measurement that never ran.** This is `providers.py`'s and `renderProviders`'s own stated doctrine — every new UI surface in this plan is required to preserve it, not just the code it's copying from.
- **A re-run must never silently narrow what the last run measured.** `findings.json` is a full overwrite, not a merge — anything that triggers a `wf-site-health` run from the dashboard must carry forward every provider flag the operator has already turned on for that client, or say explicitly that it does not.
- **Every finding a provider produces is written to `findings.json` through the existing schema.** No new artifact files.
- **A command that did nothing must say so, not read as success.** Every new dashboard command declares its real exit-code vocabulary in `COMMANDS`, matching the existing pattern.
- **`git pull --ff-only` before starting, and re-run before the final commit** — CLAUDE.md's sync contract; this repo has two operators.
- **`pytest -q` output must be pasted into the final CHANGELOG entry, not paraphrased or guessed at.** (CLAUDE.md §4, "proof or it did not happen.")
- **CHANGELOG.md `[Unreleased]` gets an entry in the same commit as the behavior change it describes** — not deferred to a later commit.
- Docs-only changes may commit directly; everything else follows the repo's ordinary "pull, test, diff --stat, push" checklist.

---

### Task 1: CrUX queries the domain's real serving origin, not the literal config string — and never a lookalike host

**Files:**
- Modify: `pipeline/audit/providers.py:118-148` (`crux_findings`)
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: `pipeline.lib.common.curl_final_host(url: str) -> str` (already exists, returns `""` on an unreachable/timed-out URL — see `pipeline/lib/common.py:51-70`).
- Produces: `crux_findings(domain: str, urls=None) -> tuple[list[Finding], str]` — same public signature as today; callers (`measure.py:294`) need no change.

**Note on the review's finding 5:** `curl_final_host` was built for B-037 specifically to detect an auth wall answering every route with a 302 to *its own* domain (Vercel Deployment Protection → `vercel.com`, Cloudflare Access, Netlify password protection). A naive `curl_final_host(...) or domain` substitution would resolve a protected client straight to `vercel.com` — which has abundant real CrUX field data — and write those Core Web Vitals into the client's `findings.json` as if they were the client's own, reporting a green `"ok:"`. The fix below only trusts a resolved host that is the same domain, `www.<domain>`, or a subdomain of it.

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


def test_a_subdomain_of_the_configured_domain_is_trusted(monkeypatch):
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "shop.example.com")
    seen = []
    monkeypatch.setattr(p, "_request", lambda e, payload=None, **k: (seen.append(payload), ({"record": {}}, None))[1])
    findings, status = p.crux_findings("example.com")
    assert seen == [{"origin": "https://shop.example.com"}]


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


def test_a_resolved_host_that_is_not_the_same_site_is_not_trusted(monkeypatch):
    """B-037's exact scenario: an auth wall (Vercel Deployment Protection,
    Cloudflare Access, Netlify password protection) 302s every route to ITS
    OWN domain, which curl_final_host correctly reports. CrUX has abundant
    real field data for vercel.com — querying it and calling the result the
    client's would be invention, not a measurement."""
    monkeypatch.setenv("CRUX_API_KEY", "k")
    monkeypatch.setattr(p, "curl_final_host", lambda url: "vercel.com")
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

Run: `.venv/bin/python -m pytest tests/test_providers.py -k "resolved_origin or unresolvable_domain or per_url_mode or no_field_data_message or subdomain_of_the_configured or not_the_same_site" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'curl_final_host'` (it isn't imported into `providers.py` yet).

- [ ] **Step 3: Add the import**

In `pipeline/audit/providers.py`, add to the imports (after the stdlib imports, before `from pipeline.lib.baseline import ...`):

```python
from pipeline.lib.common import curl_final_host
```

- [ ] **Step 4: Rewrite `crux_findings`**

Replace `pipeline/audit/providers.py:118-148` with:

```python
def _same_site(resolved: str, domain: str) -> bool:
    """True if `resolved` is `domain`, `www.<domain>`, or a subdomain of it.

    CrUX has real field data for domains this pipeline has no business
    reporting as a client's own — most notably an auth wall's own domain
    (vercel.com, *.pages.dev's SSO host, cloudflareaccess.com), which
    curl_final_host correctly follows to and reports (B-037). A resolved host
    that isn't the same site is not trusted; the caller falls back to the
    literal configured domain instead.
    """
    resolved = resolved.split(":")[0]  # drop a port, if curl reported one
    return resolved == domain or resolved == f"www.{domain}" or resolved.endswith(f".{domain}")


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
    origin — did. `curl_final_host` (built for B-037) resolves it; the result is
    only trusted when `_same_site` agrees it's the configured domain or one of
    its subdomains — otherwise (unresolvable, or an auth wall's own domain) this
    falls back to the literal string, so the fix is never worse than before it
    and never reports a stranger's Core Web Vitals as the client's. Per-URL mode
    is untouched — those URLs are already absolute.
    """
    key = os.environ.get("CRUX_API_KEY")
    if not key:
        return [], "skipped: CRUX_API_KEY unset"

    endpoint = f"https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={key}"
    if urls:
        targets = [("url", u, "/" + u.split("//", 1)[-1].split("/", 1)[-1]) for u in urls]
        report_domain = domain
    else:
        resolved = curl_final_host(f"https://{domain}")
        report_domain = resolved if resolved and _same_site(resolved, domain) else domain
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
Resolves via the existing curl_final_host helper, guarded to only trust a
same-site result — an auth wall's own domain (B-037) has real CrUX data too,
and reporting it as the client's would be invention, not a measurement."
```

---

### Task 2: `wf-seed-queries --write` — append search terms without touching anything else in the config

**Files:**
- Modify: `pipeline/audit/seed_queries.py`
- Test: `tests/test_seed_queries.py`

**Interfaces:**
- Produces: `write_seed_queries(target: Path, new_queries: list[str]) -> int` — `0` on success (including the idempotent "nothing new" case), `4` refused (blank input, missing config file, or an existing `seed_queries:` that is not a plain block list).
- CLI: `wf-seed-queries --project <dir> --write "term one" --write "term two"` — repeatable flag, one term per occurrence, matching the dashboard's `text-list` arg kind (Task 3). Also adds `--format json`, consumed by Task 3's `search-suggest` command.

**Note on the review's finding 1 (blocker):** The first draft matched `seed_queries:` with `re.compile(r"^seed_queries:[ \t]*\n", re.M)` — requiring the newline immediately after the key. But the block this same function writes on its first call carries a trailing comment (`seed_queries:                     # Bright Data SERP tracks these...`), which that regex cannot match. Every real client's *second* `--write` would take the "not a plain block list" refusal path and exit 4, permanently. Rewritten below as a line-based walk (matching `add_tier`'s own approach, which is a line append with no in-place insertion at all) that reads the key line with its comment stripped, so it round-trips its own output.

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


def test_write_seed_queries_can_write_twice_in_a_row(tmp_path):
    """The blocker the review caught: the first write's own output (a trailing
    comment on the seed_queries: line) must be re-parseable by the second."""
    target = tmp_path / "client-config.yml"
    target.write_text("tier: 1\n")
    assert sq.write_seed_queries(target, ["first term"]) == 0
    assert sq.write_seed_queries(target, ["second term"]) == 0
    text = target.read_text()
    assert "  - first term" in text
    assert "  - second term" in text
    assert text.index("- first term") < text.index("- second term")


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


def test_write_seed_queries_collapses_internal_whitespace(tmp_path):
    """Finding.context (baseline.py) normalizes whitespace before fingerprinting
    a SERP finding's query. Storing the raw double-spaced text here would make
    a stored term never match its own finding — collapse on write instead."""
    target = tmp_path / "client-config.yml"
    target.write_text("tier: 1\n")
    code = sq.write_seed_queries(target, ["  top   ai  agency  "])
    assert code == 0
    assert "  - top ai agency\n" in target.read_text()


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


# ── --write on the CLI: exit 4 (not 2) when the config is missing ────────────

def test_write_flag_on_a_missing_config_exits_4(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv",
        ["wf-seed-queries", "--project", str(tmp_path), "--write", "a term"])
    assert sq.main() == 4
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_seed_queries.py -k "write_seed_queries or write_flag" -v`
Expected: FAIL — `AttributeError: module 'pipeline.audit.seed_queries' has no attribute 'write_seed_queries'`.

- [ ] **Step 3: Add the `Path` import**

In `pipeline/audit/seed_queries.py`, add after the existing `from urllib.parse import urlsplit` line:

```python
from pathlib import Path
```

- [ ] **Step 4: Implement `write_seed_queries`**

Add to `pipeline/audit/seed_queries.py`, immediately before the `# ── the CLI ──` section marker:

```python
# ── write_seed_queries: append-only, line-based, same shape as add_tier ──────

def write_seed_queries(target: Path, new_queries: list) -> int:
    """Append new_queries to seed_queries: in an EXISTING docs/client-config.yml.

    Line-based, like bootstrap_config.add_tier — PyYAML round-tripping this
    file eats its comments. Reads the key line with any trailing `# comment`
    stripped before comparing it, specifically so this function's OWN output
    (the fresh block below carries one) is still recognized on the next call —
    a regex anchored on a bare newline after the colon cannot see past its own
    comment and would refuse every write after the first.

    Refuses (4) rather than guess when seed_queries: exists but is not a plain
    block list (`seed_queries: []` or flow-style `[a, b]`): editing that safely
    needs a real parser, and this module deliberately doesn't carry one for
    this file. Appends a fresh commented block when the key is absent
    entirely, matching add_tier's append-at-end shape. Dedupes
    case-insensitively and collapses internal whitespace — Finding.context
    (baseline.py) does the same before fingerprinting a SERP finding, and a
    stored term that doesn't match its own finding's context never resolves.
    """
    cleaned = [" ".join(q.split()) for q in new_queries if q and q.strip()]
    if not cleaned:
        print("[ERROR] no non-blank query given", file=sys.stderr)
        return 4

    lines = target.read_text().splitlines(keepends=True)
    key = next((i for i, l in enumerate(lines) if l.startswith("seed_queries:")), None)

    if key is None:
        block = ("\nseed_queries:                     # Bright Data SERP tracks "
                  "these — one paid request each per cycle\n"
                  + "".join(f"  - {q}\n" for q in cleaned))
        target.write_text("".join(lines).rstrip("\n") + "\n" + block)
        print(f"[OK] Added seed_queries: to {target} with {len(cleaned)} term(s).")
        print("[NEXT] Commit docs/client-config.yml.")
        return 0

    if lines[key].split("#", 1)[0].strip() != "seed_queries:":
        print(f"[ERROR] seed_queries: exists in {target} but is not a plain "
              f"block list — refusing to edit it blind. Edit it by hand.",
              file=sys.stderr)
        return 4

    end = key + 1
    while end < len(lines) and lines[end].lstrip().startswith("- "):
        end += 1
    have = {lines[i].lstrip()[2:].strip().lower() for i in range(key + 1, end)}

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

    lines[end:end] = [f"  - {q}\n" for q in to_add]
    target.write_text("".join(lines))
    print(f"[OK] Added {len(to_add)} term(s) to seed_queries: in {target}.")
    print("[NEXT] Commit docs/client-config.yml.")
    return 0
```

- [ ] **Step 5: Wire `--write` and `--format` into the CLI**

In `pipeline/audit/seed_queries.py`, in `main()`, add both arguments (after the existing `--timeout` argument, before `args = ap.parse_args()`):

```python
    ap.add_argument("--write", action="append", default=[], metavar="QUERY",
                    help="append this query to seed_queries: in docs/client-config.yml "
                         "and exit — skips the crawl and the agent entirely")
    ap.add_argument("--format", choices=("yaml", "json"), default="yaml",
                    help="yaml (default): a pasteable seed_queries: block. json: a "
                         "single [QUERIES] <json array> line for a caller that parses "
                         "output, e.g. the dashboard.")
```

Then, immediately after `args = ap.parse_args()` and **before** the `shutil.which("claude")` check, add:

```python
    if args.write:
        target = Path(args.project) / "docs" / "client-config.yml"
        if not target.exists():
            print(f"[ERROR] {target} does not exist", file=sys.stderr)
            return 4
        return write_seed_queries(target, args.write)
```

- [ ] **Step 6: Make the query-list output structured when asked**

In `pipeline/audit/seed_queries.py`, in `main()`, replace:

```python
    print("seed_queries:")
    for q in queries:
        print(f"  - {q}")
    print(f"\n[INFO] {len(queries)} queries. Each is one paid Bright Data request "
          f"per cycle. Review, then paste into docs/client-config.yml and commit.",
          file=sys.stderr)
    return 0
```

with:

```python
    if args.format == "json":
        # A single, unambiguous line a caller can find in merged stdout+stderr
        # (the dashboard's Run streams both together) without heuristics. The
        # `[QUERIES] ` prefix matches this repo's existing [OK]/[INFO]/[WARN]
        # vocabulary. Contrast with parsing printed `  - text` lines, which
        # this module's own docstring already names as a defect it fixed once
        # (stripped bullets and word-count heuristics that admitted CLI
        # warning lines as queries) — reintroducing that one layer up, in JS,
        # over a stderr-merged stream, would be the same mistake restaged.
        print("[QUERIES] " + json.dumps(queries))
    else:
        print("seed_queries:")
        for q in queries:
            print(f"  - {q}")
    print(f"\n[INFO] {len(queries)} queries. Each is one paid Bright Data request "
          f"per cycle. Review, then paste into docs/client-config.yml and commit.",
          file=sys.stderr)
    return 0
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_seed_queries.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add pipeline/audit/seed_queries.py tests/test_seed_queries.py
git commit -m "feat: wf-seed-queries --write appends terms; --format json for callers that parse output

--write: text-based, append-only edit of seed_queries: in docs/client-config.yml
— same pattern as wf-bootstrap-config --add-tier. Dedupes case-insensitively,
collapses whitespace, refuses rather than guesses on a flow-style list, never
touches anything else in the file, and re-parses its own prior output (a
regex anchored on a bare trailing newline could not — every second write
would have refused).

--format json: a single [QUERIES] <array> line instead of the pasteable YAML
block, for a caller (the dashboard) that needs to parse the result instead of
a human pasting it."
```

---

### Task 3: Dashboard `COMMANDS` — expose provider flags on `site-health`, add `search-add`

**Files:**
- Modify: `pipeline/dashboard/server.py:48-` (`COMMANDS`), `:309-355` (`build_argv`)
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `write_seed_queries` CLI flag from Task 2 (`--write`), `--format json` from Task 2, `--with-crux`/`--with-gsc`/`--with-dataforseo`/`--with-serp`/`--max-crawl-pages` flags on `wf-site-health` (already exist on the CLI — `pipeline/audit/measure.py:249-260`).
- Produces: `build_argv(command, project, args)` gains a `text-list` argument kind; `COMMANDS` gains `search-add` and `search-suggest`; `site-health`'s declared args grow to include `with-serp`. Frontend (Task 5) calls these by name via the existing `POST /api/clients/:slug/runs`.

**Note on the review's finding 4 (blocker):** The first draft added a separate `search-check` command (`wf-site-health --with-serp` only). `measure.py`'s `main()` overwrites `findings.json` wholesale on every run — there is no partial-provider merge. A dashboard with two buttons, one sending `{with-crux, with-gsc, with-dataforseo}` and the other sending `{with-serp}`, would let either button silently erase the other's findings from the artifact, and the next `wf-site-plan` would report the erased findings RESOLVED — exactly the false-clean-site failure `providers.py`'s own module docstring exists to prevent, reintroduced through the UI. Fixed by **deleting `search-check`** and adding `with-serp` to `site-health`'s own declared args instead: every dashboard-triggered measurement is one command, and Task 5's UI is responsible for always sending the full set of flags a "re-check" implies (see Task 5's note).

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


def test_site_health_provider_flags_are_declared_including_serp():
    argv = build_argv("site-health", "/p",
                       {"with-crux": True, "with-gsc": True, "with-dataforseo": True,
                        "with-serp": True, "max-crawl-pages": 20})
    assert "--with-crux" in argv
    assert "--with-gsc" in argv
    assert "--with-dataforseo" in argv
    assert "--with-serp" in argv
    assert "--max-crawl-pages" in argv and "20" in argv


def test_search_suggest_caps_the_agent_at_five_and_asks_for_json():
    argv = build_argv("search-suggest", "/p", {})
    assert argv == ["wf-seed-queries", "--project", "/p", "--limit", "5", "--format", "json"]


def test_there_is_no_separate_search_check_command():
    """The review's finding 4: a second command with a narrower provider set
    than site-health's would let one button silently erase the other's
    findings from findings.json. There must be exactly one measuring command."""
    assert "search-check" not in COMMANDS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -k "text_list or provider_flags or search_suggest or no_separate_search_check" -v`
Expected: FAIL — `ValueError: unknown argument for site-health: with-crux` and `ValueError: unknown command: search-add` (etc.); the "no separate command" test currently passes vacuously (nothing has added `search-check` yet) but is kept so a future change can't reintroduce it silently.

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

- [ ] **Step 4: Update `site-health` and add the two search commands**

In `pipeline/dashboard/server.py`, replace the `"site-health"` entry in `COMMANDS` (currently lines 54-60):

```python
    "site-health": {
        "argv": ["wf-site-health", "--project", "{project}"],
        "args": {"limit": "int", "url": "path-list",
                 "with-crux": "flag", "with-gsc": "flag", "with-dataforseo": "flag",
                 "with-serp": "flag", "max-crawl-pages": "int"},
        "label": "Measure live site",
        "exits": {},
        "then": "site-plan",
    },
```

Then add two new entries immediately after the `"site-plan"` entry:

```python
    "search-suggest": {
        "argv": ["wf-seed-queries", "--project", "{project}", "--limit", "5", "--format", "json"],
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
            4: ("refused", "REFUSED — seed_queries: is not a plain list, every term "
                           "given was blank, or docs/client-config.yml is missing"),
        },
    },
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/dashboard/server.py tests/test_dashboard.py
git commit -m "feat: dashboard COMMANDS — provider flags (incl. SERP) on site-health, search-add

Exposes the existing --with-crux/--with-gsc/--with-dataforseo/--with-serp
flags on the one measuring command, not a second one — findings.json is a
full overwrite, and two commands with different provider sets would let
either silently erase the other's findings and feed the ratchet a false
RESOLVED. search-add wraps the new --write mode. search-suggest asks for
--format json, matched to Task 2's structured-output mode."
```

---

### Task 4: Move the provider-status strip into `app.js`

**Files:**
- Modify: `pipeline/dashboard/static/app.js` (add `providerTone`/`renderProviders` to the render-helpers section)
- Modify: `pipeline/dashboard/static/page-findings.js` (remove the now-duplicate `providerTone`/`renderProviders`, lines 35-71)

**Interfaces:**
- Produces: two globals, `providerTone(status: string) -> string` (a Tailwind text-color class) and `renderProviders(providers: object) -> void` (renders into `#providers` in the current document). `app.js` is already this codebase's one home for cross-page render helpers (`esc`, `gitChip`, `exitChip`, `runLine`, `emptyState`, `fail`, `cycleScreen`, `cycleBranchName` all live there today) — no new script file, no new load-order rule for a page to get wrong.

**Note on the review's finding 8:** The first draft created a fourth static-JS file (`providers-strip.js`) to relocate 26 lines used by two pages, plus edited `findings.html`'s script tags and added a new one to `analytics.html`. `runLine`'s own comment states the existing rule directly: *"Lives here because four screens stream runs..."* — shared render helpers belong in `app.js`. Moving the two functions there instead means Task 4 touches two files instead of three, and `analytics.html` (Task 5) needs no extra `<script>` tag at all.

- [ ] **Step 1: Add the functions to `app.js`**

In `pipeline/dashboard/static/app.js`, add after `runLine` (which ends around line 150) and before the `streamRun` function:

```javascript
// Shared provider-status strip — used by Findings and Analytics.
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

In `pipeline/dashboard/static/page-findings.js`, delete lines 35-71 (the comment block plus the `providerTone` and `renderProviders` function definitions). The call site at line 28 (`renderProviders(doc.providers);`) stays exactly as it is — it now resolves to the global defined in `app.js`, which `findings.html` already loads first.

- [ ] **Step 3: Manually verify**

Run `wf-dashboard --clients-dir ~/clients` (or whatever `--clients-dir` this machine uses), open a client's Findings page in a browser, confirm the PROVIDERS strip still renders exactly as before (either the amber "HTTP-only cycle" message or the per-provider status line). This dashboard has no JS test harness (confirmed: no `*.test.js`, no jest/vitest anywhere in the tree) — this manual check is the verification, matching how every other dashboard screen here is tested.

- [ ] **Step 4: Commit**

```bash
git add pipeline/dashboard/static/app.js pipeline/dashboard/static/page-findings.js
git commit -m "refactor: move the provider-status strip into app.js

Findings and the new Analytics page (next commit) both need it; app.js is
already where every other cross-page render helper lives. No behavior
change on the Findings page, and no new script file or load-order rule."
```

---

### Task 5: Analytics page — skeleton, one exit-aware run helper, Section 1 (Site Health Providers)

**Files:**
- Modify: `pipeline/dashboard/server.py:439-442` (`PAGES`)
- Modify: `pipeline/dashboard/static/app.js:42-53` (`NAV`)
- Create: `pipeline/dashboard/static/analytics.html`
- Create: `pipeline/dashboard/static/page-analytics.js`

**Interfaces:**
- Consumes: `GET /api/clients/:slug` (existing — returns `{...fleet_entry, config, cycles}` in one response, `server.py:551-553`), `GET /api/clients/:slug/cycles/:ym` (existing, used today by `page-findings.js` — `bundle.artifacts['findings.json']`), `POST /api/clients/:slug/runs` (existing), global helpers from `app.js` (`api`, `post`, `esc`, `requireClient`, `streamRun`, `fail`, `renderProviders` — the last from Task 4).
- Produces: page-level globals `cfg` (the parsed config), `latestFindings` (the newest cycle's `findings.json`, or `null`), and `load()` (fetches both and re-renders everything the page shows — Task 6 extends this same function rather than calling it a second time) that Task 6 (Section 2) reads/extends. Also produces `run(command, args, logEl) -> Promise<exit|null>`, the one launch/stream/reload helper every button on this page uses.

**Note on the review's findings 6, 7, 13:** The first draft had four near-duplicate launch functions (`recheck`, `addTerm`, `checkRank`, `suggest`) with three different and mostly-missing error-handling stories — one of them (`recheck`) never re-enabled its own button on success, one (`addTerm`) had no error handling at all and would silently swallow a typed term on a `409 busy` conflict. It also called three endpoints serially (`/config`, `/cycles`, `/cycles/:ym`) where one existing endpoint already returns the first two together, and split `load()` (Task 5) from `renderTerms()` (Task 6) in a way that required Task 6 to reach back and delete a line Task 5 had just written. All three are fixed here: one `run()` helper, one `load()` that renders everything it loads (Task 6 extends it in place, nothing to delete later), one combined fetch.

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

In `pipeline/dashboard/static/app.js`, in the `NAV` array (lines 42-53), insert a new entry after `Findings` (the `Report` entry already uses the `analytics` icon, so this page uses a different one — `query_stats` — to stay visually distinct):

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
    <button id="recheck" class="font-mono-sm text-mono-sm px-sm py-xs rounded bg-primary text-on-primary hover:opacity-90">RE-CHECK NOW (CrUX + GSC + DataForSEO up to 20 pages + Bright Data for tracked terms)</button>
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
<script src="/static/page-analytics.js"></script>
</body></html>
```

(The `#search-section` placeholder body is replaced by Task 6's markup; this task only needs the section present so Task 6 can find it. No `providers-strip.js` tag — Task 4 put the strip renderer in `app.js`, already loaded above.)

- [ ] **Step 4: Write `page-analytics.js` — skeleton, `run()`, `load()`, Section 1**

Write `pipeline/dashboard/static/page-analytics.js`:

```javascript
// Analytics — trigger the four external measurement providers and curate the
// Bright Data SERP search-term list. Section 1 (providers) below; Section 2
// (search terms) is appended by a later change to this same file, extending
// load() in place rather than adding a second entry point.
const slug = requireClient();

let cfg = null, latestFindings = null;

// One combined fetch: GET /api/clients/:slug already returns config + cycles
// together, so this is one round-trip instead of three. Renders everything it
// loads — Section 2 (Task 6) extends this function's body directly instead of
// calling a second load, so the page never fetches or renders twice.
async function load() {
  try {
    const client = await api(`/api/clients/${encodeURIComponent(slug)}`);
    cfg = client.config;
    latestFindings = null;
    if (client.cycles.length) {
      const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${client.cycles[0]}`);
      latestFindings = bundle.artifacts['findings.json'] || null;
    }
    renderProviders((latestFindings && latestFindings.providers) || {});
  } catch (err) {
    fail(document.getElementById('recheck-log'), err);
  }
}

// The one launch/stream/reload path every button on this page uses. Returns
// the run's exit object ({code, kind, text}) on success, or null if the POST
// itself failed (e.g. another run is already busy against this client) — the
// error is already rendered into logEl either way, so callers only need to
// branch on whether to treat the run as having succeeded.
async function run(command, args, logEl) {
  logEl.innerHTML = '';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/runs`, { command, args });
    const ex = await streamRun(run_id, logEl);
    await load();
    return ex;
  } catch (err) {
    fail(logEl, err);
    return null;
  }
}

async function recheck() {
  const btn = document.getElementById('recheck');
  btn.disabled = true;
  try {
    await run('site-health',
      { 'with-crux': true, 'with-gsc': true, 'with-dataforseo': true,
        'with-serp': true, 'max-crawl-pages': 20 },
      document.getElementById('recheck-log'));
  } finally { btn.disabled = false; }
}

document.getElementById('recheck').addEventListener('click', recheck);
load();
```

**Why "RE-CHECK NOW" always sends all four flags, including `with-serp`:** per the review's finding 4 and this plan's Global Constraints, a re-run must never narrow what the last run measured. `serp_findings` is a safe no-op when `seed_queries` is empty (`providers.py:391` — `"skipped: no seed_queries..."`), so sending `with-serp` unconditionally costs nothing on a client with no tracked terms yet, and never silently drops SERP findings that do exist once terms are tracked.

- [ ] **Step 5: Manually verify**

Run `wf-dashboard`, navigate to a client, click "Analytics" in the sidebar. Confirm: the page loads without a console error, the PROVIDERS strip renders (either the amber "HTTP-only cycle" message or real statuses), and clicking "RE-CHECK NOW" starts a `site-health` run whose log streams live into `#recheck-log`, re-enables the button when it finishes (success or failure), and refreshes the strip. If real credentials are exported in the shell that launched `wf-dashboard`, confirm the refreshed strip shows real `ok:`/`no field data:`/`skipped:` statuses matching whichever env vars are actually set.

- [ ] **Step 6: Commit**

```bash
git add pipeline/dashboard/server.py pipeline/dashboard/static/app.js pipeline/dashboard/static/analytics.html pipeline/dashboard/static/page-analytics.js
git commit -m "feat: Analytics dashboard page — re-check all four providers with one click

New page, reusing the existing run-launch/SSE-streaming plumbing through one
exit-aware run() helper. Re-check always sends every provider flag,
including with-serp, so a re-run can never narrow what the last run
measured and silently RESOLVE findings that are still real. Search-term
tracking (Section 2) follows in the next commit."
```

---

### Task 6: Analytics page — Section 2, Search Terms

**Files:**
- Modify: `pipeline/dashboard/static/analytics.html` (replace the `#search-section` placeholder body)
- Modify: `pipeline/dashboard/static/page-analytics.js` (extend `load()`, append Section 2 functions)

**Interfaces:**
- Consumes: `cfg` and `latestFindings` globals, and the `run()` helper, all from Task 5; `search-add`/`search-suggest` dashboard commands (Task 3).
- Produces: none consumed elsewhere — this is the top of the call chain.

**Note on the review's findings 2, 3, 9, 10, 15 (blockers + medium):**
- **Finding 2 (blocker):** the first draft joined GSC findings onto a SERP finding's `location` field to find "the best-ranking page." `providers.py:337-338` states outright that `location` is hardcoded to `"/"` for every SERP finding — *"which page ranks is Google's choice and moves without the site changing"* — so that join would have matched whatever `gsc.*` findings happen to sit on the homepage and presented them as query-specific advice. There is no query→page mapping in this pipeline to join on. **Removed the GSC column entirely** rather than inventing one.
- **Finding 3 (blocker):** `parse_serp` returns no finding at all when a query already ranks on page one (`rank <= SERP_TOP_PAGE`) — there is no `serp.ranking` code. The first draft's `serp.length ? ... : 'not checked yet'` therefore rendered a term you rank #1 for identically to a term never checked, inverting the exact doctrine `renderProviders`'s own comment states. **Fixed by deriving state from `latestFindings.providers.serp`** (the status string, which is always present once a SERP run has happened) rather than from finding presence alone.
- **Finding 9 (medium):** the first draft's `SOFT_CAP` was enforced in `addTerm` only — the "suggest → add ticked" path, the one most likely to push past it, had no check at all — and its confirm-dialog copy described a "5 you add + 5 the agent suggests" split the code doesn't actually track. **Removed** — the per-term cost is already stated on the button; a synthetic count-based confirm that only half-applies doesn't add real protection.
- **Finding 10 (blocker-adjacent):** the first draft scraped `wf-seed-queries`'s merged stdout+stderr for lines matching `  - text`, which is exactly the heuristic `seed_queries.py`'s own docstring describes fixing once already (*"strip bullets... admitted a claude CLI warning line as a query"*). **Fixed in Task 2** with `--format json`; this task now looks for one `[QUERIES] ` line and `JSON.parse`s it.
- **Finding 15 (log placement):** Section 2's actions get their own log element (`#search-log`) instead of writing into Section 1's `#recheck-log`, which sits under a different header.

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
    <button id="suggest" class="font-mono-sm text-mono-sm px-sm py-xs rounded border border-outline-variant hover:bg-surface-container-highest">SUGGEST 5 WITH THE AGENT</button>
  </div>
  <div class="px-md py-sm border-b border-outline-variant flex gap-sm">
    <input id="new-term" class="flex-1 bg-surface-container-highest border border-outline-variant text-on-surface font-mono-base text-mono-base rounded px-sm py-xs focus:outline-none focus:border-primary" placeholder="Top AI agency in Cambodia"/>
    <button id="add-term" class="font-mono-sm text-mono-sm px-sm py-xs rounded border border-outline-variant hover:bg-surface-container-highest">ADD</button>
  </div>
  <div id="commit-banner" class="hidden px-md py-xs bg-tertiary-container/20 text-tertiary font-body-sm text-body-sm border-b border-outline-variant"></div>
  <div id="suggestions" class="hidden px-md py-sm border-b border-outline-variant"></div>
  <div id="search-log" class="px-md py-sm border-b border-outline-variant font-mono-sm text-mono-sm text-on-surface-variant/70 hidden"></div>
  <div id="terms" class="p-md"></div>
</section>
```

Note: there is no separate "check rank" button in Section 2 — Section 1's "RE-CHECK NOW" already measures SERP for every tracked term every time (Task 5's note), so a second trigger here would only reintroduce the two-buttons-different-coverage problem the review's finding 4 caught. The Search Terms table (below) reflects whatever the most recent `RE-CHECK NOW` found.

- [ ] **Step 2: Extend `load()` and append Section 2 to `page-analytics.js`**

In `pipeline/dashboard/static/page-analytics.js`, change the end of `load()` from:

```javascript
    renderProviders((latestFindings && latestFindings.providers) || {});
  } catch (err) {
    fail(document.getElementById('recheck-log'), err);
  }
}
```

to:

```javascript
    renderProviders((latestFindings && latestFindings.providers) || {});
    renderTerms();
  } catch (err) {
    fail(document.getElementById('recheck-log'), err);
  }
}
```

Then append to the end of the file:

```javascript
// ── Section 2: Search Terms ──────────────────────────────────────────────────

// State comes from the SERP provider's status string, not from finding
// presence — parse_serp emits NO finding at all for a query that already
// ranks on page one (rank <= SERP_TOP_PAGE), so "no finding" must render as
// "ranks on page one" once SERP has actually run, and only as "not checked
// yet" when it hasn't. Collapsing those two into one "not checked yet" state
// (the bug the review caught) would hide the client's actual wins.
//
// No GSC column: a SERP finding's `location` is hardcoded to "/" for every
// query (providers.py — "which page ranks is Google's choice"), so there is
// no query-to-page mapping in this pipeline to join GSC data through. Showing
// one anyway would mean showing whatever GSC findings happen to sit on the
// homepage, mislabeled as being about this query.
function termStatus(query) {
  const serpStatus = (latestFindings && latestFindings.providers && latestFindings.providers.serp) || '';
  if (!serpStatus || serpStatus.startsWith('skipped:')) {
    return { text: 'not checked yet', cls: 'text-on-surface-variant/50' };
  }
  const findings = (latestFindings && latestFindings.findings) || [];
  const hit = findings.find((f) => f.code.startsWith('serp.') && f.context === query);
  if (!hit) return { text: 'ranks on page one', cls: 'text-green-400' };
  return { text: `${hit.code} — ${hit.detail || ''}`, cls: 'text-error' };
}

function termRow(query) {
  const s = termStatus(query);
  return `<div class="border-b border-outline-variant/40 py-sm">
    <div class="font-mono-base text-mono-base text-on-surface">${esc(query)}</div>
    <div class="mt-xs font-mono-sm text-mono-sm ${s.cls}">${esc(s.text)}</div>
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

function searchLog() {
  const el = document.getElementById('search-log');
  el.classList.remove('hidden');
  return el;
}

async function addTerm() {
  const input = document.getElementById('new-term');
  const term = input.value.trim();
  if (!term) return;
  const btn = document.getElementById('add-term');
  btn.disabled = true;
  try {
    const ex = await run('search-add', { write: [term] }, searchLog());
    if (ex && ex.code === 0) {
      input.value = '';
      showCommitBanner();
    }
  } finally { btn.disabled = false; }
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
    const ex = await streamRun(run_id, searchLog());
    if (!ex || ex.code !== 0) {
      box.innerHTML = '<div class="font-mono-sm text-mono-sm text-on-surface-variant/70">No suggestions — see the log above.</div>';
      return;
    }
    const run_data = await api(`/api/runs/${run_id}`);
    const queriesLine = run_data.output.find((l) => l.startsWith('[QUERIES] '));
    const queries = queriesLine ? JSON.parse(queriesLine.slice('[QUERIES] '.length)) : [];
    box.innerHTML = queries.length
      ? queries.map((q) => `<label class="flex items-center gap-sm py-xs">
          <input type="checkbox" class="suggestion accent-primary" value="${esc(q)}" checked/>
          <span class="font-mono-base text-mono-base text-on-surface">${esc(q)}</span></label>`).join('')
        + `<button id="keep-suggestions" class="mt-sm font-mono-sm text-mono-sm px-sm py-xs rounded bg-primary text-on-primary hover:opacity-90">ADD TICKED</button>`
      : '<div class="font-mono-sm text-mono-sm text-on-surface-variant/70">No suggestions came back — see the log above.</div>';
    document.getElementById('keep-suggestions')?.addEventListener('click', async () => {
      const picked = [...document.querySelectorAll('.suggestion:checked')].map((c) => c.value);
      if (!picked.length) return;
      const addEx = await run('search-add', { write: picked }, searchLog());
      if (addEx && addEx.code === 0) {
        showCommitBanner();
        box.classList.add('hidden');
      }
    });
  } catch (err) {
    fail(box, err);
  } finally { btn.disabled = false; }
}

document.getElementById('add-term').addEventListener('click', addTerm);
document.getElementById('suggest').addEventListener('click', suggest);
```

- [ ] **Step 3: Manually verify**

Run `wf-dashboard`, open a client's Analytics page. Confirm: the Search Terms table renders (empty state if `seed_queries` is unset, or one row per tracked term otherwise, each reading "not checked yet" until a `RE-CHECK NOW` run has included `with-serp`). Type a term into the input, click ADD — confirm it POSTs, the commit-reminder banner appears only when the write actually succeeded (exit 0), and (checking `docs/client-config.yml` in the client checkout) the term was appended with the rest of the file untouched. Add a second term and confirm it also succeeds (this is the review's blocker — the first draft's version would refuse here). Click "SUGGEST 5 WITH THE AGENT" — confirm it requires `claude` on PATH and real page content to crawl (documented failure mode via Task 3's exit codes, not a bug). Tick some suggestions, click "ADD TICKED", confirm they're appended the same way. Run "RE-CHECK NOW" on Section 1 with `BRIGHTDATA_API_KEY`/`BRIGHTDATA_SERP_ZONE` exported and at least one tracked term — confirm the term's row updates to either "ranks on page one" or the real `serp.absent`/`serp.page_two` finding, and confirm a term that genuinely ranks #1 shows "ranks on page one", not "not checked yet".

- [ ] **Step 4: Commit**

```bash
git add pipeline/dashboard/static/analytics.html pipeline/dashboard/static/page-analytics.js
git commit -m "feat: Analytics page Section 2 — add/suggest/track search terms

Add a term or accept an agent suggestion (wf-seed-queries --format json,
capped at 5 agent-grounded picks) -> commit reminder on real success only.
Term status is derived from the SERP provider's own status string, not
finding presence, so a term ranking on page one (which parse_serp emits no
finding for by design) reads as a win, not as unmeasured. No GSC join --
SERP findings have no page-level location to join on."
```

---

### Task 7: Bundle the docs the sync contract requires

**Files:**
- Modify: `docs/BUG-LEDGER.md` (new Fixed entry)
- Modify: `CHANGELOG.md` (`[Unreleased]`)
- Modify: `pipeline/audit/providers.py` (two docstring updates)
- Modify: `pipeline/audit/seed_queries.py` (module docstring + argparse `description`)
- Modify: `docs/MODULES.md:94` (the `seed_queries.py` one-line entry)
- Modify: `docs/ADMIN-CHECKLIST.md` (the "Filling `seed_queries`" note)

**Interfaces:** none — documentation only.

**Note on the review's finding 11:** the first draft's Task 7 updated `providers.py`'s docstrings but missed four other places that state, as a documented contract, that `wf-seed-queries` never writes `docs/client-config.yml`. That sentence is now only half true — the **agent** still can never write it (the file stays on `DEFAULT_DENY` at every tier, unchanged), but a human/dashboard-triggered `--write` now can. All four locations get the same nuance: *why* it didn't write the file before (the deny floor is about the agent, not about capability), and that the new mode is still human/dashboard-triggered and still requires a commit — not a relaxation of the model, an extension of who can trigger the same paste-and-commit step.

- [ ] **Step 1: Add the CrUX bug to `docs/BUG-LEDGER.md`**

In `docs/BUG-LEDGER.md`, in the `## Fixed` table, add a new row at the top (newest first, matching the existing order) using the next sequential ID (confirm it's still unused before writing: `grep -oE "B-[0-9]+" docs/BUG-LEDGER.md | sort -t- -k2 -n -u | tail -1` — this plan assumes `B-041`):

```
| B-041 | 2026-08-14 | 2026-08-18 | `pipeline/audit/providers.py:118-148` (`crux_findings`) | **CrUX queried the literal config domain, not the host Chrome actually recorded traffic against.** Any client whose apex 301s to `www` (or the reverse) risks an exact-origin miss: CrUX's dataset is keyed per exact origin and is not redirect-aware. Proven live 2026-08-14 while verifying all three optional providers for the first time against real credentials: `wikipedia.org` (bare) returned no CrUX record; `en.wikipedia.org` (the real serving origin, same site) returned a real one. `new-wave.io` returned no record under either its bare or `www` form — consistent with too little Chrome traffic either way, not proof either origin was queried correctly, which is what motivated checking the mechanism directly against a known-high-traffic site. | Origin-level queries now resolve the domain's real serving host via the existing `curl_final_host` helper (built for B-037) before building the CrUX request, trusting the result only when it is the same domain or a subdomain of it — a thermo-nuclear review of the fix caught that a naive substitution would have let an auth wall's own domain (curl_final_host's original B-037 case, e.g. `vercel.com`) resolve through and report a stranger's real Core Web Vitals as the client's. Falls back to the literal domain if resolution fails or fails the same-site check. Per-URL queries are untouched. | `tests/test_providers.py::test_crux_queries_the_resolved_origin_not_the_configured_domain` and five siblings assert the resolved host reaches the request, an unresolvable domain falls back safely, a resolved-but-different-site host (the auth-wall case) is not trusted, per-URL mode never calls the resolver, and the "no field data" message names the host actually queried. `.venv/bin/python -m pytest -q` → **PASTE THE REAL COUNT HERE FROM STEP 3**. |
```

- [ ] **Step 2: Update the two stale "never run live" docstrings in `providers.py`**

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

- [ ] **Step 3: Fix the four other places that say `wf-seed-queries` never writes the config**

In `pipeline/audit/seed_queries.py`, the module docstring currently includes:

```
Nothing here writes docs/client-config.yml. It is on DEFAULT_DENY at every tier
including T3, and the human paste IS the review step: these queries are derived
from the site's own vocabulary but they are not volume-ranked, so a query nobody
searches would produce a real serp.absent finding that reads like a site defect.
```

Replace with:

```
The AGENT-suggestion path (no --write) still never writes docs/client-config.yml
— it prints a YAML block and the human paste IS the review step, because these
queries are derived from the site's own vocabulary but are not volume-ranked, so
a query nobody searches would produce a real serp.absent finding that reads like
a site defect. `docs/client-config.yml` stays on DEFAULT_DENY at every tier
including T3 for the AGENT specifically — it can never raise its own authority
by writing config. `--write` is a second, human/dashboard-triggered path onto
the same file (see write_seed_queries below), not a relaxation of that: it still
never runs unprompted, and the operator still must commit the result before it
takes effect on the next cycle.
```

Then, in the same file, update the CLI's `--help` text. Replace:

```python
    ap = argparse.ArgumentParser(
        prog="wf-seed-queries",
        description="Generate a grounded seed_queries list for a client. Prints "
                    "a YAML block; never writes docs/client-config.yml, which is "
                    "on the deny floor at every tier.")
```

with:

```python
    ap = argparse.ArgumentParser(
        prog="wf-seed-queries",
        description="Generate a grounded seed_queries list for a client, or "
                    "(--write) append specific terms directly. The agent-suggestion "
                    "path only ever prints a YAML block for a human to paste and "
                    "commit; --write is the same human/dashboard-triggered write, "
                    "just typed instead of pasted — docs/client-config.yml still "
                    "stays on the deny floor for the AGENT at every tier.")
```

In `docs/MODULES.md:94`, find the `seed_queries.py` entry (inside the long `onboard.py (...) · client_profile.py (...) · ...` line) which currently reads, in part:

```
`seed_queries.py` (**the query list** — crawls the client's own titles and h1s, hands those facts to Claude Code with an expansion-and-intent recipe adapted from `AgriciDaniel/claude-seo` (MIT), prints a YAML block a human pastes. Deliberately NOT a flag on `wf-site-health` and it never writes `docs/client-config.yml`: `Finding.context` is fingerprinted, so a list regenerated each cycle re-files every SERP finding as NEW and makes RESOLVED unreachable. Drops the bare brand name — you always rank first for your own name, so that entry buys a permanently green finding at full price — `wf-seed-queries`)
```

replace with:

```
`seed_queries.py` (**the query list** — crawls the client's own titles and h1s, hands those facts to Claude Code with an expansion-and-intent recipe adapted from `AgriciDaniel/claude-seo` (MIT), prints a YAML block a human pastes, or (`--write`) appends specific terms directly — same human-commit requirement either way. Deliberately NOT a flag on `wf-site-health`: `Finding.context` is fingerprinted, so a list regenerated each cycle re-files every SERP finding as NEW and makes RESOLVED unreachable — this is also why `--write` only appends, never regenerates. Drops the bare brand name — you always rank first for your own name, so that entry buys a permanently green finding at full price — `wf-seed-queries`)
```

In `docs/ADMIN-CHECKLIST.md`, find the "Filling `seed_queries`" paragraph (around line 139) and add one sentence after it noting the dashboard path:

```
The Analytics dashboard page can also do this directly — type a term or accept
an agent suggestion, both go through `wf-seed-queries --write`, same
human-commit requirement, no bare CLI flags to remember.
```

- [ ] **Step 4: Run the full suite and record the real count**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS. Copy the exact final line (e.g. `710 passed in 6.30s`) — paste it into the `docs/BUG-LEDGER.md` B-041 row from Step 1 (replacing the `PASTE THE REAL COUNT HERE FROM STEP 3` placeholder) and into the CHANGELOG entry in Step 5. Do not guess this number or carry forward the `691 passed` figure from the 2026-08-12 handoff — Tasks 1-3 added new tests.

- [ ] **Step 5: Add the `CHANGELOG.md` entry**

In `CHANGELOG.md`, under `## [Unreleased]`, add a new subsection (before any existing `### Fixed`/`### Documentation` entries already there):

```markdown
### Added

- **Analytics dashboard page — trigger and curate the four external providers
  without hand-typing CLI flags.** New `/analytics` page: a "Re-check now"
  button runs `wf-site-health` with every provider flag (CrUX, GSC,
  DataForSEO capped at 20 pages, Bright Data SERP for whatever terms are
  tracked) and streams the live log — always the full set, never a narrower
  one, so a re-run can never silently erase a previous run's findings from
  `findings.json` and feed the ratchet a false RESOLVED. A Search Terms
  panel lets the operator type terms or accept agent-suggested ones
  (`wf-seed-queries`, unchanged in its own default behavior — still never
  auto-commits) and see each term's rank status, derived from the SERP
  provider's own status string so a term that already ranks on page one
  (which produces no finding at all, by design) reads as a win rather than
  as unmeasured. New `wf-seed-queries --write` mode appends to
  `seed_queries:` in `docs/client-config.yml` (line-based, same pattern as
  `wf-bootstrap-config --add-tier` — never a PyYAML round-trip, which would
  eat the file's comments) and still requires a human commit, same as every
  other config write in this pipeline. New `--format json` mode gives a
  caller that parses output (the dashboard) one unambiguous `[QUERIES]` line
  instead of requiring it to scrape a pasteable YAML block out of merged
  stdout/stderr.

### Fixed

- **CrUX queried the literal config domain instead of the host Chrome
  actually recorded traffic against — B-041.** Proven live 2026-08-14: bare
  `wikipedia.org` had no CrUX record, `en.wikipedia.org` (the real serving
  origin) did. Any client whose apex redirects to `www` (or the reverse) was
  at risk of a false "too little traffic" read. Origin-level queries now
  resolve the real serving host via the existing `curl_final_host` helper
  before querying, trusting the result only when it's the same site (an
  auth wall's own domain, curl_final_host's original B-037 case, has real
  CrUX data too and is deliberately not trusted), and falling back to the
  literal domain otherwise.

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

- [ ] **Step 6: Commit**

```bash
git add docs/BUG-LEDGER.md CHANGELOG.md pipeline/audit/providers.py pipeline/audit/seed_queries.py docs/MODULES.md docs/ADMIN-CHECKLIST.md
git commit -m "docs: B-041 (CrUX origin fix) + first live provider verification + --write docs

Per CLAUDE.md's sync contract. Also repoints the four places that said
wf-seed-queries never writes docs/client-config.yml — that was true only of
the agent-suggestion path and stays true for the agent itself (still on the
deny floor at every tier); --write is a second human/dashboard-triggered
path onto the same file, same commit requirement."
```

---

## Self-Review Notes

- **Spec coverage:** §2.1 (CrUX fix) → Task 1, amended with the same-site guard the review's finding 5 required. §2.2 (writer CLI) → Task 2, rewritten to a line-based walk after finding 1 (the regex version could not re-parse its own output) and extended with `--format json` for finding 10. §2.3 (COMMANDS) → Task 3, with `search-check` deleted and `with-serp` folded into `site-health` per finding 4. §2.4 (frontend, both sections) → Tasks 5-6, with the GSC join and the finding-presence-as-state bug (findings 2, 3) both removed rather than patched, and the shared-strip prerequisite folded into Task 4 as a move into `app.js` rather than a new file (finding 8). §3 (data flow) has no dedicated task — it's a property of Tasks 1-6 together. §4 (cost guardrails) → the button-label wording in Tasks 5-6 states real cost; the original `SOFT_CAP` confirm-dialog idea was cut per finding 9 (enforced in one path only, described a split the storage doesn't track). §5 (bundled fixes) → Task 1 (the fix itself) + Task 7 (the record, now covering four additional stale-doc locations per finding 11). §6 (testing) → each task's own Steps; Task 7 covers "paste the real pytest count" explicitly.
- **Design-spec amendment needed:** §2.3/§2.4/§4 of `docs/superpowers/specs/2026-08-14-performance-analytics-dashboard-design.md` describe a separate `search-check` command, a GSC join on the SERP finding's page, and an editable `max-crawl-pages` field on the Analytics page — none of which this plan now implements, for the reasons in Tasks 3/6/5 respectively. The spec should be updated to match before or alongside implementation, so the two documents don't disagree about what was built.
- **Placeholder scan:** the only intentional placeholders are the two `PASTE THE REAL COUNT HERE FROM STEP 3` markers (BUG-LEDGER row and CHANGELOG entry, Task 7) — they exist because CLAUDE.md forbids writing a test count that was not actually observed, so the plan cannot pre-fill it. Every other step has complete, real code.
- **Type/name consistency checked:** `crux_findings(domain, urls=None)` signature unchanged across Task 1 and its caller in `measure.py` (not modified — no task touches it). `write_seed_queries(target: Path, new_queries: list) -> int` name and signature match between Task 2's implementation and Task 3's `search-add` COMMANDS wiring (which calls the CLI, not the function, directly — no drift risk there). `cfg`/`latestFindings`/`run()`/`load()` are defined once in Task 5 and extended (not duplicated or shadowed) by Task 6. `renderProviders`/`providerTone` signatures in Task 4 match every call site in Tasks 5/6 and the untouched call site in `page-findings.js`. `termStatus()`/`termRow()` names introduced in Task 6 are used consistently within that task and nowhere else.
- **Reviewer verification note:** the thermo-nuclear review that produced these amendments independently checked every file/line/function-signature citation in the prior draft against the actual tree (`common.curl_final_host` at `common.py:51-70`, `crux_findings` at `providers.py:118-148`, `build_argv`/`COMMANDS` at `server.py:309`/`:48`, `PAGES` at `:439-442`, `NAV` at `app.js:42-53`, the `app.js` helper signatures, `GET /api/runs/:id` and `GET /api/clients/:slug` response shapes) and found all of them accurate except one internal inconsistency in the prior Task 4 (a Files-header line range that didn't match its own Step 2) — folded into this version's Task 4, which now cites only the ranges actually used.
