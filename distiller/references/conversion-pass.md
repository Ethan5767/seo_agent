# Conversion Pass — Rewrite Rules for the Distiller

Why this layer exists: across an entire client book's monthly reports, impressions compounded 21-90% QoQ while CTR stayed flat or fell under 1.5% — the pipeline optimized everything up to the SERP and nothing past it. This pass makes every distilled page earn the click and the call, not just the ranking. The input docs are typically raw LLM drafts from the team; this pass grades them against spend-validated evidence instead of opinion.

## Craft Loading (Once Per Run, Before Rewriting)

Load from THIS skill folder:

1. `references/serp-title-meta-craft.md` — the title/meta rewrite doctrine (includes the reference exemplars). It governs sections 1-2 below.
2. `references/anti-slop-prose.md` — the full de-slop rulebook for the final prose sweep.

**These references ARE the evidence, distilled.** They were extracted from the Meridian Conversion research base (1,912 spend-proven ads ranked by run-length, 45 page teardowns, SearchPilot/Zyppy split-test data) — the package ships the conclusions, not the raw pile. On the main Meridian machine, the live Research KB (`/Volumes/Meridian Ext/All Companies/Research/Business/Conversion/`) may supplement for an unusual vertical; the references are the guaranteed baseline everywhere else.

**The grading law: every rewrite follows a rule in these references, or beats it with a reasoned angle stated in the change log. Opinion never outranks the receipts.**

**Prompt-side discipline:** state what to WRITE (approved alternatives, bank clauses, umbrella terms), and leave the "never say" enforcement to the scanner. Models violate prompt-side prohibitions at high rates (the negation/"pink elephant" failure mode); the deterministic re-scan is the enforcement layer, not your memory of the ban list.

## 1. Page Titles

Governed by `serp-title-meta-craft.md`. The short version: keep the team's entity skeleton (`[Service] [City] | [Brand]` — it is why the page ranks), spend the remaining Zone-1 characters on a click reason that passes the NESB check (New / Easier / Safe / Big with a comparison, not an adjective). Query verbatim, front-loaded. Ranking-safety is a hard fail: query tokens and geo preserved, always. H1 derives from the same assembly as the title.

**The one rule on differentiators: traceable to the config, or it does not go in the title.** Phrase it naturally per page (judgment, not assembly), but every claim must point at a config field — trust_signals, licenses, certifications, services. "GAF Master Elite" traces; "Permits Filed" and "Same-Day" invented from thin air do not. Vary which differentiator you use across pages so the set does not read as one template, and match it to the page's intent (a certification on product pages, fleet on hauling pages).

Weak: `Roofing Contractor in Charleston, SC | Summit Roofing`
Strong: `Roofing Contractor in Charleston, SC | GAF Master Elite`

## 2. Meta Descriptions

Governed by `serp-title-meta-craft.md`. Qualifier opener, then the proof stack (counted reviews, license number verbatim, response time), ownership-verb CTA with phone. 120-155 chars, gate-enforced. The meta does not rank; its only job is the click — and the phone number in it works even on zero-click SERPs. Client config bans always beat evidence patterns (a $-banned client gets no dollar figures regardless of what winning ads run).

## 3. H1 and Hero — the 3-Question Test + Pogo Gate

Every H1 + subheading pair must pass all three; if any fails, rewrite:

1. **Visualize:** can the reader picture the outcome? Concrete beats abstract.
2. **Falsify:** could a competitor NOT truthfully say this? If anyone could say it, it says nothing.
3. **Unique:** does it contain something only this client can claim (from config trust signals)?

H1 keeps the query. The subheading carries the falsifiable, client-specific proof. Then the pogo gate: whatever the rewritten title promises, the hero must answer above the fold — ideally as a content capsule (question as H2, direct 2-3 sentence answer). Title and hero are ONE asset; review them together.

## 4. Phone-First CTA Structure (Money Pages)

Local trades: the page's job is a phone call. 53% of spend-validated winners run no form at all.

- Primary CTA on every service/location page: `Call (XXX) XXX-XXXX` with the CORRECT per-state/office DID from client-config.yml (multi-state clients have different numbers per office — a wrong DID is a NAP violation).
- Secondary CTA: the concrete low-commitment offer in verb-plus-payoff form ("Get Your Free Inspection," never "Contact Us" or "Submit") — only in framing the config permits.
- The phone number appears in: topbar, hero CTA, closing section, and FAQ answers where natural. Required-phrase gates enforce presence; this pass enforces placement.
- Clarity beats clever, everywhere. No puns, no hype register.

## 5. Passage Citability

AI engines summarize passages, not pages. On every distilled section:

- **Weld the entity to the claim.** "We install 400 systems a year" is uncitable; "[Client Name] installs 400 systems a year in [City]" stands alone. Every claim worth citing carries its own subject — pronouns are invisible at passage level.
- **Semantic triples:** subject, predicate, object, plainly stated.
- **Self-contained sections:** each H2 block must make sense cut out of the page.
- FAQ answers: answer-first, 50-200 words, entity-welded.

## 6. Location Page Quality (City/Spoke Pages)

Two hard gates from the local-SEO evidence, applied to every city page in the doc:

- **The swap test:** remove the city name — can you still tell which city this page is for? If no, it is a doorway page (a documented HVAC case lost 80% of rankings for this pattern). Keep and strengthen the team's local specifics: neighborhoods, local codes, climate detail, area landmarks. That material is the page's ranking moat; never genericize it while cleaning.
- **Variation floor:** 60%+ unique content per city page, and vary paragraph openers and structure between pages — identical rhythm with swapped city names reads as one template to both Google and readers.

Plus placement rules: NAP visible, city + service in title AND H1, tel: link above the fold, 2-5 contextual internal links per 1,000 words with descriptive anchors.

**Coverage floors** (flag thin pages in the report, do not pad them): service pages ~800 words, location pages ~500-600. These are topical-coverage floors, not targets — a page below floor gets flagged for the team, never inflated with filler.

**Schema blocks in the doc:** when the source doc carries JSON-LD, every fact in it comes from the config (NAP, hours, geo, email — team docs have shipped a dozen-plus blocks per doc all carrying wrong email, hours, and coordinates). Trade subtype union always (`["LocalBusiness", "RoofingContractor"]`), never generic LocalBusiness alone; FAQPage schema on FAQ sets; one clean block per page, duplicates consolidated. If the doc's schema is mangled beyond repair, replace it with a schema fact table derived from config and say so in the change log.

## 7. Anti-Slop Prose Pass (Final Sweep)

Run the FULL `references/anti-slop-prose.md` rulebook over the output — not a summary of it. The highest-frequency tells in team docs: throat-clearing openers, false agency, negative listing, binary contrasts ("we don't just X, we Y"), adverb stacking, and the same paragraph rhythm repeating across every city page (template smell — vary openers and structure between pages).

## Per-Page Output Discipline

Each distilled page states its four grades in the change log: copy (vs the reference rules and exemplars), ranking-safety, pogo, compliance (scan.py). A page is not done until all four pass.
