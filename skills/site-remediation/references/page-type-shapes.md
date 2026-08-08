# Page Type Shapes

Adapted from `skills/seo-content-brief/references/page-type-templates.md` in
[AgricIDaniel/claude-seo](https://github.com/AgricIDaniel/claude-seo) (MIT,
© 2026 agricidaniel), rewritten for the remediation rail: the competitive-brief
framing is gone, because at remediation time there is no SERP scrape and no
competitor set — there is one measured finding and a tier.

**Read this when you are writing a page from scratch (T2, `thin_content`) or
substantially expanding a thin one.** It answers "what sections does this kind
of page owe the reader", nothing more. It does not override anything.

---

## Read this before any table below

The section tables tell you **which sections exist and what shape they take**.
They do not tell you what may go inside them, and three of the rows below are
exactly where an agent invents a fact and gets the whole PR refused:

| Section | What gets invented there |
|---|---|
| Why choose / differentiators | "licensed and insured", "family owned 30 years", "award-winning" |
| Outcomes, results, social proof | a star rating, a review count, a percentage, a case-study figure |
| Team, credentials, awards | a certification, a licence number, a named award |
| Local reviews, testimonials | a quote no customer ever said |

Every one of those must trace to `docs/client-config.yml`, the work item's
`evidence`, or text already on the site. **A section with no sourced material is
a section you leave out** — not one you fill with plausible copy. Dropping "Why
Choose Us" from a service page costs nothing. Inventing a licence number costs
the PR, and `claim_provenance_check` has no override.

Word counts are targets for a section that has something to say, never a quota.
Padding to hit them is the precise failure mode `thin_content` exists to
surface.

---

## Service Page

Converts a visitor into an enquiry.

| Section | Purpose | Format |
|---|---|---|
| What [service] is | Define it plainly | 80–120 words, answer-first |
| Who needs it | Let the reader self-qualify | Bulleted scenarios |
| How it works | Remove friction, set expectations | Numbered steps |
| Cost or pricing | The question everyone has | Table or honest range; omit entirely if config gives you no numbers |
| Outcomes | Prove it works | Only from config or evidence |
| Why choose [client] | Differentiate | Only from config `usp` / `trust_signals` |
| FAQ | Long-tail and PAA | 5–8 questions, 40–60 words each |
| CTA | Convert | One action, config `nap` phone verbatim |

**Schema:** `Service`, plus `LocalBusiness` when the page is location-specific
(`health.schema_business_missing` measures the type named in the client's
`schema_type`).
**Primary query:** H1, first 100 words, one H2, URL slug, title tag.

## Location Page

Ranks for `[service] [city]`. The one most at risk from `noncommodity_check` —
city pages are where the same three paragraphs get pasted eleven times.

| Section | Purpose | Format |
|---|---|---|
| What we do in [city] | Local relevance | City named naturally, not stuffed |
| Areas served | Hyper-local signal | Suburbs, landmarks, jurisdictions — real ones only |
| Why local matters here | Justify the page existing | 1–2 paragraphs, specific to this city |
| Team in [city] | Trust | Only if config names local staff |
| Reviews mentioning [city] | Trust | Only from config |
| FAQ | Local variations | 5 questions that differ per city |
| CTA | Convert | Local phone from config `nap` |

**Every section must say something true of this city and false of its
siblings.** If you cannot write a paragraph about Charleston that would be wrong
about Columbia, you have written a template, and `noncommodity_check` refuses
it. Concrete local material — a named suburb, a permit office, a soil or storm
condition, a drive time — is what makes the page distinct.

**Schema:** `Service` + `LocalBusiness` with the config address and phone.
**Primary query:** `[Service] [City]` in H1, title, slug, first paragraph.

## Blog Post

Ranks for an informational query and routes the reader to a service page.

| Section | Purpose | Format |
|---|---|---|
| Direct answer | Win the capsule | 40–60 words, first thing on the page |
| Context | Set the scene | 1–2 paragraphs |
| 3–5 subtopic H2s | The actual depth | Prose, lists, tables as the material demands |
| Common mistakes | Where the value usually is | Numbered, each with the reason |
| FAQ | Long-tail | ~5 questions |
| CTA to the relevant service | Convert | Contextual link, not a pitch |

Question-shaped H2, answer first, then the detail. That ordering is what
`capsule_check` measures.

**Schema:** `Article`.
**Primary query:** H1, first 100 words, slug, title, one image alt.

## Category / Hub Page

Ranks for the broad term and funnels to children.

| Section | Purpose | Format |
|---|---|---|
| What this covers | Define scope | Overview paragraph |
| One H2 per child page | The hub's whole job | Description + internal link |
| Who we help | Qualify | Bulleted personas |
| Process overview | Expectations | Numbered steps |
| FAQ | Variations | 5–8 questions |
| CTA | Convert | Clear next step |

**The child list must match the site, exactly.** Every existing sibling under
`content.location` gets a section and a link; nothing that does not exist gets
invented. A hub that omits a real child leaves it orphaned, and
`orphan_check` refuses the PR on the missing link — the same gate that refuses
your new page if you forget to wire it into `content.registry`.

**Schema:** `Service` + `BreadcrumbList` (`health.schema_breadcrumb_missing`).

## FAQ Page

| Section | Purpose | Format |
|---|---|---|
| 8–15 questions, grouped by subtopic | Answer real questions | 40–60 words each, answer-first |
| CTA after the last | Convert | Contextual |

Answers come from config and existing site copy. An FAQ page is the easiest
place in the whole site to answer a question with a fact nobody gave you.

**Schema:** `WebPage`. Google retired FAQ rich results on 2026-05-07 — `FAQPage`
markup is still valid Schema.org and harmless to carry, but it no longer earns a
search feature, so do not add it to a new page for that reason. (`measure.py`
still emits `health.schema_faq_missing`; that is **B-022**, not a mandate.)
**Primary query:** H1 as `[Topic]: Frequently Asked Questions`, and in the first
answer.

## Case Study

| Section | Purpose | Format |
|---|---|---|
| Outcome | Lead with the result | First line |
| Situation | Context | 1–2 paragraphs |
| The challenge | What was at stake | Short |
| Approach | Show the expertise | Steps or narrative |
| Result | Prove it | Specific figures |
| Takeaways | Reusable insight | 3–5 bullets |
| Related service CTA | Cross-sell | Link |

**Do not write a case study the config cannot source.** Every figure, timeline,
client name and outcome in this page type is a provenance claim, and there is
almost never enough material in `client-config.yml` to write one honestly. If
the work item asks for one and the facts are not there, `NO CHANGE` with that
reason is the correct answer — it tells the operator to collect the material.

---

## Existing pages you did not create

Homepage and About pages already exist on every client site, so you will be
expanding one rather than writing it. The shapes still apply — a homepage owes
the reader a value proposition, a services overview linking to the service
pages, differentiators, proof, and service area; an About page owes them who,
when, and credentials. Both are dense with provenance claims and both are
usually T1 text edits, so expand only the section the finding names.
