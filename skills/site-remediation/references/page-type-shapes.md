# Page Type Shapes

Adapted from `skills/seo-content-brief/references/page-type-templates.md` in
[AgricIDaniel/claude-seo](https://github.com/AgricIDaniel/claude-seo) (MIT,
© 2026 agricidaniel), rewritten for the remediation rail: the competitive-brief
framing is gone, because at remediation time there is no SERP scrape and no
competitor set — there is one measured finding and a tier.

**Read this for whole-page work: writing a new page at T2, or clearing a
`thin_content` finding at any tier.** If you are fixing a title, a meta
description or an alt text, this file is not for you — §2 of the skill still
holds, the smallest diff that clears the finding is the correct diff.

**Expanding a thin page is not the same job as writing a new one.** The page
exists, it has a shape already, and §2 of the skill still binds: expand what is
thin, do not restructure what is not. Use the matching table below to find the
section this page is *missing* — that is where the words are owed — rather than
rebuilding it to match the table row for row.

The tables below give **section shape only**. Everything a gate actually
enforces is in the two blocks that come first, stated once, so there is one
place to keep true.

---

## 1. What the gates measure on a new page

Verified against the gate source, not from memory. If this section and
`pipeline/gates/` ever disagree, the gates win and this file is the bug.

### The capsule — `capsule_check`

Applies to **every route that fits the client's `topology`, plus `/blog/*`**
(`capsule_check.py:106-122`). Under `hub-spoke` that is service pages, category
hubs, location pages and case studies — not just blog posts. Routes in
`DEFAULT_EXCLUDE` (`/`, `/about/`, `/contact/`, `/blog/` itself, legal pages)
are exempt.

Two checks, and a new page cannot baseline out of either — a baseline records
findings that already exist, and every finding on a route you just created is
new:

1. **`interrogative_h2`** — the page needs at least one `<h2>` whose text either
   ends in `?` or begins with one of: *how, what, why, when, where, which, who,
   do, does, is, are, can, should, will* (`capsule_check.py:72-73, 126-131`).
2. **`answer_first`** — the **first `<p>` or `<li>` after that H2**, up to the
   next heading, must be **40–80 words and at most 3 sentences**
   (`capsule_check.py:134-166`).

Read that band carefully, because it is the trap in this whole file. It measures
one block, not the section. A section may be 300 words; its **opening paragraph**
must land in 40–80. Write the answer as its own short paragraph, then continue in
the next one. And do not open the capsule section with a bulleted list — the
regex matches `<li>` too, so the first bullet becomes the measured block and a
six-word bullet fails.

On a client with no `topology` key, `url_fits_topology` returns `False` for
everything and this gate selects zero pages and prints PASS
(`common.py:462-464`). That is not permission to skip the capsule; it is the
gate being unable to see the page.

### Sibling differentiation — `noncommodity_check`

Two checks per page (`noncommodity_check.py:249-266`):

1. **`no_proprietary_token`** — at least one allow-list token in the page text.
   The list is built from `nap.city`, `service_areas`, `service_area.cities`
   (`:129-154`), so **naming the city satisfies it**. It is a floor, not a
   differentiation test.
2. **`duplicate_of_sibling`** — whole-page 5-gram shingle overlap against every
   sibling must be **≤ 0.60, or ≤ 0.90 when `topology` contains `hub-spoke`**
   (`:211-212`).

So the gate is loose: on a hub-spoke client a location page can be 89 percent
identical to its sibling and pass. **The house standard is stricter than the
gate and you are held to the house standard** — if a paragraph about Charleston
would also be true of Columbia, it is a template, whatever the shingle score
says. Concrete local material is what makes it not one: a named suburb, a permit
office, a soil or storm condition, a drive time.

### Schema — `measure.py`, not a gate

`measure.py:82-91` makes exactly three assertions, and all three fire on **every
URL unconditionally**:

- the type named in the client's `schema_type` (default `LocalBusiness`) —
  `health.schema_business_missing`
- `BreadcrumbList` — `health.schema_breadcrumb_missing`
- `FAQPage` — `health.schema_faq_missing`, **which is B-022**

So a new page of any kind carries the configured business type **and**
`BreadcrumbList`. This is not conditional on the page being location-specific.
Any other type — `Service`, `Article`, `WebPage` — is a reasonable addition that
**nothing measures**, so add it if it is accurate and never at the cost of the
two that are measured.

**B-022:** Google retired FAQ rich results on 2026-05-07. `FAQPage` is still
valid Schema.org and harmless to carry, but it can no longer earn a search
feature, so do not add it to a new page for that reason. `measure.py:88-89`
still emits `health.schema_faq_missing`, so it can reach you **as a work item on
any URL**. If it does, reply `NO CHANGE — health.schema_faq_missing is B-022,
the feature it targets was retired 2026-05-07`. Do not add the markup to clear
it, and do not report `FIXED`.

### Wiring — `tier_check` and `parity_check`

**No gate checks that a hub links to all of its children.** `orphan_check` walks
the *sitemap* and asserts each URL has ≥1 inbound `<a href>` from anywhere in
the built tree, and **self-links from global nav or footer count**
(`orphan_check.py:22-28, 185-205`). A hub that omits every child still passes so
long as the site has a nav. Enumerating the siblings is entirely on you.

The gate that catches an unwired new page is **`parity_check`** — built routes
and sitemap entries must match as sets. And `content.registry` is a
**`tier_check`** concept: `common.py:394-400` lists the registry paths a T2 agent
is *permitted to modify*. Nothing asserts you actually modified them. Wiring the
page in is your job, checked downstream, not a gate that will remind you.

### Headings — `check_headings`

Lenient by default (first significant word capitalized), full Title Case when a
client sets `headings.strict_title_case: true` (`check_headings.py:21-26`).
**Write full Title Case always** — §6 of the skill states it flatly, and it costs
nothing to be right on both settings. The section labels in the tables below are
written that way; use them as headings verbatim if they fit.

---

## 2. The sections where a claim gets invented

The tables tell you which sections exist. They do not tell you what may go
inside, and four rows are where an agent loses the PR:

| Section | What gets invented there |
|---|---|
| Why Choose Us / differentiators | "licensed and insured", "family owned 30 years", "award-winning" |
| Outcomes, Results, social proof | a star rating, a review count, a percentage, a case-study figure |
| Team, credentials, awards | a certification, a licence number, a named award |
| Reviews, testimonials | a quote no customer ever said |

Everything in those sections must trace to `docs/client-config.yml`, the work
item's `evidence`, text already on the page, or an explicit `http(s)://` /
`source:` citation on the line — those four are the only sources
`claim_provenance_check` accepts (`claim_provenance_check.py:20-31`).

**A section with no sourced material is a section you leave out.** Dropping "Why
Choose Us" from a service page costs nothing.

Note what the gate does and does not catch, so you know where you are on your
own: its patterns are **numeric** (`claim_provenance_check.py:70-80`) — ratings,
review counts, year-counts, `since 19xx`, licence numbers *with digits*,
warranty terms, money, percentages. Bare "licensed and insured" has no digit and
**this gate will not stop you writing it**. It is still forbidden by §1 of the
skill. The gate is a floor under the rule, not the rule.

Word counts below are targets for a section that has something to say, never a
quota. Padding to hit them is the precise failure mode `thin_content` exists to
surface.

---

## 3. Service Page

Converts a visitor into an enquiry.

| Section | Purpose | Format |
|---|---|---|
| What [Service] Is | Define it plainly | **The capsule.** H2 as written, opening paragraph 40–80 words, detail in the paragraphs after |
| Who Needs It | Let the reader self-qualify | Bulleted scenarios |
| How It Works | Remove friction, set expectations | Numbered steps |
| What It Costs | The question everyone has | Table or honest range; omit entirely if config gives you no numbers |
| Outcomes | Prove it works | Only from config or evidence |
| Why Choose [Client] | Differentiate | Only from config `usp` / `trust_signals` |
| Common Questions | Long-tail and PAA | 5–8 questions, ~40–60 words each |
| Get a Quote | Convert | One action, config `nap` phone verbatim |

**Primary query:** H1, first 100 words, one H2, URL slug, title tag.

## 4. Location Page

Ranks for `[service] [city]`. The shape most at risk of becoming a template.

| Section | Purpose | Format |
|---|---|---|
| What We Do in [City] | Local relevance | **The capsule.** 40–80 word opener, city named naturally |
| Areas We Serve | Hyper-local signal | Real suburbs, landmarks, jurisdictions |
| Why Local Matters Here | Justify the page existing | 1–2 paragraphs, specific to this city |
| Our Team in [City] | Trust | Only if config names local staff |
| What [City] Customers Say | Trust | Only from config |
| Common Questions in [City] | Local variations | 5 questions that differ per city |
| Call Our [City] Office | Convert | Local phone from config `nap` |

Every section must say something true of this city and false of its siblings —
see §1 on why the gate's 0.90 threshold does not let you off this.

## 5. Blog Post

Ranks for an informational query, routes the reader to a service page.

| Section | Purpose | Format |
|---|---|---|
| [The question, as an H2] | Win the capsule | **The capsule.** H2 ending in `?`, then a 40–80 word answer paragraph |
| Context | Set the scene | 1–2 paragraphs |
| 3–5 subtopic H2s | The actual depth | Prose, lists, tables as the material demands |
| Common Mistakes | Where the value usually is | Numbered, each with the reason |
| Common Questions | Long-tail | ~5 questions |
| CTA to the relevant service | Convert | Contextual link, not a pitch |

An answer placed above the first H2 is invisible to `capsule_check` — it only
measures the block after an interrogative H2. Put the question in an H2.

## 6. Category / Hub Page

Ranks for the broad term and funnels to children.

| Section | Purpose | Format |
|---|---|---|
| What This Covers | Define scope | **The capsule.** 40–80 word opener |
| One H2 per child page | The hub's whole job | Description + internal link |
| Who We Help | Qualify | Bulleted personas |
| How It Works | Expectations | Numbered steps |
| Common Questions | Variations | 5–8 questions |
| CTA | Convert | Clear next step |

**Enumerate the children yourself; nothing checks you.** See §1 — no gate models
hub→child completeness. Every existing sibling gets a section and a link, and
nothing that does not exist gets invented.

**Check the hub is inside your tier before you plan an edit to it.** T2 grants
`content.location` plus the `content.registry` paths (`common.py:394-400`). If
the children live in `src/content/services/` but the hub is a component at
`src/app/services/page.tsx`, that hub is a **T3 edit** and `tier_check` refuses
the run. `NO CHANGE`, with that as the reason, is the correct answer.

## 7. FAQ Page

| Section | Purpose | Format |
|---|---|---|
| Opening question as an H2 | Win the capsule | **The capsule.** H2 ending in `?`, 40–80 word answer paragraph |
| 8–15 further questions, grouped | Answer real questions | ~40–60 words each, answer-first |
| CTA after the last | Convert | Contextual |

Answers come from config and existing site copy. This is the easiest page in the
site on which to answer a question with a fact nobody gave you. Schema is the
configured business type + `BreadcrumbList`, per §1 — **not** `FAQPage`.

## 8. Case Study

| Section | Purpose | Format |
|---|---|---|
| What We Were Asked to Solve | Context, and the capsule | **The capsule.** H2 as written, 40–80 word opener |
| The Outcome | Lead with the result | Specific figures, from evidence |
| The Challenge | What was at stake | Short |
| Our Approach | Show the expertise | Steps or narrative |
| What Changed | Prove it | Specific figures |
| Takeaways | Reusable insight | 3–5 bullets |
| Related service CTA | Cross-sell | Link |

The capsule section is not decoration here: a case study written as
Outcome → Situation → Challenge → Approach has **no interrogative H2 at all**
and fails `capsule_check` outright on any topology-fitting route.

**Do not write a case study the config cannot source.** Every figure, timeline,
client name and outcome on this page is a provenance claim, and there is almost
never enough in `client-config.yml` to write one honestly. If the work item asks
for one and the facts are not there, `NO CHANGE` with that reason is the correct
answer — it tells the operator to collect the material.

---

## 9. Pages you did not create

Homepage and About already exist on every client site, so you are expanding one,
not writing it. Both are in `capsule_check`'s `DEFAULT_EXCLUDE`
(`capsule_check.py:78-81`), so the capsule rules above do not apply to them.
Both are dense with provenance claims and both are usually T1 text edits, so
expand only the section the finding names.
