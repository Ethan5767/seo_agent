---
name: seo-distiller
description: Take one raw SEO content document from the team (Discord drop, Google Doc export, docx), clean it, sanitize it against the client's canonical config, polish titles/metas/headings/CTAs against spend-validated conversion evidence, and emit ONE build-ready distilled file. Triggers - "distill [client] doc", "run the distiller", "clean this doc", "distill the [client] [month] content", "sanitize this content doc", or any team content docx handed over for a client.
---

# SEO Distiller — Team Doc In, One Clean Doc Out

One job only: a raw team content document goes in, one polished, sanitized, conversion-ready document comes out. This is NOT the v2 emit engine, NOT the monthly report pipeline, NOT live-page CTR recovery (that loop needs a GSC baseline and lives in the monthly cycle). No GSC pulls, no emit, no PR, no site code. The output file is the deliverable.

**Contract: agent proposes, gates dispose.** Your rewrites are never trusted, only verified — the output must pass the deterministic gate (`scripts/scan.py` in this skill's folder) with zero BLOCK findings before you report done.

**Prime directive: derivation only, never invent facts.** Every replacement claim comes from the client's config (usp, bio_paragraphs, trust_signals, licenses) or the source doc itself. A stat you cannot source gets removed, not reworded.

This skill is fully self-contained: every reference and the spend-validated craft pack ship inside this folder. All paths below are relative to this skill's base directory.

## Step 0 — Resolve the Client (Always First)

1. Identify the client from the filename or the operator's words.
2. Locate the canonical `client-config.yml` — the client repo's `docs/client-config.yml`, or an explicitly provided path (test corpora keep configs in a `clients examples/<Client>/` folder). Also grab the client's flat `banned-phrases.txt` if one exists.
3. Read the config. Extract and hold:
   - `forbidden_phrases` + reasons and severities (`error` blocks, `warning` warns, `flag` surfaces for the human without forcing a rewrite; an entry's `approved_alternative` is your rewrite target)
   - `required_phrases` (must appear on every service/spoke page, not just once per doc)
   - NAP + ALL office phones (multi-state clients: per-state DIDs — each page must use the office phone serving that page's state)
   - `trust_signals`, `licenses`, `usp`, `bio_paragraphs` (the ONLY sources for replacement claims and title differentiators)
   - `services_not_offered` (content selling these gets flagged HELD, not rewritten)
4. If the client cannot be identified or the config is missing, STOP and ask. Never distill against guessed rules. If the scanner reports `config-inconsistency` FLAGs (e.g. conflicting years-in-business inside the config), pick the canonical `trust_signals` value for the run AND surface the conflict as an open question in the report.

## Step 1 — Ingest + Baseline Scan (Deterministic)

```bash
# Convert (pandoc preferred — preserves heading levels; textutil as macOS fallback)
pandoc -f docx -t markdown --wrap=none "DOC.docx" -o "<scratch>/doc.md"

# Baseline scan — the findings inventory you will fix
python3 "<this skill>/scripts/scan.py" "<scratch>/doc.md" \
  --config "<client>/client-config.yml" [--banned "<client>/banned-phrases.txt"]
```

Read the full findings list. It is the FLOOR, not the ceiling — the scanner catches patterns; you catch meaning (a compliant-sounding sentence that still promises claim advocacy, a fact contradicting the config, a page selling a service the client does not offer).

These docs run 200-800 KB of text. Read them in chunks (offset/limit) and work per page. Never assume one read captured the whole file.

## Step 2 — Load the Craft (Once Per Run)

Read, from this folder:

1. `references/conversion-pass.md` — the rewrite doctrine (governs everything below).
2. `references/serp-title-meta-craft.md` — full title/meta craft including the reference exemplars, in full.
3. `references/anti-slop-prose.md` — loaded before the final sweep.

These references ARE the evidence, distilled from the Meridian Conversion research base (1,912 spend-proven ads, 45 teardowns, split-test data) — conclusions travel with the package, the raw pile stays on the research drive. Grading law: every rewrite follows a rule in the references, or beats it with a reasoned angle stated in the change log. Title differentiators must be traceable to a config field — never invented.

## Step 3 — Distill (Judgment, Per Page)

Split the doc into pages (team formats vary: "SEO META TAGS" blocks, week emojis, per-city sections — use judgment, not regex). For EACH page, in this order:

1. **Sanitize.** Fix every scanner finding on this page plus meaning-level violations. Rewrite direction comes from the forbidden-phrase `reason` + the config's compliant framing. **Negated statutory disclaimers are NOT violations:** a literal ban hit inside "We do not accept Assignment of Benefits" is the disclosure the law requires — reword to preserve the legal meaning if needed, never delete a required disclosure to satisfy the scanner.
2. **Fact gate.** Every number, credential, warranty name, rating, and year-count must exist in config `trust_signals`/`licenses` or the doc's own sourced material. Unverifiable = remove or replace with a config-verified equivalent. Strip, never soften.
3. **Conversion pass.** Apply `references/conversion-pass.md` sections 1-5: title (keep entity skeleton, add NESB click reason), meta (qualifier opener + proof stack, 120-155), H1/hero (3-question test + pogo gate), phone-first CTAs with the correct per-state DID, entity-welded passages.
4. **Writing standards.** Title Case every heading, no contractions in headings, no em dashes anywhere, professional register.
5. **Preserve intent.** Keep the team's page inventory, section order, and local research (neighborhood names, code specifics, climate detail — good material, expensive to recreate). Polish their work, do not replace it. Vary prose rhythm between city pages so the set does not read as one template.

Then the final sweep: the FULL `references/anti-slop-prose.md` rulebook over the whole output.

## Step 4 — Verify + Emit

1. Write ONE output file per `references/output-format.md`: `<Source Basename> - DISTILLED.md`, next to the source, change log + kept-WARN table at top, four grades per page (copy / ranking-safety / pogo / compliance).
2. Re-run the gate on YOUR output. **0 BLOCK findings required.** Fix and re-scan until clean. Every remaining WARN must appear in the kept-WARN table with its verification source.
3. **Review PDF (optional, when the operator asks):** convert the DISTILLED.md to standalone HTML (`pandoc -s --metadata title="..." -o review.html`, clean print CSS), then render with a Puppeteer-based HTML-to-PDF renderer if one is available on the machine. Never use Chrome CLI `--print-to-pdf`. If no renderer is available, deliver the HTML and say so.
4. Report: pages distilled, BLOCKs fixed by rule, facts stripped, titles/metas rewritten, held pages, and a coverage summary (which cities/services the source doc actually contained — surfaces team under-delivery at intake). Cite the output path and show the final scan result. Never claim done without it.

## Hard Rules

1. Never invent facts, stats, credentials, or offers. Derivation only.
2. Never distill without the client's real config loaded. No config, no run.
3. Client config bans ALWAYS beat evidence patterns (no dollar figures for a $-banned client, no matter what winning ads run).
4. Wrong-state phone DID on a page = NAP violation, always fix. Pages selling `services_not_offered`: mark `STATUS: HELD`, do not rewrite into existence.
5. The scanner's verdict is final. Zero BLOCK or it does not ship. Scope discipline: doc in, doc out — nothing else.
