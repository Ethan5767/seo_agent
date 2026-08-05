# SPEC — Data-Gen Emitter (`pipeline/generate/`)

Status: **specification only. No code yet.**
Scope: the missing generation stage. Intake + gates exist and are proven; this
document is the behavioural contract for the stage that turns a classified team
dossier into (a) typed TS data entries in the client repo and (b) `docs/briefs/*.json`,
such that every existing gate passes **by construction**.

Authority order when this document and reality disagree:
1. The gate code in `pipeline/gates/` (proven, **must not be modified**).
2. The client repo's real TS types (`src/data/services.ts`) and renderer
   (`src/components/ServicePageRenderer.tsx`).
3. The prior art (`V2-Prototype/emitter-design.md`, `emit_page.py`, build-plan 05).
4. This spec.

This is the "Phase 2" that `emitter-design.md` deferred: *"Final output shape
re-targets the repo's real TS types in Phase 2."*

---

## 0. Contract at a glance

```
IN   pass-2 output for one page:
       blocks.json           classified dossier blocks (+ section class from TAXONOMY)
       verdict ledger        KEEP / TRIM / OPTIMIZE / DROP / BANK per block
       docs/client-config.yml (client facts, allow-lists, forbidden phrases)

OUT  1. one typed `ServicePage` entry appended to the client repo data file
        (src/data/location-pages.ts or services.ts) + its registry array row
     2. docs/briefs/<slug>.json                (schema §5 — gate S19 input)
     3. docs/audit-logs/<date>/pre-build-scrub.md   (proof file, §8)
     4. verdict-ledger additions for anything the emitter could not fix
        mechanically (curation queue)

EXIT  0 emitted clean
      1 emitted with curation flags — EVERYTHING SHIPPED (entry written, ledger
        has open items). Nothing was withheld.
      2 usage / dependency error
      9 refused to emit (a hard constraint could not be satisfied — §7)
     15 one or more pages HELD for curation — emitted what it could, the held
        pages did NOT ship (§7). NOT green.
```

Each outcome owns a **distinct** code so an orchestrator can branch on exit
status alone: `1` (shipped, flags attached) must never be confusable with `15`
(did not ship) or `9` (refused). Most severe wins: `9` > `15` > `1` > `0`.

CLI shape follows the codebase convention (argparse, `def main() -> int`,
`from pipeline.lib.common import load_config, client_profile, url_fits_topology`):

```
emit_page.py PROJECT_DIR --blocks path/to/blocks.json [--out-data src/data/location-pages.ts]
             [--briefs-dir docs/briefs] [--dry-run] [--proof-dir DIR]
```

**Absolute rule carried forward:** the emitter writes to the client working tree
only. It never commits, never pushes, never touches `pipeline/gates/`.

---

## 1. Validators V1–V6 — exactly as implemented in the prototype

Source: `V2-Prototype/scripts/emit_page.py`. These are the *writing/layout*
constraints, distinct from the repo gates (§4). Reproduce them **verbatim in
behaviour**; the prototype's numbers are the contract.

### V1 — Hero rule (`v_hero` + `hero_hook`)

A hero description fails if **any** of three independent conditions is true.
All three are checked; all failing conditions are reported (not short-circuited):

| Condition | Threshold | Measure |
|---|---|---|
| words | `len(desc.split()) > 25` | whitespace split, no stripping |
| sentences | `len(sentences(desc)) > 2` | `re.split(r"(?<=[.!?])\s+", text)`, empties dropped |
| characters | `len(desc) > 160` | raw `len()` on the cleaned string |

**Auto-fix — hero-hook extraction (`hero_hook`), MECHANICAL.** Greedy prefix
accumulation over sentences: a sentence joins the hook only while the candidate
join keeps `len(hook) < 2` sentences, `<= 160` chars, and `<= 25` words, **and**
nothing has yet been demoted (`not rest` — once demotion starts it never
resumes, so the hook is always a contiguous prefix). Everything else becomes
`rest`.

Degenerate case: if the very first sentence alone busts the budget, the hook
becomes that sentence truncated at its first clause boundary
(`re.split(r"[,;] ", first)[0]`, trailing `.` stripped then re-added) and
sentences `[1:]` become `rest`.

`rest` is **demoted to body copy** — it is never discarded. In the repo shape
(§3) the demoted remainder lands in the opening `editorial-split` section's
`lede`/`paragraphs`, not in `hero.description`.

Prototype evidence: raw team copy failed 24/24; hook extraction fixed 67/68
violations. Any residual post-extraction hero failure is a **hard refuse** (§7),
because a non-compliant hero is a known renderer overflow.

### V2 — metaTitle length (`v_meta_title`)

Effective length = `len(title.replace("&", "&amp;"))`. Fails at `> 56`.
The `&`-expansion is deliberate: an ampersand costs 5 characters once the SERP
title is HTML-escaped, which is how a "54-char" title silently truncated in the
post-mortem (1.12).

**Not auto-fixable — FLAG FOR CURATION.** Shortening a title is an editorial
decision (which qualifier to drop). The emitter emits the title as given and
opens a ledger item. Rationale: mechanical truncation produces titles that read
as broken, which is worse than a long one.

### V3 — Em-dash ban (`v_emdash`)

Pattern: `re.compile(r"—|---")`. Applied to every public-facing string
(headings, hero, body copy, labels, alt text, FAQ Q&A, brief fields).
Found in 24/24 team H2s.

**Auto-fix — MECHANICAL.** Replacement character is a **per-client config
value** (`", "` vs `" | "` vs `". "`, `emitter.emdash_replacement`, default
`", "`), which was the open question in `emitter-design.md`. The scrub must also
cover the HTML entity forms the built-HTML gate looks for (`&mdash;`, `&#8212;`,
`&#x2014;`) — emitting the entity form would pass a naive source check and fail
`em_dash_check.py` at build.

### V4 — Title Case headings (`v_title_case`)

Prototype logic: tokenize `[A-Za-z']+`; a token is bad when it starts lowercase
**and** (it is not in `SMALL_WORDS` **or** it is at index 0). `SMALL_WORDS =
{a, an, and, as, at, but, by, for, in, nc, of, on, or, the, to, vs, with}`.

**Auto-fix — MECHANICAL** (capitalize offenders that are not small-words, always
capitalize first token). **But see §4.4:** the repo gate `check_headings.py` runs
*lenient* by default and Acme sets no `headings:` block, so the shipped
requirement is weaker than V4. Emitting full Title Case satisfies both modes, so
V4 stays as the emitter's internal standard — never relax it to match the lenient
gate, because a client can flip `headings.strict_title_case: true` at any time
and every previously-emitted page must still pass.

Exemptions must match `check_headings.is_exempt`: tokens containing a digit,
all-caps acronyms (GAF, TPO), camelCase brands (iPhone), tokens with no leading
alpha. The prototype's regex-only tokenizer does not implement these; the
production emitter **must**, or it will "fix" `GAF` into `Gaf`.

### V5 — Mosaic / card-grid counts (`v_mosaic`)

Legal item counts for a card grid: **3, 4, 5, 6**. Zero is legal (section absent).
Anything else ships a visible hole in the renderer grid matrix.
Prototype applied it to `MATERIALS`, `WHY ACME`, `DAMAGE_TYPES`; 10 violations found.

**Not auto-fixable — FLAG FOR CURATION** (keep/trim is a judgment call).
`emitter-design.md` proposes auto-trimming the weakest item with a ledger entry
so Alex sees it in the briefing; this spec keeps that as **opt-in**
(`emitter.mosaic_autotrim: false` default). Default behaviour is: emit the
section, flag it, block on the ledger item.

Production scope widens: the count rule applies to every repo section type with
a card/step/item array — `types.cards`, `benefits.cards`, `repairs.cards`,
`materials.items`, `credential-feature.items`, `service-mosaic.cards`,
`process-steps.steps` (4 canonically), `checklist.items`, `breakdown.cards`.

### V6 — Alt-text stub

Every image slot must carry non-empty alt text (the operator's June-2026 build gate).
The prototype only asserted the requirement (`_altTextRequired: true`).

**STRUCTURAL — the emitter cannot emit an image field without its alt sibling.**
In the repo types the pairs are: `editorial-split.image`/`imageAlt`,
`credential-feature.image`/`imageAlt`, `service-mosaic.cards[].image`/`imageAlt`,
`before-after-feature.beforeImage`/`beforeAlt` + `afterImage`/`afterAlt`,
`gallery.images[].src`/`alt`, `projects-marquee.images[].src`/`alt`,
`project-spotlight.projects[].image`/`imageAlt`.
Alt text is generated from `{service} {work-type} in {City}, {ST}` + the client's
proprietary variable where available; it is public-facing copy and therefore also
passes V3/V4 and the forbidden sweep.

### Auto-fix vs curation summary

| Validator | Mechanism | Failure disposition |
|---|---|---|
| V1 hero | hero-hook extraction | AUTO; residual failure = refuse (exit 9) |
| V2 metaTitle | none | FLAG — ledger item, entry still emitted (exit 1) |
| V3 em-dash | config-driven character swap | AUTO (glyph + entity forms) |
| V4 Title Case | capitalization with exemption list | AUTO |
| V5 mosaic count | none (autotrim opt-in) | FLAG — ledger item (exit 1) |
| V6 alt text | required field, generated | STRUCTURAL; missing = refuse (exit 9) |

---

## 2. The 3-pass design and the core-body band

### 2.1 Passes

```
pass 1  EXTRACT   docx/md -> blocks (title, meta, URL, H1, hero para, sections)
                  Docling-validated, zero content loss. Regex scaffolding beat
                  a classifier (~100% vs 88.2%) — keep it mechanical.
pass 2  CLASSIFY  each block -> TAXONOMY class + core_body:bool (build-plan 05 §2)
                  + verdict (KEEP/TRIM/OPTIMIZE/DROP/BANK). Enum-constrained.
pass 3  EMIT      <- THIS SPEC. constraint-validate -> auto-fix the mechanical ->
                  flag the judgment calls -> write typed data + brief + proof.
```

The emitter is **pass 3 only**. It consumes a ledger; it does not re-classify.
If a block reaches the emitter without a verdict, the emitter refuses (exit 9) —
`ledger_complete` is a precondition, not something the emitter can paper over.

### 2.2 Core-body band (settled; do not re-litigate)

- `core_words ∈ [800, 1500]` — **HARD**, blocking under `coverage_method: curated-distill`.
- `~1200` is an **advisory sweet spot, not a target**. In-band but far from 1200
  raises `sweet_spot_drift` (advisory only, never blocks).
- `core_words` counts **CORE BODY sections only**, after distillation. The core
  set is closed and default-safe:
  `{INTRO, MATERIALS, COMPARISON, DAMAGE_TYPES, WHATS_INCLUDED, COST, STORM_INSURANCE}`.
  Every other class — including any unknown/new class — is STRUCTURED and is
  **never** silently counted.
- Excluded from the count by construction: hero, process, why-us, service-areas,
  warranty, cost-of-inaction, testimonials, reviews, FAQs, CTA, schema/JSON-LD.
- The count is **mechanical and re-verified** — never the model's self-reported
  integer. Counting rule is `V2-Prototype/distill-verify/word_count.py`:
  strip leading `#{1,6}` heading markers per line, strip `**`/`*` emphasis
  markers, split on whitespace, count non-empty tokens.
- Legacy `word-ratio` (0.70 whole-page) is **never** applied to a curated page.
  Acme currently sets `coverage_method: "builder-collapse"`; the emitter reads
  the method from config and must not assume curated-distill.
- Primary keyword ~4x across the core, evenly distributed. Flag if `<2` or `>6`.
  Advisory, surfaced for review, **never auto-edited**.
- Anti-invention: no number, stat, or capability may appear in the emitted entry
  that is absent from the source dossier. The full dossier stays banked, so every
  distillation is reversible.

### 2.3 Structured-body model (proven in `distill-verify/`)

Distilled core is **not** a prose blob. Each core section carries internal
structure so the renderer produces real hierarchy:

```jsonc
{
  "subheading": "Title Case string, renders as <h3>",
  "paragraphs": ["...", "..."],
  "items":    [{"leadin": "...", "text": "..."}],       // optional
  "callouts": [{"type": "stat", "value": "48 inches", "label": "..."},
               {"type": "pullquote", "text": "..."}]     // optional
}
```

plus page-level `related_links: [{anchor, target, source_section, intent}]`.

Two load-bearing consequences:
1. **Internal links are template metadata, not prose.** Link intent is preserved
   without polluting the body — and it is what feeds the inbound-link surface
   `orphan_check.py` measures.
2. **Stats become scannable nodes** (`stat-strip.stats`, `editorial-split.pullQuote`,
   `before-after-feature.meta`), which is what makes the page liftable by an
   answer engine rather than a wall of text.

Mapping to the repo types: `subheading` → a section `title` (h2) or an item
`title` (h3); `paragraphs` → `editorial-split.paragraphs` / `content-block.content`;
`callouts[type=stat]` → `stat-strip.stats[{num,label}]`;
`callouts[type=pullquote]` → `editorial-split.pullQuote` or a
`testimonial-pullquote` section; `items` → `credential-feature.items` /
`checklist.items`.

---

## 3. Target output shape — the client repo's REAL types

Authority: `acme-roofing-site/src/data/services.ts`. **Do not invent a schema.**

```ts
export interface ServicePage {
  slug: string;                 // 'charlotte-nc' | 'charlotte-nc/matthews'  (NO leading/trailing slash)
  title: string;
  metaTitle: string;            // <= 56 effective chars (V2)
  metaDescription: string;
  lastUpdated?: string;         // 'YYYY-MM-DD'
  hero: {
    badgeIcon: string; badgeText: string;
    title: string;              // may contain <span>…</span>
    description: string;        // <= 25w AND <= 2 sentences AND <= 160ch (V1)
    bgImage?: string;
    buttons?: Array<{ text; url; className; iconBefore?; iconAfter? }>;
    features?: string[];
  };
  markdownContent?: string;     // LEGACY — see §3.2. DO NOT EMIT.
  sections: ServiceSection[];
  faqs?: Array<{ question: string; answer: string }>;
}
```

`ServiceSection` is a 31-member discriminated union on `type`. Full field lists
live in `services.ts` lines 30–395; the emitter must import/mirror them, not
guess. The types the emitter is expected to produce for a location page:
`editorial-split`, `stat-strip`, `credential-feature`, `service-mosaic`,
`before-after-feature`, `testimonial-pullquote`, `project-spotlight`,
`closing-cta-editorial`, plus legacy `types` / `benefits` / `content-block` /
`process-steps` / `service-areas` / `related-services` where a builder is reused.

### 3.1 Renderer facts that change what the emitter must emit

These were verified in `ServicePageRenderer.tsx` and are non-obvious:

1. **`section.title` renders as `<h2 class="section-title">`.** Every gate that
   reads `<h2>` (capsule §20, check-headings) is reading a section `title`.
2. **`stat-strip.headline` renders as `<h3>`, not `<h2>`.** It cannot carry the
   capsule's interrogative H2.
3. **FAQ questions render inside `<span>` in a `<button class="faq-question">`,
   NOT as a heading** (`FAQSection.tsx` L39–43). **Therefore FAQs can never
   satisfy `capsule.interrogative_h2`.** The interrogative H2 must come from a
   `section.title`.
4. **`editorial-split` renders `<h2>` immediately followed by
   `<p class="editorial-lede">`.** This is the only clean h2→p adjacency in the
   renderer, which makes `editorial-split` the **designated capsule carrier**:
   `title` = the interrogative H2, `lede` = the answer-first block.
5. **`transformLocationSections()` (L196–235) silently REWRITES a location
   page's sections** when the page uses only legacy types — it invents its own
   `editorial-split` with a hardcoded title
   (`"${city} weather is brutal. <em>Your roof should not be the weak link.</em>"`)
   and picks its own photos. **What the emitter emitted is then not what the
   gates see.** Escape hatch: the transform passes through untouched if the page
   contains **at least one** of the "new" types. The emitter MUST therefore emit
   at least one new-type section (it emits `editorial-split` anyway per #4), so
   its output is deterministic end-to-end.
6. `renderEm()` allows `<em>` / `<span>` inside titles. Gates strip tags before
   checking, so markup is safe — but the *stripped* text is what must satisfy
   Title Case, em-dash, and forbidden-phrase rules.

### 3.2 `markdownContent` is dead — do not emit it

`ServicePageRenderer.tsx` L22–26: "the `markdownContent` field on data records is
now **ignored by the renderer**." Historic entries carry hundreds of lines of raw
DOCX in that field (it is most of the 21,844 lines of `location-pages.ts`). It is
invisible to every built-HTML gate but **fully visible to
`forbidden_sweep.py source`**, which scans `src/data/*.ts` raw. Emitting the raw
dossier there would red-gate the legal sweep on content that never ships.
The dossier belongs in the **content bank**, not in the TS file.

### 3.3 Registry / linked-by-construction

An entry is not "emitted" until it is in the registry array. For Acme that is
`export const allLocationPages: ServicePage[]` at `location-pages.ts:21764`, which
feeds sitemap + hub + footer generation. Appending the `const` without appending
the registry row produces exactly the orphan bug `orphan_check.py` exists to
catch: in the sitemap, linked from nowhere. **Both writes are one atomic step.**

### 3.4 Emission mechanics

- Append-only. Never rewrite or reformat existing entries (the file is 21,844
  lines of hand-tuned data; a formatter diff is unreviewable).
- Match surrounding style exactly: 2-space indent, single quotes, trailing
  commas, backticks only where a string contains an apostrophe.
- Escape apostrophes in single-quoted strings; prefer `"…"` when the string
  contains `'` and no `"`.
- `slug` has no leading or trailing slash; the route is `/{slug}/`.
- `lastUpdated` = emission date, ISO.
- Idempotent: re-emitting the same page replaces its own block between sentinel
  boundaries, never duplicating the registry row.
- `--dry-run` prints the entry + brief and writes nothing.

---

## 4. Gate contracts the emitted output must satisfy

Read from the real gate code. Exit codes are the gates', not the emitter's.

### 4.1 `capsule_check.py` — §20, exit 6 (built HTML)

Runs on every page whose route `url_fits_topology(route, topology)` or starts
with `/blog/`; `DEFAULT_EXCLUDE` drops `/`, `/contact/`, `/about/`, `/privacy*`,
`/terms*`, `/thank-you/`, `/404/`, `/500/`, `/_not-found/`, `/blog/`.

| Sub-check | Requirement |
|---|---|
| `interrogative_h2` | ≥1 `<h2>` whose text ends with `?` **or** matches `^(how\|what\|why\|when\|where\|which\|who\|do\|does\|is\|are\|can\|should\|will)\b` |
| `answer_first` | the first `<p>` or `<li>` after that H2 (up to the next heading): non-empty, **40 ≤ words ≤ 80**, **≤3 sentences** (`[.!?]+` count) |
| `tldr_on_long` | if whole-page stripped body words > `content.long_page_threshold` (default **1200**), the page text must match `tl;?dr\|key takeaways\|in short\|the short answer\|bottom line` |

Notes that matter:
- `answer_first` is auto-passed when no interrogative H2 exists (the H2 failure
  already blocks the page) — so a missing H2 hides the answer problem. The
  emitter must satisfy both independently.
- `body_words` for the TL;DR trigger is the **whole page**, including structured
  components — not `core_words`. A page with an 900-word core will still trip the
  1200 threshold once chrome + FAQs are counted. **Assume every emitted service
  page is "long" and always emit the TL;DR node.**

### 4.2 `noncommodity_check.py` — §21, exit 7 (built HTML), exit 4 on empty allow-list

| Sub-check | Requirement |
|---|---|
| `no_proprietary_token` | ≥ `--min-tokens` (default 1) allow-list tokens present in the page text. Word tokens matched with `\b…\b` case-insensitive; punctuated tokens (phone numbers) as literal substrings |
| `duplicate_of_sibling` | max 5-gram overlap vs every other selected page ≤ threshold. `auto` → **0.90 if `'hub-spoke' in topology`, else 0.60** |

Allow-list = `required_phrases` ∪ `nap.city` ∪ `nap.street` ∪ `service_areas[]` ∪
`service_area.primary_city` ∪ `service_area.cities[]` ∪ `primary_metro` ∪
`business.crew_names[]` ∪ `owner_name`. Empty ⇒ exit 4.

Acme's resolved allow-list: `GAF Master Elite`, `(555) 555-0100`, `Licensed`,
`Matthews, NC 28105` (+`Matthews`), the six `service_areas` entries, `Charlotte`.

**⚠ Load-bearing finding.** Acme sets `topology: franchise`. `'hub-spoke' not in
'franchise'` ⇒ the auto threshold is **0.60, not 0.90** — the strict one — even
though the site is a programmatic hub-and-spoke with four shared builder sections
(`certificationsSection`, `whyAcmeSection`, `financingSection`,
`processSection`) rendered near-identically on every spoke. Those builders alone
are several hundred shared words of 5-gram-identical text. The emitter cannot fix
this by writing better prose alone; it must be treated as a **budget**:
- overlap is computed as `|A∩B| / |A|`, so the denominator is the emitting page's
  own 5-gram count. **More unique text lowers the ratio.** A page whose unique
  core is small relative to shared chrome fails structurally.
- the emitter must **measure projected sibling overlap before writing** (§6) and
  refuse rather than ship a page that will red-gate the suite.
- if measurement shows the shared-builder floor alone exceeds 0.60, that is a
  **config/architecture escalation** (set `--overlap-threshold 0.90` explicitly,
  or vary the builders per city), not something the emitter may silently absorb.
  Report it; do not tune the gate.

### 4.3 `brief_fanout_check.py` — §19, exit 9 (pre-draft, JSON)

Reads `PROJECT/docs/briefs/**/*.json`. A file may hold one brief object **or** a
list of briefs. **The directory does not exist yet in `acme-roofing-site` — the
gate currently exits 0 with a `[NOTE] blocked-on-input`. The emitter is what
unblocks it.** Full schema in §5.

### 4.4 `check_headings.py` — exit 1 (built HTML)

Scans `<h1>`–`<h6>` in all `out/**/*.html`, script/style blanked line-preserving,
entities unescaped.
- **Default = LENIENT**: fails only when the first significant token starts
  lowercase, or the heading is entirely lowercase.
- **`--strict` / `headings.strict_title_case: true`**: every non-exempt,
  non-stopword token must be capitalized; stopwords may be lowercase only
  strictly *between* first and last token.
- Exempt in both modes: tokens with a digit, all-caps acronyms, camelCase,
  tokens with no leading alpha.
- Acme has **no `headings:` block** ⇒ lenient today. Emit strict-clean anyway (§1 V4).

### 4.5 `forbidden_sweep.py` — exit 3 on hits, exit 4 on empty ledger

Two modes; the emitter must survive both.
- `source`: scans `src/data/**/*.ts|tsx` with the bare-word form of each pattern.
  Skips lines starting `import`/`from`/`//`/`*`/`/*`; skips heading-anchored
  patterns; honours slug-exemptions and same-line disclosure/negation context.
  **This mode reads `markdownContent` — see §3.2.**
- `built`: scans `out/**/*.html` with the full patterns, script/style blanked.

Patterns = union of config `forbidden_phrases[]` and `docs/banned-phrases.txt`
(the latter gets an implicit `(?i)`).
Acme actives include `\$[0-9]` (**no dollar amounts anywhere** — market-context
figures must be written as words: "high four figures") and `—`.

### 4.6 Other gates the emitted entry can break

| Gate | Exit | Emitter obligation |
|---|---|---|
| `em_dash_check.py` | 1 | no `—`, `&mdash;`, `&#8212;`, `&#x2014;` outside script/style |
| `fingerprint_check.py` | 8 | zero zero-width/bidi/tag chars, no `data-generated-by`. **This gate does NOT strip script/style and reads raw bytes.** Emitted strings must be ASCII-clean; strip U+200B/200E/FEFF-non-leading/E0000-E007F before writing |
| `orphan_check.py` | 1 | every sitemap URL needs ≥1 inbound `<a href>` ⇒ registry row + `related-services`/`service-mosaic` cross-links (§3.3) |
| `pages_are_data_check.py` | 1 | never emit a bespoke `page.tsx`; data rows only. Dynamic routes always pass |
| `image_budget_check.py` | 1 | reference only existing in-repo images already under budget (hero 200 KB / content 100 KB / thumb 30 KB). Never emit a path to a file that is not on disk |
| `lcp_hygiene_check.py` | 1 | no `loading="lazy"` on a preloaded/`fetchpriority=high` image; raster `<img>` needs width/height (`src/data/image-dimensions.json` exists — reuse it) |
| `llms_sales_purge.py` | 1 | no CTA phrasing in anything destined for `llms.txt` |
| `parity_check.py` | — | sitemap ↔ llms.txt URL parity: a new page must reach both |

---

## 5. `docs/briefs/*.json` — exact schema (gate S19 input)

Derived field-by-field from `brief_fanout_check.validate_brief()`. One file per
page, `docs/briefs/<slug-with-dashes>.json`; a list of objects is also accepted.

```jsonc
{
  // 1. fanout — REQUIRED, must be a list. Distinct count is case-insensitive
  //    (strip + lower, empties/non-strings dropped) and must be >= min_fanout
  //    (config brief.min_fanout, DEFAULT 6).
  "fanout": [
    "gutter installation cost", "seamless vs sectional gutters",
    "6-inch vs 5-inch sizing", "downspout sizing", "gutter guards",
    "Charlotte rainfall load"
  ],

  // 2. capsule — REQUIRED object with all three keys.
  "capsule": {
    // must be a non-empty string ENDING IN '?' (gate is stricter than
    // capsule_check.py, which also accepts an interrogative lead word).
    "interrogative_h2": "How Much Rainfall Do Charlotte Gutters Have To Handle?",

    // non-empty; >= brief.min_answer_words (DEFAULT 8) by this gate.
    // *** EMIT 40-80 WORDS AND <= 3 SENTENCES — see the divergence note below. ***
    "answer_first": "Charlotte averages 48 inches of rain a year...",

    // non-empty string; content unconstrained by the gate.
    "tldr": "Six-inch K-style aluminum with 3x4 downspouts is the right default..."
  },

  // 3. semantic_triples — REQUIRED, non-empty list, >= 1 WELL-FORMED entry.
  //    Well-formed = an object with non-empty subject/predicate/object, OR a
  //    3-element list/tuple of non-empty values. Malformed entries are ignored,
  //    not errors — but at least one must be well-formed.
  "semantic_triples": [
    { "subject": "Acme Roofing", "predicate": "installs",
      "object": "seamless K-style aluminum gutters in Charlotte, NC" }
  ],

  // 4. proprietary_variable — REQUIRED non-empty string. If an allow-list is
  //    configured (brief.proprietary_variables | brief.proprietary_variable_allowlist
  //    | top-level proprietary_variables | --allowlist), the value's .lower()
  //    must be a member. If NO allow-list exists the membership check is SKIPPED
  //    with a WARN (presence still required).
  //    NOTE: this is a DIFFERENT allow-list from noncommodity_check's §21 list.
  //    Acme configures neither `brief:` block today -> currently WARN-only.
  "proprietary_variable": "neighborhoods",

  // 5. intent — REQUIRED, compared .strip().lower() against the enum
  //    (config brief.intent_enum, DEFAULT below).
  "intent": "commercial"   // informational | commercial | transactional | navigational
}
```

Validation semantics to honour:
- A missing field is itself a reported failure — never `null`, never omitted.
- The gate reports **all** failures per brief, then exits 9 if any exist.
- Invalid JSON is a per-file failure, not a crash.
- Extra keys are ignored by the gate. The emitter SHOULD carry provenance
  (`page_slug`, `route`, `emitted_at`, `core_words`, `coverage_method`,
  `source_dossier`) so the brief is auditable — but nothing extra may be
  required for validity.

**⚠ Cross-gate divergence (real, and a trap).** `brief_fanout_check` accepts an
`answer_first` of **≥8 words**; `capsule_check` requires the rendered answer block
to be **40–80 words and ≤3 sentences**. A brief that passes S19 at 8 words
produces a page that fails S20 at build. **Do not "fix" either gate.** The
emitter resolves it by authoring `capsule.answer_first` to the *stricter* rule
(40–80 words, ≤3 sentences) and then emitting that exact string as the
`editorial-split.lede` under the interrogative `title`. One string, two gates,
satisfied by construction.

---

## 6. Produce-by-construction checklist

For each gate: what the emitter does **before writing** so the output passes by
construction rather than being audited after. Every row is a pre-write assertion;
a failed assertion is a refuse (§7) or a ledger flag, never a silent emit.

| # | Gate (exit) | Emitter obligation — enforced BEFORE the write |
|---|---|---|
| C1 | `capsule_check` `interrogative_h2` (6) | Emit exactly one `editorial-split` whose `title` is the brief's `capsule.interrogative_h2`, ending in `?`. Assert the rendered-text form (tags stripped) still ends in `?`. |
| C2 | `capsule_check` `answer_first` (6) | That section's `lede` **is** `capsule.answer_first`, pre-verified at 40–80 words and ≤3 sentences with the gate's own counters (`len(split())`, `re.findall(r"[.!?]+")`). Assert no `<p>`/`<li>` can render between the h2 and the lede — guaranteed by the `editorial-split` JSX. |
| C3 | `capsule_check` `tldr_on_long` (6) | Always emit a TL;DR node (a `content-block`/`stat-strip` eyebrow or `credential-feature.intro` containing a literal `TL;DR` or `Key Takeaways`). Never gamble on the 1200-word whole-page threshold. |
| C4 | `capsule_check` selection | Assert the target route passes `common.url_fits_topology(route, cfg.topology)` and is not in `DEFAULT_EXCLUDE`. If it is excluded, the capsule requirements do not apply — record that in the proof file rather than emitting dead structure. |
| C5 | `noncommodity_check` `no_proprietary_token` (7) | Build the §21 allow-list with the gate's own `build_allow_list` + `compile_token_matchers` logic, run it against the emitter's own concatenated page text, and assert ≥1 (configurably ≥2) hit **before** writing. Seed the phone number and `GAF Master Elite` into hero features/CTAs as a floor, and a genuinely page-unique fact (neighborhood, street, project number) into the core. |
| C6 | `noncommodity_check` `duplicate_of_sibling` (7) | Compute `five_grams()` of the projected page text and its max overlap against every already-emitted sibling using the gate's exact formula (`|A∩B|/|A|`) and the **resolved** threshold (0.90 only if `'hub-spoke' in topology`, else **0.60**). Over threshold ⇒ do not write; report the worst sibling + overlap and route to curation. Re-check the whole set after each emit — adding page N can push page N−1 over. |
| C7 | `brief_fanout_check` fanout (9) | ≥6 case-insensitively distinct fanout terms, drawn from the dossier's real sub-intents, deduped with the gate's `_distinct_ci` logic before writing. |
| C8 | `brief_fanout_check` capsule (9) | Author `answer_first` to the **stricter** capsule rule (40–80w) so S19 and S20 agree (§5). Assert `interrogative_h2` ends in `?` (S19 does not accept a lead word). |
| C9 | `brief_fanout_check` triples (9) | ≥1 triple with all three parts non-empty; subject = the client entity, object grounded in a dossier fact (anti-invention applies). |
| C10 | `brief_fanout_check` proprietary/intent (9) | `proprietary_variable` non-empty and, when `brief.proprietary_variables` exists, a member (lowercased). `intent` from the enum. When no `brief:` block exists (Acme today) still emit valid values — the gate only WARNs, but the config can appear at any time. |
| C11 | `check_headings` (1) | Run V4 with `check_headings.is_exempt` semantics over every string that reaches an `<h2>`/`<h3>` — section `title`s, card/step/item `title`s, `stat-strip.headline`, `faqs[].question` — on the **tag-stripped, entity-unescaped** text. Emit strict-Title-Case-clean regardless of the client's current mode. |
| C12 | `em_dash_check` (1) | V3 scrub over every emitted string, glyph **and** entity forms, with the per-client replacement character. Applied last, after all other text transforms, so no fix reintroduces one. |
| C13 | `forbidden_sweep source` (3) | Compile the union of `forbidden_phrases[]` + `docs/banned-phrases.txt` and run the gate's own `derive_word_pattern` matching over the exact TS text about to be appended. Hard blockers for Acme: `\$[0-9]` (write "high four figures", never `$8,000`) and `—`. Never emit `markdownContent` (§3.2). |
| C14 | `forbidden_sweep built` (3) | Also run the full angle-bracket patterns against a rendered projection of the entry, so heading-anchored rules (skipped in source mode) are caught pre-build. |
| C15 | `fingerprint_check` (8) | Normalize every emitted string: reject/strip U+200B/C/D, U+2060–2064, U+00AD, U+180E, non-leading U+FEFF, U+200E/F, U+061C, U+202A–E, U+2066–9, U+E0000–E007F. No `data-generated-by` or tool markers. This gate reads raw bytes and does not skip script/style. |
| C16 | `orphan_check` (1) | Append the registry row (`allLocationPages`) in the same atomic write as the entry, and emit ≥1 inbound link from a sibling/hub via `related-services` / `service-mosaic.cards[].href` / the structured model's `related_links`. Assert the new route is reachable from at least one already-registered page. |
| C17 | `pages_are_data_check` (1) | Emit **only** data rows. Never create or grow a `page.tsx`. Assert no file under `src/app/` is touched. |
| C18 | `image_budget_check` (1) | Every emitted image path must exist on disk and already sit under its tier ceiling (hero 200 KB / content 100 KB / thumb 30 KB) — stat the file before writing the path. Never invent an image reference. |
| C19 | `lcp_hygiene_check` (1) | Pair every raster image with width/height from `src/data/image-dimensions.json`; never emit a lazy attribute on an image the page declares as the LCP candidate. |
| C20 | `llms_sales_purge` (1) | Keep CTA phrasing (`call now`, `book`, `schedule today`, `sign up`, …) out of any field that flows to `llms.txt`. CTA copy belongs in `hero.buttons` / `closing-cta-editorial`, which do not. |
| C21 | V1 hero (renderer) | Hero-hook extraction runs before write; assert the final `hero.description` satisfies all three limits; demoted remainder lands in the opening `editorial-split`. Residual failure ⇒ refuse. |
| C22 | V2 metaTitle | Assert `len(metaTitle.replace('&','&amp;')) <= 56`. Over ⇒ emit + ledger flag (curation), exit 1. |
| C23 | V5 mosaic counts | Assert every card/step/item array length ∈ {3,4,5,6} (or 0). Violation ⇒ emit + ledger flag (curation), exit 1, unless `emitter.mosaic_autotrim` is on. |
| C24 | V6 alt text | Structurally impossible to emit an image field without its alt sibling; alt strings pass C11/C12/C13. Missing ⇒ refuse. |
| C25 | Core-body band | Mechanically recount `core_words` (§2.2 rules, `word_count.py` semantics) over CORE-BODY sections only, post-distill. Out of [800,1500] under `curated-distill` ⇒ refuse. In-band-but-far-from-1200 ⇒ advisory note only. |
| C26 | Ledger completeness | Assert every dossier block carries a verdict in {KEEP,TRIM,OPTIMIZE,DROP,BANK} before emitting. Assert the >40% dropped/banked circuit breaker has not tripped un-acknowledged. |
| C27 | Anti-invention | Every number/stat/claim in the entry must be traceable to a dossier block. Unsourced figure ⇒ refuse. |
| C28 | Renderer transform (§3.1 #5) | Assert the emitted `sections[]` contains ≥1 "new" type so `transformLocationSections` passes it through untouched. Otherwise the renderer rewrites the page and every preceding assertion is void. |
| C29 | Config reality | Read `coverage_method`, `topology`, `headings`, `brief`, `content.long_page_threshold`, `performance` from `docs/client-config.yml` via `common.load_config`. Never hardcode a client's values; never assume `curated-distill` (Acme is `builder-collapse` today). |

---

## 7. Refuse-to-emit conditions (exit 9)

The emitter writes nothing when any of these hold. A refusal is a **success**
(the failure was found before it entered the repo) and must name the exact
constraint and the offending text:

- residual V1 hero violation after hook extraction (C21)
- an image field without alt text, or an image path not on disk (C24, C18)
- projected sibling 5-gram overlap over the resolved threshold (C6)
- `core_words` out of [800,1500] under `curated-distill` (C25)
- a dossier block without a verdict, or an un-acknowledged >40% drop (C26)
- an unsourced number/stat/claim (C27)
- a forbidden-phrase hit that survives the mechanical scrub (C13/C14)
- no "new"-type section, i.e. the renderer would rewrite the output (C28)
- the brief would fail `validate_brief` (C7–C10)

### Held for curation (exit 15) — distinct from both 1 and 9

A CURATE finding is a quality decision a human must make (a hero that cannot be
reduced mechanically, an over-length `metaTitle`, missing alt text, a missing
capsule node). The page is **HELD**: it does *not* ship, but it does not stop any
sibling emitting, and it lands in `docs/briefs/_curation.md` with the offending
text and a concrete proposed fix.

A held page exits **15**, never 1. `1` means *everything shipped* with warn flags
attached; `15` means *the emitter emitted what it could and N pages did not
ship*. An orchestrator that cannot tell those apart mis-reports the cycle
outcome — the same defect class as the retired 3-vs-9 refusal collision. Codes
1–10 are the gate registry's, 11–14 are `pipeline/audit/preflight.py`'s, so 15 is
the first free code in the fleet.

Warn flags (exit 1, entry still written, nothing withheld): V2 metaTitle over 56,
V5 mosaic count, keyword frequency outside ~2–6, `sweet_spot_drift`, S21
allow-list membership WARN.

---

## 8. Proof file

No proof file = the gate did not happen. Every run writes
`docs/audit-logs/<date>/pre-build-scrub.md` in the prototype's proof-file style
(`V2-Prototype/results/pre-build-scrub.md`): one row per page with issues-pre,
issues-post, and the remaining top issues, plus totals by issue type. Production
additions: `coverage_method` in force, mechanical `core_words`, the per-section
core/structured split, the projected sibling-overlap number and threshold, the
allow-list tokens matched, and every refusal with its reason.

---

## 9. Open items (carried from `emitter-design.md` §"Phase 2 Asks", now answered or escalated)

| Ask | Status |
|---|---|
| Real TS interfaces | **ANSWERED** — `services.ts` `ServicePage` + 31-member `ServiceSection` union (§3) |
| Unified data array shape | **ANSWERED** — `allLocationPages: ServicePage[]`, `location-pages.ts:21764` (§3.3) |
| `## State:` marker for multi-state clients | **OPEN** — Acme is `single-site-multi-state`, NC/SC/VA/WV; slug convention `city-state`. Needs a rule for which state's data a page inherits |
| Legally-untrimmable block class → verdict ledger | **OPEN** — insurance/claims language is unguarded on Acme today; needs a `LEGAL_LOCKED` verdict that forbids TRIM/DROP |
| Em-dash replacement char | **ANSWERED** — per-client `emitter.emdash_replacement`, default `", "` |
| Mosaic auto-trim vs surface | **ANSWERED** — surface by default; `emitter.mosaic_autotrim` opt-in |
| S21 overlap threshold vs `topology: franchise` | **ESCALATE** — resolves to the strict 0.60 for Acme while shared builders emit hundreds of identical 5-grams. Config/architecture decision, not an emitter fix (§4.2) |
| S19/S20 `answer_first` word-count divergence | **ANSWERED** — author to the stricter 40–80w rule (§5) |
| `brief:` block absent from Acme config | **OPEN** — `min_fanout`, `intent_enum`, `proprietary_variables` all defaulting; the allow-list check is WARN-only until seeded |
