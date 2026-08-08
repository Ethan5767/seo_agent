# Title + Meta Rewrite Craft (Pre-Publish Edition)

Adapted from Meridian Conversion's SERP CTR recovery module (born from the July 2026 five-client cycle: ~300 top-three rankings producing near-zero clicks; CTR flat or declining under 1.5% while impressions grew 21-90% QoQ). The live-page loop (ctr_gap.py detection, AI-Overview triage, clicks-recovered tracking) needs a GSC baseline and stays in the monthly cycle. THIS file is the rewrite craft applied pre-publish, so pages are born earning the click instead of being recovered later.

**The frame: the SERP listing is an ad. Title = headline, meta = body, sitelink = CTA. Grade it like one.**

## The Team-Playbook Rule (Read First — This Is the Distiller's Whole Title Job)

The team builds titles from the entity formula: `[Service] [City] | [Business Name]`. That formula is CORRECT for entity relevance and is why the rankings exist. It also produces zero-differentiator titles ("Roofing Contractor in Charleston, SC | Summit Roofing") — every competitor running the same playbook ships the same title, and nobody gives the searcher a reason to pick one.

**Keep their entity skeleton. Spend the remaining ~25 characters on the click reason. Never strip the entity half — that undoes their correct work.**

## Title Rules

1. **Query stays verbatim (or near-verbatim), front-loaded.** The ranking exists because the query matches the title. What changes is everything after it.
2. **30-60 characters, hard gate — 51-60 is the sweet spot** (lowest Google rewrite rate, ~40%). Query + one differentiator clause, front-loaded. The long-title neighborhood-stacking play (Sterling Sky, 200+ char tags for ranking breadth) is real evidence but it is a live-site ranking experiment, NOT document cleaning — it lives in meridian-conversion's monthly optimization work, never in distilled output. One rule here, no exceptions, so the doctrine and the scanner always agree.
3. **One differentiator + one specificity element** (number, timeframe, credential) in the remaining space. "Adds 15 Years" beats "Extends Roof Life."
4. **NESB check:** the added clause must hit New, Easier, Safe, or Big WITH a comparison, not an adjective. "Free Same-Day Estimates" (Easier + Safe) passes. "Top Rated Service" fails.
5. **Named mechanism where it fits** (every local trade is a stage 3-4 market): "21-Point Storm Check" earns curiosity a generic promise cannot.

**Formula:** `[Query, Verbatim] | [Differentiator or Mechanism] + [Specific]`

**Evidence-class rule for differentiator clauses** (SearchPilot split-test data): concrete specifics WIN (+8-15%: proper-noun credentials, real numbers, freshness, location placement); commodity USPs ("Free Quotes," "Free Shipping" class) test NULL; naked CTAs ("Book Now," "Call Today" class) tested NEGATIVE (-6%) and are banned from titles. Pick clauses accordingly.

**H1 mirrors the title.** Matched title + H1 pairs survive Google's rewriting with key elements retained 97% of the time vs 26% when mismatched. Derive both from the same assembly; never let them drift apart.

**Google rewrite reality:** Google now rewrites ~76% of titles in SERPs. The title still feeds ranking regardless of display, and the 51-60 char front-load minimizes rewrites — but this is why the meta description and the GBP carry more of the click burden than most people assume. Do not over-invest in display-copy perfection; DO invest in the ranking payload and the meta.

**Ranking-safety grade is a HARD FAIL, never a judgment call:** query tokens preserved, geo preserved, front-loaded. Two reasons: titles are a ranking input (onsite structure is the #1 local factor beyond table stakes), and titles feed the MAP PACK (a documented case moved map position 4.75 to 2.03 from a title change alone). A careless rewrite damages both surfaces.

## Meta Description Rules

The meta does not rank. Its ONLY job is the click. Write it like the friction-remover line under a CTA button.

1. **155 visible characters max** (the gate enforces 120-155).
2. **Qualifier opener:** first clause picks the reader out of the crowd and sets stakes ("Roof damage in Charleston?"), then the proof stack.
3. **Counted beats vague:** "4.9★ (271 Reviews)" beats "Top Rated." "5,000+ Roofs" beats "Experienced." Every count must be config-verified.
4. **License number verbatim** where it fits ("Licensed CCC1337163") — an 18-of-45-winners trust habit.
5. **Ownership verbs in the CTA:** See / Claim / Check / Get outrun Submit / Contact.

## Word-Level Rules (Spend-Validated)

- **Clarity beats clever.** No puns, no wordplay, no guru direct-response voice. Homeowners read hype as scam. Plain professional English with one specific reason to click.
- **Free-offer framing beats the offer:** "Free 14-Point Inspection" beats "Free Estimate." Only 22% of winners lead with the free offer, so naming it differentiates against most of the local SERP — but only in the framing the client's config permits.
- **Flat dollars beat percentages** in the general evidence — but **client config ALWAYS wins**: many clients ban dollar figures site-wide, and for them the specificity element is counted reviews, credentials, or timeframes instead. Never override a config ban with an evidence pattern.

## The Anti-Pogo Gate (Title and Page Are ONE Asset)

Every promise in the title must be answered above the fold on the page. An overpromising title that bounces users back to the SERP deranks the win. When you rewrite a title, check the page's hero/intro cashes the check in the same pass. The ideal above-the-fold answer is a content capsule: the question as an H2, a direct answer in the paragraph under it — the same block that earns AI citations cashes the title's promise. `capsule_check` measures that paragraph at 40-80 words and at most 3 sentences; see `page-type-shapes.md` §1 for the full contract, which is the one place those numbers are maintained. Note the floor as well as the ceiling — a crisp two-sentence answer can land under 40 words and fail. If the page cannot cash it, fix the hero or soften the title.

## Reference Exemplars (From the Spend-Proven Winner Set)

Four instructive winners from the 1,912-ad research base — each ran 800+ days of paid spend. Use them as register and shape references, not templates to copy:

1. `"Best of the Region" Local Roofing Company` (1,177 days) — a NAMED third-party award ("Voted Post Star 2023 Best of the Region") is falsifiable proof; "award-winning" alone is not.
2. `Keep Rodents Out` (1,202 days) — outcome-direct plainness. The reader's goal as the headline, zero cleverness.
3. `Heating Company Aurora` / `Tucson Garage Door Repair` (845/802 days) — the bare entity skeleton (service + city) runs for YEARS. This is why the skeleton is never stripped; the differentiator is added to it, not instead of it.
4. Waukesha Landscape Supply's opener (857 days): "Family owned mulch supply company, over 10 types, call today for same day delivery" + phone — the full stack in one line: ownership signal, counted claim, ops-speed, phone-first.

## Per-Page Grades (State All Four in the Change Log)

1. **Copy grade:** does the added clause use a proven move from the craft pack (number, mechanism, guarantee, question)?
2. **Ranking-safety grade:** query tokens + geo preserved, front-loaded? Any "no" = fail.
3. **Pogo grade:** does the hero answer the title's promise?
4. **Compliance grade:** scan.py, zero BLOCK.
