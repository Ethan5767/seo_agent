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

Exit codes:
    0  no em dashes in public text
    1  one or more found (lists file:line:context)

Usage:
    em-dash-check.py --out /tmp/acme/out
    em-dash-check.py --out ./out --also-en
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

EM_FORMS = ["—", "&mdash;", "&#8212;", "&#x2014;", "&#X2014;"]
EN_FORMS = ["–", "&ndash;", "&#8211;", "&#x2013;"]


def blank_keep_lines(match: re.Match) -> str:
    """Replace a script/style block with the same number of newlines."""
    return "\n" * match.group(0).count("\n")


def scan_file(path: str, forms: list[str]) -> list[tuple[int, str]]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        html = fh.read()
    stripped = SCRIPT_STYLE_RE.sub(blank_keep_lines, html)
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(stripped.splitlines(), start=1):
        for form in forms:
            idx = line.find(form)
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(line), idx + len(form) + 40)
                snippet = line[start:end].strip()
                hits.append((i, f"[{form}] …{snippet}…"))
                break
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail if em dashes appear in built public HTML.")
    ap.add_argument("--out", default="./out")
    ap.add_argument("--also-en", action="store_true", help="Also flag en dashes (U+2013)")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        print(f"ERROR: out dir not found: {out_dir}", file=sys.stderr)
        return 1

    forms = list(EM_FORMS) + (EN_FORMS if args.also_en else [])
    files = sorted(glob.glob(os.path.join(out_dir, "**", "*.html"), recursive=True))

    total = 0
    flagged_files = 0
    for path in files:
        hits = scan_file(path, forms)
        if hits:
            flagged_files += 1
            rel = os.path.relpath(path, out_dir)
            for line_no, ctx in hits:
                total += 1
                print(f"  {rel}:{line_no}: {ctx}")

    print(f"em-dash-check: scanned {len(files)} HTML files")
    if total:
        print(f"FAIL: {total} em dash(es) in public text across {flagged_files} file(s).")
        return 1
    print("PASS: no em dashes in public HTML text.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
