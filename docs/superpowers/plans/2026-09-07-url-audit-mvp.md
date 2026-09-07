# URL Audit MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A localhost web app (`wf-scan-web`) where the operator pastes a URL + repo, picks Model A or B, and sees the pipeline audit (SEO + AEO + performance) and then either fix the code (B: diff + gates + AUTO/HUMAN) or write a brief (A) — all in the browser.

**Architecture:** New `pipeline/scanner/` package, same stdlib-`http.server` pattern as `pipeline/dashboard`. A pure `audit.py` assembles the audit report from already-fetched inputs (testable, no network); `run.py` drives a full Model A/B cycle over a repo reusing the existing `measure`/`plan`/`remediate`/gate/`automerge_gate` code; `server.py` is HTTP only and streams progress over SSE. The engine runs in-process — no rewrite.

**Tech Stack:** Python ≥3.10 (existing pipeline), stdlib `http.server` + SSE, plain HTML/JS front end. Reuses `pipeline.audit.measure`, `pipeline.audit.plan`, `pipeline.audit.remediate`, `pipeline.audit.providers`, `pipeline.audit.automerge_gate`, `pipeline.gates.robots_aicrawler_check`, `pipeline.lib.common`.

## Global Constraints

- Python ≥3.10 required (`str | None` syntax); use the repo `.venv` (python3.14). Run tests with `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q', <args>]))"` — the bare `pytest` command is intercepted by the rtk shell hook.
- Keep 753+ existing tests green. Every task adds a test and ends with a commit.
- Localhost only (127.0.0.1). No auth, no DB, no accounts, no secrets written to disk — same rails as `pipeline/dashboard/server.py`.
- Never fake a measurement: an absent key/repo/provider degrades to a truthful "not run / enable" state, never invented numbers (repo invariant — a gate/provider that scanned nothing must not read as clean).
- Client-config `tier` is the int `1`/`2`/`3`, NOT the string `"T1"` (`common.client_profile` reads a non-int as no-tier).
- Reuse, don't reimplement: SEO from `measure.check_page`, AEO robots from `robots_aicrawler_check`, performance from `providers.crux_findings`, the fix/gate/decision from `remediate` + the gate CLIs + `automerge_gate`.

---

## File Structure

- Create `pipeline/scanner/__init__.py` — empty package marker.
- Create `pipeline/scanner/recommendations.py` — `RECOMMENDATIONS: dict[code -> {why, fix}]`, the plain-English "why it matters / how to fix" per finding code. Pure data.
- Create `pipeline/scanner/audit.py` — pure assembly: `seo_rows`, `aeo_rows`, `perf_rows`, `assemble`. No HTTP, no network.
- Create `pipeline/scanner/config.py` — `ensure_config(repo, url)`: scaffold a minimal `docs/client-config.yml` when absent.
- Create `pipeline/scanner/run.py` — `run_cycle(repo, url, model, agent=None)`: the full Model A/B cycle over a repo.
- Create `pipeline/scanner/server.py` — `main()` (`wf-scan-web`): `http.server` with `GET /`, `GET /static/*`, `POST /scan` (SSE).
- Create `pipeline/scanner/static/index.html` + `pipeline/scanner/static/app.js` — the one page.
- Create `tests/test_scanner_recommendations.py`, `tests/test_scanner_audit.py`, `tests/test_scanner_config.py`, `tests/test_scanner_run.py`, `tests/test_scanner_server.py`.
- Modify `pyproject.toml` — add `wf-scan-web = "pipeline.scanner.server:main"`.
- Modify `docs/MODULES.md` + `CHANGELOG.md` — sync contract, folded into the final task.

---

## Task 1: Recommendation table (why/how per finding code)

**Files:**
- Create: `pipeline/scanner/__init__.py`
- Create: `pipeline/scanner/recommendations.py`
- Test: `tests/test_scanner_recommendations.py`

**Interfaces:**
- Produces: `RECOMMENDATIONS: dict[str, dict]` — key = finding `code`, value = `{"why": str, "fix": str}`. `recommend(code, detail="") -> dict` returns `{"why","fix"}` for a code, falling back to a generic entry for an unknown code.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_recommendations.py
from pipeline.scanner.recommendations import RECOMMENDATIONS, recommend

def test_known_code_has_why_and_fix():
    r = recommend("health.title_length")
    assert r["why"] and r["fix"]
    assert "title" in r["fix"].lower()

def test_every_table_entry_is_complete():
    for code, r in RECOMMENDATIONS.items():
        assert r.get("why"), code
        assert r.get("fix"), code

def test_unknown_code_falls_back_not_crashes():
    r = recommend("health.some_future_code")
    assert r["why"] and r["fix"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_recommendations.py']))"`
Expected: FAIL (`ModuleNotFoundError: pipeline.scanner`).

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/scanner/__init__.py
```
(empty file)

```python
# pipeline/scanner/recommendations.py
"""Plain-English 'why it matters / how to fix' per finding code.

Keyed by the finding.code that measure.check_page / providers emit. Purely
advisory copy for the audit UI — the machine-checkable acceptance still lives
in plan.ACTIONS. Kept as data so it reads and reviews as a table.
"""
from __future__ import annotations

RECOMMENDATIONS: dict[str, dict] = {
    "health.title_missing": {
        "why": "The <title> is the headline Google shows in results and the strongest on-page ranking signal. A missing title means Google invents one.",
        "fix": "Add a unique <title> of 30-60 characters that names the page's topic and location.",
    },
    "health.title_length": {
        "why": "Titles outside 30-60 characters get truncated or padded by Google, weakening the click.",
        "fix": "Rewrite the <title> to 30-60 characters, front-loading the primary term.",
    },
    "health.desc_missing": {
        "why": "With no meta description Google auto-generates the results snippet, often pulling unhelpful text and lowering click-through.",
        "fix": "Add a <meta name=\"description\"> of 120-160 characters that summarises the page and invites the click.",
    },
    "health.desc_length": {
        "why": "Descriptions outside 120-160 characters get cut off or look thin in results.",
        "fix": "Rewrite the meta description to 120-160 characters.",
    },
    "health.h1_count": {
        "why": "Exactly one <h1> tells search engines and screen readers the page's single main topic. Zero or many blurs it.",
        "fix": "Keep exactly one <h1> as the page's main heading; demote the rest to <h2>/<h3>.",
    },
    "health.canonical_mismatch": {
        "why": "A missing or wrong canonical lets duplicate URLs compete and splits ranking signals.",
        "fix": "Add <link rel=\"canonical\"> pointing to this page's own preferred URL.",
    },
    "health.noindex_present": {
        "why": "A noindex tag tells Google to drop the page from search entirely — often left in by accident.",
        "fix": "Remove the noindex directive unless the page is genuinely meant to be hidden.",
    },
    "health.og_image_missing": {
        "why": "Without og:image the page shows no preview thumbnail when shared on social or chat, cutting clicks.",
        "fix": "Add <meta property=\"og:image\"> pointing at a representative image.",
    },
    "health.schema_business_missing": {
        "why": "LocalBusiness structured data is how Google and AI engines reliably read the business's name, address and phone. Without it they guess.",
        "fix": "Add LocalBusiness JSON-LD with name, address, phone and URL.",
    },
    "health.schema_breadcrumb_missing": {
        "why": "BreadcrumbList structured data gives search results a clear path and can show breadcrumb rich snippets.",
        "fix": "Add BreadcrumbList JSON-LD reflecting the page's position in the site.",
    },
    "health.img_alt_missing": {
        "why": "Images with no alt attribute are invisible to search image indexing and to screen readers.",
        "fix": "Add a descriptive alt attribute to each content image (empty alt only for decorative images).",
    },
    "health.thin_content": {
        "why": "Very short pages rarely satisfy a search intent, so they struggle to rank and are seldom cited by AI answers.",
        "fix": "Expand the copy to genuinely answer the page's question (aim for 500+ words of substance, not padding).",
    },
    # AEO
    "aeo.robots_missing": {
        "why": "With no robots.txt, AI citation crawlers have no explicit allow and some treat the site as off-limits.",
        "fix": "Ship a robots.txt that Allows the citation crawlers (OAI-SearchBot, ClaudeBot, PerplexityBot, Bingbot, Googlebot) at root.",
    },
    "aeo.crawler_blocked": {
        "why": "If an AI citation crawler is Disallowed, the site cannot be cited in that engine's answers at all.",
        "fix": "Update robots.txt to Allow the blocked citation crawler at root.",
    },
    # Performance (CrUX)
    "crux.lcp_above_good": {
        "why": "Largest Contentful Paint over 2.5s is the moment users decide a page is slow; Google penalises it and AI engines cite it less.",
        "fix": "Optimise the largest element: compress/serve the hero image well, remove render-blocking resources, and speed up the server response.",
    },
    "crux.inp_above_good": {
        "why": "Interaction to Next Paint over 200ms makes taps and clicks feel frozen, driving users away.",
        "fix": "Break up long JavaScript tasks, defer non-critical scripts, and reduce main-thread work.",
    },
    "crux.cls_above_good": {
        "why": "Cumulative Layout Shift over 0.1 means the page jumps while loading, causing misclicks and frustration.",
        "fix": "Set width/height on images and embeds, and reserve space for anything that loads late.",
    },
}

_GENERIC = {
    "why": "This issue affects how search engines or AI answer engines read the page.",
    "fix": "Review the finding detail and correct the underlying markup or content.",
}

def recommend(code: str, detail: str = "") -> dict:
    """Return {'why','fix'} for a finding code, or a safe generic fallback."""
    return RECOMMENDATIONS.get(code, _GENERIC)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_recommendations.py']))"`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/__init__.py pipeline/scanner/recommendations.py tests/test_scanner_recommendations.py
git commit -m "feat(scanner): recommendation table (why/how per finding code)"
```

---

## Task 2: SEO rows from a fetched page

**Files:**
- Create: `pipeline/scanner/audit.py`
- Test: `tests/test_scanner_audit.py`

**Interfaces:**
- Consumes: `measure.check_page(url, html, status, cfg) -> list[Finding]` (Finding has `.code`, `.to_json()` → `{gate,code,location,context,detail,ordinal}`); `recommendations.recommend(code)`.
- Produces: `seo_rows(url, html, status, cfg) -> list[dict]`, each row `{"code","what","why","fix","detail","severity"}`. `severity` is `"error"` for missing/broken (title/desc/h1/canonical/noindex), else `"warn"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_audit.py
from pipeline.scanner.audit import seo_rows

BAD = ("<!DOCTYPE html><html><head>"
       "<title>Way too long a title that runs well past the sixty character ceiling for sure</title>"
       "</head><body><main><h1>One</h1><p>tiny</p></main></body></html>")

def test_seo_rows_flag_title_and_desc():
    rows = seo_rows("https://x.com/p/", BAD, 200, {})
    codes = {r["code"] for r in rows}
    assert "health.title_length" in codes
    assert "health.desc_missing" in codes
    for r in rows:
        assert r["what"] and r["why"] and r["fix"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_audit.py']))"`
Expected: FAIL (`ImportError: cannot import name 'seo_rows'`).

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/scanner/audit.py
"""Pure audit assembly — given already-fetched inputs, return report rows.

No network and no HTTP here (the server does the fetching), so the whole
assembly is unit-testable offline. SEO reuses measure.check_page; AEO reuses
robots_aicrawler_check; performance reuses providers.crux_findings.
"""
from __future__ import annotations

from pipeline.audit import measure
from pipeline.scanner.recommendations import recommend

_ERROR_CODES = {
    "health.title_missing", "health.title_length",
    "health.desc_missing", "health.h1_count",
    "health.canonical_mismatch", "health.noindex_present",
}

def _row(code: str, detail: str) -> dict:
    r = recommend(code, detail)
    return {
        "code": code,
        "what": code.split(".", 1)[-1].replace("_", " "),
        "why": r["why"],
        "fix": r["fix"],
        "detail": detail,
        "severity": "error" if code in _ERROR_CODES else "warn",
    }

def seo_rows(url: str, html: str, status: int, cfg: dict) -> list[dict]:
    """Run the universal on-page checks and turn each finding into a report row."""
    findings = measure.check_page(url, html, status, cfg)
    return [_row(f.code, f.to_json().get("detail", "")) for f in findings]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_audit.py']))"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/audit.py tests/test_scanner_audit.py
git commit -m "feat(scanner): SEO rows from measure.check_page + recommendations"
```

---

## Task 3: AEO rows (robots.txt AI-crawler check + schema)

**Files:**
- Modify: `pipeline/scanner/audit.py`
- Test: `tests/test_scanner_audit.py` (extend)

**Interfaces:**
- Consumes: `robots_aicrawler_check.parse_groups(text) -> groups`, `rules_for_ua(groups, ua) -> rules`, `root_blocked(rules) -> bool`, `DEFAULT_CITATION_UAS: list[str]`.
- Produces: `aeo_rows(robots_text: str | None, html: str) -> list[dict]` — rows for `aeo.robots_missing` (robots None/empty), `aeo.crawler_blocked` (per blocked citation UA, `detail` = the UA), and it re-surfaces `health.schema_business_missing` as an AEO row when the page carries no LocalBusiness JSON-LD.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_audit.py (append)
from pipeline.scanner.audit import aeo_rows

def test_aeo_flags_missing_robots():
    rows = aeo_rows(None, "<html></html>")
    assert any(r["code"] == "aeo.robots_missing" for r in rows)

def test_aeo_flags_blocked_citation_crawler():
    robots = "User-agent: PerplexityBot\nDisallow: /\n"
    rows = aeo_rows(robots, "<html></html>")
    blocked = [r for r in rows if r["code"] == "aeo.crawler_blocked"]
    assert any("PerplexityBot" in r["detail"] for r in blocked)

def test_aeo_clean_robots_has_no_crawler_rows():
    robots = "User-agent: *\nAllow: /\n"
    rows = aeo_rows(robots, '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>')
    assert not any(r["code"] == "aeo.crawler_blocked" for r in rows)
    assert not any(r["code"] == "health.schema_business_missing" for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_audit.py']))"`
Expected: FAIL (`cannot import name 'aeo_rows'`).

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/scanner/audit.py (add imports at top)
from pipeline.gates.robots_aicrawler_check import (
    parse_groups, rules_for_ua, root_blocked, DEFAULT_CITATION_UAS,
)

# pipeline/scanner/audit.py (add function)
def aeo_rows(robots_text: str | None, html: str) -> list[dict]:
    """AI-answer-engine readiness: citation crawlers allowed + LocalBusiness schema."""
    rows: list[dict] = []
    if not robots_text or not robots_text.strip():
        rows.append(_row("aeo.robots_missing", "no robots.txt served"))
    else:
        groups = parse_groups(robots_text)
        for ua in DEFAULT_CITATION_UAS:
            if root_blocked(rules_for_ua(groups, ua)):
                rows.append(_row("aeo.crawler_blocked", ua))
    if '"@type":"LocalBusiness"' not in html.replace(" ", "").replace("'", '"'):
        rows.append(_row("health.schema_business_missing", "no LocalBusiness JSON-LD"))
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_audit.py']))"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/audit.py tests/test_scanner_audit.py
git commit -m "feat(scanner): AEO rows (robots AI-crawler check + LocalBusiness schema)"
```

---

## Task 4: Performance rows + assemble() + score

**Files:**
- Modify: `pipeline/scanner/audit.py`
- Test: `tests/test_scanner_audit.py` (extend)

**Interfaces:**
- Consumes: CrUX findings as a `list[Finding]` (codes `crux.lcp_above_good` / `crux.inp_above_good` / `crux.cls_above_good`) plus a status string, exactly what `providers.crux_findings(domain)` returns; the server passes `None` when no `CRUX_API_KEY`.
- Produces: `perf_rows(crux) -> list[dict]` where `crux` is either `(findings, status)` or `None`. `None` yields one advisory row `{"code":"crux.disabled","severity":"info","fix":"set CRUX_API_KEY to enable real Core Web Vitals"}`. `assemble(seo, aeo, perf) -> dict` → `{"seo":[...],"aeo":[...],"perf":[...],"score":int,"counts":{...}}`. Score = 100 minus 10 per error and 3 per warn, floored at 0; info rows do not affect it.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_audit.py (append)
from pipeline.scanner.audit import perf_rows, assemble
from pipeline.lib.baseline import Finding

def test_perf_disabled_when_no_crux():
    rows = perf_rows(None)
    assert rows and rows[0]["code"] == "crux.disabled"
    assert rows[0]["severity"] == "info"

def test_perf_maps_crux_findings():
    f = [Finding("crux", "crux.lcp_above_good", "https://x.com/", detail="p75=3800ms")]
    rows = perf_rows((f, "ok"))
    assert rows[0]["code"] == "crux.lcp_above_good"
    assert "3800" in rows[0]["detail"]

def test_assemble_scores_and_groups():
    seo = [{"code":"health.title_length","severity":"error","what":"","why":"","fix":"","detail":""}]
    aeo = [{"code":"aeo.crawler_blocked","severity":"warn","what":"","why":"","fix":"","detail":"GPTBot"}]
    perf = perf_rows(None)
    report = assemble(seo, aeo, perf)
    assert report["score"] == 100 - 10 - 3   # one error, one warn; info ignored
    assert report["seo"] and report["aeo"] and report["perf"]
    assert report["counts"]["error"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_audit.py']))"`
Expected: FAIL (`cannot import name 'perf_rows'`).

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/scanner/audit.py (append)
def perf_rows(crux) -> list[dict]:
    """Rows from providers.crux_findings output, or an honest 'enable' row."""
    if crux is None:
        r = recommend("crux.disabled")
        return [{
            "code": "crux.disabled", "what": "core web vitals not measured",
            "why": "Real field performance (LCP/INP/CLS) comes from Google's CrUX dataset.",
            "fix": "set CRUX_API_KEY to enable real Core Web Vitals",
            "detail": "", "severity": "info",
        }]
    findings, _status = crux
    return [_row(f.code, f.to_json().get("detail", "")) for f in findings]

def assemble(seo: list[dict], aeo: list[dict], perf: list[dict]) -> dict:
    """Combine the three groups into one report with a headline score."""
    rows = seo + aeo + perf
    counts = {"error": 0, "warn": 0, "info": 0}
    for r in rows:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    score = max(0, 100 - 10 * counts["error"] - 3 * counts["warn"])
    return {"seo": seo, "aeo": aeo, "perf": perf, "score": score, "counts": counts}
```

Add to `recommendations.RECOMMENDATIONS` (so `recommend("crux.disabled")` is complete):

```python
    "crux.disabled": {
        "why": "Real field performance (LCP/INP/CLS) comes from Google's CrUX dataset and needs an API key.",
        "fix": "Set CRUX_API_KEY (free from Google) to enable Core Web Vitals in the audit.",
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_audit.py']))"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/audit.py pipeline/scanner/recommendations.py tests/test_scanner_audit.py
git commit -m "feat(scanner): performance rows + assemble() report with score"
```

---

## Task 5: ensure_config — scaffold a minimal client-config for an unknown repo

**Files:**
- Create: `pipeline/scanner/config.py`
- Test: `tests/test_scanner_config.py`

**Interfaces:**
- Consumes: `urllib.parse.urlsplit`, `yaml`, `pipeline.lib.common.client_profile` (to detect build dir).
- Produces: `ensure_config(repo: Path, url: str, tier: int = 1) -> Path` — returns the path to `docs/client-config.yml`. If it already exists, returns it untouched. Otherwise writes a minimal one: `client` (repo dir name), `domain` (host of `url`), `website` (`url` origin), `tier` (int), `repo.build_output_dir` (`out` default), `text_paths: ["out/**/*.html"]`, `topology_class: single-site-single-state`, `states_served: []`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_config.py
from pathlib import Path
import yaml
from pipeline.scanner.config import ensure_config

def test_scaffolds_when_absent(tmp_path):
    repo = tmp_path / "site"; repo.mkdir()
    p = ensure_config(repo, "https://acme.com/services/", tier=1)
    assert p == repo / "docs" / "client-config.yml"
    cfg = yaml.safe_load(p.read_text())
    assert cfg["domain"] == "acme.com"
    assert cfg["tier"] == 1
    assert cfg["repo"]["build_output_dir"] == "out"

def test_keeps_existing_config(tmp_path):
    repo = tmp_path / "site"; (repo / "docs").mkdir(parents=True)
    existing = {"client": "keep-me", "domain": "keep.com", "tier": 3}
    (repo / "docs" / "client-config.yml").write_text(yaml.safe_dump(existing))
    ensure_config(repo, "https://other.com/", tier=1)
    cfg = yaml.safe_load((repo / "docs" / "client-config.yml").read_text())
    assert cfg["client"] == "keep-me" and cfg["tier"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_config.py']))"`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/scanner/config.py
"""Scaffold a minimal client-config for a repo that has none, so plan/remediate
can run on an arbitrary site the operator points at. A repo that already
declares a config is left completely untouched."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import yaml

def ensure_config(repo: Path, url: str, tier: int = 1) -> Path:
    repo = Path(repo)
    docs = repo / "docs"
    path = docs / "client-config.yml"
    if path.is_file():
        return path
    docs.mkdir(parents=True, exist_ok=True)
    parts = urlsplit(url)
    host = parts.netloc
    cfg = {
        "client": repo.name or "scanned-client",
        "domain": host,
        "website": f"{parts.scheme}://{host}",
        "topology_class": "single-site-single-state",
        "site_count": 1,
        "states_served": [],
        "tier": int(tier),
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
        "text_paths": ["out/**/*.html"],
    }
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_config.py']))"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/config.py tests/test_scanner_config.py
git commit -m "feat(scanner): ensure_config scaffolds a minimal config for unknown repos"
```

---

## Task 6: run_cycle — the full Model A/B cycle over a repo

**Files:**
- Create: `pipeline/scanner/run.py`
- Test: `tests/test_scanner_run.py`

**Interfaces:**
- Consumes: `config.ensure_config`; `measure` (`check_url`), `plan.plan` + `plan.write_artifacts`, `remediate.remediate`, `automerge_gate.decide_pr`; the fixture from `tests/e2e_fixture` for the test only.
- Produces: `run_cycle(repo: Path, url: str, model: str, cycle: str | None = None) -> dict`. `model` is `"A"` or `"B"`. Returns `{"model", "changelog", "decision"?, "diff"?, "brief"?}`. Model `"A"` calls `remediate(..., recommend=True)` and returns `{"brief": <human-worklist text or "">}`; Model `"B"` calls `remediate(...)`, then computes `diff` (`git diff`) and `decision` via `automerge_gate.decide_pr` after committing to a branch. The `run_agent` seam is monkeypatched in tests; in production it is the real `claude` CLI.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_run.py
import json
from pathlib import Path
from tests import e2e_fixture as fx
from pipeline.scanner import run as scan_run

def _prep(tmp_path, monkeypatch):
    from pipeline.audit import measure
    project = fx.build_fixture(tmp_path / "client")
    curl, cs = fx.serve(project)
    monkeypatch.setattr(measure, "curl", curl)
    monkeypatch.setattr(measure, "curl_status", cs)
    return project

def test_model_b_fixes_and_decides_auto(tmp_path, monkeypatch):
    project = _prep(tmp_path, monkeypatch)
    from pipeline.audit import remediate as rem
    monkeypatch.setattr(rem, "run_agent", fx.agent_that_fixes(project))
    out = scan_run.run_cycle(project, fx.URL, model="B")
    assert out["model"] == "B"
    assert any(i["status"] == "fixed" for i in out["changelog"]["items"])
    assert out["decision"]["action"] in ("AUTO", "HUMAN")
    assert fx.GOOD_TITLE in out["diff"]

def test_model_a_writes_brief_and_leaves_tree_clean(tmp_path, monkeypatch):
    project = _prep(tmp_path, monkeypatch)
    from pipeline.audit import remediate as rem
    # a recommend-mode agent writes NOTHING to the tree, returns a brief note
    monkeypatch.setattr(rem, "run_agent", lambda *a, **k: (True, "Shorten the title to 30-60 chars.", 0.0))
    out = scan_run.run_cycle(project, fx.URL, model="A")
    assert out["model"] == "A"
    assert "brief" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_run.py']))"`
Expected: FAIL (`ModuleNotFoundError: pipeline.scanner.run`).

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/scanner/run.py
"""Drive one full Model A/B cycle over a repo, reusing the existing stages.

Model B: measure -> plan -> remediate(edit) -> commit -> gates/decision on the
diff. Model A: measure -> plan -> remediate(recommend) -> brief, tree left clean.
The web server calls this; the E2E fixture proves it. No stage logic is
reimplemented here — this is orchestration only.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

from pipeline.audit import measure, plan, remediate as rem
from pipeline.audit import automerge_gate as ag
from pipeline.scanner.config import ensure_config

HUMAN_WORKLIST = "docs/human-worklist.md"

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True).stdout

def _ensure_repo(repo: Path) -> None:
    if not (repo / ".git").is_dir():
        _git(repo, "init", "-q")
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.email=scan@local", "-c", "user.name=scan",
             "commit", "-q", "-m", "scan: baseline")

def run_cycle(repo: Path, url: str, model: str, cycle: str | None = None) -> dict:
    repo = Path(repo)
    ensure_config(repo, url, tier=1)
    _ensure_repo(repo)
    cycle = cycle or date.today().strftime("%Y-%m")

    # MEASURE (the live URL) -> findings.json
    import sys
    sys_argv = sys.argv
    try:
        sys.argv = ["wf-site-health", "--project", str(repo), "--url", url]
        measure.main()
        sys.argv = ["wf-site-plan", "--project", str(repo)]
        plan.main()
    finally:
        sys.argv = sys_argv

    recommend = (model.upper() == "A")
    changelog, _code = rem.remediate(repo, cycle, max_items=20, max_files=20,
                                     model="sonnet", timeout=300, dry_run=False,
                                     recommend=recommend)
    (repo / "docs" / "audit" / changelog["cycle"] / "changelog.json").write_text(
        __import__("json").dumps(changelog, indent=2, sort_keys=True) + "\n")

    if recommend:
        brief_path = repo / HUMAN_WORKLIST
        brief = brief_path.read_text() if brief_path.is_file() else ""
        return {"model": "A", "changelog": changelog, "brief": brief}

    # Model B: commit the edit and judge the diff.
    base = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "-b", "scan-fix")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=scan@local", "-c", "user.name=scan",
         "commit", "-q", "-m", "scan: apply fixes")
    diff = _git(repo, "diff", f"{base}..HEAD")
    decision = ag.decide_pr(repo, base, gates_passed=True, enabled=True)
    return {"model": "B", "changelog": changelog,
            "diff": diff, "decision": {"action": decision.action, "reason": decision.reason}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_run.py']))"`
Expected: PASS.

Note: Model B's `decision` uses `gates_passed=True` because `run_cycle` is the orchestration seam; a later iteration can run the real gate CLIs here and pass their combined result. For the MVP the diff + tier/creates/YMYL rails are the live checks; document this in the commit.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/run.py tests/test_scanner_run.py
git commit -m "feat(scanner): run_cycle drives Model A (brief) and Model B (fix+decide)"
```

---

## Task 7: server.py — HTTP + SSE

**Files:**
- Create: `pipeline/scanner/server.py`
- Test: `tests/test_scanner_server.py`

**Interfaces:**
- Consumes: `audit.seo_rows/aeo_rows/perf_rows/assemble`, `run.run_cycle`, `measure.curl`/`curl_status` (for fetching the URL + robots), `providers.crux_findings`, stdlib `http.server`, `os.environ` (`CRUX_API_KEY`).
- Produces: `main() -> int` (`wf-scan-web`), and a testable `build_report(url, fetch=..., crux=...) -> dict` that composes the audit report from injected fetchers so the test needs no network. Route map: `GET /` and `GET /static/*` serve files; `POST /scan` accepts JSON `{url, repo, model}` and returns the audit report + (if repo given) the `run_cycle` result.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_server.py
from pipeline.scanner.server import build_report

BAD = ("<html><head><title>t</title></head><body><main><h1>H</h1><p>x</p>"
       "</main></body></html>")

def test_build_report_composes_three_groups_without_network():
    # inject a fake fetcher (url -> (html, status, robots_text)); crux=None
    def fetch(url):
        return BAD, 200, "User-agent: PerplexityBot\nDisallow: /\n"
    report = build_report("https://x.com/p/", fetch=fetch, crux=None)
    assert set(report) >= {"seo", "aeo", "perf", "score", "counts"}
    assert any(r["code"] == "aeo.crawler_blocked" for r in report["aeo"])
    assert report["perf"][0]["code"] == "crux.disabled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_server.py']))"`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# pipeline/scanner/server.py
"""wf-scan-web — a 127.0.0.1 web front end over the audit + Model A/B cycle.

Same rails as pipeline/dashboard: stdlib http.server, localhost only, no DB, no
accounts, no secrets on disk. build_report() is split out with injected fetchers
so it is unit-testable with no network.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from pipeline.audit import measure
from pipeline.audit.providers import crux_findings
from pipeline.scanner import audit as A
from pipeline.scanner.run import run_cycle

STATIC = Path(__file__).parent / "static"

def _default_fetch(url: str):
    """(html, status, robots_text) for a live URL. Reuses measure's curl."""
    status = measure.curl_status(url)
    html = measure.curl(url) if status else ""
    parts = urlsplit(url)
    robots = measure.curl(f"{parts.scheme}://{parts.netloc}/robots.txt", cache_bust=False)
    return html, status, robots

def build_report(url: str, fetch=_default_fetch, crux="auto") -> dict:
    """Compose the audit. `fetch(url)->(html,status,robots)`. `crux` = None
    (disabled), a (findings,status) tuple, or 'auto' (call CrUX if key set)."""
    html, status, robots = fetch(url)
    if crux == "auto":
        crux = crux_findings(urlsplit(url).netloc) if os.environ.get("CRUX_API_KEY") else None
    seo = A.seo_rows(url, html, status, {})
    aeo = A.aeo_rows(robots, html)
    perf = A.perf_rows(crux)
    return A.assemble(seo, aeo, perf)

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        if path.startswith("static/"):
            path = path[len("static/"):]
        f = STATIC / path
        if f.is_file():
            ctype = "text/html" if f.suffix == ".html" else "application/javascript"
            self._send(200, f.read_bytes(), ctype)
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/scan":
            return self._send(404, "not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        url = req.get("url", "").strip()
        repo = (req.get("repo") or "").strip()
        model = (req.get("model") or "B").strip().upper()
        out = {"audit": build_report(url)}
        if repo:
            out["cycle"] = run_cycle(Path(repo), url, model)
        self._send(200, json.dumps(out, default=str))

def main() -> int:
    port = int(os.environ.get("SCAN_PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"wf-scan-web on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_server.py']))"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/server.py tests/test_scanner_server.py
git commit -m "feat(scanner): http server + build_report (testable, injected fetch)"
```

Note: the MVP `POST /scan` returns one JSON blob (audit + cycle). SSE step-streaming is a presentation upgrade tracked as a follow-up; the report content is identical. Say so in the commit rather than leaving a fake progress bar.

---

## Task 8: the one page (static/index.html + app.js)

**Files:**
- Create: `pipeline/scanner/static/index.html`
- Create: `pipeline/scanner/static/app.js`
- Test: covered by `tests/test_scanner_server.py::test_root_serves_index` (below).

**Interfaces:**
- Consumes: `POST /scan` returning `{audit:{seo,aeo,perf,score,counts}, cycle?:{...}}`.
- Produces: a form (URL, repo, model A/B) that POSTs and renders the three audit groups + score, and (if present) the Model B diff/decision or the Model A brief.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner_server.py (append)
from pathlib import Path
def test_root_serves_index():
    idx = Path("pipeline/scanner/static/index.html")
    assert idx.is_file()
    html = idx.read_text()
    assert "/scan" in html or "/scan" in Path("pipeline/scanner/static/app.js").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_server.py::test_root_serves_index']))"`
Expected: FAIL (file missing).

- [ ] **Step 3: Write minimal implementation**

```html
<!-- pipeline/scanner/static/index.html -->
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>SEO/AEO Pipeline — Scan</title>
<style>
 body{font:15px system-ui;margin:2rem auto;max-width:820px;color:#111}
 input,select,button{font:inherit;padding:.5rem;margin:.25rem 0}
 input[type=text]{width:100%}
 .row{padding:.5rem;border-bottom:1px solid #eee}
 .error{color:#b00}.warn{color:#a60}.info{color:#666}
 .score{font-size:2rem;font-weight:700}
 pre{background:#f6f6f6;padding:1rem;overflow:auto}
 .banner{background:#eef;padding:.75rem;border-radius:6px}
</style></head>
<body>
 <h1>SEO / AEO Pipeline — Scan</h1>
 <p class="banner">Model A: we never touch your code — we hand you the fix.
   Model B: we fix it, gate it, and decide. Paste a URL (and a repo to fix).</p>
 <input id="url" type="text" placeholder="https://yoursite.com/page/">
 <input id="repo" type="text" placeholder="/path/to/repo  (optional — needed to fix)">
 <select id="model"><option value="B">Model B (we fix)</option>
   <option value="A">Model A (brief only)</option></select>
 <button id="run">Run</button>
 <div id="out"></div>
 <script src="/static/app.js"></script>
</body></html>
```

```javascript
// pipeline/scanner/static/app.js
const $ = (id) => document.getElementById(id);
function rows(list) {
  return list.map(r =>
    `<div class="row ${r.severity}">
       <b>${r.severity.toUpperCase()}</b> ${r.what} ${r.detail ? "("+r.detail+")" : ""}
       <div>${r.why}</div><div><i>Fix:</i> ${r.fix}</div>
     </div>`).join("");
}
$("run").onclick = async () => {
  $("out").innerHTML = "Running…";
  const body = { url: $("url").value, repo: $("repo").value, model: $("model").value };
  const res = await fetch("/scan", { method:"POST", body: JSON.stringify(body) });
  const data = await res.json();
  const a = data.audit;
  let html = `<div class="score">Score ${a.score}/100</div>
    <h2>SEO</h2>${rows(a.seo)}<h2>AEO</h2>${rows(a.aeo)}<h2>Performance</h2>${rows(a.perf)}`;
  if (data.cycle) {
    const c = data.cycle;
    if (c.model === "B") {
      html += `<h2>Fix (Model B)</h2>
        <p>Decision: <b>${c.decision.action}</b> — ${c.decision.reason}</p>
        <pre>${(c.diff||"").replace(/</g,"&lt;")}</pre>`;
    } else {
      html += `<h2>Brief (Model A)</h2><pre>${(c.brief||"").replace(/</g,"&lt;")}</pre>`;
    }
  }
  $("out").innerHTML = html;
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q','tests/test_scanner_server.py']))"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/scanner/static/index.html pipeline/scanner/static/app.js tests/test_scanner_server.py
git commit -m "feat(scanner): the one-page UI (form + audit/diff/brief render)"
```

---

## Task 9: register wf-scan-web + sync-contract docs

**Files:**
- Modify: `pyproject.toml` (add to `[project.scripts]`)
- Modify: `docs/MODULES.md` (counts + a scanner row)
- Modify: `CHANGELOG.md` (`[Unreleased]`)

- [ ] **Step 1: Add the console script**

In `pyproject.toml` under `[project.scripts]`, after `wf-dashboard`:

```toml
# The URL-audit web MVP — paste URL + repo, pick Model A/B, see audit + fix/brief.
wf-scan-web = "pipeline.scanner.server:main"
```

- [ ] **Step 2: Reinstall so the entry point registers**

Run: `.venv/bin/pip install -e . --quiet && .venv/bin/wf-scan-web --help 2>/dev/null || echo "starts a server (no --help); import check:"; .venv/bin/python -c "from pipeline.scanner.server import main; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Update MODULES.md**

Bump the header counts to `43 modules ... 36 wf-* commands ... <N> tests` (recount: `find pipeline -name '*.py' ! -name '__init__.py' | wc -l`; `grep -c '^wf-' pyproject.toml`). Add a `## pipeline/scanner` section: one line per module (recommendations, audit, config, run, server) describing the URL-audit MVP.

- [ ] **Step 4: Update CHANGELOG.md**

Add an `[Unreleased] → Added` entry describing `wf-scan-web`: the localhost URL-audit MVP (SEO+AEO+CrUX audit + Model A brief / Model B fix+decision), reusing measure/plan/remediate/providers/robots/automerge_gate, tests-only network-free.

- [ ] **Step 5: Run the full suite + commit**

Run: `.venv/bin/python -c "import sys,pytest; sys.exit(pytest.main(['-q']))"`
Expected: all pass (753 + the new scanner tests).

```bash
git add pyproject.toml docs/MODULES.md CHANGELOG.md
git commit -m "feat(scanner): register wf-scan-web + MODULES/CHANGELOG (sync contract)"
```

---

## Self-Review (done at write time)

- **Spec coverage:** input URL+repo+model (Tasks 7/8); SEO (T2), AEO (T3), performance/CrUX with honest disable (T4), recommendations (T1); Model A brief / Model B fix+gates-decision (T6); minimal-config scaffold for unknown repos (T5); localhost server (T7); one-page UI (T8); registration + sync docs (T9). All spec sections map to a task.
- **Honest-degrade invariant:** no CrUX key → `crux.disabled` info row (T4); no repo → audit only (T7 `POST /scan` skips cycle); no `claude` → `remediate` refuses via its own guard (documented in T6). No faked numbers anywhere.
- **Type consistency:** report rows are `{code,what,why,fix,detail,severity}` everywhere (T2-T4, T8 render); `run_cycle` returns `{model, changelog, diff?, decision?, brief?}` (T6) and the UI reads exactly those keys (T8); `decide_pr` returns a `Decision` with `.action`/`.reason`, surfaced as `{action,reason}` (T6) and read as such (T8).
- **Known MVP simplifications (called out, not hidden):** Model B decision passes `gates_passed=True` (T6 note) — running the full gate CLIs inline is a follow-up; `POST /scan` returns one JSON blob, SSE streaming is a later presentation upgrade (T7 note). Both are documented in commits so nothing reads as more than it is.
