# SEO/AEO Scanner — Stages, Tools & Where Every Result Comes From

This documents the web scanner (Onboard → Measure → Plan) and, for every check,
**where the data comes from** — so a result is never a mystery or a static
number. Each finding carries a `code` whose prefix names its source (see the
legend at the bottom).

---

## Stage 1 — Onboard

Collects the client profile and saves it (Supabase `clients`, owner-only RLS).

| Field | Purpose |
|---|---|
| Business name | brand for GBP / mentions lookups |
| Website URL | the site we Measure |
| Model | A (read-only brief) or B (we fix the code) |
| Repo | GitHub repo for the source-code lane (Model B) |
| Keywords | target terms for rank tracking |
| Competitors | for keyword-gap + mention comparison |
| Goal | framing for the plan |

No scanning here — just capture. Sign-in is GitHub OAuth (read-only).

---

## Stage 2 — Measure

Runs in **4 ordered phases**, cheapest first, so money is only spent after the
free signal is in. Each tool streams a live card; each card's rows carry the
exact source + evidence.

### What gets fetched
A URL scan fetches **exactly 3 things**: the page HTML, `/robots.txt`,
`/sitemap.xml`. The free tools all read that **one page**. Whole-site depth is
DataForSEO Site Health's job (it crawls every page).

### Phase 1 — Page & technical (FREE, instant, one page)
Runs on the fetched HTML in memory (no network → milliseconds, not fake).

| Tool | What it checks | Data source |
|---|---|---|
| On-page SEO | title, meta, H1, canonical, indexable, OG image, schema, alt, depth | the fetched page HTML |
| Technical | HTTPS, viewport, lang, OG/Twitter, favicon, rendering, sitemap, schema | the fetched page HTML |
| Schema validation | JSON-LD valid / @type / types | the fetched page HTML |
| Sitemap & hreflang | sitemap validity + hreflang tags | `/sitemap.xml` + HTML |
| Content / info-gain | depth, original data, comprehensiveness | the fetched page HTML |
| Video | VideoObject schema + (if key) YouTube metadata | HTML + YouTube Data v3 |
| Trust (E-E-A-T) | author, contact, policies, proof, authority, citation-ready | the fetched page HTML |
| AI visibility (AEO) | AI-crawler robots access, answer-first structure | `/robots.txt` + HTML |
| Internal links | count, anchor quality, contextual, nofollow, over-opt, outbound | the fetched page HTML |
| Performance (CrUX) | LCP / INP / CLS (real users, 28-day field data) | Google CrUX API |

### Phase 2 — Google Lighthouse (FREE, external, ~10-30s)
Google runs Lighthouse in their cloud; we read the result.

| Tool | What | Data source |
|---|---|---|
| Lighthouse: Performance / SEO / Accessibility / Best practices | category scores + failing audits | Google PageSpeed Insights API |

### Phase 3 — Search data (PAID, DataForSEO, seconds–minutes)
Third-party data about the live site + Google's index. Works on any domain.

| Tool | What | Data source |
|---|---|---|
| Site Health | **whole-site crawl** (JS-aware): orphans, broken links, duplicates, 54 on-page checks | DataForSEO On-Page API |
| Keywords | volume, difficulty, intent, ideas, gap vs competitors | DataForSEO Labs + Keyword Data |
| Rankings | SERP position per target keyword | DataForSEO SERP API |
| Rankings trend | historical visibility | DataForSEO Labs |
| Backlinks | referring domains, broken backlinks | DataForSEO Backlinks API |
| AI citations | brand citation across AI engines | DataForSEO LLM Mentions |
| Local / GBP | category, reviews, NAP, claimed | DataForSEO Business Data |
| Web mentions | where the brand is talked about + sentiment | DataForSEO Content Analysis |

### Phase 4 — Source code (FREE, needs repo, seconds)
Reads the client's GitHub repo (read-only) — things the live HTML can't reveal.

| Tool | What | Data source |
|---|---|---|
| Source code | framework, rendering, routes, robots/sitemap, config, metadata, analytics (17 checks) | GitHub API (repo tree + key files) |

---

## Stage 3 — Plan (the ratchet)

Compares a client's **two most recent scans** by each finding's stable `code`:

- **NEW** — appeared this scan
- **PERSISTING** — still present
- **REGRESSION** — severity got worse (e.g. warn → error)
- **RESOLVED** — gone since last scan (a win)

Produces a **priority worklist** (error-first, then new/regression before
persisting); `ok`/`info` are excluded. Source: the stored `findings` rows.

---

## Where every result comes from — the `code` legend

Each finding's `code` prefix tells you its exact source, so nothing is a black box:

| Prefix | Source |
|---|---|
| `dfs.` / `health.` | DataForSEO (live crawl / SERP / labs / backlinks / business data) |
| `lh.` | Google Lighthouse (PageSpeed Insights) |
| `src.` | Your source code (GitHub repo) |
| `crux` / perf | Google Chrome UX Report (real-user field data) |
| everything else | our analysis of the fetched page HTML |

Every row also carries `what` (the finding), `why` (why it matters), `fix` (what
to do), `severity`, and `detail` (the evidence — the count/value we saw). The UI
lets you expand any finding to see all of these plus the source — proof it was
measured, not invented.
