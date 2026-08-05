# Phase 1 — `wf-site-health` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `pipeline/audit/audit_live.py`'s printed markdown summary with typed `Finding` objects written to `docs/audit/<YYYY-MM>/findings.json`, exposed as a new `wf-site-health` command.

**Architecture:** One new module, `pipeline/audit/measure.py`, split at the network seam. `check_page()` is pure — it takes already-fetched HTML and returns `Finding`s, so the whole test suite runs offline. `check_url()` is the thin fetching wrapper. `main()` discovers URLs from the live sitemap, loops, and writes the JSON artifact. The `Finding` class, its content-based fingerprinting, and `sort_findings()` all come from the existing `pipeline/lib/baseline.py` — phase 1 writes no new ratchet machinery, it only produces input the phase 3 ratchet will consume.

**Tech Stack:** Python 3, stdlib only (`re`, `json`, `argparse`, `urllib.parse`, `pathlib`), plus PyYAML via the existing `load_config`. Network I/O shells out to `curl` through the existing `pipeline/lib/common.py` helpers. Tests are pytest, hermetic, no network.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-05-phase1-site-health-design.md`. Read it before starting.
- **Sync contract:** `CLAUDE.md` governs. Every behavior-changing commit carries its own `CHANGELOG.md` entry under `[Unreleased]` in the **same** commit.
- **Proof or it did not happen.** Paste real terminal output. Never pipe a verification command into `tail`/`head`/`grep` inside an `&&` chain — the pipeline's exit status is the last command's, so a failing `pytest` reports success.
- **No new dependencies.** The repo has exactly one runtime dependency (`PyYAML>=6.0`) and one test dependency (`pytest>=8.0`). Phase 1 adds neither.
- **`gate` field is the literal string `"site_health"`** on every finding.
- **`location` is the URL path, never an absolute URL, never a line number.** `/roofing/`, not `https://example.com/roofing/`.
- **`context` is fingerprinted; `detail` is not.** Never put a measured quantity (length, count, word total, byte size) in `context` — that would let a finding become "new" merely by getting worse. Volatile numbers go in `detail`.
- **No em dashes in public-facing copy.** Internal markdown, code comments, and commit messages are exempt (`CLAUDE.md`, Writing Standards).
- **Run tests with `.venv/bin/pytest`** — that is the virtualenv the repo is set up with.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `pipeline/audit/measure.py` | Create | The whole phase. `check_page` (pure checks), `check_url` (fetch), `discover_urls` (sitemap), `main` (CLI + artifact) |
| `tests/test_measure.py` | Create | Hermetic tests for all of the above |
| `pipeline/audit/audit_live.py` | Delete | Superseded by `measure.py` |
| `pyproject.toml` | Modify | Drop `wf-audit-live`, add `wf-site-health` |
| `CHANGELOG.md` | Modify | `[Unreleased]` entry |
| `docs/MODULES.md` | Modify | Line 104, `audit_live.py` reference |

One module rather than four is deliberate. `measure.py` lands at roughly 200 lines, which is smaller than `bootstrap_config.py` (294) and far smaller than `baseline.py` (647) — it fits the tree's existing shape, and splitting a single command across four files would be structure for its own sake.

---

## Task 1: `check_page` — the 18 checks, pure

The bulk of the phase. No network, no filesystem, no config loading. Every check that `audit_live.py` performs, re-expressed as `Finding`s.

**Files:**
- Create: `pipeline/audit/measure.py`
- Create: `tests/test_measure.py`

**Interfaces:**
- Consumes: `pipeline.lib.baseline.Finding`, `pipeline.lib.baseline.assign_ordinals`
- Produces: `check_page(url: str, html: str, status: int, cfg: dict) -> list[Finding]`, and the module constant `GATE = "site_health"`

**Behavior notes carried from the spec** — these are deliberate differences from `audit_live.py`, not oversights:

1. `health.img_alt_missing` is emitted **per offending image**, with the `src` as `context`. A page with **zero** images emits nothing (`audit_live.py` reported a violation, which is a false positive).
2. `health.forbidden_phrase` is emitted **per matching rule**, with the rule's pattern as `context`.
3. Missing and out-of-band are **mutually exclusive**. A page with no `<title>` emits `health.title_missing` only, never also `health.title_length`. Same for description.
4. A check whose config input is unset is **skipped, not failed**. No `nap.phone_tel` in config means no `health.tel_link_missing` findings — the pipeline cannot measure what was never declared, and emitting the finding on every page would be a fabricated result. Task 3 prints a warning naming every skipped check, so the skip is never silent.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_measure.py`:

```python
"""measure.py — live-site measurement as typed Findings.

Hermetic: check_page takes already-fetched HTML, so nothing here touches the
network. The fingerprint-stability tests at the bottom are the ones that matter
most; they are the property phase 3's ratchet depends on.
"""
from __future__ import annotations

import json
import textwrap
from datetime import date

import pytest
import yaml

from pipeline.audit import measure as m

URL = "https://example.com/roofing/"

CFG = {
    "domain": "example.com",
    "schema_type": "RoofingContractor",
    "ga4_id": "G-TESTID1234",
    "nap": {"phone": "(704) 555-0100", "phone_tel": "17045550100"},
    "forbidden_phrases": [
        {"pattern": r"\$[0-9]", "reason": "no dollar amounts on site"},
        {"pattern": "—", "reason": "no em dashes in deliverables"},
    ],
}


def build_page(*, title="Roofing Replacement and Repair in Charlotte, NC",
               desc=("Charlotte roof replacement and repair from a local crew, with "
                     "a written estimate before any work begins and a warranty on "
                     "every job we complete."),
               h1_count=1, canonical=URL, noindex=False, og_image=True,
               schema_types=("RoofingContractor", "FAQPage", "BreadcrumbList"),
               body="", images=('<img src="/hero.jpg" alt="A finished roof">',),
               ga4=True, words=600):
    """A page that passes every check by default. Each keyword trips exactly one."""
    head = []
    if title is not None:
        head.append(f"<title>{title}</title>")
    if desc is not None:
        head.append(f'<meta name="description" content="{desc}">')
    if canonical is not None:
        head.append(f'<link rel="canonical" href="{canonical}">')
    if og_image:
        head.append('<meta property="og:image" content="/og.jpg">')
    if noindex:
        head.append('<meta name="robots" content="noindex">')
    schema = "".join(f'<script type="application/ld+json">{{"@type":"{t}"}}</script>'
                     for t in schema_types)
    ga = '<script src="https://www.googletagmanager.com/gtag/js?id=G-TESTID1234"></script>' if ga4 else ""
    filler = " ".join(["shingle"] * words)
    h1s = "<h1>Roofing in Charlotte, NC</h1>" * h1_count
    return textwrap.dedent(f"""\
        <!DOCTYPE html><html lang="en"><head>{''.join(head)}{schema}{ga}</head>
        <body><main>{h1s}
        <p>Call <a href="tel:17045550100">(704) 555-0100</a> for an estimate.</p>
        {''.join(images)}
        <p>{filler}</p>
        {body}
        </main></body></html>
    """)


def check(html, url=URL, status=200, cfg=None):
    return m.check_page(url, html, status, cfg if cfg is not None else CFG)


def codes(findings):
    return sorted(f.code for f in findings)


# ── the clean baseline ───────────────────────────────────────────────────────

def test_clean_page_has_no_findings():
    """build_page()'s defaults satisfy every check. If this fails, read which
    codes came back — a threshold or a regex is off, not the test."""
    assert check(build_page()) == []


# ── one test per code ────────────────────────────────────────────────────────

def test_status_not_200():
    f = check(build_page(), status=404)
    assert "health.status_not_200" in codes(f)
    assert [x for x in f if x.code == "health.status_not_200"][0].detail == "status=404"


def test_title_missing():
    c = codes(check(build_page(title=None)))
    assert "health.title_missing" in c
    assert "health.title_length" not in c, "missing and out-of-band are exclusive"


def test_title_length():
    f = check(build_page(title="Roofing"))
    assert "health.title_length" in codes(f)
    assert [x for x in f if x.code == "health.title_length"][0].detail == "len=7"


def test_desc_missing():
    c = codes(check(build_page(desc=None)))
    assert "health.desc_missing" in c
    assert "health.desc_length" not in c


def test_desc_length():
    assert "health.desc_length" in codes(check(build_page(desc="Too short.")))


def test_h1_count_zero_and_many():
    assert "health.h1_count" in codes(check(build_page(h1_count=0)))
    f = check(build_page(h1_count=3))
    assert [x for x in f if x.code == "health.h1_count"][0].detail == "count=3"


def test_canonical_mismatch_absent_and_wrong():
    f = check(build_page(canonical=None))
    assert [x for x in f if x.code == "health.canonical_mismatch"][0].detail == "absent"
    assert "health.canonical_mismatch" in codes(
        check(build_page(canonical="https://example.com/other-page/")))


def test_noindex_present():
    assert "health.noindex_present" in codes(check(build_page(noindex=True)))


def test_og_image_missing():
    assert "health.og_image_missing" in codes(check(build_page(og_image=False)))


def test_schema_findings():
    c = codes(check(build_page(schema_types=())))
    assert "health.schema_business_missing" in c
    assert "health.schema_faq_missing" in c
    assert "health.schema_breadcrumb_missing" in c


def test_schema_business_context_is_the_required_type():
    f = check(build_page(schema_types=("FAQPage", "BreadcrumbList")))
    biz = [x for x in f if x.code == "health.schema_business_missing"][0]
    assert biz.context == "RoofingContractor"


def test_forbidden_phrase_one_per_rule():
    f = check(build_page(body="<p>Roofs from $5,000 and up — call today.</p>"))
    hits = [x for x in f if x.code == "health.forbidden_phrase"]
    assert len(hits) == 2, "one finding per matching rule, not one per page"
    assert sorted(h.context for h in hits) == sorted([r"\$[0-9]", "—"])


def test_forbidden_phrase_ignores_script_blocks():
    """Next RSC flight payloads carry $1 / $L3 tokens. audit_live stripped
    <script> before the sweep to stop them false-positiving the dollar rule."""
    page = build_page(body='<script>self.__next_f.push([1,"$1 $L3"])</script>')
    assert "health.forbidden_phrase" not in codes(check(page))


def test_tel_and_phone_missing():
    page = build_page().replace('href="tel:17045550100"', 'href="#"').replace(
        "(704) 555-0100", "call us")
    c = codes(check(page))
    assert "health.tel_link_missing" in c
    assert "health.phone_missing" in c


def test_ga4_missing():
    assert "health.ga4_missing" in codes(check(build_page(ga4=False)))


def test_thin_content():
    f = check(build_page(words=50))
    assert "health.thin_content" in codes(f)
    assert [x for x in f if x.code == "health.thin_content"][0].detail.startswith("words=")


# ── the two deliberate behavior changes ──────────────────────────────────────

def test_img_alt_is_per_image_with_src_as_context():
    page = build_page(images=('<img src="/a.jpg">', '<img src="/b.jpg">',
                              '<img src="/c.jpg" alt="fine">'))
    hits = [x for x in check(page) if x.code == "health.img_alt_missing"]
    assert len(hits) == 2
    assert sorted(h.context for h in hits) == ["/a.jpg", "/b.jpg"]
    assert len({h.fingerprint for h in hits}) == 2, "distinct images, distinct findings"


def test_page_with_zero_images_has_no_alt_finding():
    """audit_live.py used `len(imgs) > 0 and not missing_alt`, so an image-free
    page reported an alt violation. That is a false positive."""
    assert "health.img_alt_missing" not in codes(check(build_page(images=())))


def test_repeated_identical_findings_get_distinct_ordinals():
    """Two images sharing a src on one page must not collapse to one fingerprint."""
    page = build_page(images=('<img src="/a.jpg">', '<img src="/a.jpg">'))
    hits = [x for x in check(page) if x.code == "health.img_alt_missing"]
    assert len(hits) == 2
    assert sorted(h.ordinal for h in hits) == [0, 1]
    assert len({h.fingerprint for h in hits}) == 2


# ── config-driven skipping ───────────────────────────────────────────────────

def test_unset_config_keys_skip_their_checks_rather_than_fail():
    """No declared phone or GA4 id means those checks cannot be measured. A
    finding on every page would be a fabricated result, so they are skipped.
    Task 3's CLI prints a warning naming each skipped check."""
    bare = {"domain": "example.com", "schema_type": "RoofingContractor",
            "nap": {}, "forbidden_phrases": []}
    c = codes(check(build_page(ga4=False), cfg=bare))
    assert "health.tel_link_missing" not in c
    assert "health.phone_missing" not in c
    assert "health.ga4_missing" not in c


# ── the fingerprint properties phase 3 depends on ────────────────────────────

def test_location_is_the_path_never_the_absolute_url():
    f = check(build_page(title="Short"))
    assert all(x.location == "/roofing/" for x in f)


def test_gate_is_site_health_on_every_finding():
    assert all(x.gate == "site_health" for x in check(build_page(title="Short")))


def test_fingerprint_is_stable_across_identical_runs():
    a = check(build_page(title="Short"))
    b = check(build_page(title="Short"))
    assert [x.fingerprint for x in a] == [x.fingerprint for x in b]


def test_fingerprint_unchanged_when_only_detail_changes():
    """A title going from 7 to 12 characters is the SAME finding getting slightly
    different. If this breaks, the ratchet reports resolved-and-new instead of
    persisting, and run #2 becomes unreadable."""
    a = [x for x in check(build_page(title="Short")) if x.code == "health.title_length"][0]
    b = [x for x in check(build_page(title="Short Title!")) if x.code == "health.title_length"][0]
    assert a.detail != b.detail
    assert a.fingerprint == b.fingerprint
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/test_measure.py -q
```

Expected: collection error, `ModuleNotFoundError: No module named 'pipeline.audit.measure'`.

- [ ] **Step 3: Write `check_page`**

Create `pipeline/audit/measure.py`:

```python
#!/usr/bin/env python3
"""Live-site measurement. Returns typed Findings instead of printing a summary.

Ported from audit_live.py: the same check logic, re-expressed as lib/baseline.py
Findings so plan.py (phase 3) can fingerprint them by content and partition them
into RESOLVED / PERSISTING / NEW / REGRESSION.

The split at check_page/check_url is the testable seam: check_page touches no
network and no filesystem, so the whole suite runs offline.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from pipeline.lib.baseline import Finding, assign_ordinals

GATE = "site_health"

TITLE_MIN, TITLE_MAX = 30, 60
DESC_MIN, DESC_MAX = 120, 160
THIN_CONTENT_WORDS = 500


def check_page(url: str, html: str, status: int, cfg: dict) -> list:
    """Every check, against one already-fetched page. Pure.

    A check whose config input is unset is SKIPPED, not failed: the pipeline
    cannot measure what was never declared, and emitting the finding on every
    page would be a fabricated result. main() warns about each skip by name.
    """
    path = urlsplit(url).path or "/"
    out: list = []

    def add(code: str, context: str = "", detail: str = "") -> None:
        out.append(Finding(GATE, code, path, context=context, detail=detail))

    if status != 200:
        add("health.status_not_200", detail=f"status={status}")

    # title — missing and out-of-band are mutually exclusive
    t = re.search(r"<title[^>]*>([^<]+)</title>", html)
    title = t.group(1) if t else ""
    if not title:
        add("health.title_missing")
    elif not TITLE_MIN <= len(title) <= TITLE_MAX:
        add("health.title_length", detail=f"len={len(title)}")

    # meta description
    d = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)
    desc = d.group(1) if d else ""
    if not desc:
        add("health.desc_missing")
    elif not DESC_MIN <= len(desc) <= DESC_MAX:
        add("health.desc_length", detail=f"len={len(desc)}")

    # h1 — count opening tags, which handles nested spans inside the h1
    h1s = re.findall(r"<h1[^>]*>", html)
    if len(h1s) != 1:
        add("health.h1_count", detail=f"count={len(h1s)}")

    # canonical — loose substring comparison, as audit_live.py did
    c = re.search(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', html)
    if not (c and url.rstrip("/") in c.group(1)):
        add("health.canonical_mismatch", detail=c.group(1) if c else "absent")

    if "noindex" in html.lower():
        add("health.noindex_present")

    if not re.search(r'<meta[^>]*property="og:image"', html):
        add("health.og_image_missing")

    # schema
    types = set(re.findall(r'"@type":"([^"]+)"', html))
    required = cfg.get("schema_type") or "LocalBusiness"
    if required not in types:
        add("health.schema_business_missing", context=required,
            detail=f"found={','.join(sorted(types)) or 'none'}")
    if "FAQPage" not in types:
        add("health.schema_faq_missing")
    if "BreadcrumbList" not in types:
        add("health.schema_breadcrumb_missing")

    # forbidden phrases — strip <script> first (Next RSC flight payloads carry
    # $1 / $L8 tokens that false-positive the dollar rule), then priceRange
    # schema literals. Both strips are inherited from audit_live.py.
    body = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'"priceRange":"[^"]*"', "", body)
    for rule in cfg.get("forbidden_phrases") or []:
        hit = re.search(rule["pattern"], body)
        if hit:
            add("health.forbidden_phrase", context=rule["pattern"], detail=hit.group()[:80])

    nap = cfg.get("nap") or {}
    tel = nap.get("phone_tel")
    if tel and f"tel:{tel}" not in html:
        add("health.tel_link_missing")
    phone = nap.get("phone")
    if phone and phone not in html:
        add("health.phone_missing")

    ga4 = cfg.get("ga4_id")
    if ga4 and ga4 not in html:
        add("health.ga4_missing")

    # images — one finding per offending image, src as the stable identity.
    # A page with no images emits nothing.
    for img in re.findall(r"<img[^>]*>", html):
        if not re.search(r'\salt="[^"]+"', img):
            src = re.search(r'\ssrc="([^"]*)"', img)
            add("health.img_alt_missing", context=src.group(1) if src else img[:80])

    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    words = len(text.split())
    if words < THIN_CONTENT_WORDS:
        add("health.thin_content", detail=f"words={words}")

    # Disambiguate repeated identical findings on one page, per baseline.py's
    # contract. Without this, two images sharing a src collapse to one fingerprint.
    return assign_ordinals(out)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/test_measure.py -q
```

Expected: all tests in the file pass. If `test_clean_page_has_no_findings` fails, read which codes came back — the `build_page` default is meant to satisfy every check, and a mismatch there means a threshold or a regex is off, not that the test is wrong.

- [ ] **Step 5: Run the whole suite**

```bash
.venv/bin/pytest -q
```

Expected: 87 pre-existing tests plus the new ones, all passing.

- [ ] **Step 6: Commit**

```bash
git add pipeline/audit/measure.py tests/test_measure.py
git commit -m "measure.py: check_page returns typed Findings

Ports audit_live.py's checks to lib/baseline.py Findings. Pure function,
no network, so the tests are hermetic. Two deliberate behavior changes:
per-image alt findings (a page with zero images no longer reports a
violation, which was a false positive) and per-rule forbidden-phrase
findings. Checks whose config input is unset are skipped, not failed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `check_url` and `discover_urls` — the network seam

**Files:**
- Modify: `pipeline/audit/measure.py`
- Modify: `tests/test_measure.py`

**Interfaces:**
- Consumes: `check_page` from Task 1; `pipeline.lib.common.curl`, `pipeline.lib.common.curl_status`
- Produces: `check_url(url: str, cfg: dict) -> tuple[list, bool]` (findings, reachable) and `discover_urls(cfg: dict, url_args: list, limit: int | None = None) -> list[str]`

**Reachability:** `curl_status` already returns `0` on connection failure — that is the unreachable signal, and it is distinct from a reachable `404`, which is a `health.status_not_200` finding. An unreachable URL contributes no findings and increments a counter.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_measure.py`:

```python
# ── the network seam (curl monkeypatched; still no network) ──────────────────

def test_check_url_returns_findings_and_reachable(monkeypatch):
    monkeypatch.setattr(m, "curl_status", lambda url: 200)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: build_page(title="Short"))
    findings, reachable = m.check_url(URL, CFG)
    assert reachable is True
    assert "health.title_length" in codes(findings)


def test_check_url_marks_status_zero_unreachable_and_returns_no_findings(monkeypatch):
    """status 0 is curl's connection failure. It is NOT a 404 — a 404 is a
    reachable page with a finding. An unreachable URL must contribute nothing,
    so a dead host cannot look like a clean site."""
    monkeypatch.setattr(m, "curl_status", lambda url: 0)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pytest.fail("must not fetch"))
    findings, reachable = m.check_url(URL, CFG)
    assert (findings, reachable) == ([], False)


def test_check_url_404_is_reachable_with_a_finding(monkeypatch):
    monkeypatch.setattr(m, "curl_status", lambda url: 404)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "<html></html>")
    findings, reachable = m.check_url(URL, CFG)
    assert reachable is True
    assert "health.status_not_200" in codes(findings)


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/roofing/</loc></url>
  <url><loc>https://example.com/roofing/</loc></url>
  <url><loc>  https://example.com/siding/  </loc></url>
</urlset>"""


def test_discover_urls_reads_the_live_sitemap(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: SITEMAP)
    assert m.discover_urls(CFG, []) == [
        "https://example.com/", "https://example.com/roofing/", "https://example.com/siding/"]


def test_discover_urls_dedupes_preserving_order(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: SITEMAP)
    urls = m.discover_urls(CFG, [])
    assert len(urls) == len(set(urls))


def test_discover_urls_honors_limit(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: SITEMAP)
    assert m.discover_urls(CFG, [], limit=2) == [
        "https://example.com/", "https://example.com/roofing/"]


def test_discover_urls_explicit_args_skip_the_sitemap(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pytest.fail("must not fetch"))
    assert m.discover_urls(CFG, ["/roofing/", "https://example.com/siding"]) == [
        "https://example.com/roofing/", "https://example.com/siding/"]


def test_discover_urls_root_path_does_not_double_slash(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pytest.fail("must not fetch"))
    assert m.discover_urls(CFG, ["/"]) == ["https://example.com/"]


def test_discover_urls_unreachable_sitemap_raises_unreachable(monkeypatch):
    """curl returns '' on failure. No sitemap and no --url means no sources at
    all, which is exit 19 territory, not a green run over zero pages."""
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "")
    with pytest.raises(m.Unreachable):
        m.discover_urls(CFG, [])


def test_discover_urls_sitemap_without_loc_tags_raises_usage(monkeypatch):
    """Fetched but malformed is a different failure from unreachable: something
    answered, it just was not a sitemap. That is exit 2."""
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "<html>404 not found</html>")
    with pytest.raises(m.UsageError):
        m.discover_urls(CFG, [])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/test_measure.py -q
```

Expected: failures with `AttributeError: module 'pipeline.audit.measure' has no attribute 'check_url'` and `... has no attribute 'Unreachable'`.

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `pipeline/audit/measure.py`:

```python
from pipeline.lib.common import curl, curl_status
```

Append to `pipeline/audit/measure.py`:

```python
# ── the network seam ─────────────────────────────────────────────────────────

class Unreachable(RuntimeError):
    """Every source failed. Exit 19 — a run that measured nothing must be red."""


class UsageError(RuntimeError):
    """Bad arguments, or a sitemap that answered but was not a sitemap. Exit 2."""


_LOC_RE = re.compile(r"<loc>\s*([^<\s][^<]*?)\s*</loc>")


def _absolute(u: str, domain: str) -> str:
    """Normalize one URL or site-relative path to an absolute, trailing-slash URL."""
    if u.startswith("http"):
        return u.rstrip("/") + "/"
    path = u.strip("/")
    return f"https://{domain}/{path}/" if path else f"https://{domain}/"


def check_url(url: str, cfg: dict) -> tuple:
    """Fetch one URL and check it. Returns (findings, reachable).

    status 0 is curl's connection-failure signal and means unreachable. A 404 is
    reachable — it is a real measurement, and it becomes a finding.
    """
    status = curl_status(url)
    if status == 0:
        return [], False
    return check_page(url, curl(url), status, cfg), True


def discover_urls(cfg: dict, url_args: list, limit: int | None = None) -> list:
    """Explicit --url arguments when given, otherwise every <loc> in the live
    sitemap. Deduped, order preserved, truncated to `limit`."""
    domain = cfg["domain"]
    if url_args:
        urls = [_absolute(u, domain) for u in url_args]
    else:
        xml = curl(f"https://{domain}/sitemap.xml", cache_bust=False)
        if not xml.strip():
            raise Unreachable(f"https://{domain}/sitemap.xml is unreachable "
                              f"and no --url was given: nothing to measure")
        locs = _LOC_RE.findall(xml)
        if not locs:
            raise UsageError(f"https://{domain}/sitemap.xml answered but contains "
                             f"no <loc> entries: not a sitemap")
        urls = [_absolute(u, domain) for u in locs]
    urls = list(dict.fromkeys(urls))
    return urls[:limit] if limit else urls
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/test_measure.py -q
```

Expected: every test in the file passes.

- [ ] **Step 5: Commit**

```bash
git add pipeline/audit/measure.py tests/test_measure.py
git commit -m "measure.py: check_url and sitemap-based URL discovery

curl_status 0 (connection failure) means unreachable and contributes no
findings; a 404 is a reachable page with a finding. Unreachable sitemap
raises Unreachable (exit 19), a sitemap with no <loc> raises UsageError
(exit 2) — answered-but-malformed is a different failure from silent.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `main()` — the CLI, the artifact, the exit codes

**Files:**
- Modify: `pipeline/audit/measure.py`
- Modify: `tests/test_measure.py`
- Modify: `pyproject.toml` (add the `wf-site-health` entry point)

**Interfaces:**
- Consumes: `check_url`, `discover_urls` from Task 2; `pipeline.lib.common.load_config`; `pipeline.lib.baseline.sort_findings`
- Produces: `main() -> int`, the console script `wf-site-health`, and the `findings.json` artifact that phase 3's `plan.py` will read

**Exit codes:**

| exit | meaning |
|---|---|
| 0 | every URL clean |
| 1 | findings written |
| 2 | usage error — bad arguments, or a sitemap with no `<loc>` entries |
| 19 | every URL unreachable — REFUSE, write nothing |

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_measure.py`:

```python
# ── the CLI ──────────────────────────────────────────────────────────────────

@pytest.fixture
def project(tmp_path):
    """A client project holding just docs/client-config.yml."""
    proj = tmp_path / "client"
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "client-config.yml").write_text(yaml.safe_dump(CFG, sort_keys=False))
    return proj


def run(monkeypatch, project, argv, pages):
    """Drive main() with sys.argv and a fake network. `pages` maps URL -> html,
    or URL -> None to simulate an unreachable host."""
    monkeypatch.setattr("sys.argv", ["wf-site-health", "--project", str(project)] + argv)
    monkeypatch.setattr(m, "curl_status", lambda url: 0 if pages.get(url) is None else 200)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pages.get(url) or "")
    return m.main()


def artifact(project):
    month = date.today().strftime("%Y-%m")
    return json.loads((project / "docs" / "audit" / month / "findings.json").read_text())


def test_clean_site_exits_0(monkeypatch, project):
    code = run(monkeypatch, project, ["--url", "/roofing/"],
               {"https://example.com/roofing/": build_page()})
    assert code == 0
    assert artifact(project)["findings"] == []


def test_findings_exit_1_and_are_written(monkeypatch, project):
    code = run(monkeypatch, project, ["--url", "/roofing/"],
               {"https://example.com/roofing/": build_page(title="Short")})
    assert code == 1
    doc = artifact(project)
    assert doc["schema"] == "site-health/1"
    assert doc["domain"] == "example.com"
    assert doc["urls_checked"] == 1
    assert doc["urls_unreachable"] == 0
    assert any(f["code"] == "health.title_length" for f in doc["findings"])
    assert all(len(f["fingerprint"]) == 16 for f in doc["findings"])


def test_every_url_unreachable_exits_19_and_writes_nothing(monkeypatch, project):
    """The load-bearing exit. A run where nothing answered must be red, never a
    green report with zero findings."""
    code = run(monkeypatch, project, ["--url", "/roofing/", "--url", "/siding/"],
               {"https://example.com/roofing/": None, "https://example.com/siding/": None})
    assert code == 19
    month = date.today().strftime("%Y-%m")
    assert not (project / "docs" / "audit" / month / "findings.json").exists()


def test_partial_outage_still_reports_with_the_count_visible(monkeypatch, project):
    code = run(monkeypatch, project, ["--url", "/roofing/", "--url", "/dead/"],
               {"https://example.com/roofing/": build_page(), "https://example.com/dead/": None})
    assert code == 0
    doc = artifact(project)
    assert (doc["urls_checked"], doc["urls_unreachable"]) == (1, 1)


def test_sitemap_without_loc_exits_2(monkeypatch, project):
    monkeypatch.setattr("sys.argv", ["wf-site-health", "--project", str(project)])
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "<html>nope</html>")
    assert m.main() == 2


def test_artifact_is_byte_identical_across_two_runs(monkeypatch, project):
    """sort_findings + sorted JSON keys. A churning artifact would produce a diff
    on every run and make the PR unreadable."""
    pages = {"https://example.com/roofing/": build_page(title="Short", images=(
        '<img src="/b.jpg">', '<img src="/a.jpg">'))}
    run(monkeypatch, project, ["--url", "/roofing/"], pages)
    month = date.today().strftime("%Y-%m")
    path = project / "docs" / "audit" / month / "findings.json"
    first = path.read_bytes()
    run(monkeypatch, project, ["--url", "/roofing/"], pages)
    assert path.read_bytes() == first


def test_unset_config_keys_are_warned_about(monkeypatch, project, capsys):
    """A skipped check must never be silent — that is the failure mode where a
    green report means 'not measured' rather than 'fine'."""
    bare = {"domain": "example.com", "schema_type": "RoofingContractor"}
    (project / "docs" / "client-config.yml").write_text(yaml.safe_dump(bare))
    run(monkeypatch, project, ["--url", "/roofing/"],
        {"https://example.com/roofing/": build_page()})
    err = capsys.readouterr().err
    assert "nap.phone_tel" in err and "ga4_id" in err
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/bin/pytest tests/test_measure.py -q
```

Expected: failures with `AttributeError: module 'pipeline.audit.measure' has no attribute 'main'`.

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `pipeline/audit/measure.py`:

```python
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from pipeline.lib.baseline import sort_findings
from pipeline.lib.common import load_config
```

and add the schema constant beside `GATE`:

```python
SCHEMA = "site-health/1"
```

Append to `pipeline/audit/measure.py`:

```python
# ── the CLI ──────────────────────────────────────────────────────────────────

# Checks that cannot run without a config value. Skipping one silently is the
# failure mode where a green report means "not measured" rather than "fine", so
# every skip is named on stderr.
_CONFIG_GATED = (
    ("nap.phone_tel", "health.tel_link_missing", lambda c: (c.get("nap") or {}).get("phone_tel")),
    ("nap.phone", "health.phone_missing", lambda c: (c.get("nap") or {}).get("phone")),
    ("ga4_id", "health.ga4_missing", lambda c: c.get("ga4_id")),
    ("forbidden_phrases", "health.forbidden_phrase", lambda c: c.get("forbidden_phrases")),
)


def _warn_unmeasurable(cfg: dict) -> None:
    for key, code, get in _CONFIG_GATED:
        if not get(cfg):
            print(f"[WARN] {code} not measured: {key} is unset in docs/client-config.yml",
                  file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-site-health",
        description="Measure a live site and write typed findings for the ratchet.")
    ap.add_argument("--project", required=True, help="client repo root")
    ap.add_argument("--url", action="append", default=[], metavar="PATH",
                    help="measure exactly these URLs instead of the live sitemap")
    ap.add_argument("--limit", type=int, help="stop after N URLs")
    args = ap.parse_args()

    cfg = load_config(args.project)
    _warn_unmeasurable(cfg)

    try:
        urls = discover_urls(cfg, args.url, args.limit)
    except Unreachable as e:
        print(f"[REFUSED] {e}", file=sys.stderr)
        return 19
    except UsageError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    findings, checked, unreachable = [], 0, 0
    for url in urls:
        page_findings, reachable = check_url(url, cfg)
        if reachable:
            checked += 1
            findings.extend(page_findings)
        else:
            unreachable += 1
            print(f"[WARN] unreachable: {url}", file=sys.stderr)

    if checked == 0:
        print(f"[REFUSED] all {unreachable} URLs unreachable: nothing was measured, "
              f"so no findings file was written", file=sys.stderr)
        return 19

    out_dir = Path(args.project) / "docs" / "audit" / date.today().strftime("%Y-%m")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "findings.json"
    doc = {
        "schema": SCHEMA,
        "generated": date.today().isoformat(),
        "domain": cfg["domain"],
        "urls_checked": checked,
        "urls_unreachable": unreachable,
        # sort_findings + sorted keys: the artifact must be byte-identical across
        # two runs over an unchanged site, or every run produces a noise diff.
        "findings": [dict(f.to_json(), fingerprint=f.fingerprint)
                     for f in sort_findings(findings)],
    }
    out_path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

    print(f"[OK] {checked} URLs measured, {len(findings)} findings -> {out_path}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add the console script**

In `pyproject.toml`, under `[project.scripts]` in the `# ── audit / setup ──` block, add:

```toml
wf-site-health = "pipeline.audit.measure:main"
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/bin/pytest tests/test_measure.py -q
```

Expected: every test passes.

- [ ] **Step 6: Verify the console script resolves**

```bash
.venv/bin/pip install -e . --quiet --no-deps
.venv/bin/wf-site-health --help
```

Expected: the argparse help text, listing `--project`, `--url`, and `--limit`.

- [ ] **Step 7: Commit**

```bash
git add pipeline/audit/measure.py tests/test_measure.py pyproject.toml
git commit -m "wf-site-health: CLI, findings.json artifact, exit codes

Writes docs/audit/<YYYY-MM>/findings.json in the client repo, sorted and
with sorted JSON keys so two runs over an unchanged site are byte-identical.
Exit 19 when every URL is unreachable and nothing is written: a run that
measured nothing must be red, not a green report with zero findings.
Config-gated checks warn by name on stderr rather than skipping silently.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Retire `audit_live.py` and correct the docs

Last, so it happens only once `wf-site-health` is proven. `audit_live.py` has no importers — the only references in the tree are its own docstring and one stale line in `docs/MODULES.md`.

**Files:**
- Delete: `pipeline/audit/audit_live.py`
- Modify: `pyproject.toml` (drop `wf-audit-live`)
- Modify: `docs/MODULES.md:104`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: nothing
- Produces: nothing — this task removes code

- [ ] **Step 1: Confirm nothing imports it**

```bash
grep -rn "audit_live" --include="*.py" --include="*.yml" --include="*.toml" --include="*.sh" . | grep -v "\.venv\|egg-info"
```

Expected: hits only in `pipeline/audit/audit_live.py` itself and `pyproject.toml`. If anything else appears, stop and report it before deleting.

- [ ] **Step 2: Delete the module and its entry point**

```bash
git rm pipeline/audit/audit_live.py
```

In `pyproject.toml`, delete the line:

```toml
wf-audit-live = "pipeline.audit.audit_live:main"
```

- [ ] **Step 3: Correct `docs/MODULES.md:104`**

Replace `audit_live.py` / `poll_live.py` (live-site audits) with:

```
`measure.py` (live-site measurement, returns typed Findings) / `poll_live.py` (post-deploy polling)
```

Note that line 104 also still names `cycle_status.py`, `gbp_baseline.py`, and `setup_gtm_foundation.py`, all deleted in `79b0b5b`. Remove those three names in the same edit — they are wrong today and the line is being touched anyway.

- [ ] **Step 4: Write the CHANGELOG entry**

Under `## [Unreleased]`, add an `### Added` section above the existing `### Removed`:

```markdown
### Added

- **`wf-site-health`** (`pipeline/audit/measure.py`) — measures a live site and
  writes `docs/audit/<YYYY-MM>/findings.json` in the client repo as typed
  `lib/baseline.py` `Finding`s. Phase 1 of `SITE-AUDIT-PIPELINE.md`. URLs come
  from the live sitemap, or from `--url`; `--limit` caps the run. Exits 0 clean,
  1 findings, 2 usage, **19 when every URL was unreachable** (writes nothing —
  a run that measured nothing must be red, not a green report with zero findings).

  Ports `audit_live.py`'s 13 check groups to 18 finding codes, with three
  deliberate behavior changes: `health.img_alt_missing` is per-image and a page
  with zero images no longer reports a violation (a false positive in
  `audit_live.py`); `health.forbidden_phrase` is per-rule; and a check whose
  config input is unset is skipped with a named warning on stderr rather than
  failing on every page.
```

Extend the existing `### Removed` section with:

```markdown
- `pipeline/audit/audit_live.py` and the `wf-audit-live` entry point, superseded
  by `wf-site-health`. Nothing imported it.
```

- [ ] **Step 5: Run the full suite**

```bash
.venv/bin/pytest -q
```

Read the output. Do not pipe it into anything. Expected: all tests pass, including the 87 pre-existing ones.

- [ ] **Step 6: Verify the module and its entry point are gone**

```bash
grep -c "audit_live" pyproject.toml; ls pipeline/audit/audit_live.py
```

Expected: `0` from grep, and `No such file or directory` from `ls`.

Do not test this by invoking `.venv/bin/wf-audit-live` — a stale console script can linger in the virtualenv until the next reinstall, so its presence or absence proves nothing about the source tree.

- [ ] **Step 7: Commit**

Paste the real `pytest -q` output into the CHANGELOG entry before committing, per `CLAUDE.md` §4.

```bash
git add -A
git commit -m "Retire audit_live.py in favor of wf-site-health

Nothing imported it. Drops the wf-audit-live entry point and corrects
docs/MODULES.md:104, which still named audit_live.py plus three modules
deleted in 79b0b5b.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 8: Push**

Per `CLAUDE.md`, as separate steps. Never chain the verification into the push.

```bash
git pull --ff-only
.venv/bin/pytest -q
```

Read that output, then:

```bash
git push origin main
```

Then tell Robin what changed. Do not assume the log gets read.

---

## Done When

- `wf-site-health --project <client-repo>` writes `docs/audit/<YYYY-MM>/findings.json` against a real client site.
- Two consecutive runs over an unchanged site produce a byte-identical artifact.
- A run against an unreachable domain exits 19 and writes nothing.
- `.venv/bin/pytest -q` is green, and the output is pasted in the CHANGELOG.
- `audit_live.py` and `wf-audit-live` are gone.

## Deliberately Not In Phase 1

Per the spec §6, so a reviewer does not flag these as gaps: no ratchet (phase 3 builds it on `lib/baseline.py`), no `report.md` (phase 3), no `worklist.json` or `acceptance` contract (phase 3), no gates (phase 4), no Dockerfile (phase 5), no external providers or `--no-api`/`--no-gsc` flags (phase 6), and no consolidation of the two-requests-per-URL fetch (revisit with a measurement, not a guess).
