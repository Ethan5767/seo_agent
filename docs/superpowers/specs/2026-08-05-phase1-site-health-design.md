# Phase 1 — `wf-site-health`: measurement returns typed Findings

**Status:** approved · **Date:** 2026-08-05 · **Implements:** `SITE-AUDIT-PIPELINE.md` §4.5, build sequence phase 1

Phase 1 of the v3 design. It ships the first arrow of the target flow — `live site →
findings.json` — and nothing else. No ratchet (phase 3), no gates (phase 4), no agent
(phase 5), no external providers (phase 6).

The whole phase is a refactor: `audit_live.py`'s 13 existing check groups stop printing
a markdown summary and start returning `lib/baseline.py` `Finding` objects. That single
change is what makes every later phase possible, because `Finding` is the type the
ratchet already knows how to fingerprint and partition.

---

## 1. Module

One new file, `pipeline/audit/measure.py`, split at the network seam:

```python
check_page(url: str, html: str, status: int, cfg: dict) -> list[Finding]   # pure
check_url(url: str, cfg: dict) -> tuple[list[Finding], bool]              # fetches; bool = reachable
main() -> int                                                              # wf-site-health
```

`check_page` takes no network and touches no filesystem. Every check lives there, so the
test suite exercises the real logic against HTML strings with no fixtures beyond a config
dict. `check_url` is the thin wrapper that calls `curl_status` + `curl` from
`lib/common.py` and hands the result down.

`assign_ordinals()` runs once over each page's findings before they are written, per
`baseline.py`'s contract — repeated identical findings on one page (two images missing
alt, two hits of the same forbidden pattern) must disambiguate or they collapse to one
fingerprint.

**Deleted in the same commit:** `pipeline/audit/audit_live.py` and its `wf-audit-live`
entry point. `wf-site-health` supersedes it; nothing in the tree imports it. The stale
mention at `docs/MODULES.md:104` is corrected here rather than left to rot.

---

## 2. Finding mapping

`gate` is `site_health` for every finding. `location` is the URL path, never an absolute
URL and never a line number. `context` carries stable identity only. `detail` carries the
volatile numbers — `baseline.py` excludes it from the fingerprint precisely so a finding
cannot become "new" by getting worse.

| # | code | fires when | context | detail |
|---|---|---|---|---|
| 1 | `health.status_not_200` | status ≠ 200 | — | `status=404` |
| 2 | `health.title_missing` | no `<title>` | — | — |
| 3 | `health.title_length` | title outside 30–60 | — | `len=71` |
| 4 | `health.desc_missing` | no meta description | — | — |
| 5 | `health.desc_length` | desc outside 120–160 | — | `len=71` |
| 6 | `health.h1_count` | `<h1>` count ≠ 1 | — | `count=3` |
| 7 | `health.canonical_mismatch` | canonical absent or not self-referential | — | the href found |
| 8 | `health.noindex_present` | `noindex` anywhere in the HTML | — | — |
| 9 | `health.og_image_missing` | no `og:image` | — | — |
| 10 | `health.schema_business_missing` | `cfg.schema_type` absent from `"@type"` values | the required type | types found |
| 11 | `health.schema_faq_missing` | no `FAQPage` | — | — |
| 12 | `health.schema_breadcrumb_missing` | no `BreadcrumbList` | — | — |
| 13 | `health.forbidden_phrase` | a `forbidden_phrases` pattern matches | the rule pattern | the matched text, 80 chars |
| 14 | `health.tel_link_missing` | no `tel:<phone_tel>` | — | — |
| 15 | `health.phone_missing` | display phone not in HTML | — | — |
| 16 | `health.ga4_missing` | `ga4_id` unset or absent from HTML | — | — |
| 17 | `health.img_alt_missing` | an `<img>` has no non-empty `alt` | the `src` | — |
| 18 | `health.thin_content` | body word count < 500 | — | `words=312` |

Check logic is carried over verbatim from `audit_live.py`, including its quirks: the
script-stripping before the forbidden sweep (Next RSC payload tokens like `$1` false-positive
on the dollar rule), the `priceRange` schema literal strip, and the loose substring
canonical comparison. Phase 1 changes the output type, not the measurements.

### Four deliberate behavior changes

**`health.img_alt_missing` is per-image, and a page with zero images is not a finding.**
`audit_live.py` collapsed this to one boolean, `len(imgs) > 0 and len(missing_alt) == 0`,
which reports a violation on any page containing no images at all. That is a false
positive, and per-image findings are what let the ratchet track one image being fixed.

**`health.forbidden_phrase` is per-rule.** `audit_live.py` counted hits and emitted one
boolean. One finding per matching rule is what makes each one separately resolvable.

**Missing and out-of-band are mutually exclusive.** A page with no `<title>` emits
`health.title_missing` and never also `health.title_length`. `audit_live.py` evaluated
`title_present` and `title_length_30_60` independently, so an absent title failed both.
Two findings for one root cause is double-counting, and it makes the ratchet report a
"resolved" the moment a title appears at any length. Same rule for the description.

**A check whose config input is unset is skipped, not failed.** `audit_live.py` read
`cfg["nap"]["phone_tel"]` unguarded, which is a `KeyError` on any config that omits it.
Emitting `health.tel_link_missing` on every page instead would be worse: the pipeline
cannot measure what was never declared, and reporting an unmeasured check as a failure is
a fabricated result. The skip covers `nap.phone_tel`, `nap.phone`, `ga4_id`, and
`forbidden_phrases`. It is never silent — `main()` prints one `[WARN]` per skipped check
naming both the code and the missing config key, so a green report can never quietly mean
"not measured".

### Two known-noisy checks, left alone

`health.schema_faq_missing` and `health.schema_breadcrumb_missing` fire on every page
lacking those types, which on most sites is the homepage and every non-article route.
Phase 1 preserves the inherited behavior; phase 3's ratchet is the correct place to absorb
pre-existing noise, and re-tuning before there is real measured output would be guessing.

---

## 3. CLI

```
wf-site-health --project <dir> [--url PATH ...] [--limit N]
  → <project>/docs/audit/<YYYY-MM>/findings.json
```

`--project` is required. Config loading stays with `load_config`, which already exits 10
on a missing `docs/client-config.yml`.

**URL discovery.** With no `--url`, fetch `https://<domain>/sitemap.xml` and take every
`<loc>`. With one or more `--url`, use exactly those — absolute URLs pass through,
relative paths resolve against `domain`, matching `audit_live.py`'s current argument
handling. `--limit N` truncates the list after discovery, in sitemap order.

**Output.** `docs/audit/<YYYY-MM>/findings.json`, in the *client* repo, per §1 of the v3
doc — artifacts ship inside the PR and the worker holds no state.

```jsonc
{
  "schema": "site-health/1",
  "generated": "2026-08-05",
  "domain": "example.com",
  "urls_checked": 12,
  "urls_unreachable": 0,
  "findings": [ { "gate": "site_health", "code": "…", "location": "/roofing/",
                  "context": "", "detail": "len=71", "ordinal": 0,
                  "fingerprint": "a3f9…" } ]
}
```

Findings are written through `sort_findings()` so the file is byte-identical across two
runs over an unchanged site. `fingerprint` is included for readability; it is derived, and
phase 3 recomputes rather than trusts it.

**Exit codes.**

| exit | meaning |
|---|---|
| 0 | every URL clean |
| 1 | findings written |
| 2 | usage error — bad arguments, or a sitemap that answered but carries no `<loc>` |
| 19 | every URL unreachable, or the sitemap unreachable with no `--url` given — REFUSE |

Exit 19 is the load-bearing one. A run where every fetch failed must be red, not a green
report with zero findings, and nothing is written on 19. A URL is unreachable when
`curl_status` returns 0 — the value it already returns on connection failure. A reachable
404 is not unreachable; it is a real measurement and becomes a `health.status_not_200`
finding. Unreachable URLs are excluded from the findings and counted in
`urls_unreachable`; a *partial* outage still exits 0 or 1 with the count visible in the
artifact.

The sitemap splits across both codes on purpose. **Nothing answered** (`curl` returns an
empty body) is the same condition as every URL being unreachable, so it is 19. **Something
answered but was not a sitemap** (a body with no `<loc>` entries — typically an HTML 404
page) is a different failure: the host is up and the configured `domain` is probably
wrong. That is 2, and collapsing the two would hide which one happened.

**Not built:** `--no-api` and `--no-gsc` from the v3 doc's sketch. There are zero external
sources to disable until phase 6. The flags land with the providers that need them.

---

## 4. Testing

One new file, `tests/test_measure.py`, hermetic like the rest of the suite — no network,
no real client repo. It drives `check_page` directly with HTML strings and a config dict
built from `conftest.py`'s existing `_minimal_config` shape.

Coverage:

- One clean page produces zero findings.
- Each of the 18 codes fires on a page constructed to trip exactly it.
- Two images missing `alt` on one page produce two findings with distinct fingerprints
  (the `assign_ordinals` contract).
- A page with zero images produces no `health.img_alt_missing` — the false positive being
  fixed.
- Fingerprints are stable across two calls on identical input, and unchanged when only
  `detail` changes (a title going from 71 to 74 characters is the same finding).

The last one is the test that matters most: it is the property phase 3's ratchet depends
on, and the easiest to break in a later edit.

---

## 5. Documentation, per the sync contract

Shipped in the same commit as the code:

- `CHANGELOG.md` under `[Unreleased]` — the new command, the deleted one, the two behavior
  changes in §2.
- `docs/MODULES.md:104` — `audit_live.py` replaced by `measure.py`.
- `pytest -q` output pasted into the CHANGELOG entry, not paraphrased.

`docs/gate-reference.md` is untouched: `wf-site-health` is a measurement command, not a
gate. It runs on the operator's machine before the PR exists, not in the PR's Actions job.

---

## 6. What this phase deliberately does not do

- **No ratchet.** Every run reports every finding, including ones present last month.
  RESOLVED / PERSISTING / NEW / REGRESSION is phase 3, built on `lib/baseline.py`.
- **No `report.md`.** The human-readable artifact is phase 3's, where the four lanes give
  it something to say. `findings.json` is the phase 1 deliverable.
- **No work items.** `worklist.json` and the `acceptance` contract are phase 3.
- **No Dockerfile.** The single ~20-line image of §5 lands in phase 5, alongside
  `remediate.py` — that is the first phase with a dependency worth declaring (Claude Code
  itself). Phases 1–4 run on local Python. The image will hold only the above-the-PR half
  of the flow; gates and deploy stay in Actions on the client repo, where the client's
  `GITHUB_TOKEN` is.
- **No fetch consolidation.** `check_url` makes two requests per URL — `curl_status` then
  `curl` — as `audit_live.py` does today. Real at 2,000 pages, irrelevant under `--limit`.
  Revisit when a full-site run is actually slow, with a measurement rather than a guess.
