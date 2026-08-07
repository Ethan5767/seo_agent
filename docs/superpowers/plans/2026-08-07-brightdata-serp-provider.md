# Bright Data SERP Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Bright Data's SERP API as a fourth optional measurement provider, so a cycle can see the queries a client ranks poorly for or not at all — the blind spot GSC structurally cannot cover.

**Architecture:** One pure parser plus one network function in the existing `pipeline/audit/providers.py`, following the module's stated doctrine ("not a `providers/` package with an ABC and a registry"). Keywords come from `seed_queries`, which already exists in `client-config.starter.yml` and is currently only counted. `measure.py` gains a `--with-serp` flag alongside the three existing provider flags. No new module, no new config key, no new dependency.

**Tech Stack:** Python 3.12+, stdlib `urllib` only (the repo's one runtime dependency stays PyYAML), pytest.

## Global Constraints

- **No new runtime dependency.** All HTTP goes through the existing `_request()` helper in `providers.py:69`.
- **A skip is never an empty measurement.** Missing credentials return `([], "skipped: ...")`. A total fetch failure returns `([], "failed: ...")`. Never return `[]` with an `ok:` status when nothing was actually measured — the ratchet would read the difference as RESOLVED.
- **Volatile numbers go in `detail`, never `context`.** `Finding.context` is fingerprinted (`baseline.py:221-224`); `detail` is explicitly not. Rank and ranking URL are both volatile. If either reaches `context`, every rank movement becomes RESOLVED + NEW every cycle and the ratchet is worthless.
- **Credentials by name only.** `BRIGHTDATA_API_KEY` and `BRIGHTDATA_SERP_ZONE` from the environment. No `.env` read, nothing written to either repo.
- **The network path will be unverified.** Same standing caveat as CrUX/GSC/DataForSEO (CLAUDE.md sharp edge #6). Only the parser is testable offline. Say so in the docstring and the CHANGELOG — do not claim it works.
- Internal markdown and code comments may use em dashes freely; the `em_dash_check` rule applies to client-facing copy only.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `pipeline/audit/providers.py` | The parser, the codes, the network function | Modify (append a fourth section; update the module docstring table + env list) |
| `pipeline/audit/measure.py` | CLI flag and provider invocation | Modify (`:219-231` argparse block, `:263-276` provider block) |
| `tests/test_providers.py` | Offline parser coverage + named-skip parametrize | Modify |
| `CHANGELOG.md` | `[Unreleased]` entry | Modify |
| `docs/MODULES.md` | `providers.py` line + test count in the header | Modify |
| `config/client-config.starter.yml` | Comment `seed_queries` as feeding the SERP provider | Modify (`:299`) |

**No change needed to `pipeline/gates/acceptance_check.py`.** Its guard at `:106` is an allowlist (`if not code.startswith("health.")`), so `serp.*` codes are already refused as unverifiable-against-a-build. Verified before planning; do not "fix" this.

---

### Task 1: The parser and its codes

Pure functions over an already-fetched payload. This is the whole testable seam — everything in this task runs offline.

**Files:**
- Modify: `pipeline/audit/providers.py` (append after `parse_dataforseo_pages`, before `dataforseo_findings`)
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: `Finding` and `assign_ordinals` from `pipeline.lib.baseline` (already imported at `providers.py:47`); `urllib.parse` (already imported).
- Produces: `_serp_host(url_or_domain: str) -> str`, `parse_serp(payload: dict, domain: str, query: str) -> list[Finding]`, and module constants `SERP_PAGE_ONE_MAX = 10`, `SERP_PAGE_TWO_MAX = 30`. Task 2 calls `parse_serp` and reuses `_serp_host`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_providers.py`:

```python
# ── Bright Data SERP ─────────────────────────────────────────────────────────

def _serp(*ranked):
    """A brd_json=1 payload: (rank, link) pairs in the `organic` array."""
    return {"organic": [{"rank": r, "global_rank": r, "link": u,
                         "title": "t", "description": "d"} for r, u in ranked]}


def test_page_one_is_not_a_finding():
    payload = _serp((3, "https://acme.com/roofing/"))
    assert p.parse_serp(payload, "acme.com", "metal roofing") == []


def test_page_two_fires_with_the_query_as_context():
    payload = _serp((1, "https://other.com/"), (14, "https://acme.com/roofing/"))
    found = p.parse_serp(payload, "acme.com", "metal roofing")
    assert [f.code for f in found] == ["serp.page_two"]
    assert found[0].context == "metal roofing"
    assert found[0].location == "/"


def test_rank_and_url_are_volatile_so_they_live_in_detail():
    """The fingerprint must survive a rank change, or the ratchet reports
    RESOLVED plus NEW every single cycle and means nothing."""
    a = p.parse_serp(_serp((12, "https://acme.com/a/")), "acme.com", "q")[0]
    b = p.parse_serp(_serp((27, "https://acme.com/b/")), "acme.com", "q")[0]
    assert a.detail != b.detail
    assert a.fingerprint == b.fingerprint


def test_absent_from_the_results_is_a_finding():
    found = p.parse_serp(_serp((1, "https://other.com/")), "acme.com", "siding")
    assert [f.code for f in found] == ["serp.absent"]
    assert found[0].context == "siding"


def test_ranking_past_page_three_reads_as_absent_not_as_nothing():
    found = p.parse_serp(_serp((61, "https://acme.com/deep/")), "acme.com", "q")
    assert [f.code for f in found] == ["serp.absent"]


def test_a_lookalike_domain_is_not_the_client():
    """Substring matching would make notacme.com count as acme.com and report a
    rank the client does not have."""
    found = p.parse_serp(_serp((2, "https://notacme.com/x/")), "acme.com", "q")
    assert [f.code for f in found] == ["serp.absent"]


def test_www_and_bare_host_are_the_same_site():
    assert p.parse_serp(_serp((4, "https://www.acme.com/x/")), "acme.com", "q") == []


def test_an_empty_result_set_is_not_evidence_of_absence():
    """No organic array means the fetch or the parse failed. Emitting
    `serp.absent` there would invent a finding out of a broken response."""
    assert p.parse_serp({}, "acme.com", "q") == []
    assert p.parse_serp({"organic": []}, "acme.com", "q") == []
    assert p.parse_serp(None, "acme.com", "q") == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_providers.py -k serp -v
```

Expected: FAIL, `AttributeError: module 'pipeline.audit.providers' has no attribute 'parse_serp'`

- [ ] **Step 3: Write the parser**

Insert into `pipeline/audit/providers.py` immediately after `parse_dataforseo_pages` ends:

```python
# ── Bright Data SERP — the queries GSC cannot see ────────────────────────────
# GSC only reports queries that already have impressions, so it is structurally
# blind to "we rank nowhere for this". That gap is the entire reason this
# provider exists; everything it can already tell you is left to gsc_findings.

SERP_PAGE_ONE_MAX = 10          # on page one there is nothing to remediate
SERP_PAGE_TWO_MAX = 30          # past ~page three the fix is content, not copy


def _serp_host(url_or_domain: str) -> str:
    """Comparable host for either a full URL or a bare domain. Substring
    matching would let notacme.com satisfy a check for acme.com."""
    s = url_or_domain if "//" in url_or_domain else "//" + url_or_domain
    return urllib.parse.urlsplit(s).netloc.lower().removeprefix("www.")


def parse_serp(payload: dict, domain: str, query: str) -> list:
    """Findings from one `brd_json=1` Google response for one seed query.

    `context` is the query and nothing else. Rank and the ranking URL are both
    volatile, so they live in `detail`, which the fingerprint excludes — without
    that, ordinary rank movement would read as RESOLVED plus NEW every cycle.

    `location` is "/" for the same reason CrUX measures at origin level: which
    page ranks is Google's choice and changes without the site changing.
    """
    organic = (payload or {}).get("organic") or []
    if not organic:
        # A missing or empty result set is a broken response, not a site that
        # ranks for nothing. Inventing serp.absent here would be invention.
        return []

    want = _serp_host(domain)
    for item in organic:
        link = item.get("link") or ""
        rank = item.get("global_rank") or item.get("rank")
        if _serp_host(link) != want or not isinstance(rank, int):
            continue
        if rank <= SERP_PAGE_ONE_MAX:
            return []
        if rank <= SERP_PAGE_TWO_MAX:
            return [Finding("serp", "serp.page_two", "/", context=query,
                            detail=f"rank={rank} url={link}")]
        break                                    # ranked, but far past useful

    return [Finding("serp", "serp.absent", "/", context=query,
                    detail=f"not in the top {len(organic)} organic results")]
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_providers.py -k serp -v
```

Expected: PASS, 8 passed

- [ ] **Step 5: Run the full suite for regressions**

```bash
pytest -q
```

Expected: all green, 8 more tests than the 564 in the `docs/MODULES.md` header.

- [ ] **Step 6: Commit**

```bash
git add pipeline/audit/providers.py tests/test_providers.py
git commit -m "providers: parse Bright Data SERP results, rank kept out of the fingerprint"
```

---

### Task 2: The network path, the flag, and the paper trail

Wires the parser to the API and to `measure.py`. The network path cannot be tested offline, so this task's tests cover the credential and failure contracts only — and the docs must say the live path is unverified.

**Files:**
- Modify: `pipeline/audit/providers.py` (module docstring table + env list at `:6-35`; append `serp_findings` at end of file)
- Modify: `pipeline/audit/measure.py` (`:21` import, `:219-231` argparse, `:263-276` provider block)
- Modify: `config/client-config.starter.yml:299`
- Modify: `CHANGELOG.md`, `docs/MODULES.md`
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: `parse_serp` and `_serp_host` from Task 1; `_request(url, payload, headers) -> (json, error)` from `providers.py:69`; `assign_ordinals` from `pipeline.lib.baseline`.
- Produces: `serp_findings(domain: str, queries=None) -> tuple[list, str]`, matching the `(findings, status)` contract of `crux_findings` / `gsc_findings` / `dataforseo_findings`.

- [ ] **Step 1: Write the failing tests**

Add the new provider to the existing named-skip parametrize list at `tests/test_providers.py:20-25`:

```python
    (p.serp_findings, ["BRIGHTDATA_API_KEY", "BRIGHTDATA_SERP_ZONE"]),
```

Then append:

```python
def test_no_seed_queries_is_a_skip_not_a_clean_sweep(monkeypatch):
    """Zero queries measured must never look like zero problems found."""
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    findings, status = p.serp_findings("acme.com", [])
    assert findings == []
    assert status.startswith("skipped:") and "seed_queries" in status


def test_every_query_failing_is_a_failure_not_a_measurement(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    monkeypatch.setattr(p, "_request", lambda *a, **k: (None, "HTTP 429"))
    findings, status = p.serp_findings("acme.com", ["a", "b"])
    assert findings == []
    assert status.startswith("failed:")
    assert "HTTP 429" in status          # the reason, not just the fact


def test_a_partial_failure_is_named_in_the_status(monkeypatch):
    """Two of three queries silently dropped would make the site look cleaner
    than it is, which is exactly what the status string exists to prevent."""
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    calls = []

    def fake(url, payload=None, headers=None, timeout=45):
        calls.append(payload["url"])
        if "bad" in payload["url"]:
            return None, "HTTP 500"
        return {"organic": [{"rank": 1, "link": "https://other.com/"}]}, None

    monkeypatch.setattr(p, "_request", fake)
    findings, status = p.serp_findings("acme.com", ["good", "bad"])
    assert status.startswith("ok: 1/2")
    assert "1 failed" in status
    assert [f.code for f in findings] == ["serp.absent"]


def test_the_query_is_url_encoded_into_the_google_target(monkeypatch):
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "z")
    seen = {}

    def fake(url, payload=None, headers=None, timeout=45):
        seen.update(payload)
        return {"organic": [{"rank": 1, "link": "https://acme.com/"}]}, None

    monkeypatch.setattr(p, "_request", fake)
    p.serp_findings("acme.com", ["metal roofing & siding"])
    assert "metal+roofing+%26+siding" in seen["url"]
    assert "brd_json=1" in seen["url"]
    assert seen["zone"] == "z"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_providers.py -k "serp or credentials" -v
```

Expected: FAIL, `AttributeError: module 'pipeline.audit.providers' has no attribute 'serp_findings'`

- [ ] **Step 3: Write the network function**

Append to the end of `pipeline/audit/providers.py`:

```python
def serp_findings(domain: str, queries=None) -> tuple:
    """(findings, status). One Google SERP request per seed query.

    NOTE: like the other three providers, this network path has never been run
    against the live API — it is written from Bright Data's documented request
    shape and only `parse_serp` is covered by tests. Treat the first real run as
    the verification, and read the status string, not the finding count.
    """
    api_key = os.environ.get("BRIGHTDATA_API_KEY")
    zone = os.environ.get("BRIGHTDATA_SERP_ZONE")
    if not (api_key and zone):
        return [], "skipped: BRIGHTDATA_API_KEY / BRIGHTDATA_SERP_ZONE unset"

    queries = [q.strip() for q in (queries or []) if q and q.strip()]
    if not queries:
        return [], ("skipped: no seed_queries in docs/client-config.yml — there "
                    "is nothing to look up")

    headers = {"Authorization": f"Bearer {api_key}"}
    findings, measured, failed, last_err = [], 0, [], ""
    for query in queries:
        target = ("https://www.google.com/search?q="
                  + urllib.parse.quote_plus(query) + "&brd_json=1")
        payload, err = _request("https://api.brightdata.com/request",
                                {"zone": zone, "url": target, "format": "raw"},
                                headers)
        if err:
            failed.append(query)
            last_err = err
            continue
        findings.extend(parse_serp(payload, domain, query))
        measured += 1

    if not measured:
        # Carry the error itself. "all queries failed" without the reason sends
        # the operator to the dashboard to find out what a status line was for.
        return [], f"failed: none of the {len(queries)} queries returned — {last_err}"

    status = f"ok: {measured}/{len(queries)} queries measured"
    if failed:
        status += f" ({len(failed)} failed: {', '.join(failed[:3])})"
    return assign_ordinals(findings), status
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/test_providers.py -v
```

Expected: PASS

- [ ] **Step 5: Wire it into measure.py**

Change the import at `pipeline/audit/measure.py:21`:

```python
from pipeline.audit.providers import (crux_findings, dataforseo_findings,
                                      gsc_findings, serp_findings)
```

Add the flag after `--with-dataforseo`'s `--max-crawl-pages` in the argparse block (~`:228`):

```python
    ap.add_argument("--with-serp", action="store_true",
                    help="rank and absence for the config's seed_queries (PAID; "
                         "needs BRIGHTDATA_API_KEY / BRIGHTDATA_SERP_ZONE)")
```

Add the invocation after the `--with-dataforseo` block (~`:276`):

```python
    if args.with_serp:
        found, providers["serp"] = serp_findings(cfg["domain"],
                                                 cfg.get("seed_queries"))
        findings.extend(found)
```

- [ ] **Step 6: Confirm the config key actually reaches the provider**

`load_config` currently exposes only `seed_query_count` (`pipeline/lib/common.py:571`), not the list itself. Run:

```bash
python -c "from pipeline.lib.common import load_config; print(load_config('.').get('seed_queries'))"
```

If this prints `None`, add the passthrough beside the existing count at `common.py:571`:

```python
        "seed_queries": cfg.get("seed_queries") or [],
```

Then re-run the command and confirm it prints a list. **Do not skip this step** — without it `--with-serp` always reports the "no seed_queries" skip and the provider is wired to nothing, which is exactly the B-007 failure mode (implemented is not wired).

- [ ] **Step 7: Prove the flag is reachable and skips loudly**

```bash
env -u BRIGHTDATA_API_KEY -u BRIGHTDATA_SERP_ZONE python -m pipeline.audit.measure --help | grep -A2 with-serp
```

Expected: the flag and its PAID help text appear.

- [ ] **Step 8: Update `config/client-config.starter.yml:299`**

```yaml
seed_queries: []                       # AEO citation-sweep seeds; also the query
                                       # list for --with-serp (Bright Data SERP)
```

- [ ] **Step 9: Update the paper trail**

`CHANGELOG.md`, under `[Unreleased]`:

```markdown
### Added
- **Bright Data SERP as a fourth optional provider** (`--with-serp`). Fires
  `serp.page_two` (rank 11-30) and `serp.absent` (rank >30 or not in the result
  set) per entry in the config's `seed_queries`. Fills the one gap GSC cannot
  cover by construction: GSC only reports queries that already have impressions,
  so it can never say "we rank nowhere for this".
- Rank and the ranking URL are carried in `Finding.detail`, which the
  fingerprint excludes, so ordinary rank movement stays PERSISTING instead of
  churning RESOLVED + NEW every cycle. Covered by
  `test_rank_and_url_are_volatile_so_they_live_in_detail`.

### Unverified
- The Bright Data network path has **never been run live**, exactly as with
  CrUX / GSC / DataForSEO (sharp edge #6). Only `parse_serp` is tested. On the
  first real run read the `[serp]` status line, not the finding count.
```

`docs/MODULES.md`: update the test count in the header line (`564 tests` → the number `pytest -q` now reports) and extend the `providers.py` line to name the fourth source. The module count does not change — `providers.py` already exists.

- [ ] **Step 10: Run the full suite and read the result**

```bash
pytest -q
```

Read the output before continuing. Do not pipe it into `tail`/`grep` inside an `&&` chain — CLAUDE.md §4: the pipeline's exit status is the last command's, so a failing suite reports success and the chain proceeds to push.

- [ ] **Step 11: Commit**

```bash
git add pipeline/audit/providers.py pipeline/audit/measure.py pipeline/lib/common.py \
        tests/test_providers.py config/client-config.starter.yml \
        CHANGELOG.md docs/MODULES.md
git commit -m "measure: --with-serp, the queries Search Console cannot see"
```

---

## Deliberately Not In This Plan

- **SERP feature findings** (AI overview, featured snippet, local pack). These are the highest-value findings this provider could produce, but the parsed field names for them are not confirmed in Bright Data's public docs — only `organic[]` with `rank` / `global_rank` / `link` / `title` / `description` is. Adding them now would mean inventing a schema, which is the exact thing `claim_provenance_check` exists to refuse. Capture the real payload on the first live run, then add them against the observed shape.
- **Competitor tracking.** Same request, different domain filter, but every finding it produces is actionable only at T2 (create a page), and T1 is the default tier. Add it when a T2 client actually exists.
- **Proxies / Web Unlocker / Browser API.** `measure.py` fetches the client's own site over plain HTTP. Nothing in this pipeline needs an unblocking proxy.
- **A `providers/` package.** The module docstring is explicit: add the abstraction when a second vendor in a category lands, not in advance of one. Bright Data is the first SERP vendor.

## Before Any Of This

CLAUDE.md sharp edge #6: three provider network paths have shipped and none has run live. This plan adds a fourth. Consider running one live `wf-site-measure --with-gsc` against a real client first and reading the status string — verifying an existing path is worth more than adding an unverified one.
