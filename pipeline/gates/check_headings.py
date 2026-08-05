#!/usr/bin/env python3
"""
check-headings.py — heading casing hygiene gate (T07).

Historically flagged 4+ times: an emitter dropping a lowercase / sentence-broken
heading like a bare `our services` H2, or `the best roofers`, into otherwise
proper copy. This gate scans the BUILT HTML (the final served bytes, like
em-dash-check.py) and fails loud with file:line on any heading whose casing is
broken.

Two modes:

  DEFAULT (lenient) — the fleet-safe default. A heading FAILS only when its
    first significant word is not capitalized (e.g. `our services`,
    `the best roofers`) or the heading is entirely lowercase. Intentional
    sentence-case marketing headlines ("Arden weather is brutal. Your roof
    should not be the weak link.") PASS, because their voice is deliberate and
    they start with a capital. This is what keeps the gate usable across the
    whole heterogeneous fleet instead of red-gating every page.

  --strict (full Title Case) — opt-in for clients whose house style mandates
    Title-Case headings. Every significant (non-stopword) word must be
    capitalized; short stopwords (a/an/the/in/of/for/and/or/...) may be
    lowercase mid-heading; the first and last word are always required capital.
    Acronyms (GAF), numbers (24/7), and brand camelCase (iPhone) are exempt in
    both modes. Enable per-client via `headings.strict_title_case: true` in
    docs/client-config.yml when --project is given.

Everything OUTSIDE <script>/<style> is scanned; those blocks are blanked
line-preserving (same masking as em-dash-check.py) so reported line numbers
match the real file. HTML entities in heading text are unescaped before checking
(`Siding &amp; Exteriors` -> `Siding & Exteriors`).

Exit codes:
    0  all headings properly cased
    1  one or more heading-casing violations (lists file:line)

Usage:
    check-headings.py --out ./out
    check-headings.py --out ./out --strict
    check-headings.py --out ./out --strict --extra-stopwords "than,onto"
    check-headings.py --out ./out --project /path/to/client   # read config block
"""
from __future__ import annotations

import argparse
import glob
import html as htmlmod
import os
import re
import sys
from pathlib import Path

from pipeline.lib import baseline as bl

GATE = "check_headings"

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
HEADING_RE = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")

# Short words that Title Case leaves lowercase when they fall mid-heading.
DEFAULT_STOPWORDS = {
    "a", "an", "the", "and", "or", "nor", "but", "for", "of", "to", "in", "on",
    "at", "by", "with", "from", "as", "per", "via", "vs", "into", "onto", "over",
    "up", "off", "out", "so", "yet", "if", "than", "then",
}

# Punctuation stripped off the edges of a token before casing analysis.
_EDGE = ".,:;!?\"'()[]{}—–-&/…“”‘’"


def blank_keep_lines(match: "re.Match") -> str:
    return "\n" * match.group(0).count("\n")


def is_exempt(word: str) -> bool:
    """A word whose casing the gate never judges:
        - contains a digit           (24/7, 5,000+, GAF-2000)
        - is an all-caps acronym      (GAF, HVAC, TPO)
        - is brand camelCase          (iPhone, eBook) — uppercase after pos 0
        - has no leading alpha char   (&, •, 100%)
    """
    if any(ch.isdigit() for ch in word):
        return True
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return True
    if all(c.isupper() for c in letters):
        return True
    if any(c.isupper() for c in word[1:]):  # camelCase / brand casing
        return True
    return False


def tokenize(text: str) -> list[str]:
    toks = []
    for raw in text.split():
        w = raw.strip(_EDGE).strip()
        if w:
            toks.append(w)
    return toks


def lenient_violation(text: str) -> str | None:
    """Fail only on a clearly-broken heading: uncapitalized first word, or an
    entirely-lowercase heading. Sentence-case marketing copy passes."""
    toks = tokenize(text)
    if not toks:
        return None
    first = toks[0]
    if not is_exempt(first) and first[:1].islower():
        return f"first word '{first}' is not capitalized"
    if not any(c.isupper() for c in text if c.isalpha()):
        return "heading is entirely lowercase"
    return None


def strict_violation(text: str, stopwords: set[str]) -> str | None:
    """Full Title Case: every significant word capitalized; stopwords may be
    lowercase only when they are neither the first nor the last word."""
    toks = tokenize(text)
    if not toks:
        return None
    last = len(toks) - 1
    bad = []
    for i, w in enumerate(toks):
        if is_exempt(w):
            continue
        if w[:1].isupper():
            continue
        # w starts lowercase
        if 0 < i < last and w.lower() in stopwords:
            continue  # allowed lowercase stopword mid-heading
        bad.append(w)
    if bad:
        return f"not Title Case; lowercase word(s): {bad}"
    return None


def _load_config_headings(project: str) -> dict:
    """Best-effort read of the `headings:` block from docs/client-config.yml via
    the shared common.load_config helper. Degrades silently to {} if the helper
    or the key is absent (never KeyError)."""
    try:
        from pipeline.lib.common import load_config  # type: ignore
        cfg = load_config(project) or {}
        block = cfg.get("headings")
        return block if isinstance(block, dict) else {}
    except SystemExit:
        return {}
    except Exception:
        return {}


def scan_file(path: str, strict: bool, stopwords: set[str]) -> list[tuple[int, str, str]]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        html = fh.read()
    stripped = SCRIPT_STYLE_RE.sub(blank_keep_lines, html)
    hits: list[tuple[int, str, str]] = []
    for m in HEADING_RE.finditer(stripped):
        text = htmlmod.unescape(TAG_RE.sub(" ", m.group(2)))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        reason = strict_violation(text, stopwords) if strict else lenient_violation(text)
        if reason:
            line_no = stripped.count("\n", 0, m.start()) + 1
            hits.append((line_no, text, reason))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail on broken heading casing in built HTML.")
    ap.add_argument("--out", default="./out")
    ap.add_argument("--strict", action="store_true",
                    help="Enforce full Title Case (default: lenient first-word-capitalized).")
    ap.add_argument("--extra-stopwords", default="",
                    help="Comma-separated extra lowercase-allowed stopwords (strict mode).")
    ap.add_argument("--project", default=None,
                    help="Client dir; reads optional headings.{strict_title_case,extra_stopwords}.")
    bl.add_baseline_args(ap)
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        print(f"ERROR: out dir not found: {out_dir}", file=sys.stderr)
        return 1

    strict = args.strict
    stopwords = set(DEFAULT_STOPWORDS)
    stopwords.update(s.strip().lower() for s in args.extra_stopwords.split(",") if s.strip())

    if args.project:
        block = _load_config_headings(args.project)
        if block.get("strict_title_case"):
            strict = True
        extra = block.get("extra_stopwords") or []
        if isinstance(extra, str):
            extra = re.split(r"[,\s]+", extra)
        stopwords.update(s.strip().lower() for s in extra if isinstance(s, str) and s.strip())

    files = sorted(glob.glob(os.path.join(out_dir, "**", "*.html"), recursive=True))
    findings = []
    for path in files:
        rel = os.path.relpath(path, out_dir)
        # Fingerprint on (gate, reason, out-relative file, HEADING TEXT). The line
        # number is excluded — it moves on every unrelated edit. The heading text IS
        # the finding, so it is the context; whitespace is normalized but CASE is
        # preserved, since casing is precisely what this gate judges.
        for line_no, text, reason in scan_file(path, strict, stopwords):
            findings.append(bl.Finding(GATE, reason, Path(rel).as_posix(), context=text,
                                       detail=f"line {line_no}: {text!r}"))

    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    shown = verdict.blocking if args.baseline else findings
    for f in shown:
        print(f"  {f.location}: [{f.code}] {f.detail}")

    mode = "strict Title-Case" if strict else "lenient"
    print(f"check-headings ({mode}): scanned {len(files)} HTML file(s)")
    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        n_files = len({f.location for f in verdict.blocking})
        print(f"FAIL: {len(verdict.blocking)} {label}heading-casing violation(s) across {n_files} file(s).")
        return 1
    if args.baseline:
        print(f"PASS: no new heading-casing violations ({len(verdict.preexisting)} pre-existing accepted as legacy debt).")
        return 0
    print("PASS: all headings properly cased.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
