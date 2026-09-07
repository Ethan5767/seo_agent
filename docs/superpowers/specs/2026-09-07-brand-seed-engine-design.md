# Brand Seed Engine — Design

**Date:** 2026-09-07
**Status:** Approved (design), pre-implementation
**Home:** `pipeline/seed/` module inside `~/seo_agent`

## Problem

Brand-mention (citation) share is a real answer-engine (AEO/GEO) ranking signal:
LLM answer engines cite brands that appear across web content. Our existing
measure+gap agent already detects *where a brand is and is not cited*. Nothing
acts on those gaps. This module closes the loop — it **creates brand-mentioning
topics/posts** on the platforms where the brand is absent.

Scope boundary: this module **does not measure**. Measurement and gap detection
are an existing function (the measure+gap agent). This module consumes its
output and produces posts.

## Non-Goals

- Measuring citation share or detecting gaps (existing agent owns this).
- Commenting on other users' existing threads (spam/astroturf; excluded).
- Auto-editing Wikipedia (violates paid-editing/COI policy; permanent public
  history; blacklist risk). Wikipedia is **red tier — never auto**.
- Full auto-posting to strict platforms (Reddit/Quora) — shadowban risk.

## Risk Model — Tiering (the core safety rule)

| Tier | Platforms | Mode | Rationale |
|------|-----------|------|-----------|
| **Green** | Medium, Dev.to, Hashnode, Tumblr, Blogger | **Full auto-post** via API | Owned or content-welcoming; low ban risk; real AEO weight |
| **Yellow** | Reddit, Quora | Auto-**draft** → `drafts/`, 1-click human approve | Strict anti-spam; auto-post = shadowban |
| **Red** | Wikipedia | Logged `skipped: never-auto` | COI/paid-editing violation; permanent public record |

Tier membership lives in `pipeline/seed/tiers.py` as plain data. Adding a
platform = add a poster fn + one tier entry.

## Architecture

Mirrors `pipeline/audit/providers.py` conventions exactly:
- **One flat module, one function per platform.** No ABC, no registry, no
  `posters/` package. Add abstraction when a real second axis appears, not
  before.
- **Credentials from environment only.** No `.env` read in code, nothing stored
  in the repo.
- **Every skip is loud.** A platform with missing creds returns
  `("skipped: no DEVTO_API_KEY", None)` and that string is recorded in
  `seed-log.json`. A silent success would make a cycle look like it seeded when
  it did not.
- **Pure parse/build functions** take already-assembled payloads → offline
  testable, same seam as `check_page`.

### Files

| File | Responsibility | Purity |
|------|----------------|--------|
| `pipeline/seed/gaps.py` | Parse `gaps.json` → `list[Gap]`. Validate required fields, drop+log malformed. | Pure |
| `pipeline/seed/generate.py` | `Gap` → `Draft` (title, body, brand mention, target link). Uses Claude API. `build_prompt(gap)` is pure; the API call is the only side effect. | Pure prompt build |
| `pipeline/seed/posters.py` | One fn per green platform: `post_medium`, `post_devto`, `post_hashnode`, `post_tumblr`, `post_blogger`. Each: read env creds → loud skip if absent → build request → POST → return `PostResult`. `build_*_payload(draft)` pure. | Pure payload build |
| `pipeline/seed/tiers.py` | Tier map + `tier_of(platform)`. Plain data. | Pure |
| `pipeline/seed/run.py` | Orchestrate: parse → generate → dispatch by tier → write `seed-log.json` + yellow `drafts/`. `--dry-run` default. | Side effects |

### Data model

```python
@dataclass
class Gap:
    brand: str
    platform: str          # medium | devto | ... | reddit | wikipedia
    topic: str             # human topic/title seed
    target_keyword: str
    angle: str             # why-this-post rationale
    url_target: str        # brand URL to link

@dataclass
class Draft:
    gap: Gap
    title: str
    body: str              # markdown
    brand_mention: str     # the exact sentence citing the brand + link

@dataclass
class PostResult:
    platform: str
    status: str            # "posted" | "queued" | "skipped"
    url: str | None        # live post URL when posted
    detail: str | None     # reason when skipped/queued
```

### Data flow

```
gaps.json
   │ gaps.parse()            (pure, drops+logs malformed)
   ▼
list[Gap]
   │ generate.draft()        (build_prompt pure; Claude call)
   ▼
list[Draft]
   │ run.dispatch()  ── tier_of(platform)
   ├─ green  → posters.post_<platform>(draft)      → PostResult(posted|skipped)
   ├─ yellow → write drafts/<platform>-<slug>.md   → PostResult(queued)
   └─ red    → PostResult(skipped, "never-auto")
   ▼
seed-log.json   { run_ts, results: [PostResult...], counts }
```

## Error Handling

- Malformed gap (missing field) → dropped, logged to `seed-log.json.dropped`,
  run continues.
- Missing platform creds → `PostResult(status="skipped", detail="no DEVTO_API_KEY")`.
- LLM failure for a gap → skip that gap, log, continue (one bad draft ≠ dead run).
- Platform API non-2xx → `PostResult(status="skipped", detail="devto 422: <msg>")`.
  Never silently drop.
- `--dry-run` (default): generate + write drafts/log, **no live POST**. Live
  posting requires explicit `--live`.

## Testing

- `build_prompt`, `build_*_payload`, `tier_of`, `gaps.parse` — pure, full
  offline unit coverage with fixtures (mirror existing `tests/` + fixtures).
- Poster HTTP behind the pure payload seam; live POST path exercised only under
  `--live` integration, not in the offline suite.
- `--dry-run` default guarantees the suite never posts.

## Environment (new)

```
ANTHROPIC_API_KEY     Claude API (draft generation)
DEVTO_API_KEY         Dev.to
MEDIUM_TOKEN          Medium integration token
HASHNODE_TOKEN        Hashnode PAT
TUMBLR_CONSUMER_KEY / TUMBLR_CONSUMER_SECRET / TUMBLR_OAUTH_TOKEN / TUMBLR_OAUTH_SECRET
BLOGGER_ACCESS_TOKEN / BLOGGER_BLOG_ID
```
Each optional; absence → loud skip for that platform only.

## MVP (v1) — core engine, no external platform accounts

Build the pipeline end-to-end with a **stub poster**, so the only external
dependency is `ANTHROPIC_API_KEY`:

```
gaps.json → generate (Claude) → dispatch by tier → seed-log.json
   green  → stub poster: logs "would POST to <platform>: <title>"  (no HTTP)
   yellow → REAL: writes drafts/<platform>-<slug>.md               (free, no account)
   red    → skip, logged
```

This proves gaps parsing, draft generation, tiering, dispatch, and logging with
zero platform signup. Real green posters (Dev.to first — free API key, cleanest)
are added afterward as identical-shape fns that replace the stub one platform at
a time. Free platform APIs only (Dev.to / Hashnode / Tumblr / Blogger); paid or
locked APIs (Medium) deferred/swapped.

## Future (not now — YAGNI)

- Re-measure hook after posting (belongs to the measure agent, not here).
- Scheduling/cron (run manually first).
- Reddit/Quora automated posting with aged-account pool (yellow stays manual
  until proven).
