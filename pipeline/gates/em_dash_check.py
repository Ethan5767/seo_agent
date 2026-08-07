#!/usr/bin/env python3
"""
em-dash-check.py — no em dashes in public-viewable copy (Lesson 10 / hard rule).

The house style bans the em dash (— / U+2014) in anything a visitor or a crawler
reads. LLM-written copy constantly drifts em dashes back in, so this gate greps
the BUILT HTML (the final served bytes), not the source, and fails loud with the
exact file + line.

What counts as public text:
    Everything OUTSIDE <script> and <style> blocks. That deliberately excludes:
      - JSON-LD structured data (<script type="application/ld+json">) — machine
        copy, and an em dash inside a JSON string there is not visitor-facing.
      - inline JS / CSS.
    Forms detected (all map to the same banned glyph):
      - literal U+2014  (—)
      - &mdash;
      - &#8212;  /  &#x2014;
    U+2013 (en dash) and U+2012/2015 are NOT flagged here (only the em dash is
    the house-style violation); add them with --also-en if desired.

Line numbers are preserved: <script>/<style> bodies are blanked in place (kept
as newlines) so reported line numbers match the real file.

BASELINEABLE — AND WHY (B-008)
------------------------------
An em dash in the client's PRE-EXISTING copy is legacy content debt, structurally
identical to a heading that is not in Title Case — and `check_headings` has been
baselineable all along. `NEVER_BASELINEABLE` is for live falsehoods (an invented
credential, a fix that never landed) and structural invariants (sitemap parity, an
orphaned route). A legacy em dash is neither.

This gate sat in NEITHER list, so `assert_baselineable` refused it as "not in the
allow-list", which left a legacy client's every PR permanently red with no
recording that could accept the debt. The cause was mechanical: it predates the
ratchet and printed `(line_no, context)` tuples, and the ratchet needs fingerprints.

It emits `Finding`s now. Fingerprint is (gate, code, out-relative file, the
OFFENDING TEXT) — the line number rides in `detail`, which is never fingerprinted,
so an unrelated edit above a legacy em dash does not turn it into a new finding.

Exit codes:
    0  no em dashes in public text (or none NEW, with --baseline)
    1  one or more found (lists file:line:context)

Usage:
    em-dash-check.py --out /tmp/acme/out
    em-dash-check.py --out ./out --also-en
    em-dash-check.py --out ./out --baseline docs/gate-baseline.json
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

from pipeline.lib import baseline as bl

GATE = "em_dash_check"
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

# glyph -> rule name. The rule name is part of the FINGERPRINT, so it must not
# change once a client has recorded a baseline. Held as one dict per dash rather
# than a list plus a parallel lookup: adding a form to a bare list without touching
# the lookup would silently file it as "other", collapsing two distinct rules into
# one fingerprint — in a gate that is now baselineable, which means a baseline entry
# accepting more than it was recorded for.
EM_RULES = {"—": "literal", "&mdash;": "mdash_entity", "&#8212;": "decimal_entity",
            "&#x2014;": "hex_entity", "&#X2014;": "hex_entity"}
EN_RULES = {"–": "en_literal", "&ndash;": "ndash_entity",
            "&#8211;": "en_decimal_entity", "&#x2013;": "en_hex_entity"}
EM_FORMS = list(EM_RULES)
EN_FORMS = list(EN_RULES)
RULES = {**EM_RULES, **EN_RULES}


def blank_keep_lines(match: re.Match) -> str:
    """Replace a script/style block with the same number of newlines."""
    return "\n" * match.group(0).count("\n")


def scan_file(path: str, forms: list[str]) -> list[tuple[int, str, str]]:
    """[(line_no, form, snippet)] for one file.

    The SNIPPET is the finding's identity — the surrounding copy is what a reviewer
    accepts or fixes, and it survives the line moving. The line number is reported
    but never fingerprinted.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        html = fh.read()
    stripped = SCRIPT_STYLE_RE.sub(blank_keep_lines, html)
    hits: list[tuple[int, str, str]] = []
    for i, line in enumerate(stripped.splitlines(), start=1):
        for form in forms:
            idx = line.find(form)
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(line), idx + len(form) + 40)
                hits.append((i, form, line[start:end].strip()))
                break
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail if em dashes appear in built public HTML.")
    ap.add_argument("--out", default="./out")
    ap.add_argument("--also-en", action="store_true", help="Also flag en dashes (U+2013)")
    bl.add_baseline_args(ap)
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        print(f"ERROR: out dir not found: {out_dir}", file=sys.stderr)
        return 1

    forms = list(EM_FORMS) + (EN_FORMS if args.also_en else [])
    files = sorted(glob.glob(os.path.join(out_dir, "**", "*.html"), recursive=True))

    findings = []
    for path in files:
        rel = Path(os.path.relpath(path, out_dir)).as_posix()
        for line_no, form, snippet in scan_file(path, forms):
            # code = the glyph form, so `&mdash;` and a literal — are separate rules
            # a reviewer can tell apart in the baseline file.
            findings.append(bl.Finding(GATE, f"em_dash.{RULES[form]}", rel,
                                       context=snippet,
                                       detail=f"line {line_no}: [{form}] …{snippet}…"))

    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    shown = verdict.blocking if args.baseline else findings
    for f in shown:
        print(f"  {f.location}: {f.detail}")

    print(f"em-dash-check: scanned {len(files)} HTML files")
    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        n_files = len({f.location for f in verdict.blocking})
        print(f"FAIL: {len(verdict.blocking)} {label}em dash(es) in public text "
              f"across {n_files} file(s).")
        return 1
    if args.baseline:
        print(f"PASS: no new em dashes ({len(verdict.preexisting)} pre-existing "
              f"accepted as legacy debt).")
        return 0
    print("PASS: no em dashes in public HTML text.")
    return 0



if __name__ == "__main__":
    sys.exit(main())
