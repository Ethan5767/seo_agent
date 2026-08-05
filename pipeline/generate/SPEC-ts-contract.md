# SPEC — Typed-Data Contract For The Data-Gen Emitter (Phase 2)

Status: reverse-engineered from the live pilot repo, 2026-07-21.
Scope: **what the emitter must produce.** No schema is invented here. Every type,
field, literal and count rule below was read out of the pilot repo and is cited
by file + line.

Sources of truth (read; not modified):

| Concern | File |
|---|---|
| Type definitions | `acme-roofing-site/src/data/services.ts` L1-391 |
| Hub / spoke / sub-service entries | `acme-roofing-site/src/data/location-pages.ts` (21,844 L) |
| Unified array (linked-by-construction) | `location-pages.ts` L21708-21844 (`allLocationPages`) |
| 1-segment route (services + metro hubs) | `src/app/[slug]/page.tsx` |
| 2-segment route (city spokes + metro sub-services) | `src/app/[slug]/[city]/page.tsx` |
| 3-segment route (city sub-services) | `src/app/[slug]/[city]/[subservice]/page.tsx` |
| Renderer + auto-enrichment transform | `src/components/ServicePageRenderer.tsx` (1,597 L) |
| Hero render | `src/components/Hero.tsx` |
| FAQ render | `src/components/FAQSection.tsx` |
| Brand constants | `src/data/company.ts` |

This replaces "Phase 2 Asks" 1 and 2 in `V2-Prototype/emitter-design.md`.

---

## 0. The one-sentence contract

> The emitter's unit of output is **one `ServicePage` object literal**, appended to
> `src/data/location-pages.ts`, exported by name, **and** registered in
> BOTH `allLocationPages` **and** the route-file array whose segment-count matches
> its `slug`. There is exactly one shape for hub, spoke and sub-service — they
> differ only by `slug` segment count and by which sections they carry.

There is no separate hub type, spoke type or sub-service type. `ServicePage` is
the whole surface.

---

## 1. `ServicePage` — the root object

`services.ts` L1-29, verbatim:

```ts
export interface ServicePage {
  slug: string;
  title: string;
  metaTitle: string;
  metaDescription: string;
  lastUpdated?: string;
  hero: {
    badgeIcon: string;
    badgeText: string;
    title: string;
    description: string;
    bgImage?: string;
    buttons?: Array<{
      text: string;
      url: string;
      className: string;
      iconBefore?: string;
      iconAfter?: string;
    }>;
    features?: string[];
  };
  markdownContent?: string;
  sections: ServiceSection[];
  faqs?: Array<{ question: string; answer: string }>;
}
```

### 1.1 Field-by-field

| Field | Type | Req | Emitter obligation |
|---|---|---|---|
| `slug` | `string` | **yes** | No leading/trailing slash. Segment count IS the page class (§2). Uniqueness is enforced by nothing — the emitter owns it. |
| `title` | `string` | **yes** | Plain text, no HTML. Drives breadcrumb label, `Service` schema name, `WebPage` schema name, `BreadcrumbList` name. NOT rendered as the H1. |
| `metaTitle` | `string` | **yes** | `<title>` + OG title + Twitter title. `<=56` effective chars (`&` counts as 5 — post-mortem 1.12). |
| `metaDescription` | `string` | **yes** | `<meta description>` + OG + Twitter + `Service` schema `description` + `WebPage` schema description. 150-160 chars. |
| `lastUpdated` | `string?` | optional | `YYYY-MM-DD`. Feeds `AuthorByline` and `webPageSchema` `dateModified`. Renderer falls back to `'2026-04-30'` when absent (`ServicePageRenderer.tsx` L42) — **always emit it**; the fallback silently backdates the page. |
| `hero` | object | **yes** | Not optional. `data.hero.badgeIcon` is dereferenced unconditionally at L59; a missing `hero` is a build crash, not a soft failure. |
| `markdownContent` | `string?` | optional | **DEAD FIELD — renderer ignores it** (`ServicePageRenderer.tsx` L22-27, since 2026-05-02). Kept on disk as the team's source-of-truth reference. The emitter MAY bank the distilled DOCX here; it will never reach HTML, will never be word-counted by a built-HTML gate, and must never be relied on for content. |
| `sections` | `ServiceSection[]` | **yes** | Not optional, may be `[]` but never is in practice. This is the entire page body. |
| `faqs` | `Array<{question,answer}>?` | optional | Renders a FAQ accordion **and** emits `FAQPage` JSON-LD (L47). See §7.3 for the capsule-gate trap. |

### 1.2 The `hero` sub-object

| Field | Type | Req | Notes |
|---|---|---|---|
| `badgeIcon` | `string` | **yes** | Font Awesome class, e.g. `'fas fa-map-marker-alt'` (hub/spoke), `'fas fa-hammer'` (sub-service). |
| `badgeText` | `string` | **yes** | ALL CAPS by house convention: `'SERVING CHARLOTTE and MECKLENBURG COUNTY'`, `'CHARLOTTE FASCIA INSTALLATION'`. |
| `title` | `string` | **yes** | **Rendered as the page H1 via `dangerouslySetInnerHTML`** (`Hero.tsx` L98/L101). House pattern: `'Fascia Installation in <span>Charlotte, NC</span>'` — the `<span>` is the brand accent wrap on the geo phrase. Exactly one `<span>` pair; no other markup. |
| `description` | `string` | **yes** | THE hero gate target: `<=25 words`, `<=2 sentences`, `<=160 chars` (prototype `v_hero`). Overflow is demoted to `sections[0].content[0]`. |
| `bgImage` | `string?` | optional in type, **required in practice** | Site-root path under `/images/`. Renders as the LCP element. Governed by `image_budget_check` hero tier (200 KB default). |
| `buttons` | array | optional | Always emit 2. Slot 1 = `className: 'btn-primary'`, `url: '/contact/'`, `iconAfter: 'fas fa-arrow-right'`. Slot 2 = `className: 'btn-ghost-white'`, `url: 'tel:5550100199'`, `iconBefore: 'fas fa-phone'`. `Hero.tsx` L52 substitutes defaults if omitted — do not rely on that. |
| `features` | `string[]?` | optional | 4 trust chips. Hub/spoke: `['GAF Master Elite', '5,000+ Projects', '26+ Years', '5-Star Rated']`. Values are client-config derived, never invented. |

`className` is a free `string`, not a union — but only two values exist across the
corpus (`'btn-primary'`, `'btn-ghost-white'`). Treat it as a **de facto enum**;
anything else ships unstyled.

---

## 2. Page classes — slug shape is the ONLY discriminator

| Class | Slug segments | Example | Route file | Registered in |
|---|---|---|---|---|
| **Global service** | 1 | `residential-roof-replacement` | `[slug]/page.tsx` → `SERVICE_PAGES` | `services.ts` |
| **HUB (metro)** | 1 | `charlotte-nc` | `[slug]/page.tsx` → `METRO_PAGES` | `location-pages.ts` + `allLocationPages` |
| **Metro sub-service** | 2 | `charlotte-nc/fascia-installation` | `[slug]/[city]/page.tsx` → `SPOKE_PAGES` | `allLocationPages` |
| **SPOKE (city)** | 2 | `charlotte-nc/matthews` | `[slug]/[city]/page.tsx` → `SPOKE_PAGES` | `allLocationPages` |
| **City SUB-SERVICE** | 3 | `charlotte-nc/mint-hill/gutter-replacement` | `[slug]/[city]/[subservice]/page.tsx` → `SUBSERVICE_PAGES` | `allLocationPages` |

Two 2-segment shapes share one route file. The renderer disambiguates by regex,
not by data:

```ts
// ServicePageRenderer.tsx L106
const SUB_SERVICE_SUFFIX_RE = /-(installation|repair|replacement|services|claims)$/i;
```

**Emitter rule (structural, non-negotiable):** the last segment of a sub-service
slug MUST end in one of `installation | repair | replacement | services | claims`.
If it does not, `locationLabel()` (L182-194) resolves the city name from the wrong
segment and the page renders "Fascia Installation weather is brutal" instead of
"Charlotte weather is brutal". This bug already shipped once (fixed 2026-05-22).

**`isLocationPage`** (L97-99): `slug.includes('/') || slug === 'charlotte-nc' ||
slug === 'asheville-nc'`. Hub slugs are **hard-coded**. A third metro hub
(`raleigh-nc`) requires a code edit — out of the emitter's scope, but the emitter
must flag it to the verdict ledger, because a new hub silently loses the location
marquee, the editorial transform and the closing CTA.

### 2.1 Linked-by-construction (the Acme orphan scar)

An entry is not "shipped" until it appears in **two** arrays:

1. `allLocationPages` in `location-pages.ts` — feeds `sitemap.ts`, hub link grids, footers.
2. The route array matching its segment count (`SERVICE_PAGES` / `METRO_PAGES` / `SPOKE_PAGES` / `SUBSERVICE_PAGES`) — feeds `generateStaticParams()`.

`dynamicParams = false` on all three routes. Missing from (2) → the page does not
build (404). Missing from (1) → the page builds and is crawlable but has zero
inbound links → **`orphan_check` exit 1**. The emitter writes both, in the same
transaction, or writes neither.

---

## 3. SEO surface — which fields drive what

All three route files carry byte-identical `generateMetadata()`.

| Output | Source |
|---|---|
| `<title>` | `page.metaTitle` |
| `<meta name=description>` | `page.metaDescription` |
| `rel=canonical` | `` `${company.url}/${page.slug}/` `` — **derived, never authored.** Trailing slash mandatory. `company.url = 'https://acmeroofing.example.com'`. |
| OG `title` / `description` / `url` / `siteName` / `type` | `metaTitle` / `metaDescription` / canonical / `company.name` / `'website'` |
| OG image | Hard-coded `/images/service-categories/homepagehero.webp`, 1200x630, alt = `` `${page.metaTitle}, Acme Roofing` `` |
| Twitter card | `summary_large_image` + same title/desc/image |
| **H1** | `page.hero.title` (raw HTML) |
| JSON-LD `@graph` | `localBusinessSchema()`, `serviceSchema(title, metaDescription, pageUrl)`, `webPageSchema(pageUrl, title, metaDescription, lastUpdated)`, `breadcrumbSchema([Home, title])`, `faqSchema(faqs)` if present, `reviewSchemas(slug)` |

The emitter authors exactly four SEO strings: `metaTitle`, `metaDescription`,
`title`, `hero.title`. Everything else is derived. **Do not emit a canonical
field — there is none.**

---

## 4. `ServiceSection` — the discriminated union

32 members, discriminated on `type`. `services.ts` L31-63. All `type` values are
string literals; the set below is closed — an unknown `type` fails `tsc` and
falls through `SectionRenderer`'s switch to render nothing.

### 4.1 Full member table

Legend: **arr** = the repeating collection whose length feeds the grid.

| `type` | Required fields | Optional | arr | Alt text |
|---|---|---|---|---|
| `materials` | `label,title,subtitle,items[{image,title,description}]` | — | `items` | derived from `title` (L454) |
| `process-dark` | `label,title,subtitle,steps[{title,description}]` | `red?:boolean` | `steps` | — |
| `warranty` | `label,title,subtitle,gafBadge,cards[{icon,years,yearsLabel,title,description}]` | `cards[].featured?` | `cards` | — |
| `repairs` | `label,title,subtitle,cards[{icon,title,description}]` | — | `cards` | — |
| `why` | `label,title,description,checklist[],buttonText,image` | — | `checklist` | derived from `title` (L560) |
| `emergency-dark` | `label,title,description,stats[{number,label}],buttons[]` | — | `stats` | — |
| `process-steps` | `label,title,subtitle,steps[{title,description}]` | `steps[].eyebrow?,steps[].photo?,steps[].icon?`, `light?`, `variant?: 'horizontal'\|'rail'` | `steps` | derived from `step.title` (L627) |
| `types` | `label,title,subtitle,cards[{icon,title,description}]` | — | `cards` | — |
| `checklist` | `label,title,description,buttonText,items[{title,description}]` | — | `items` | — |
| `free` | `label,title,description,benefits[],cardTitle,cardDesc` | — | `benefits` | — |
| `overview-split` | `label,title,content[],image,buttonText` | — | `content` | derived from `title` (L768) |
| `benefits` | `label,title,subtitle,cards[{icon,title,description}]` | `dark?` | `cards` | — |
| `breakdown` | `label,title,subtitle,cards[{icon,title,items[]}]` | — | `cards` | — |
| `gallery` | `label,title,subtitle,images[{src,alt}]` | — | `images` | **`alt` REQUIRED** |
| `testimonial` | `label,title,text,name,initials,location` | — | — | — |
| `response` | `label,title,subtitle,cards[{icon,number,label}]` | — | `cards` | — |
| `insurance-steps` | `label,title,subtitle,steps[{title,description}]` | — | `steps` | — |
| `commercial-types` | `label,title,subtitle,cards[{image,title,description}]` | — | `cards` | derived from `card.title` (L934) |
| `industries` | `label,title,subtitle,items[{icon,title}]` | — | `items` | — |
| `service-areas` | `label,title,subtitle,areas[{city,state}]` | — | `areas` | — |
| `related-services` | `label,title,subtitle,services[{title,description,url,icon}]` | — | `services` | — |
| `content-block` | `label,title,content[]` | `subtitle?`, `items[{icon,title,description}]?`, `dark?` | `items` | — |
| `comparison` | `label,title,subtitle,leftTitle,leftItems[],rightTitle,rightItems[]` | — | 2 cols | — |
| `projects-marquee` | `label,title,subtitle,images[{src,alt}]` | `images[].tag?`, `ctaText?`, `ctaUrl?` | `images` | **`alt` REQUIRED** |
| `editorial-split` | `label,title,lede,paragraphs[],image,imageAlt` | `pullQuote?`, `credentialStrip?{mark,sublabel}`, `caption?{text,meta?}`, `bigWord?` | `paragraphs` | **`imageAlt` REQUIRED** |
| `stat-strip` | `headline,stats[{num,label}]` | `eyebrow?`, `bgImage?`, `dark?` | `stats` | bg, no alt |
| `credential-feature` | `label,title,intro,image,imageAlt,items[{title,description}]` | `imageStamp?{mark,label}` | `items` | **`imageAlt` REQUIRED** |
| `service-mosaic` | `title,subtitle,cards[{title,image,imageAlt,href,size}]` | `label?`, `cards[].description?`, `cards[].category?`, `cards[].num?` | `cards` | **`imageAlt` REQUIRED per card** |
| `before-after-feature` | `label,title,paragraphs[],beforeImage,afterImage,beforeLabel{stage,address},afterLabel{stage,address},meta[{value,label}]` | `beforeAlt?`, `afterAlt?`, `background?: 'cream'\|'burgundy'` | `meta` | alt optional — **emit anyway** |
| `testimonial-pullquote` | `text,name,initials,location` | `attribution?` | — | — |
| `project-spotlight` | `title,projects[{image,imageAlt,tag,title,location}]` | `ctaText?`, `ctaUrl?`, `projects[].href?` | `projects` | **`imageAlt` REQUIRED** |
| `closing-cta-editorial` | `label,title,description,bgImage,primaryCta{text,url,icon?}` | `secondaryCta?`, `showForm?`, `formCity?` | — | bg, no alt |

### 4.2 Literal / enum constraints (the complete set)

```ts
ServiceSection['type']                       // 32 literals, closed union (L31-63)
ServiceMosaicSection.cards[].size            // 'feature' | 'mid' | 'third' | 'half' | 'full'
BeforeAfterFeatureSection.background         // 'cream' | 'burgundy'
ProcessStepsSection.variant                  // 'horizontal' | 'rail'
```

De facto enums (typed `string`, but only these values exist and only these are styled):

```
hero.buttons[].className   'btn-primary' | 'btn-ghost-white'
*.icon / hero.badgeIcon    /^fas fa-[a-z0-9-]+$/   (Font Awesome 6 solid)
service-areas.areas[].state 'NC' | 'SC' | 'VA' | 'WV'   (per client-config states_served)
```

### 4.3 `<em>` and `<span>` in headings

- `hero.title` → rendered raw via `dangerouslySetInnerHTML`. House pattern: one `<span>` around the geo phrase.
- Section `title` / `headline` → passed through `renderEm()` (L429-437), which converts `<em>...</em>` to accent italic. **Only `<em>` is parsed.** Any other tag ships as literal text.
- Everything else (`subtitle`, `description`, `content[]`, `lede`, `paragraphs[]`, card `description`, FAQ `answer`) is plain-text React children. **HTML in those fields renders as escaped literal text.** The emitter must strip all markup from them.

---

## 5. Layout mapping — section → page region

The renderer runs `transformLocationSections()` then `injectLocationMarquee()`
before rendering (L74). This matters enormously: **on a location page the
emitter's sections are not what renders.**

### 5.1 Fixed chrome (never authored, always present)

`Hero` → `EmergencyHeroForm` (slug contains `emergency`) → `Breadcrumb` →
`AuthorByline` → **[sections]** → `FAQSection` (if `faqs`) →
`InspectionCTAForm` (slug contains `inspection`) → `CTASection`.

Note the two **slug-keyword side effects**: `emergency` and `inspection` anywhere
in the slug inject extra forms (L35-36). The emitter must not use those words
incidentally.

### 5.2 The editorial transform — the single biggest emitter constraint

`transformLocationSections()` (L199-425) applies when:

- `isLocationPage(slug)` is true, **AND**
- the entry contains **zero** sections of type `editorial-split`, `stat-strip`, `credential-feature`, `service-mosaic`, `before-after-feature`, `testimonial-pullquote`, `project-spotlight`, `closing-cta-editorial` (L205-206).

So there are exactly **two authoring modes**, and the emitter must pick one
deliberately:

| Mode | Trigger | What the emitter writes |
|---|---|---|
| **A — hand-authored** (the Charlotte hub) | ≥1 "new editorial" section present | The literal section sequence. Passes through untouched. Full control, full responsibility. |
| **B — legacy/transformed** (every spoke + sub-service) | zero editorial sections | `content-block` / `types` / `benefits` / `process-steps` / `service-areas` / `related-services` only. The renderer **synthesizes** the editorial page from them. |

Mode B's synthesis, in emitted order (L219-424):

| # | Emitted section | Built from | If source missing |
|---|---|---|---|
| 1 | `editorial-split` | first `content-block`: `content[0]`→`lede`, `content[1..2]`→`paragraphs`, last para→`pullQuote` if `<220` chars | section skipped entirely |
| 2 | `stat-strip` | **hard-coded brand stats** (5K+ / 2% / 4 / 24/7) | always present |
| 3 | `credential-feature` | the `types` section whose `label` or `title` matches `/credential\|award\|certif/i`, else `types[0]`; `cards.slice(0,4)` | skipped |
| 4 | `service-mosaic` | first `types` section that is NOT the credential one and whose label does not match `/financ/i`; `cards.slice(0,6)` | skipped |
| 5 | `process-steps` (`variant:'rail'`) | the `process-steps` section; `steps.slice(0,4)`, titled `'Four steps. <em>No surprises.</em>'` | skipped |
| 6 | `before-after-feature` | portfolio photos, hard-coded copy | always present |
| 7 | `testimonial-pullquote` | hard-coded, city-interpolated | always present |
| 8 | `project-spotlight` | 3 deterministic portfolio photos | always present |
| 9 | `service-areas` | passed through verbatim | skipped |
| 10 | `related-services` | **ALL** such sections passed through, in order | skipped |
| 11 | `closing-cta-editorial` | hard-coded + `formCity` | always present |

Consequences the emitter must internalise:

- In Mode B, a `testimonial`, `content-block` #2+, `comparison`, `gallery`, `warranty`, `checklist`, `breakdown` or any other section **is silently dropped**. Real prose the team wrote will not appear on the page. This is the highest-value thing for the emitter to detect and route to the verdict ledger.
- `label` text on the credentials `types` block is **load-bearing routing**, not decoration. Emit `label: 'Awards and Credentials'` (the existing `certificationsSection()` value) or the credentials block lands in the photo mosaic and the services block lands in the credential slot — the exact inversion bug fixed on 2026-05-22.
- A `types` section labelled with `financ` is excluded from the mosaic by design.
- Photos, alt text, hrefs and `size` for the mosaic are **generated by the renderer** in Mode B. The emitter supplies only `{icon, title, description}` per card.
- All photo assignment in Mode B is a deterministic hash of the slug (`pickPhotos`, L157-177). Changing a slug changes every photo on the page.

### 5.3 Marquee injection

`injectLocationMarquee` (L138-153): on location pages with no existing
`projects-marquee` or `gallery`, a marquee is inserted **after the last `types`
or `benefits` section** (else at index `min(3, len)`). Emitting a `gallery`
suppresses it.

### 5.4 Shared builder functions (call, do not inline)

`location-pages.ts` L9-73 define four parameterised section builders reused by
every spoke. The emitter emits **calls**, not literals:

```ts
certificationsSection(city: string, neighborhoods: string): ServiceSection  // type 'types',   4 cards
whyAcmeSection(city: string): ServiceSection                              // type 'benefits',6 cards
financingSection(city: string): ServiceSection                              // type 'types',   4 cards
processSection(): ServiceSection                                            // type 'process-steps', 4 steps
```

`neighborhoods` is a prose fragment ("Sardis Forest, Brookhaven, Callonwood, and
the streets around Downtown Matthews") — it is the page's proprietary-variable
carrier for `noncommodity_check`. Metro-level pages pass the module constants
`CHARLOTTE_NEIGHBORHOODS_PROSE` / `CHARLOTTE_NEARBY` (L17220-17229).

---

## 6. The mosaic / card-grid item-count rule

`ServicePageRenderer.tsx` L283-293, verbatim:

```ts
// Card-count-aware sizing so the grid always fills cleanly (12-col grid):
// 3 cards → feature(7,2rows) + mid(5)×2 stacked = perfect fill
// 4 cards → feature(7,2rows) + mid(5)×2 stacked + full(12) row3 = perfect fill
// 5 cards → feature(7,2rows) + mid(5)×2 stacked + half(6)×2 row3 = perfect fill
// 6 cards → feature(7,2rows) + mid(5)×2 stacked + third(4)×3 row3 = perfect fill
const cardCount = Math.min(servicesType.cards.length, 6);
let sizes: Array<'feature' | 'mid' | 'third' | 'half' | 'full'>;
if (cardCount === 3) sizes = ['feature', 'mid', 'mid'];
else if (cardCount === 4) sizes = ['feature', 'mid', 'mid', 'full'];
else if (cardCount === 5) sizes = ['feature', 'mid', 'mid', 'half', 'half'];
else sizes = ['feature', 'mid', 'mid', 'third', 'third', 'third'];
```

**THE RULE: the source `types` card grid must contain exactly 3, 4, 5 or 6 cards.**

- `n < 3` → the `else` branch assigns a 6-slot `sizes` array to `n` cards; the grid under-fills and leaves a visible ragged hole. **Not caught by `tsc`.**
- `n > 6` → `Math.min(…, 6)` and `.slice(0, 6)` **silently discard** cards 7..n. Team prose vanishes with no error, no warning, no ledger entry.

Both are invisible failures. This is why the prototype gate `v_mosaic` is
non-auto-fixable: trimming to 6 or padding to 3 is a curation judgment. The
emitter must route every violation to the verdict ledger with the discarded card
titles enumerated. (The prototype found 10 such violations on the Dana archive.)

In **Mode A** the emitter authors `size` itself and must reproduce the same
matrix by hand — the renderer applies no sizing to hand-authored mosaics.

Adjacent count rules found in the same renderer:

| Section | Rule | Line |
|---|---|---|
| `credential-feature` items | `cards.slice(0, 4)` — cards 5+ discarded | L274 |
| `process-steps` (rail) | `steps.slice(0, 4)`; icon/photo arrays are length-4 | L343-349 |
| `content-block` items | grid switches to `grid-3` when `items.length % 2 !== 0 \|\| items.length >= 6` | L1101 |
| `project-spotlight` | exactly 3 (renderer-built) | L165-169 |
| `stat-strip` stats | 4 by convention | L246-251 |
| `hero.features` | 4 by convention | — |

---

## 7. Alt text — where it is structurally required

the operator's June-2026 build gate: every image slot carries alt. Three tiers exist in
the type system:

**Tier 1 — alt is a required field. Omitting it fails `tsc`:**

```
gallery.images[].alt
projects-marquee.images[].alt
editorial-split.imageAlt
credential-feature.imageAlt
service-mosaic.cards[].imageAlt
project-spotlight.projects[].imageAlt
```

**Tier 2 — alt field exists but is optional. `tsc` passes, the image ships
without meaningful alt. The emitter MUST emit these anyway:**

```
before-after-feature.beforeAlt
before-after-feature.afterAlt
```

**Tier 3 — no alt field at all; the renderer substitutes the adjacent title:**

```
materials.items[].image        → alt = item.title            (L454)
why.image                      → alt = section.title         (L560)
process-steps.steps[].photo    → alt = step.title            (L627)
overview-split.image           → alt = section.title         (L768)
commercial-types.cards[].image → alt = card.title            (L934)
```

Tier 3 means **the `title` field doubles as alt text.** The emitter must treat
those titles as accessibility strings, not just headings: descriptive, no
truncation, no bare `'Repair'`.

**Background images carry no alt and are decorative** (`hero.bgImage`,
`stat-strip.bgImage`, `closing-cta-editorial.bgImage`) — correct, do not add one.

All image paths are site-root-absolute (`/images/...`), served unoptimized
(`images.unoptimized: true`), and are subject to `image_budget_check`:
hero ≤200 KB, content ≤100 KB, thumb ≤30 KB.

---

## 8. Gate obligations that land on the emitted data

Gates are proven and immutable. The emitter satisfies them. Non-obvious ones:

### 8.1 `em_dash_check` (exit 1)

Scans built HTML **outside** `<script>`/`<style>`. Flags `—`, `&mdash;`, `&#8212;`,
`&#x2014;`. Since `markdownContent` never renders, banked DOCX text there is
exempt — **but every rendered string is not.** Mechanical scrub, auto-fixable.
Replacement char is a per-client config value (`', '` vs `' | '`).

### 8.2 `check_headings` (exit 1)

Default **lenient** mode (no `headings.strict_title_case` in
`acme-roofing-site/docs/client-config.yml`): a heading fails only if its first
significant word is uncapitalised or it is entirely lowercase. This is why
`'Four steps. <em>No surprises.</em>'` passes. Entities are unescaped before
checking. If a client flips `strict_title_case: true`, every section `title`,
card `title`, step `title`, and `hero.title` must become full Title Case.

### 8.3 `capsule_check` (exit 6) — THE TRAP

Three sub-checks, per selected (topology-fitting) page:

1. **`interrogative_h2`** — ≥1 `<h2>` whose text ends in `?` or begins with
   `how|what|why|when|where|which|who|do|does|is|are|can|should|will`.

   > **FAQ questions do NOT satisfy this.** `FAQSection.tsx` L43 renders each
   > question as `<span>` inside a `<button>`, never as an `<h2>`. The only `<h2>`
   > elements on the page are section `title` / `headline` values.
   >
   > **Emitter obligation:** at least one section `title` must be interrogative.
   > Existing compliant examples: `'Why Substrate Preparation Is the Single
   > Biggest Performance Factor'`, `'When to Repair Gutters vs. When to Replace
   > Them in Mint Hill'`.

2. **`answer_first`** — the **first `<p>` or `<li>` after the FIRST interrogative
   H2**, up to the next heading, must be 40-80 words and ≤3 sentences.

   Which string that is depends on section type:
   - `types` / `benefits` / `materials` / `repairs` → `subtitle` (always renders as the next `<p>`)
   - `content-block` → `subtitle` if present, else `content[0]`
   - `editorial-split` → `lede`

   > **Emitter obligation:** the emitter must know *which* section becomes the
   > first interrogative H2 and size that specific string to 40-80 words / ≤3
   > sentences. Most current Acme `content-block` opening paragraphs run
   > 80-150 words and would fail. Distillation must not blindly optimise this
   > paragraph for the band — it is the one paragraph on the page with an upper
   > bound.

3. **`tldr_on_long`** — if total stripped body words > 1200 (config
   `content.long_page_threshold`; absent in Acme's config → default 1200), the
   page must contain `tl;dr | key takeaways | in short | the short answer |
   bottom line`.

   > **Live finding:** only 8 occurrences of any of those markers exist across
   > all 21,844 lines of `location-pages.ts`, all incidental prose uses of "in
   > short". Every location page exceeds 1200 total words (core body alone
   > targets 800-1500, plus hero + FAQs + nav + footer + 11 synthesized
   > sections). **This sub-check is currently unsatisfied by construction on
   > effectively every page.** The emitter must emit a TL;DR-bearing block —
   > a `content-block` with `label: 'Key Takeaways'` is the natural carrier —
   > or the pipeline must record a documented waiver. Flagging, not fixing:
   > the decision is the operator's.

### 8.4 `noncommodity_check` (exit 7)

Every page needs ≥1 proprietary token (allow-list = `required_phrases` ∪
`nap.city` ∪ `service_areas[]` ∪ crew names ∪ `primary_metro`) and ≤0.90 5-gram
overlap with siblings (0.90 because `topology: franchise` contains hub-spoke).

`required_phrases` for Acme: `'GAF Master Elite'`, `'(555) 555-0100'`,
`'Licensed'` — all three are already carried by `certificationsSection()` and
`hero.buttons[1].text`. The **overlap** half is the emitter's real problem: four
shared builders emit byte-identical prose on every spoke. Differentiation has to
come from the `content-block` / `types` sections the emitter authors, and from
the `neighborhoods` argument.

### 8.5 `fingerprint_check` (exit 8)

Raw-byte scan, **does not strip `<script>`/`<style>`**, so JSON-LD is in scope.
Zero-width chars, bidi controls, U+E0000-E007F tag block, `data-generated-by`.
LLM-authored strings routinely carry these. The emitter must NFC-normalise and
strip invisibles from every string before writing. A single leading BOM is
tolerated; any other U+FEFF fails.

### 8.6 `pages_are_data_check` (exit 1)

Dynamic routes always pass. The emitter must never create a static
`src/app/<slug>/page.tsx`. Data-only, always.

### 8.7 Core-body distillation (module 05)

Band: **800-1500 CORE-BODY words HARD, ~1200 advisory-not-a-target.** Adversarially
proven; not re-litigated here. Mapping onto this contract's section types:

| Bucket | Section types | Counted |
|---|---|---|
| **CORE BODY** | `content-block.content[]`, `editorial-split.lede`+`paragraphs[]`, `overview-split.content[]`, `comparison.leftItems`+`rightItems`, `checklist`, `breakdown`, and the `description` of a `types`/`materials` grid that carries substantive service explanation | **yes** |
| **STRUCTURED** | `hero.*`, `process-steps`, `process-dark`, `warranty`, `service-areas`, `related-services`, `testimonial`, `testimonial-pullquote`, `faqs[]`, `closing-cta-editorial`, `stat-strip`, `credential-feature`, `project-spotlight`, `projects-marquee`, `gallery`, `before-after-feature`, and everything emitted by the four shared builders | no |

Default-safe: an unmapped section is STRUCTURED (excluded), never silently counted.

---

## 9. EMITTER OUTPUT CONTRACT

### 9.1 Common minimum — every page class

```ts
import type { ServicePage, ServiceSection } from './services';

const page: ServicePage = {
  slug: string,              // no leading/trailing slash; segments = page class
  lastUpdated: string,       // 'YYYY-MM-DD' — ALWAYS emit; the fallback backdates
  title: string,             // plain text, no HTML
  metaTitle: string,         // <=56 effective chars
  metaDescription: string,   // 150-160 chars
  hero: {
    badgeIcon: string,       // 'fas fa-*'
    badgeText: string,       // ALL CAPS
    title: string,           // H1, exactly one <span> around the geo phrase
    description: string,     // <=25 words, <=2 sentences, <=160 chars
    bgImage: string,         // '/images/...' <=200 KB
    buttons: [
      { text: string, url: '/contact/',   className: 'btn-primary',     iconAfter: 'fas fa-arrow-right' },
      { text: string, url: 'tel:...',     className: 'btn-ghost-white', iconBefore: 'fas fa-phone' },
    ],
    features: [string, string, string, string],
  },
  sections: ServiceSection[],                          // see per-class below
  faqs: Array<{ question: string; answer: string }>,   // 5-6; does NOT satisfy capsule
};
```

Plus, in the same write transaction:
1. `export const <camelName>: ServicePage = { … }` in `src/data/location-pages.ts`
2. append `<camelName>` to `allLocationPages`
3. append `<camelName>` to the segment-matched route array + its import block

### 9.2 HUB (1 segment, `charlotte-nc`) — Mode A, hand-authored

Sections, in exact order, all 11 authored literally (no transform runs):

```ts
sections: [
  { type: 'editorial-split',        /* label,title(<em>),lede,paragraphs[],pullQuote,image,imageAlt,credentialStrip,caption,bigWord */ },
  { type: 'stat-strip',             /* eyebrow,headline(<em>),stats[4]{num,label},bgImage */ },
  { type: 'credential-feature',     /* label,title(<em>),intro,image,imageAlt,imageStamp,items[<=4]{title,description} */ },
  { type: 'service-mosaic',         /* title(<em>),subtitle,cards[3|4|5|6] each {num,category?,title,description?,image,imageAlt,href,size} — size matrix §6 authored BY HAND */ },
  { type: 'process-steps',          /* label,title(<em>),subtitle,variant:'rail',steps[4]{eyebrow,title,description,photo?|icon?} */ },
  { type: 'before-after-feature',   /* label,title(<em>),paragraphs[],beforeImage,afterImage,beforeAlt,afterAlt,beforeLabel,afterLabel,meta[3],background */ },
  { type: 'testimonial-pullquote',  /* text,name,initials,location,attribution */ },
  { type: 'project-spotlight',      /* title(<em>),ctaText,ctaUrl,projects[3]{image,imageAlt,tag,title,location} */ },
  { type: 'service-areas',          /* label,title,subtitle,areas[]{city,state} */ },
  { type: 'related-services',       /* label,title,subtitle,services[]{title,description,url,icon} */ },
  { type: 'closing-cta-editorial',  /* label,title(<em>),description,bgImage,primaryCta,secondaryCta,showForm,formCity */ },
]
```

Worked example — real, copied from `location-pages.ts` L459-535 (`charlotteNC`), abridged to two sections:

```ts
export const charlotteNC: ServicePage = {
  slug: 'charlotte-nc',
  lastUpdated: '2026-05-22',
  title: 'Roofing Contractor in Charlotte, NC',
  metaTitle: 'Roofing and Exterior Services Charlotte NC | Since 2000',
  metaDescription:
    'GAF Master Elite roofing contractor in Charlotte, NC. Residential, commercial, siding, gutters. 26+ years, 5K+ projects. Free inspection. Call (555) 555-0100.',
  hero: {
    badgeIcon: 'fas fa-map-marker-alt',
    badgeText: 'SERVING CHARLOTTE and MECKLENBURG COUNTY',
    title: 'Roofing Contractor in <span>Charlotte, NC</span>',
    description:
      'Residential roofing, commercial roofing, siding, gutters, soffit, and fascia, all from one GAF Master Elite certified contractor with 26+ years of local experience across Mecklenburg County.',
    bgImage: '/images/service-categories/residential-services/hero-residential-roofing.webp',
    buttons: [
      { text: 'Get Free Charlotte Inspection', url: '/contact/', className: 'btn-primary', iconAfter: 'fas fa-arrow-right' },
      { text: 'Call: (555) 555-0100', url: 'tel:5550100199', className: 'btn-ghost-white', iconBefore: 'fas fa-phone' },
    ],
    features: ['GAF Master Elite', '5,000+ Projects', '26+ Years in Charlotte', '5-Star Rated'],
  },
  sections: [
    {
      type: 'editorial-split',
      label: 'Charlotte, NC',
      title: "The Carolinas' Weather Is Brutal. <em>Your Roof Should Not Be the Weak Link.</em>",
      lede: 'Charlotte sits at a weather crossroads. Spring hail, summer thunderstorms, hurricane remnants pushing inland from the coast. These are not abstractions. They are the reason 5,000+ Mecklenburg County homeowners and businesses have called Acme since 2000.',
      paragraphs: [
        'Whether you need a full residential replacement in Ballantyne, a commercial repair near Uptown, or new siding and gutters in Matthews, one GAF Master Elite team handles your entire exterior. No juggling contractors. No finger-pointing.',
      ],
      pullQuote: 'Fewer than 2% of roofers in North America hold GAF Master Elite. Charlotte deserves one of them.',
      image: '/images/portfolio/residential/aster.webp',
      imageAlt: 'Acme residential roof replacement in Charlotte, NC',
      credentialStrip: { mark: 'Master Elite', sublabel: 'GAF Certified · Top 2% in North America' },
      caption: { text: 'Aster Lane, Ballantyne. GAF Timberline replacement.', meta: 'Project № 4,217' },
      bigWord: 'CHARLOTTE',
    },
    {
      type: 'service-mosaic',
      title: 'Residential and Commercial. <em>One Charlotte Team.</em>',
      subtitle: 'Every Acme service ships with GAF Master Elite installation standards and full insurance support. Same crews on a small targeted repair as a complete commercial replacement.',
      cards: [
        { num: '01', category: 'Residential', title: 'Roof Replacement', description: 'Full residential replacements using GAF premium systems backed by the strongest warranties in the industry. Architectural and designer shingles available.', image: '/images/portfolio/residential/7600-willowdale-2.webp', imageAlt: 'Residential roof replacement Charlotte', href: '/residential-roof-replacement/', size: 'feature' },
        { num: '02', category: 'Residential', title: 'Roof Repair', image: '/images/portfolio/residential/3012-olde-elizabeth.webp', imageAlt: 'Roof repair Charlotte', href: '/residential-roof-repair/', size: 'mid' },
        { num: '03', category: 'Commercial', title: 'Commercial Replacement', image: '/images/portfolio/commercial/img-2972.webp', imageAlt: 'Commercial roofing Charlotte', href: '/commercial-roof-replacement/', size: 'mid' },
        { num: '04', title: 'Storm and Emergency', image: '/images/portfolio/before-after/2216-annabel-ct-after.webp', imageAlt: 'Storm response Charlotte', href: '/storm-damage-roof-repair/', size: 'third' },
        { num: '05', title: 'Roof Inspection', image: '/images/portfolio/before-after/3318-lakeside-dr-after.webp', imageAlt: 'Roof inspection Charlotte', href: '/residential-roof-inspection/', size: 'third' },
        { num: '06', title: 'Siding · Gutters · Fascia', image: '/images/portfolio/residential/3011-on-roof.webp', imageAlt: 'Siding gutters fascia Charlotte', href: '/siding-services/', size: 'third' },
      ],
    },
    // … 9 more sections
  ],
  faqs: [ /* 5-6 */ ],
};
```

Note: 6 mosaic cards → `['feature','mid','mid','third','third','third']`. The
matrix in §6, applied by hand. Card 2, 3 and 6 omit `description` — legal
(`description?`), and the renderer degrades cleanly.

Registration: `METRO_PAGES` in `[slug]/page.tsx` + `allLocationPages`. Adding a
NEW metro hub also requires editing `isLocationPage()` and `getCityName()` —
flag to the ledger.

### 9.3 SPOKE (2 segments, `charlotte-nc/matthews`) — Mode B

Zero editorial sections. Minimum viable, in this exact order:

```ts
sections: [
  { type: 'content-block',   label, title, content: [string, string, string] },   // → editorial-split
  { type: 'types',           label, title, subtitle, cards: [3|4|5|6 × {icon,title,description}] }, // → service-mosaic
  certificationsSection(city, neighborhoodProse),   // → credential-feature (label MUST match /credential|award|certif/i)
  whyAcmeSection(city),
  { type: 'content-block',   label, title, content: [string, string], dark: true },  // DROPPED by transform — ledger it
  financingSection(city),                            // excluded from mosaic by /financ/i
  processSection(),                                  // → process-steps rail
  { type: 'testimonial',     label, title, text, initials, name, location },          // DROPPED by transform
  { type: 'service-areas',   label, title, subtitle, areas: [{city,state} × 6] },     // passed through
  { type: 'related-services',label, title, subtitle, services: [{title,description,url,icon} × 4] }, // passed through
],
faqs: [ /* 5-6 */ ],
```

Worked example — real, `location-pages.ts` L636+ (`matthewsNC`), abridged:

```ts
export const matthewsNC: ServicePage = {
  slug: 'charlotte-nc/matthews',
  lastUpdated: '2026-04-30',
  title: 'Roofing Contractor in Matthews, NC',
  metaTitle: 'Roofing and Exterior Services Matthews NC | Acme',
  metaDescription: '…',
  hero: {
    badgeIcon: 'fas fa-map-marker-alt',
    badgeText: 'SERVING MATTHEWS and MECKLENBURG COUNTY',
    title: 'Roofing Contractor in <span>Matthews, NC</span>',
    description:
      'Matthews homeowners trust Acme for every project, from routine inspections along the Sardis Road corridor to full roof replacements in Providence Hills and Brookhaven. GAF Master Elite certified, top 2% of roofers in North America.',
    bgImage: '/images/service-categories/residential-services/hero-residential-roofing.webp',
    buttons: [
      { text: 'Get Free Matthews Inspection', url: '/contact/', className: 'btn-primary', iconAfter: 'fas fa-arrow-right' },
      { text: 'Call: (555) 555-0100', url: 'tel:5550100199', className: 'btn-ghost-white', iconBefore: 'fas fa-phone' },
    ],
    features: ['GAF Master Elite', '5,000+ Projects', '26+ Years', '5-Star Rated'],
  },
  sections: [
    {
      type: 'content-block',
      label: 'Trusted Since 2000',
      title: "Matthews's Complete Exterior Contractor",
      content: [
        'Matthews sits at the southeastern edge of Mecklenburg County, about 11 miles from Uptown Charlotte. Homes here deal with fast-moving thunderstorm cells tracking northeast out of the southwest, dropping hail, driving wind, and heavy rain that can compromise shingles, push water behind siding, and overwhelm gutters in minutes.',
        'Acme has worked throughout Matthews for over two decades, on brick colonials in Sardis Forest, newer construction in Callonwood and Brookhaven, established ranches near Downtown Matthews along Trade Street, and larger homes in Providence Hills off McKee Road. …',
        'GAF Master Elite certification puts Acme in the top 2% of roofing contractors across North America. …',
      ],
    },
    {
      type: 'types',
      label: 'Our Services in Matthews',
      title: 'Roofing and Exterior Services in Matthews, NC',
      subtitle:
        'From the established neighborhoods around Matthews Township Parkway to the growing communities along Independence Boulevard, Acme provides every exterior service your Matthews home or business needs.',
      cards: [
        { icon: 'fas fa-home',                  title: 'Roof Replacement',      description: '…' },
        { icon: 'fas fa-wrench',                title: 'Roof Repair',           description: '…' },
        { icon: 'fas fa-cloud-bolt',            title: 'Storm Damage Repair',   description: '…' },
        { icon: 'fas fa-city',                  title: 'Commercial Roofing',    description: '…' },
        { icon: 'fas fa-house-chimney-window',  title: 'Siding and Exteriors',  description: '…' },
        { icon: 'fas fa-cloud-rain',            title: 'Gutters',               description: '…' },
      ],   // 6 cards — hits the ['feature','mid','mid','third','third','third'] branch
    },
    certificationsSection('Matthews', 'Sardis Forest, Brookhaven, Callonwood, and the streets around Downtown Matthews'),
    whyAcmeSection('Matthews'),
    { type: 'content-block', label: 'Storm Season', title: 'Storm Damage Protection for Matthews Homes', content: ['…', '…'], dark: true },
    financingSection('Matthews'),
    processSection(),
    { type: 'testimonial', label: 'What Matthews Homeowners Say', title: 'Matthews Customer Review', text: '…', initials: '…', name: '…', location: '…' },
    { type: 'service-areas', label: 'Where We Work', title: '…', subtitle: '…', areas: [ /* 6 */ ] },
    { type: 'related-services', label: 'Related Services', title: '…', subtitle: '…', services: [ /* 4 */ ] },
  ],
  faqs: [ /* 6 */ ],
};
```

Registration: `SPOKE_PAGES` in `[slug]/[city]/page.tsx` + `allLocationPages`.

Emitter must ledger: content-block #2 and the `testimonial` section are dropped
by `transformLocationSections`; their prose never reaches HTML.

### 9.4 SUB-SERVICE — Mode B, two slug shapes

Metro-level (2 segments, `charlotte-nc/fascia-installation`) → `SPOKE_PAGES`.
City-level (3 segments, `charlotte-nc/mint-hill/gutter-replacement`) →
`SUBSERVICE_PAGES`. **Identical object shape.** Last segment MUST match
`/-(installation|repair|replacement|services|claims)$/`.

Differences from a spoke:
- `hero.badgeIcon` is service-semantic (`'fas fa-hammer'`, `'fas fa-recycle'`), not `'fas fa-map-marker-alt'`.
- `hero.badgeText` is service-scoped: `'CHARLOTTE FASCIA INSTALLATION'` / `'SERVING MINT HILL, NC'`.
- `hero.features` drop the geo chip: `['GAF Master Elite', '5,000+ Projects', '26+ Years', 'Free Estimates']`.
- `hero.buttons[0].text` is service-specific: `'Get Free Fascia Estimate'`.
- The `types` grid enumerates **materials or scope options**, not services.
- `related-services` links siblings within the same city + the parent metro page — this is the reciprocity edge that keeps `orphan_check` green.

Worked example — real, `location-pages.ts` L17234-17330 (`charlotteFasciaInstallation`), abridged:

```ts
export const charlotteFasciaInstallation: ServicePage = {
  slug: 'charlotte-nc/fascia-installation',
  lastUpdated: '2026-05-22',
  title: 'Fascia Installation in Charlotte, NC',
  metaTitle: 'Fascia Installation Charlotte NC | GAF Master Elite',
  metaDescription:
    'Professional fascia installation in Charlotte, NC. Aluminum wrap, PVC, wood, fiber cement. GAF Master Elite contractor. Free estimate. (555) 555-0100.',
  hero: {
    badgeIcon: 'fas fa-hammer',
    badgeText: 'CHARLOTTE FASCIA INSTALLATION',
    title: 'Fascia Installation in <span>Charlotte, NC</span>',
    description:
      'Aluminum wrap, PVC, solid aluminum, fiber cement, and wood fascia installation across Charlotte. GAF Master Elite certified.',
    bgImage: '/images/service-categories/residential-services/hero-residential-roofing.webp',
    buttons: [
      { text: 'Get Free Fascia Estimate', url: '/contact/', className: 'btn-primary', iconAfter: 'fas fa-arrow-right' },
      { text: 'Call: (555) 555-0100', url: 'tel:5550100199', className: 'btn-ghost-white', iconBefore: 'fas fa-phone' },
    ],
    features: ['GAF Master Elite', '5,000+ Projects', '26+ Years', 'Free Estimates'],
  },
  sections: [
    { type: 'content-block', label: "Charlotte's Exterior Contractor Since 2000", title: "Fascia Installation Built for Charlotte's Climate", content: ['…', '…', '…'] },
    {
      type: 'types',
      label: 'Fascia Materials',
      title: 'Fascia Materials We Install in Charlotte',
      subtitle: "Each material has a different performance profile and service life in Charlotte's climate. Here is what to know before deciding.",
      cards: [
        { icon: 'fas fa-shield',   title: 'Aluminum-Wrapped Wood Fascia', description: '…' },
        { icon: 'fas fa-cube',     title: 'PVC Fascia',                   description: '…' },
        { icon: 'fas fa-mountain', title: 'Solid Aluminum Fascia',        description: '…' },
        { icon: 'fas fa-gem',      title: 'Fiber Cement Fascia',          description: '…' },
        { icon: 'fas fa-tree',     title: 'Wood Fascia',                  description: '…' },
      ],   // 5 cards → ['feature','mid','mid','half','half']
    },
    certificationsSection('Charlotte', CHARLOTTE_NEIGHBORHOODS_PROSE),
    whyAcmeSection('Charlotte'),
    financingSection('Charlotte'),
    processSection(),
    { type: 'content-block', label: 'Substrate Matters', title: 'Why Substrate Preparation Is the Single Biggest Performance Factor', content: ['…', '…', '…'], dark: true },
    { type: 'testimonial', label: 'What Charlotte Homeowners Say', title: 'Charlotte Customer Review', text: '…', initials: 'JC', name: 'Jennifer C.', location: 'Myers Park, Charlotte NC' },
    { type: 'service-areas', label: 'Where We Work', title: 'Fascia Installation Across Charlotte and the Metro Area', subtitle: '…', areas: CHARLOTTE_NEARBY },
    { type: 'related-services', label: 'Related Services', title: 'Coordinate Your Fascia Project With Adjacent Exterior Work', subtitle: '…', services: [ /* 4 */ ] },
  ],
  faqs: [ /* 6 */ ],
};
```

`'Why Substrate Preparation Is the Single Biggest Performance Factor'` is the
interrogative H2 satisfying `capsule.interrogative_h2` — but it is a `content-block`
with no `subtitle`, so `capsule.answer_first` measures `content[0]`, which runs
~95 words and **fails the 40-80 band**. This is a real, live example of the §8.3
trap and the concrete reason the emitter must size that specific paragraph.

### 9.5 Emitter pre-write assertion list

Fail the write, do not warn, on any of:

1. `slug` collides with an existing export or `slug` in either data file.
2. Segment count does not match the route array being written.
3. 2/3-segment slug whose last segment fails `/-(installation|repair|replacement|services|claims)$/` while intended as a sub-service.
4. `hero.description` > 25 words / > 2 sentences / > 160 chars.
5. `metaTitle` > 56 effective chars.
6. Em dash in any rendered string.
7. Any invisible codepoint (§8.5) in any string.
8. A `types`/`benefits`/`materials`/`repairs` grid with card count outside {3,4,5,6}.
9. A Tier-1 alt field missing or empty; a Tier-2 alt omitted; a Tier-3 `title` shorter than 3 words.
10. Mode B entry containing any of the 8 editorial section types (would suppress the transform silently).
11. Mode B entry whose credentials section `label` does not match `/credential|award|certif/i`.
12. Zero interrogative section `title` on the page.
13. First-interrogative-H2 answer paragraph outside 40-80 words or > 3 sentences.
14. Core-body word count outside 800-1500 (per §8.7 bucket mapping).
15. Entry not appended to BOTH `allLocationPages` and the segment-matched route array.

Assertions 8, 10, 13 and 14 are **curation-judgment** failures: route to the
verdict ledger for Alex, do not auto-fix. 6, 7 and (partially) 4 are mechanical:
auto-fix and log.
