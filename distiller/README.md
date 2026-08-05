# SEO Distiller — Portable Skill Package

Self-contained Claude Code skill: one raw team content document in, one sanitized, conversion-graded, build-ready document out. This folder is the canonical source — everything the skill needs ships inside it. No external volumes, no machine-specific paths.

## What Is in the Box

```
Distiller/
├── SKILL.md                          The runbook Claude follows
├── scripts/scan.py                   Deterministic gate (Python 3 + PyYAML)
└── references/
    ├── conversion-pass.md            Rewrite doctrine (titles, metas, heroes, CTAs, citability, location pages, schema)
    ├── serp-title-meta-craft.md      Title/meta craft + reference exemplars (pre-publish edition)
    ├── anti-slop-prose.md            De-LLM prose rulebook (MIT, stop-slop v2.0.0)
    └── output-format.md              Canonical single-file output schema
```

The references are distilled conclusions from the Meridian Conversion research base (1,912 spend-proven ads, 45 page teardowns, SearchPilot/Zyppy split-test data) and the Meridian SEO skill stack. The raw evidence stays on the research drive; the package ships only what a run needs.

## Install

Copy this folder into a Claude Code skills directory and rename it to the skill name:

- Per machine: `~/.claude/skills/seo-distiller/`
- Per repo (recommended for the v2 pipeline): `<repo>/.claude/skills/seo-distiller/`

Claude Code picks it up automatically. Trigger with: "distill the [client] [month] doc — source: <docx path>, config: <client-config.yml path>".

## Runtime Requirements

1. Claude Code (any current model; stronger models produce better rewrites — the gate quality is constant).
2. Python 3 with PyYAML (`python3 -c "import yaml"` must pass).
3. pandoc for docx conversion (`brew install pandoc` / `apt install pandoc`). macOS `textutil` works as a fallback.

## Inputs Per Run

1. The team's content document (.docx, Google Doc export, .md, or .txt).
2. The client's canonical `client-config.yml` (forbidden/required phrases, NAP + per-office phones, verified trust signals, licenses, services not offered).
3. Optional: the client's flat `banned-phrases.txt`.

## Config Schema Extensions (v1.1, 2026-08-03)

Each `forbidden_phrases` entry supports two optional fields:

- `severity: error | warning | flag` (default `error`). `error` blocks the gate; `warning` warns; `flag` surfaces the hit for human review without forcing a rewrite — use it for context-dependent terms regex cannot judge.
- `approved_alternative: "<replacement framing>"` — the compliant rewrite target, shown inline in scanner findings so fixes are guided replacement, not open-ended rewriting.

Title differentiators are judgment-phrased but must trace to a config field (trust_signals, licenses, certifications, services) — never invented. Evidence rule from split-test data: credentials with proper nouns, real numbers, and ops-speed claims win; commodity USPs test null; naked CTAs test negative and are banned from titles.

The scanner also cross-checks the config itself and emits a `config-inconsistency` FLAG when it states conflicting facts (e.g. two different years-in-business values).

## The Contract

Agent proposes, gates dispose. Claude does the judgment (page splitting, compliant rewrites, conversion polish); `scan.py` gives the deterministic verdict (banned phrases, lengths, headings, phones, fact-gate flags). The output must exit the scanner with zero BLOCK findings, and every kept WARN must carry a verification source in the output's change log. Facts are never invented — only derived from the config or the source doc.

## Maintenance

- The reference docs are refreshed from the research base when its quarterly re-harvest lands or when a new vertical's evidence warrants a rule change — doctrine updates, not snapshot shipping. The change log of each run cites which rules drove each rewrite.
- Per-client rules live in each client's `client-config.yml`, never in this package. New client = new config, zero changes here.
