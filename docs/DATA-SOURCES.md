# Data Sources — what each tool uses, and what can run free

**Purpose:** one place that says, per feature, where its data comes from and
whether a free Google source can replace the paid one. So nobody hunts for a
free swap that does not exist, and nobody assumes a paid tool is the only option
when Google already covers it.

The per-tool source map lives in code (`web/lib/toolSources.ts`, `TOOL_SOURCES`)
with a `disabled` reason on every option that cannot run; this doc is the summary
and the reasoning behind it.

## Free-able via Google (the "your own site" half)

These can run on a free Google API for the operator's own property. The switch
prefers Google when connected and falls back to DataForSEO.

| Tool(s) | Free source | State |
|---|---|---|
| Top Keywords · Organic Rankings · Domain Overview · Position Tracking · SERP Positions | **Google Search Console** (`webmasters.readonly`) | data layer built (`web/lib/gscRankings.ts`, G1); screen wiring + badge = G3 |
| Local / GBP audit (category, NAP, hours, verification) | **Google Business Profile** (`business.manage`) | data layer built (`web/lib/gbpLocal.ts`, G2); wiring = G3 |
| Core Web Vitals · Lighthouse · Performance | **CrUX + PageSpeed** | already Google, already free |
| Traffic (queries, pages, countries, devices) | **Google Search Console** | already wired |
| Headless Render Verification (CSR/SSR triage) | **Playwright (Chromium)** | Opt-in via `render_verify: true` in `client-config.yml`; requires `requirements-render.txt`. Emits `health.csr_content_gap`. |

GSC caveats vs DataForSEO: your own verified property only (no competitors), no
search volume, position is a 28-day average not a live SERP check.

## Free-able via Google, but heavy setup

| Tool | Free source | Blocker |
|---|---|---|
| Keyword volume · Keyword Ideas | **Google Ads Keyword Planner** | needs a Google Ads account + developer-token approval (Google review) + the `adwords` OAuth scope; volume is bucketed without ad spend. Tracked as G4 |

## Paid-only — no free Google equivalent exists

Google exposes none of this. DataForSEO (or Ahrefs/Semrush) is unavoidable.

| Tool | Why no free source |
|---|---|
| Backlinks · Backlink Overview · Backlink Audit · Backlink Gap | No free backlink index exists. Google Search Console shows *some* links in its UI but the **API does not expose them**. (`NO_LINK_INDEX`) |
| Keyword Gap · Compare Domains · competitor rankings · keyword difficulty | No free source has data about *other* sites' rankings. (`NO_OTHER_SITES`) |
| AI Mentions (`dfs.llm_mentions`) | No free source records what AI answer engines say about a brand. |
| Web Mentions / reputation | No free source for cross-web brand mentions + sentiment. |

## Rule of thumb

- **Owned-property data** (your rankings, your traffic, your GBP, your speed) →
  free via Google.
- **Off-site intelligence** (competitors, backlinks, AI/web mentions) →
  inherently third-party, paid.
