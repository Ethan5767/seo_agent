# Plan — IA Consolidation and Design System (web)

**Date:** 2026-09-11
**Surface:** `web/` (Next.js 15 App Router, React 18, no CSS framework)
**Context:** [PRODUCT.md](../../../PRODUCT.md) · [DESIGN.md](../../../DESIGN.md)
**Cost:** $0. No scanner run, no paid API, no live DataForSEO call.

## The problem, measured

Two independent defects present as one feeling ("everything is messy").

### 1. Three competing navigation systems

| Layer | Entries |
|---|---|
| Icon rail (`Sidebar.tsx`) | 8: Home · SEO · AI · Traffic · Local · Content · Reports · Apps |
| `ReaiTab` (`types.ts`) | 16 |
| `NavSubTab` (`types.ts`) | 19 |

43 nav entries for roughly 14 real screens, and they contradict each other:

- `Position Tracking`, `Organic Rankings`, and `Top Pages` all open `Keyword Data Lab`.
  Three labels, one destination.
- Sidebar `Backlink Gap` opens `Data Lab & Backlinks`, while a separate
  `Backlink Gap` tab also exists. One label, two destinations.
- `On-Page SEO`, `Local SEO`, and `Reports` each exist as both a tab and a sub-tab.

17 of the 20 routes are 5-line shims rendering `<ReaiApp initialTab="..." />`.
There are no real pages; there is one 13,706-line component wearing 17 URLs.

### 2. No design system

No stylesheet, no tokens, 3,240 inline `style={{ }}` objects.

| Dimension | Distinct values | Worst offender |
|---|---|---|
| padding | 132 | `10px 14px` (143), `11px 14px` (83), `10px 12px` (48), `12px 14px` (44) |
| hex colors | 170 | six different "gray text" values |
| font sizes | 47 | **11px used 486 times; 723 elements at <= 11px** |
| border radii | 32 | 8, 6, 4, 3, 50, 10, 5, 12, 14, 0, 2, 20 |

Contrast, computed (`scratchpad/contrast.mjs`):

| Color | Uses as text | vs `#ffffff` | vs `#f1f5f9` | vs body `#f4f5f7` | AA body |
|---|---|---|---|---|---|
| `#64748b` | 444 | 4.76 | 4.34 | 4.36 | **fail** |
| `#94a3b8` | 70 | 2.56 | 2.34 | 2.35 | **fail** |
| `#059669` | 94 | 3.77 | 3.44 | 3.45 | **fail** |

The most-used text color in the app fails AA on every surface but pure white, and
it is mostly rendered at 11px. That is the readability problem, and it is physics
rather than taste.

## Decisions taken

Confirmed with the operator before planning:

- **Nav model:** Semrush-shaped structure, 5 groups, real routes. Icon rail is
  removed. The duplicate sub-tab layer is removed.
- **Home:** an analytics overview, Semrush-shaped, with REAI's own vocabulary
  rather than Semrush's branded product names.
- **Positioning:** Semrush is the competitor. Learn the structure, do not clone
  the look or the words.
- **Scope:** token layer plus a sweep. Not a re-brand. The slate ramp, the indigo
  primary, and the emerald success stay; they get names and lose their duplicates.
  The only color changes are the three contrast corrections above.

## Target IA

Five groups. One label per screen, one route per screen.

| Group | Screen | Route | Replaces |
|---|---|---|---|
| — | Overview | `/` | `Overview` tab, `/dashboard`, `/overview` |
| Research | Organic Research | `/research/organic` | `Organic Research` |
| Research | Keywords | `/research/keywords` | `Keyword Data Lab` + `Keyword Magic Tool` + "Position Tracking" + "Organic Rankings" + "Top Pages" |
| Research | Competitor Gap | `/research/gap` | `Keyword Gap` + `Backlink Gap` |
| Research | Backlinks | `/research/backlinks` | `Data Lab & Backlinks` + `Backlink Audit` |
| Research | Traffic | `/research/traffic` | `Traffic Analytics` |
| Site Health | Site Audit | `/site/audit` | `Site Health & Audit` |
| Site Health | Page Optimizer | `/site/pages` | `On-Page SEO` |
| Site Health | SERP Preview | `/site/serp` | `SERP Optimizer` |
| Site Health | Local Presence | `/site/local` | `Local SEO & GBP` |
| AI Visibility | Readiness | `/ai/readiness` | AEO sub-view `matrix` |
| AI Visibility | Citations | `/ai/citations` | AEO sub-view `citations` |
| AI Visibility | Schema | `/ai/schema` | AEO sub-view `schema` |
| AI Visibility | Answers | `/ai/answers` | AEO sub-view `answers` |
| AI Visibility | Crawler Access | `/ai/crawlers` | AEO sub-view `crawlers` |
| Fixes | Priorities | `/fixes/priorities` | `Priority Actions` |
| Fixes | Review Changes | `/fixes/review` | `Auto-Fix Engine`, `Auto-Fix Review` |
| Fixes | History | `/fixes/history` | `Change History` |
| Utility | Reports | `/reports` | `Reports` |
| Utility | Integrations | `/integrations/google` | unchanged |
| Utility | Profile | `/profile` | unchanged |
| Utility | All Tools | `/tools` | `All Tools Directory` |

Vocabulary is deliberately not Semrush's: "Keywords" not "Keyword Magic Tool",
"Competitor Gap" not "Keyword Gap / Backlink Gap", "Page Optimizer" not "On Page
SEO Checker", "Site Audit" kept because it is the plain English name.

Every retired route (`/keyword-magic-tool`, `/backlink-gap`, `/auto-fix`, ...)
keeps working via a redirect table, so no bookmark breaks.

## Steps

Each step is independently shippable and independently verifiable.

### Step 1 — Token layer (no visual change intended)

- Add `web/app/tokens.css` holding every token from DESIGN.md, and import it from
  `app/layout.tsx`. Move the inline `<style>` block in `layout.tsx` into it.
- Add `web/lib/ui.ts`: typed constants (`space`, `text`, `radius`, `color`,
  `shadow`, `z`) so TSX inline styles can reference tokens without a refactor to
  CSS classes. Inline styles stay legal; magic numbers do not.
- Verify: `tsc --noEmit`, app boots, screens render unchanged.

### Step 2 — Contrast and type-floor sweep (the readability fix)

The only step that deliberately changes what you see, and the one that answers
"everything is hard to read".

- Replace `#64748b`, `#94a3b8`, `#059669` **used as text** with the DESIGN.md
  roles. Keep them where they are borders, icons, or fills.
- Raise every `fontSize` at or below 11 to 12, per the migration map in DESIGN.md.
- Add `font-variant-numeric: tabular-nums` to metric and table numerals.
- Verify: re-run `scratchpad/contrast.mjs` over the swept files and show zero
  failing text pairs; grep proves no `fontSize` below 12 survives.

### Step 3 — Space, radius, and control normalization

- Map all 132 padding values onto the seven-step scale and the six standard
  component paddings.
- Map all 32 radii onto the five radius tokens.
- Map gaps onto the same space scale.
- Verify: grep counts drop to the target table; visual diff on three screens.

### Step 4 — Nav consolidation

- Rewrite `types.ts` around the target IA: one `Screen` union, one
  `SCREEN_ROUTES` map, one `ROUTE_REDIRECTS` map for the retired URLs.
- Rewrite `Sidebar.tsx` as a single grouped sidebar. Delete the icon rail.
- Delete the duplicate `NavSubTab` layer; each former sub-tab is now a screen.
- Verify: a test asserts every screen has exactly one label and one route, that
  no two labels share a route, and that every retired route resolves.

### Step 5 — Real routes

- Convert the 17 shim pages into real route files that render their own screen
  component, rather than `<ReaiApp initialTab>`.
- Split `ReaiDashboard.tsx` (13,706 lines) along those seams. This is also the
  AGENTS.md Rule 1 debt: no file over 1,000 lines.
- Verify: `tsc --noEmit`, `node --test web/tests/*.test.mjs`, every route returns
  200 and renders its own screen.

### Step 6 — Component states

- Give buttons, inputs, tables, and disclosures the full seven states.
- Skeletons in content shape; empty states that teach.
- `prefers-reduced-motion` branch covering `reaiShimmer`.

## Guards

- No visual redesign. Palette identity is preserved; only the three failing
  contrast pairs change hue.
- No scanner, no network, no paid API. Pure frontend work.
- `web/tsconfig.tsbuildinfo` gets gitignored before any commit; it is a build
  artifact currently sitting untracked.
- Steps 1-3 are mechanical and reversible. Step 5 is the structural one and lands
  on its own branch.

## Test

- `npx tsc --noEmit` in `web/` after every step.
- `node --test tests/*.test.mjs` (navigation + security suites, currently 0 fail).
- A new `web/tests/nav.test.mjs` asserting the one-label-one-route invariant.
- `scratchpad/contrast.mjs` re-run as the contrast proof.
- `python -m pytest -q -m "not dataforseo"` stays green (currently 985 passed);
  this plan touches no Python.
