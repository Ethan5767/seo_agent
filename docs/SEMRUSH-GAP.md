# REAI vs Semrush — gap analysis

**Date:** 2026-09-11
**Method:** static read of the codebase. No DataForSEO request was issued.
**Source of truth:** the code, not the UI copy. Counts below are greps over
`web/app` and `web/components`.

---

## The diagnosis

This is not a visual-polish problem. The shell already matches Semrush: icon
rail, drawer, project switcher, content column. What is missing is the layer
between the page header and the data — the controls that turn a screen into a
tool.

| Control | Count in REAI | Semrush |
|---|---|---|
| Date-range picker | **0** | every report screen |
| Sortable table | **0** | every table |
| Table filter | **0** | every table |
| Pagination | **0** | every table |
| CSV export | 1 | every report |
| PDF / client report | **0** | My Reports, scheduled |
| Scanner tools (real) | **23** | — |

A screen with no sort, no filter, no date range and no export reads as a slide,
not a tool. That is the whole reason it feels worse than it is.

## Screen anatomy, top to bottom

| Layer | Semrush | REAI today |
|---|---|---|
| Chrome | logo, project switcher, search, credits, account | logo, project switcher, search, account |
| Nav | grouped sidebar, one label per report | rail + drawer, one label per screen |
| Scope | domain input, country database, device | domain from selected project |
| Time | date range **+** compare period | **none** |
| Controls | filter row, column chooser, export | **none** |
| Summary | metric row with delta vs previous | score + counts from last scan |
| Data | sortable, paginated table with sparklines | static list |
| Exit | export, schedule, share | **none** |

The shell is fine. Rows 4, 5, 7 and 8 are the gap.

## What Semrush has that we do not

Ordered by cost to close.

| Capability | Semrush | REAI | To close |
|---|---|---|---|
| **Competitor index** | owned index, 26B keywords / 43T backlinks, crawled continuously | scans your site only; "Competitor Gap" has nothing behind it | Structural. DataForSEO answers per query, but you pay per call and hold no history. |
| **Rank tracking over time** | daily, per keyword, per device, with alerts | snapshot only when a scan runs | Scheduler + a rankings table. The scan already returns positions. |
| **Historical comparison** | every metric carries a delta | data exists in `scans`; only `ScannerApp` reads it | **Small.** `scanHistory()`, `getScanReport()` and `lib/trend.ts` already exist and the dashboard never calls them. |
| **Scheduled re-audits** | weekly per project | manual | Cron + queue. Needs a spend cap first: each run bills real money. |
| **Client reporting** | white-label PDF, scheduled email | none | Medium. The report JSON is already the full data source. |
| **Table mechanics** | sort, filter, paginate, column chooser, export | none | One reusable component, adopted screen by screen. |
| **Country / device scope** | selector on every keyword screen | location passed to DataForSEO, not exposed in UI | Small. The scanner already takes a location code. |
| **Bulk analysis** | up to 200 domains | one at a time | Low priority for two operators. |
| **Seats and roles** | client seats, permissions, shared projects | single tenant, Supabase RLS per user | Matters only when a client logs in directly. |

## What we have that they do not

- **REAI fixes the site. Semrush only reports on it.** The remediation rail runs
  Claude Code inside the client's checkout, inside a declared tier, and opens a
  gated PR: 20 gates, `tier_check` on the diff, `claim_provenance_check` on the
  copy, human merge. Semrush has no path that edits a customer's repository.
  This is the product.
- **Answer-engine visibility per page.** Crawler access checked at the edge for
  GPTBot, ClaudeBot, PerplexityBot, Google-Extended; answer structure; schema;
  `llms.txt`. Semrush's AI Visibility Index scores a domain, not which page
  blocks which crawler.
- **It reads the source code.** Route existence, `next.config` redirects and
  headers, SSR posture, analytics wiring. No external SEO tool can see this.
- **Cost is on screen.** Every tool declares its price before it runs and the
  scan reports what it spent. Semrush bills opaque monthly credits.
- **Findings are gated, not just listed.** A finding carries a code with
  machine-checkable acceptance; it passes the gate on the PR or it does not.

## Build order

Sequenced by value per unit of work. The first three need no new data source.

1. **One table component: sort, filter, paginate.** Zero exist today. Every data
   screen improves the moment one does. Single biggest closer of the felt gap.
2. **Wire scan history into the dashboard.** `scanHistory()`, `getScanReport()`
   and `lib/trend.ts` are written and tested but only `ScannerApp` calls them.
   Turns every metric into a trend with **no new API calls and no cost**.
3. **Date range + compare-to-previous.** Once history is reachable, this is what
   makes it read as an analytics tool rather than a one-shot scanner.
4. **Client report export.** Print stylesheet on a dedicated route; the report
   JSON is already the whole data source. No new dependency.
5. **Scheduled re-audits, with a spend cap.** Build the cap before the scheduler.
6. **Replace the last fabricated panels.** On-Page TF-IDF, AI Citation
   percentages, traffic geography split — see `CHANGELOG.md` under
   `[Unreleased]`. These are the screens most likely to be shown to a client.
