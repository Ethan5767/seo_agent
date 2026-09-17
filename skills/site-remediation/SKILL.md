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
| `meta_description_missing`, `meta_description_out_of_band` | 120–160 characters. Worth knowing before you spend effort here: Google rewrites 61–76% of meta descriptions, and a controlled test of *removing* over-long ones measured +4.2%. Write one where the page has a promise the SERP would otherwise miss; do not manufacture one to fill the tag |
| `h1_count_wrong` | Exactly one `<h1>`, and make it the page's actual subject. Promoting the first `<h2>` to `<h1>` measured +4.5% in a controlled test; inventing a new heading above the content did not |
| `canonical_mismatch` | Point the canonical at this page's own URL. **Never** point it at a different page to resolve a duplicate — that is a deindexing decision and belongs to a human |
| `og_image_missing` | Add `og:image` referencing an image that already exists in the repo. Never invent a path, never hotlink |
| `schema_business_missing` | Add LocalBusiness JSON-LD built **only** from `docs/client-config.yml`. Every value traceable; no invented rating, review count or licence number — `claim_provenance_check` refuses them |
| `schema_breadcrumb_missing` | BreadcrumbList matching the *rendered* breadcrumb exactly. A schema that disagrees with the DOM measured −5.5%; getting it wrong is worse than leaving it out |
| `tel_link_missing` | Wrap the existing phone number in `tel:`. Use the config `nap` string verbatim |
| `ga4_tag_missing` | Add the GA4 tag using the measurement id from the client config. If none is declared, this is a human step — never guess an id |
| `noindex_present` | **Do not remove it on your own judgement.** A `noindex` is usually deliberate — a staging route, a thin variant, a page someone chose to keep out. Report which page carries it and why you believe it is wrong, and let a human decide. Removing one adds a page to the index, which is the same class of irreversible act as removing one |
| `url_not_200` | Diagnose only. Do not create the page, do not add a redirect, do not noindex it. Report what the status was and stop |
| `csr_empty_shell` | Make the main content present in the server-rendered HTML. No AI crawler executes JavaScript, so content behind CSR is invisible to every one of them |
| `onpage.charset`, `onpage.doctype` | Add `<!DOCTYPE html>` / `<meta charset="utf-8">` as the first elements. Mechanical |
| `onpage.legacy_meta_keywords` | Delete the tag. Google ignores it entirely and Bing treats stuffing as a mild spam signal |
| `onpage.meta_refresh` | Remove it and let the server redirect, or leave the page in place. Never add one |
| `onpage.apple_touch_icon` | Add the link only if the icon already exists in the repo |
| `onpage.mixed_content` | Rewrite `http://` subresources to `https://`. **Verify each host answers over HTTPS first** — a broken asset is worse than an insecure one |
| `onpage.external_link_safety` | Add `rel="noopener"` to every `target="_blank"`. Zero risk |
| `onpage.image_dimensions` | Add the real `width`/`height` from the file. A CLS fix; guessed numbers make it worse |
| `onpage.deprecated_html`, `onpage.flash` | Replace with the modern equivalent, or remove where it carries no content |
| `onpage.semantic_main` | Wrap the existing main content in `<main>`. Move nothing |
| `onpage.heading_order` | Fix skipped levels. This is an **accessibility** fix (WCAG 1.3.1) — Google states heading order does not matter to it, so do not sell it as a ranking change |
| `onpage.placeholder_text` | Remove lorem ipsum and "TODO" copy. If the section then has nothing to say, flag it for a human rather than writing filler |
| `onpage.empty_links` | Give the anchor real text, or remove it. An empty link is invisible to a crawler and a screen reader alike |
| `onpage.hreflang` | Fix the code (`en-UK` is invalid; the UK is `GB`), add the self-reference, and complete the return links. Every locale lives in this repo, so the whole graph is completable — and if two pages do not both point at each other, Google ignores the tags entirely |
| `onpage.render-blocking_scripts` | Add `defer` to scripts that do not run before paint. Never to one the page depends on during render |

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
