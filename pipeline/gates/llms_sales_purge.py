#!/usr/bin/env python3
"""
llms-sales-purge.py — keep sales / CTA language out of llms.txt (T07, §30 half).

llms.txt is a FACTUAL machine-readable brief for AI engines: who the business is,
what it does, where, and the canonical URL list. Marketing / call-to-action copy
("call now", "contact us today for a free quote") pollutes that signal and reads
as spam to a citation engine. parity-check.py already covers llms.txt existence
and URL parity; this gate covers the missing half — purging sales language.

Matching is WORD-BOUNDARY anchored (\\bphrase\\b, whitespace inside a phrase
matches any run of whitespace), so:
    - `book` does NOT match inside `notebook`
    - `call now` matches `Call now!` (case-insensitive, trailing punctuation ok)

The default blocklist is intentionally conservative — only unambiguous CTA
phrasing — so factual copy like "Free inspections", "no obligation",
"Military and first responder discounts" or "Financing options available" stays
clean. Add client-specific terms with --extra-phrases (or a
`llms.sales_blocklist:` list in docs/client-config.yml via --project).

Exit codes:
    0  llms.txt clean (or absent — parity-check owns existence)
    1  one or more sales/CTA phrases found (lists file:line:col + phrase)

Usage:
    llms-sales-purge.py --out ./out
    llms-sales-purge.py --llms ./public/llms.txt
    llms-sales-purge.py --out ./out --extra-phrases "limited spots,call jake"
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from pipeline.lib import baseline as bl

GATE = "llms_sales_purge"

# Conservative CTA / sales blocklist. Verified to leave a real factual roofing
# llms.txt (Acme) green. Multi-word entries match across any whitespace run.
DEFAULT_BLOCKLIST = [
    "call now", "call today", "call us", "call jake",
    "book",                       # \bbook\b — will NOT hit 'notebook'
    "book now", "book online",
    "schedule now", "schedule today", "schedule your appointment",
    "sign up", "signup",
    "buy now", "order now", "shop now", "act now",
    "get started", "get a quote", "get your free quote",
    "request a quote", "free quote",
    "contact us", "reach out",
    "limited time", "limited spots", "don't wait", "hurry", "today only",
    "special offer", "exclusive offer", "best price", "lowest price",
    "click here", "learn more today",
]


def compile_phrase(phrase: str) -> re.Pattern:
    """Word-boundary-anchored, case-insensitive; internal spaces -> \\s+."""
    escaped = re.escape(phrase.strip())
    escaped = re.sub(r"\\?\s+", r"\\s+", escaped)  # collapse escaped/literal spaces
    return re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)


def _load_config_blocklist(project: str) -> list[str]:
    """Best-effort read of llms.sales_blocklist from docs/client-config.yml via
    the shared common.load_config helper. Degrades to [] (never KeyError)."""
    try:
        from pipeline.lib.common import load_config  # type: ignore
        cfg = load_config(project) or {}
        block = (cfg.get("llms") or {}).get("sales_blocklist") or []
        return [p for p in block if isinstance(p, str) and p.strip()]
    except SystemExit:
        return []
    except Exception:
        return []


def resolve_llms(out_dir: str, explicit: str | None) -> str:
    if explicit:
        return os.path.abspath(explicit)
    for cand in (os.path.join(out_dir, "llms.txt"),
                 os.path.join(os.path.dirname(out_dir), "public", "llms.txt")):
        if os.path.exists(cand):
            return cand
    return os.path.join(out_dir, "llms.txt")


def scan(llms_file: str, patterns: list[tuple[str, re.Pattern]]) -> list[tuple[int, int, str, str]]:
    with open(llms_file, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    hits: list[tuple[int, int, str, str]] = []
    for line_no, line in enumerate(lines, start=1):
        for phrase, rx in patterns:
            for m in rx.finditer(line):
                col = m.start() + 1
                snippet = line.strip()[:100]
                hits.append((line_no, col, phrase, snippet))
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail if sales/CTA language appears in llms.txt.")
    ap.add_argument("--out", default="./out")
    ap.add_argument("--llms", default=None, help="Explicit path to llms.txt.")
    ap.add_argument("--extra-phrases", default="",
                    help="Comma-separated extra phrases to block.")
    ap.add_argument("--project", default=None,
                    help="Client dir; reads optional llms.sales_blocklist from config.")
    bl.add_baseline_args(ap)
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    llms_file = resolve_llms(out_dir, args.llms)

    if not os.path.exists(llms_file):
        # parity-check owns existence; nothing to purge here.
        print(f"llms-sales-purge: no llms.txt at {llms_file} (skipping — parity-check owns existence).")
        return 0

    phrases = list(DEFAULT_BLOCKLIST)
    phrases += [p.strip() for p in args.extra_phrases.split(",") if p.strip()]
    if args.project:
        phrases += _load_config_blocklist(args.project)
    # dedupe, preserve order
    seen, ordered = set(), []
    for p in phrases:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(p)
    patterns = [(p, compile_phrase(p)) for p in ordered]

    hits = scan(llms_file, patterns)
    rel = os.path.relpath(llms_file)
    # Fingerprint on (gate, blocked phrase, file, the LINE'S TEXT). Line and column
    # numbers are excluded — reordering the URL list in llms.txt moves every hit
    # without changing a single one of them. The line text is the stable identity of
    # WHICH occurrence this is, so two different lines carrying "call now" stay two
    # distinct findings, and editing that line's copy correctly retires the entry.
    findings = [
        bl.Finding(GATE, f"llms_sales.{phrase}", "llms.txt", context=snippet,
                   detail=f"{rel}:{line_no}:{col}: [{phrase}]  {snippet}")
        for line_no, col, phrase, snippet in hits
    ]
    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    print(f"llms-sales-purge: scanned {rel} against {len(patterns)} blocked phrase(s)")
    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        for f in verdict.blocking:
            print(f"  {f.detail}")
        print(f"FAIL: {len(verdict.blocking)} {label}sales/CTA phrase hit(s) in llms.txt.")
        return 1
    if args.baseline:
        print(f"PASS: no new sales/CTA phrases ({len(verdict.preexisting)} pre-existing accepted as legacy debt).")
        return 0
    print("PASS: llms.txt free of sales/CTA language.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
