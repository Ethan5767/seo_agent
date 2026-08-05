#!/usr/bin/env python3
"""
fingerprint-check.py — invisible-character / generator-fingerprint scrub (T07).

Copy pasted out of an LLM web app routinely carries invisible steganographic
characters — zero-width spaces, bidirectional-override controls, and Unicode
"tag" characters (U+E0000..U+E007F) — plus tool markers like a
`data-generated-by` attribute. These survive every normal review because they
render to nothing, and a hidden run can also mark exactly where a downstream
scan should skip.

THIS IS THE ONE GATE THAT SCANS RAW BYTES AND DOES **NOT** STRIP <script>/<style>.
Every other built-HTML gate blanks those blocks; here we must not, because the
fingerprint's whole purpose is to hide in the regions other scans ignore. We read
the file's raw bytes, decode UTF-8, and inspect every codepoint.

A single leading BOM (U+FEFF at byte offset 0) is tolerated — legitimate editors
emit it. Any OTHER U+FEFF (a second one, or one mid-file) is a violation.

What is flagged (file:line:col + U+XXXX NAME):
    - zero-width & word-joiner:   U+200B U+200C U+200D U+2060 U+FEFF(non-leading)
      U+2061..U+2064 (invisible math operators), U+180E, U+00AD (soft hyphen)
    - bidi controls:              U+200E U+200F U+061C U+202A..U+202E U+2066..U+2069
    - Unicode tag block:          U+E0000..U+E007F  (tag chars, incl. TAG SPACE)
    - generator markers (regex):  data-generated-by  (+ any via --extra-markers)

Exit codes:
    0  clean
    8  one or more fingerprints found

Usage:
    fingerprint-check.py --out ./out
    fingerprint-check.py --out ./out --extra-markers "data-gramm,x-ai-origin"
    fingerprint-check.py --out ./out --include "**/*.html,llms.txt"
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import unicodedata

BOM = 0xFEFF

INVISIBLE: set[int] = {
    0x200B, 0x200C, 0x200D, 0x2060,          # zero-width space / non-joiner / joiner / word joiner
    0x2061, 0x2062, 0x2063, 0x2064,          # invisible math operators
    0x00AD,                                  # soft hyphen
    0x180E,                                  # mongolian vowel separator
    0x061C,                                  # arabic letter mark
    0x200E, 0x200F,                          # LTR / RTL mark
}
INVISIBLE |= set(range(0x202A, 0x202F))      # LRE RLE PDF LRO RLO (+2F reserved)
INVISIBLE |= set(range(0x2066, 0x206A))      # LRI RLI FSI PDI
TAG_RANGE = range(0xE0000, 0xE0080)          # Unicode tag characters

# Generator/tool fingerprint markers. Kept deliberately tight so the gate stays
# green on legitimate content; extend per-run with --extra-markers.
DEFAULT_MARKERS = [
    r"data-generated-by",
]


def codepoint_label(cp: int) -> str:
    name = unicodedata.name(chr(cp), "UNASSIGNED/UNNAMED")
    return f"U+{cp:04X} {name}"


def scan_text(data: str) -> list[tuple[int, int, str]]:
    """Return [(line, col, label)] for every invisible/tag codepoint. Tolerates a
    single leading BOM. line/col are 1-indexed and count the BOM as column 1 of
    line 1 so downstream columns stay truthful."""
    hits: list[tuple[int, int, str]] = []
    line = 1
    col = 0
    for idx, ch in enumerate(data):
        cp = ord(ch)
        if ch == "\n":
            line += 1
            col = 0
            continue
        col += 1
        if cp == BOM:
            if idx == 0:
                continue  # tolerate a single leading BOM
            hits.append((line, col, codepoint_label(cp) + " (unexpected non-leading BOM)"))
            continue
        if cp in INVISIBLE or cp in TAG_RANGE:
            hits.append((line, col, codepoint_label(cp)))
    return hits


def scan_markers(data: str, markers: list[re.Pattern]) -> list[tuple[int, int, str]]:
    hits: list[tuple[int, int, str]] = []
    for rx in markers:
        for m in rx.finditer(data):
            line = data.count("\n", 0, m.start()) + 1
            line_start = data.rfind("\n", 0, m.start()) + 1
            col = m.start() - line_start + 1
            hits.append((line, col, f"generator marker /{rx.pattern}/ -> {m.group(0)!r}"))
    return hits


def scan_file(path: str, markers: list[re.Pattern]) -> list[tuple[int, int, str]]:
    with open(path, "rb") as fh:
        raw = fh.read()
    data = raw.decode("utf-8", errors="replace")
    hits = scan_text(data) + scan_markers(data, markers)
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail on invisible/fingerprint chars in built deliverables (raw-byte scan).")
    ap.add_argument("--out", default="./out")
    ap.add_argument("--include", default="**/*.html",
                    help="Comma-separated globs (relative to --out) to scan. Default: **/*.html")
    ap.add_argument("--extra-markers", default="",
                    help="Comma-separated extra generator-marker regexes to flag.")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        print(f"ERROR: out dir not found: {out_dir}", file=sys.stderr)
        return 1

    marker_src = list(DEFAULT_MARKERS)
    marker_src += [m.strip() for m in args.extra_markers.split(",") if m.strip()]
    markers = [re.compile(p, re.IGNORECASE) for p in marker_src]

    files: list[str] = []
    for pat in (g.strip() for g in args.include.split(",") if g.strip()):
        files.extend(glob.glob(os.path.join(out_dir, pat), recursive=True))
    files = sorted({f for f in files if os.path.isfile(f)})

    total = 0
    flagged_files = 0
    for path in files:
        hits = scan_file(path, markers)
        if hits:
            flagged_files += 1
            rel = os.path.relpath(path, out_dir)
            for line, col, label in hits:
                total += 1
                print(f"  {rel}:{line}:{col}: {label}")

    print(f"fingerprint-check: scanned {len(files)} file(s) (raw bytes, no <script> strip)")
    if total:
        print(f"FAIL: {total} fingerprint hit(s) across {flagged_files} file(s).")
        return 8
    print("PASS: no invisible/fingerprint characters found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
