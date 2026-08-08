---
name: site-remediation
description: Use when fixing one measured SEO finding in a client repo — the house rules for what may be claimed, what may be touched, and what "done" means. Loaded automatically by wf-site-remediate.
---

# Site Remediation

You are fixing **one measured finding** in a client's website repository. The
finding was produced by measuring the live site, not by an opinion. Your edit is
judged by re-measuring the same thing.

Everything below is enforced by a gate on the pull request. None of it is advice.

---

## 1. Derivation only, never invent

**This is the rule that matters most, and copy edits are exactly where it gets
broken.** Rewriting a sentence is where an invented credential appears.

Every number, credential, rating, review count, licence number, certification,
warranty term, year-count, price, percentage and superlative you write must come
from one of:

- `docs/client-config.yml` in this repo (`trust_signals`, `licenses`, `usp`,
  `bio_paragraphs`, `nap`, `business`, …)
- the work item's own `evidence` — that is a real measurement
- **text that is already on the page** — moving an existing claim is not
  inventing one

A claim you cannot source **gets removed, not reworded**. Do not soften it, do
not hedge it, do not replace "4.9 stars from 1,200 reviews" with "highly rated".
Cut it and write something true instead.

`claim_provenance_check` refuses the PR on any claim it cannot trace, and there
is no configuration that turns it off. If the fact is genuinely real, it belongs
in `docs/client-config.yml` — added by a human, in a human pull request, because
that file is on the deny list and you cannot touch it.

Watch for the phrasings that read as harmless and are not:

| Do not write | Unless |
|---|---|
| "licensed and insured" | a licence exists in config |
| "family owned for over 30 years" | a founding year in config supports it |
| "the only / the largest / #1 in" | config already makes that claim |
| "award-winning" | the award is named in config |
| "free estimates", "lifetime warranty" | config says so |

## 2. Fix exactly one finding

You are given one work item. Fix that finding and stop.

- Do not fix other findings you notice. Each has its own work item, its own
  acceptance check, and its own place in the ledger. Fixing it here makes the
  file→item map wrong.
- Do not reformat, reorder, rename, or tidy. A diff that touches ten unrelated
  lines is a diff a human cannot review, and a human reviews every one of these.
- Do not "improve" copy that was not the finding.

The smallest diff that clears the finding is the correct diff.

## 3. Stay inside the tier

Your prompt names the exact paths you may touch. That list comes from
`docs/client-config.yml` and is enforced against the real diff by `tier_check`.

- **T1** — modify existing files matching `text_paths`. No new files, no deletes.
- **T2** — T1, plus create pages under `content.location`, plus modify the
  `content.registry` files that wire a new page in.
- **T3** — anything not on the deny list.

The deny list applies at every tier: `.github/**`, `docs/client-config.yml`,
`package*.json`, `wrangler.toml`, `.env*`. You may never edit the gates that
judge you, and you may never raise your own tier.

If the fix genuinely requires authority you do not have, **change nothing** and
say `NO CHANGE` with the reason. That is a useful, correct outcome — it tells the
operator this client needs a higher tier. Working around the limit is not.

## 4. Where the content actually lives

Content on these sites is **data, not markup**. A page's title and meta
description are almost always fields in a typed data file (`src/data/*.ts`,
`src/content/*.mdx`), not literals in a component. Find the data entry whose slug
matches the finding's URL and edit the field.

If you can only find the string inside a component or template, that is a T3 edit
and probably not what you were asked to do. Check again for a data file first.

## 5. What "fixed" means per finding

Bands come from the client's config where declared; these are the defaults.

| Finding | Fix |
|---|---|
| `title_missing`, `title_out_of_band` | 30–60 characters, primary service + city, Title Case, no filler |
| `meta_description_missing/_out_of_band` | 120–160 characters, specific benefit + a reason to click, no keyword stuffing |
| `image_alt_missing` | Describe the image's content and function. Not "image", not the filename, not a keyword dump |
| `nap_phone_missing` | Use the exact phone string from config `nap`. Never a different format, never a guess |
| `forbidden_phrase_live` | Remove the phrase. Do not paraphrase around a legal restriction — the restriction is on the claim, not the wording |
| `thin_content` | **The page already exists — expand the copy that is there, do not create anything.** A page can only be measured as thin if it is live, so this is a modify, and at T1 the entry is normally in a data file you already have. Answer the query the page is for; padding to the word count is the failure mode this finding exists to surface |

See `references/serp-title-meta-craft.md` for titles and metas and
`references/anti-slop-prose.md` for the prose rules. Read them before writing any
sentence a visitor will see. `references/page-type-shapes.md` is for **whole-page
work only** — writing a new page at T2, or expanding a `thin_content` page at any
tier. It is an outline of sections; following it while fixing a title or an alt
text would blow the one-finding rule above.

## 6. House writing standards (each is a gate)

- **Title Case on every heading.** "Florida's Only Active Stone Quarry", never
  "Florida's only active stone quarry". → `check_headings`
- **No em dashes in public-facing copy.** Rewrite the sentence. → `em_dash_check`
- **No possessive contractions in headings.** "Summer Is Around the Corner", not
  "Summer's Around the Corner". → `check_headings`
- **No invisible or zero-width characters.** Type plain ASCII punctuation.
  → `fingerprint_check`
- Every page must stay distinct from its siblings. Do not reuse a sentence across
  city pages. → `noncommodity_check`

## 7. T2 — writing a new page

Only when your prompt says T2 and `content.location` is declared.

- The page goes under `content.location`, in the declared `format`.
- **Wire it into `content.registry` in the same run**, and do not count on a gate
  to remind you. T2 *permits* you to modify the registry; nothing asserts that
  you did. `orphan_check` counts a self-link from the global nav as inbound, so a
  page nothing else links to still passes it, and `parity_check` only catches the
  page if it built without reaching the sitemap. An unwired page can clear both.
- Match the URL shape of its siblings exactly. Read three existing pages first.
- Question-shaped H2, then the answer as its own opening paragraph, then the
  detail. The band is 40–80 words and at most 3 sentences, measured on that one
  paragraph, not the section — `references/page-type-shapes.md` §1 states the
  whole contract and is the only place to keep it current. → `capsule_check`
- **Read `references/page-type-shapes.md` before you write the outline.** It
  gives the section shape for a service, location, blog, hub, FAQ or case-study
  page, states what the gates actually measure on a new page (verified against
  `pipeline/gates/`, not from memory), and names the four sections where an
  invented claim usually appears. A section you have no sourced material for
  gets left out, not filled.
- Every factual claim still comes from config. A new page is not a licence to
  invent a history for the business.

## 8. T3 — structural work

Only when your prompt says T3. Components, templates, layout, routing.

- Change the template, not forty pages. If the same fix appears on many pages,
  the fix belongs in one place.
- Never change what a component renders for pages outside the finding's scope
  without saying so.
- The build must pass. A structural edit that breaks `tsc` or the build wastes
  the whole run — every OUT gate is skipped and nothing is verified.

## 9. Report honestly

Reply with one line:

- `FIXED <path>` — you changed that file and the finding should now clear
- `NO CHANGE <reason>` — you did not change anything, and why

Do not claim a fix you did not make. `acceptance_check` re-measures every claimed
fix against the built output and refuses the PR when the finding still fires, so
a false claim does not ship — it just wastes a cycle and burns the trust that
lets an agent write to a client's site at all.
