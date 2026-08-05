# Distilled Output Format — One File, Canonical Shape

The distiller emits exactly ONE markdown file next to the source document:

```
<source directory>/<Source Basename> - DISTILLED.md
```

Example: `South Carolina Content _ Acme Roofing _ July 2026 - DISTILLED.md`

The whole file must pass `scan.py` with 0 BLOCK findings. That includes the change log, so no em dashes anywhere, even in internal notes.

## File Skeleton

```markdown
# [Client Name] | Distilled Content | [Month Year]

Source: [original filename]
Client config: [path used]
Distilled: [YYYY-MM-DD]
Pages: [N]
Coverage: [cities and services/subjects the source doc actually contained — so under-delivery against the client's ask is visible at intake, before anything ships]
Craft tier: [exact vertical / nearest neighbor: X / universal only]
Gate result: 0 BLOCK / [N] WARN (all resolved or justified below)

## Change Log

| Page | Change | Rule |
|------|--------|------|
| Charleston, SC | Removed "we attend the adjuster walkthrough" claim, replaced with inspect-and-document framing from config USP | forbidden-phrase |
| Charleston, SC | Title rewritten to add GAF Master Elite differentiator, query kept verbatim | conversion-pass |
| All pages | Stripped "26+ years" trust stat, not present in config trust_signals | fact-gate |

## Kept WARN Findings

| Line | Finding | Why Kept |
|------|---------|----------|
| ... | year-count claim "18 years" | Verified in config trust_signals |

---

# PAGE 1: [Page Name / Target City]

Canonical URL: [from source doc, verbatim unless obviously wrong]
Page Title: [30-60 chars]
Meta Description: [120-160 chars]

## TOPBAR
[...]

## HERO
Badge: [...]
H1: [...]
Subheading: [...]
Trust Stats: [only config-verified stats]
CTA Buttons: [phone-first]

## [Each Content Section in Source Order]
[...]

## FAQ
[Q/A pairs, answer-first, 50-200 words each]

---

# PAGE 2: [...]
```

## Rules

1. **Preserve the team's section order and page inventory.** The distiller polishes; it does not restructure the site or invent/drop pages. If a page is unshippable (built on a banned premise), keep a stub with `STATUS: HELD` and one sentence saying why, so Alex decides.
2. **Every page keeps its Canonical URL line** so the builder can map pages without guessing.
3. **Change log is per-meaningful-change, not per-line.** Group identical fixes ("All pages: ...").
4. **WARN findings table is mandatory** when the final scan reports WARNs. Every kept WARN needs a verification source (config line or client-confirmed fact). No source, no keep.
5. **No em dashes, Title Case on all headings, professional register** throughout, including internal notes, because the gate scans the whole file.
6. **Quoting removed language without retriggering the gate:** the change log never reproduces a banned phrase verbatim. Describe by rule and count ("removed 13 financing offers"), or quote with a visible break token inside the phrase, e.g. `free [·] roof`, `manage [·] the claim`. The scanner has no report exemption on purpose — the gate stays pure; the report adapts.
