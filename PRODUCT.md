# Product

## Register

product

## Users

SEO operators running audit-and-fix cycles on client websites, plus the clients
who read the resulting reports.

- **Operator (primary).** Runs a scan against a client domain, reads what came
  back, decides what to fix, drives the remediation rail, and checks whether the
  numbers moved. Works across multiple client sites in one session. Lives in this
  UI for long stretches, so density and scan-ability beat hand-holding.
- **Client (secondary, read-mostly).** Wants to know: is my site healthy, what is
  being fixed, did it improve. Does not know what "TF-IDF" or "JSON-LD" means and
  should never have to.

Context of use: desk, two monitors, daylight, an analytical mood. Not mobile-first,
but must not break on a laptop screen.

## Product Purpose

REAI measures a website (technical SEO, on-page, Core Web Vitals, AI/answer-engine
visibility, local presence), ranks what is wrong by impact, and drives the fixes
through a gated pipeline. Success is the operator opening one screen and knowing
what to do next without assembling it themselves.

The product's differentiator is the **AI search visibility (AEO) lane** and the
**fix rail**: competitors report problems, REAI reports them and then fixes them
behind a human merge.

## Brand Personality

Precise, opinionated, calm.

- **Precise.** Every number traces to a source. Estimates are labeled estimates.
- **Opinionated.** The product ranks. It says "fix this first, here is why",
  rather than handing over an undifferentiated data dump.
- **Calm.** An instrument, not a scoreboard. No confetti, no gradient hero
  metrics, no urgency theater.

Voice: plain words over jargon. "Pages missing a title", not "Metadata Integrity
Matrix". Where a competitor's term is the industry standard, use the plain
equivalent and define it once.

## Anti-references

- **Semrush / Ahrefs density wall.** Semrush is the direct competitor. Its
  structure is worth learning from; its execution is the thing to beat. Do not
  clone its look, its vocabulary, or its everything-at-once screens. Where Semrush
  shows forty widgets, REAI shows the ranked few and keeps the rest one click away.
- **Cutesy marketing dashboard.** Big gradient hero numbers, illustrations, toy
  energy. This is an instrument.
- **Dark hacker terminal.** Neon on black, monospace everywhere. Looks sharp in a
  screenshot, hurts across a two-hour analysis session.

## Design Principles

1. **One name, one place.** Every screen has exactly one label and exactly one
   route. Three sidebar entries must never open the same view, and one label must
   never open two. This is the principle the current build most violates.
2. **Rank, do not dump.** The interface's job is ordering. If everything is on
   screen at equal weight, the product has done no work.
3. **Say it plainly, then show the proof.** Lead with the plain-language finding;
   put the JSON-LD, the Lighthouse trace, and the crawler headers behind a
   disclosure for the operator who wants them.
4. **Label the trust level.** Estimated, demo data, needs a Google connection, not
   yet verified. A number with no provenance is worse than no number.
5. **Values come from the scale, never from the element.** Spacing, color, type
   size, and radius are chosen from a token set. An element that needs a value the
   scale does not have is a signal the scale is wrong, not a licence to type a
   new number.

## Accessibility & Inclusion

- Target **WCAG 2.2 AA**. Body text at or above 4.5:1, large text at or above 3:1,
  placeholders held to the body-text ratio.
- Status must never be carried by color alone. Pass / warn / fail needs a shape,
  an icon, or a word alongside the hue, for the ~8% of men with red-green color
  vision deficiency who are squarely in this audience.
- Every animation needs a `prefers-reduced-motion: reduce` alternative.
- Full keyboard reachability across the sidebar, the audit form, and every
  disclosure. Visible focus rings, never `outline: none` without a replacement.
- Tabular data uses real `<table>` semantics with scoped headers, not div grids.
