#!/usr/bin/env python3
"""claim_provenance_check — every factual claim in changed text must be sourced.

WHY THIS IS THE FIRST GATE v3 ASKED FOR (§4.1)
----------------------------------------------
A model "improving the wording" of a sentence is exactly where an invented
credential appears, so **T1 does not reduce this risk — it is where the risk
lives.** A sentence like *"licensed and insured for 28 years, 4.9 stars across
1,200 reviews"* about a business with none of that is legal exposure, and it is
the error class models produce most fluently.

The rule already existed as prose in the ported distiller doctrine. This is that
prose promoted to code:

    Derivation only, never invent. Every number, credential, rating, warranty
    term, year-count and superlative comes from config, from the work item's own
    evidence, or from the text that was already there. A claim you cannot source
    gets REMOVED, not reworded.

WHAT COUNTS AS A SOURCE
-----------------------
1. `docs/client-config.yml` — every string and number in it, at any depth
   (`trust_signals`, `licenses`, `usp`, `bio_paragraphs`, `nap`, …).
2. The cycle's `worklist.json` — a work item's own `evidence`, which is a real
   measurement of the live site.
3. **The pre-change version of the file itself.** A claim that was already on the
   site was not invented by this run. Without this the gate would refuse every PR
   that reflows a paragraph, and a gate that always refuses gets switched off.
4. An explicit citation on the line: an `http(s)://` URL or a `source:` marker.
   The human merging judges whether the citation is any good; the gate only
   insists one is offered.

Scanning is deliberately narrow: prose lines in markdown, and **quoted string
literals only** in code and data files. A bare `id: 1204` in a TS file is not a
claim about the business, and a gate that says it is gets ignored.

An empty corpus is a REFUSAL (exit 4), the same rule as `forbidden_sweep`'s empty
ruleset: a gate that cannot run must refuse, not pass.

Usage:
  wf-claim-provenance-check --project . [--base origin/main] [--diff-file PATH]
                            [--cycle YYYY-MM]

Exit: 0 clean · 18 unsourced claim(s) · 4 empty corpus (refusal) · 2 usage
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from pipeline.gates.tier_check import DiffError, resolve_base
from pipeline.lib.common import load_config

UNSOURCED_EXIT = 18
EMPTY_CORPUS_EXIT = 4
USAGE_EXIT = 2

TEXT_SUFFIXES = {".md", ".mdx", ".txt", ".html", ".astro", ".vue", ".svelte"}
CODE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml"}

# ── what a claim looks like ──────────────────────────────────────────────────
# Each pattern captures the VERIFIABLE token in group 1 — the number, or the
# superlative word. Unit-anchored on purpose: "5 Signs You Need a New Roof" is a
# heading, "5 stars" is a claim, and a gate that cannot tell them apart is noise.
CLAIM_PATTERNS = [
    ("rating",      re.compile(r"(\d+(?:\.\d+)?)\s*(?:★|\bstars?\b|/\s*5\b)", re.I)),
    ("reviews",     re.compile(r"([\d,]+)\+?\s*(?:reviews?|ratings?|testimonials?)", re.I)),
    ("years",       re.compile(r"(?:over|more than|nearly)?\s*([\d,]+)\+?\s*(?:\+\s*)?years?\b", re.I)),
    ("since",       re.compile(r"\bsince\s+((?:19|20)\d{2})\b", re.I)),
    ("license",     re.compile(r"(?:license|lic\.?|licence|permit|registration)\s*(?:no\.?|number|#)?\s*[:#]?\s*([A-Z]{0,3}[-\s]?\d[\d\-]{3,})", re.I)),
    ("warranty",    re.compile(r"([\d,]+)[-\s]?year\s+(?:warrant|guarantee)", re.I)),
    ("money",       re.compile(r"\$\s*([\d,]+(?:\.\d{2})?)")),
    ("percent",     re.compile(r"([\d,]+(?:\.\d+)?)\s*%")),
    ("jobs",        re.compile(r"([\d,]+)\+?\s*(?:homes?|roofs?|jobs?|projects?|customers?|clients?|families)\s+(?:served|completed|helped|protected|installed)", re.I)),
]

# Superlatives are unverifiable by arithmetic, so the rule is different: the word
# must already appear in a source. If the client never claimed to be "the only",
# the agent may not start.
SUPERLATIVE_RE = re.compile(
    r"\b(only|largest|biggest|best|first|fastest|cheapest|top[-\s]?rated|highest[-\s]?rated|"
    r"award[-\s]?winning|most\s+trusted|#\s?1|number\s+one|leading|premier|unmatched|guaranteed)\b",
    re.I)

CITATION_RE = re.compile(r"https?://|\bsources?\s*:", re.I)
STRING_LITERAL_RE = re.compile(r"""(["'`])((?:\\.|(?!\1)[^\\])*)\1""")


class ProvenanceError(RuntimeError):
    """Usage failure — no diff, or an unreadable artifact."""


# ── the corpus of sourced facts ──────────────────────────────────────────────

def _walk_strings(node) -> list:
    """Every scalar in a nested config, flattened to strings."""
    if isinstance(node, dict):
        return [s for v in node.values() for s in _walk_strings(v)]
    if isinstance(node, (list, tuple)):
        return [s for v in node for s in _walk_strings(v)]
    if isinstance(node, bool) or node is None:
        return []
    return [str(node)]


def normalize(text: str) -> str:
    """Lowercased, comma-stripped-from-digits, whitespace-collapsed."""
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return re.sub(r"\s+", " ", text).lower()


def build_corpus(project, cycle: str | None) -> tuple:
    """(corpus_text, sources_used). The corpus is one normalized blob — a claim is
    sourced when its token appears in it."""
    parts, used = [], []
    cfg = load_config(str(project))
    cfg_strings = _walk_strings(cfg)
    if cfg_strings:
        parts += cfg_strings
        used.append("docs/client-config.yml")

    audit = Path(project) / "docs" / "audit"
    cycles = sorted(d.name for d in audit.iterdir()
                    if d.is_dir() and (d / "worklist.json").is_file()) if audit.is_dir() else []
    target = cycle or (cycles[-1] if cycles else None)
    if target and (audit / target / "worklist.json").is_file():
        try:
            doc = json.loads((audit / target / "worklist.json").read_text())
        except json.JSONDecodeError as exc:
            raise ProvenanceError(f"{audit / target}/worklist.json is not valid JSON: {exc}")
        for item in doc.get("items", []):
            parts += _walk_strings(item.get("evidence"))
        used.append(f"docs/audit/{target}/worklist.json")

    return normalize(" \n ".join(parts)), used


# ── the changed text ─────────────────────────────────────────────────────────

def added_lines(project, ref: str, diff_file: str | None) -> dict:
    """{path: [added line, ...]} for text-bearing files in the diff."""
    if diff_file:
        raw = Path(diff_file).read_text()
    else:
        r = subprocess.run(["git", "-C", str(project), "diff", "-U0", f"{ref}...HEAD"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise ProvenanceError(r.stderr.strip() or "git diff failed")
        raw = r.stdout

    out: dict = {}
    path = None
    for line in raw.splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip()
            path = None if p == "/dev/null" else p[2:] if p.startswith("b/") else p
        elif line.startswith("+") and not line.startswith("+++") and path:
            out.setdefault(path, []).append(line[1:])
    return out


def prose_from(path: str, line: str) -> list:
    """The human-facing text in one added line.

    Markdown and HTML are prose end to end. In code and data, only the contents
    of string literals can reach a page, so only those are scanned — a bare
    numeric field is not a claim about the business.
    """
    suffix = Path(path).suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return [line]
    if suffix in CODE_SUFFIXES:
        return [m.group(2) for m in STRING_LITERAL_RE.finditer(line)]
    return []


def claims_in(text: str) -> list:
    """[(kind, token, snippet)] for one piece of prose."""
    found = []
    for kind, rx in CLAIM_PATTERNS:
        for m in rx.finditer(text):
            found.append((kind, m.group(1), m.group(0).strip()))
    for m in SUPERLATIVE_RE.finditer(text):
        found.append(("superlative", m.group(1), m.group(0).strip()))
    return found


def is_sourced(kind: str, token: str, corpus: str) -> bool:
    tok = normalize(token).strip()
    if not tok:
        return False
    if kind == "superlative":
        # Collapse "top rated"/"top-rated"/"#1"/"# 1" so a config spelling variant
        # still counts as the source it plainly is.
        return re.sub(r"[\s-]+", "", tok) in re.sub(r"[\s-]+", "", corpus)
    # The token must be the WHOLE number, so "9" does not source itself off the
    # "4.9" in the config — but a trailing sentence period must not break the
    # match, which is why the guard is "not a decimal point followed by a digit"
    # rather than "not a period".
    return re.search(rf"(?<!\d)(?<!\d\.){re.escape(tok)}(?!\d)(?!\.\d)", corpus) is not None


def scan(added: dict, corpus: str, baselines: dict) -> list:
    """[(path, snippet, kind, token)] for every claim with no source."""
    unsourced = []
    for path, lines in sorted(added.items()):
        prior = normalize(baselines.get(path, ""))
        for line in lines:
            if CITATION_RE.search(line):
                continue
            for text in prose_from(path, line):
                for kind, token, snippet in claims_in(text):
                    if is_sourced(kind, token, corpus):
                        continue
                    if prior and is_sourced(kind, token, prior):
                        continue        # it was already on the page; not invented here
                    unsourced.append((path, snippet, kind, token))
    return unsourced


def base_versions(project, ref: str, paths) -> dict:
    """{path: file contents at `ref`} — the pre-change text, so a reflowed
    paragraph is not reported as a fresh fabrication."""
    out = {}
    for p in paths:
        r = subprocess.run(["git", "-C", str(project), "show", f"{ref}:{p}"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            out[p] = r.stdout
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-claim-provenance-check",
        description="Refuse changed text carrying a factual claim that resolves to no source.")
    ap.add_argument("--project", default=".", help="client repo root")
    ap.add_argument("--base", help="ref to diff against (default: origin/main, then main)")
    ap.add_argument("--diff-file", help="read `git diff -U0` output from a file instead")
    ap.add_argument("--cycle", help="YYYY-MM whose worklist evidence counts as a source")
    args = ap.parse_args()

    project = Path(args.project)
    try:
        corpus, used = build_corpus(project, args.cycle)
    except ProvenanceError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return USAGE_EXIT

    if not corpus.strip():
        print("[FAIL] no provenance corpus loaded (docs/client-config.yml carried no values "
              "and no worklist.json was found). Refusing to run an empty claim gate — every "
              "claim would 'pass' for want of anything to check it against.", file=sys.stderr)
        return EMPTY_CORPUS_EXIT

    ref = None
    try:
        if not args.diff_file:
            ref = resolve_base(project, args.base)
        added = added_lines(project, ref, args.diff_file)
    except (DiffError, ProvenanceError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return USAGE_EXIT

    baselines = base_versions(project, ref, added) if ref else {}
    unsourced = scan(added, corpus, baselines)

    print(f"[CORPUS] {len(corpus.split())} words from: {', '.join(used)}")
    if not unsourced:
        print(f"[OK] claim-provenance: every claim in {len(added)} changed file(s) resolves "
              f"to a source.")
        return 0

    for path, snippet, kind, token in unsourced:
        print(f"[UNSOURCED] {path}: {snippet!r} ({kind}) — {token!r} appears in no config "
              f"field, no work-item evidence, and not in the previous version of this file.")
    sys.stdout.flush()
    print(f"\n[BLOCKED] {len(unsourced)} unsourced claim(s). Derivation only, never invent: "
          f"a claim you cannot source gets REMOVED, not reworded. If the fact is real, put "
          f"it in docs/client-config.yml in a human PR first.", file=sys.stderr)
    return UNSOURCED_EXIT


if __name__ == "__main__":
    sys.exit(main())
