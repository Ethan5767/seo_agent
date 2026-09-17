# Site Audit expansion — acceptance criteria

This is the definition of done for the A–K coverage expansion. A capability is
not accepted merely because its module exists: it must be registered, invoked
by the correct Site Audit mode, produce normalized evidence, and be visible in
the report or an explicit prerequisite state.

## Registry and execution

- Every capability is a discrete entry in `pipeline/scanner/server.py` or a
  clearly documented extension of an existing entry; no duplicate tool is
  added for an already-covered capability.
- Every entry declares `name`, `data_source`, `cost_per_run`, `requires_auth`,
  and `avg_runtime` through the scanner catalog.
- Site Audit core entries run from `ONPAGE_AUDIT_TOOLS`.
- GSC, Bing, log-upload, migration, and scheduled entries are visible in Site
  Audit but emit an explicit `unavailable.*`/connection state when their
  prerequisite is absent.
- Every execution emits `running` and `done` events and records success,
  unavailable, or error; no tool disappears silently.
- Every finding is normalized to `id`, `category`, `severity`,
  `affected_urls`, `evidence`, `why_it_matters`, `how_to_fix`, `effort`,
  `estimated_impact`, `source_tool`, and `confidence`.

## Coverage acceptance

| Area | Acceptance test |
|---|---|
| A. Crawl/logs | Access-log formats parse; bots are reverse-DNS plus forward-confirmed; crawl waste, bot response codes, directories, traps, depth, and orphans are reported or explicitly unavailable. |
| B. Index reality | GSC connection supports coverage, performance, inspection, enhancements, CWV, and crawl statistics; reconciliation distinguishes indexed/submitted/discovered-not-indexed/crawled-not-indexed; Bing/IndexNow/Indexing API/removals states are explicit. |
| C. Rendering | Googlebot mobile/desktop renders capture raw-vs-rendered text, links, title/meta, canonical, hreflang, schema, lazy content, blocked resources, and hydration errors. |
| D. Mobile | Mobile/desktop parity, interstitials, tap targets, viewport, and horizontal overflow produce URL-level findings. |
| E. Media | Image/video sitemaps, image format/size/dimensions/alt/lazy/srcset, VideoObject, thumbnail, and transcript/caption checks are reported. |
| F. Infrastructure | CDN/TTFB, uptime/503 Retry-After, TLS chain/protocol/HSTS, malware/defacement, mixed content, and cloaking checks have evidence and confidence. |
| G. Migration | Authenticated staging snapshots, 1:1 redirect maps, loops/chains/many-to-one/unmapped URLs, post-launch diffs, and staging leaks are reported. |
| H. Duplicates/URLs | SimHash/shingling clusters, parameter classes, faceted expansion, cross-domain syndication, variants, and URL consistency are reported. |
| I. Schema | Schema types/properties, required vs recommended coverage, visible-content mismatch, entity consistency, and historical rich-result errors are reported. |
| J. hreflang | Whole-cluster return links, x-default, code validity, self-reference, implementation conflicts, bad targets, and geo redirects are checked. |
| K. Monitoring | Recurring schedules, historical snapshots, severity-weighted diffs, alerts, and robots/sitemap watchers are persisted and visible. |

## DataForSEO selection rule

Where DataForSEO has an exact documented endpoint, the implementation must use
that endpoint and record its endpoint, pricing source, and concurrency/rate
limit in the tool comment. Current candidates include:

- `/v3/on_page/non_indexable`
- `/v3/on_page/redirect_chains`
- `/v3/on_page/duplicate_content`
- `/v3/on_page/resources`
- `/v3/on_page/links`
- `/v3/on_page/lighthouse`
- `/v3/domain_analytics/technologies/domain_technologies/live`

DataForSEO-disabled runs must still produce an explicit state and use an owned
fallback where equivalent evidence can be collected without paid data.

## Analysis and visualization

- Severity distribution is rendered as a pie/donut with an exact denominator.
- Findings by category and source are rendered as bars with exact counts.
- Crawl depth is rendered as a depth-distribution chart.
- Index reality is rendered as an indexed/submitted/discovered/crawled funnel.
- Rendering parity exposes raw-vs-rendered deltas per URL.
- Migration and regression views show severity-weighted changes over time.
- Empty, unavailable, and unverified states are never rendered as passing data.

## Verification

- Unit tests cover each parser and finding mapper with hermetic fixtures.
- Registry tests prove every accepted tool is reachable from its intended Site
  Audit mode.
- A live run is performed only when credentials and spend approval permit it;
  the report records exact endpoint calls and printed cost.
- `pytest`, `npm test`, and TypeScript/build checks pass before acceptance.
- `CHANGELOG.md` is updated under `[Unreleased]` with the implemented tools,
  verified counts, and any remaining unverified integrations.
