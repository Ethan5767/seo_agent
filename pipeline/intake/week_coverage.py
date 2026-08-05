#!/usr/bin/env python3
"""pipeline.intake.week_coverage — which weeks of the month are DONE, per doc.

the operator's ask (2026-08-02, verbatim intent): "detect what weeks are done for the
month, what's missing still". The team delivers a month's content in WEEKLY
increments into one growing document — so "the doc changed" is usually a new
week landing, not a revision pass, and the useful question is coverage, not
diffing.

HOW WEEKS ARE MARKED (surveyed across all 7 real 2026 docs):
  5 of 7 use a Title-style divider line per week: "🗓️ Week 1" (April) or
  "🟥 Week 2" (July), including a "Week  1" double-space variant. 2 of 7
  (different authors) have NO week structure at all.

VERDICTS, per week between markers:
  DONE     >=1 page under the marker and a real word count
  PARTIAL  the marker exists but carries only a stub (words < --min-words)
  EMPTY    the marker exists with nothing under it (pre-scaffolded template)
  and any of Weeks 1-4 with no marker at all is reported MISSING.

A doc with NO markers is reported honestly as "no week structure" with its
page/word totals — never guessed into weeks.

Usage:
  week_coverage.py DOC.docx [DOC2.docx ...] [--json OUT] [--min-words 300]

Exit: 0 all listed docs have all 4 weeks DONE · 4 coverage gaps found ·
      2 usage/read error. (4 is informational, not a build gate.)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if __name__ == '__main__' and __package__ is None:  # see distill.py invocation caveat
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

WEEK_RE = re.compile(r'\bweek\s*([0-9]{1,2})\b', re.IGNORECASE)
#: One anchor line per page, tried in order — using several at once double-counts
#: (every July page carries BOTH 'Page Title' and 'Canonical URL'). 'SEO Meta' is
#: the A.Blueline convention; 'Meta Title'/'Slug:' are April's.
PAGE_ANCHORS = [re.compile(r'^Canonical URL\b', re.I), re.compile(r'^Page Title\b', re.I),
                re.compile(r'^Meta Title\b', re.I), re.compile(r'^SEO Meta\b', re.I),
                re.compile(r'^Slug:', re.I)]


def _page_anchor(paras):
    """The single busiest anchor style for THIS doc (never sum several)."""
    best = None
    for rx in PAGE_ANCHORS:
        n = sum(1 for _, t in paras if t and rx.match(t))
        if n and (best is None or n > best[1]):
            best = (rx, n)
    return best[0] if best else PAGE_ANCHORS[0]
EXPECTED_WEEKS = (1, 2, 3, 4)


def _is_week_marker(style: str, text: str) -> int | None:
    """Week number when this paragraph is a divider line, else None.
    Title-style and SHORT — a sentence merely mentioning 'week 2' is not a divider."""
    t = text.strip()
    if not t or len(t) > 60:
        return None
    m = WEEK_RE.search(t)
    if not m:
        return None
    if style == 'Title':
        return int(m.group(1))
    # tolerate a heading-styled divider whose line is essentially just the marker
    if style.startswith('Heading') and len(WEEK_RE.sub('', t).strip(' -—:🗓️🟥📅')) <= 6:
        return int(m.group(1))
    return None


def analyze(path: str, min_words: int = 300) -> dict:
    from docx import Document
    d = Document(path)
    paras = [(p.style.name, p.text.strip()) for p in d.paragraphs]

    markers: list[tuple[int, int]] = []          # (paragraph index, week number)
    for i, (style, text) in enumerate(paras):
        wk = _is_week_marker(style, text)
        if wk is not None:
            markers.append((i, wk))

    anchor = _page_anchor(paras)
    total_pages = sum(1 for _, t in paras if t and anchor.match(t))
    total_words = sum(len(t.split()) for _, t in paras if t)

    out = {'doc': Path(path).name, 'has_week_structure': bool(markers),
           'total_pages': total_pages, 'total_words': total_words, 'weeks': {}}
    if not markers:
        return out

    # slice content between consecutive markers
    bounds = markers + [(len(paras), None)]
    for (start, wk), (end, _) in zip(bounds, bounds[1:]):
        seg = paras[start + 1:end]
        pages = sum(1 for _, t in seg if t and anchor.match(t))
        words = sum(len(t.split()) for _, t in seg if t)
        if pages >= 1 and words >= min_words:
            status = 'DONE'
        elif words > 40:
            status = 'PARTIAL'
        else:
            status = 'EMPTY'
        # a repeated week marker (rare) keeps the fuller measurement
        prev = out['weeks'].get(wk)
        cur = {'pages': pages, 'words': words, 'status': status}
        if not prev or (cur['words'] > prev['words']):
            out['weeks'][wk] = cur

    for wk in EXPECTED_WEEKS:
        out['weeks'].setdefault(wk, {'pages': 0, 'words': 0, 'status': 'MISSING'})
    out['weeks'] = {k: out['weeks'][k] for k in sorted(out['weeks'])}
    return out


def render(r: dict) -> str:
    lines = [f"{r['doc']}"]
    if not r['has_week_structure']:
        lines.append(f"  no week structure — {r['total_pages']} pages, "
                     f"{r['total_words']} words total (delivery cadence not markable)")
        return '\n'.join(lines)
    icons = {'DONE': '✅', 'PARTIAL': '🟡', 'EMPTY': '⬜', 'MISSING': '❌'}
    for wk, w in r['weeks'].items():
        lines.append(f"  week {wk}: {icons[w['status']]} {w['status']:8}"
                     f" {w['pages']:>2} pages, {w['words']:>5} words")
    missing = [str(k) for k, w in r['weeks'].items() if w['status'] != 'DONE']
    lines.append(f"  -> {'ALL 4 WEEKS DONE' if not missing else 'still open: week ' + ', '.join(missing)}")
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Which weeks of the month are done, per doc.")
    ap.add_argument('docs', nargs='+')
    ap.add_argument('--json', dest='json_out')
    ap.add_argument('--min-words', type=int, default=300,
                    help="words for a week to count as DONE (default 300)")
    args = ap.parse_args()

    results, gaps = [], False
    for p in args.docs:
        try:
            r = analyze(p, args.min_words)
        except Exception as e:
            print(f"[FAIL] {p}: {e}", file=sys.stderr)
            return 2
        results.append(r)
        print(render(r))
        if r['has_week_structure'] and any(
                w['status'] != 'DONE' for w in r['weeks'].values()):
            gaps = True
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2))
    return 4 if gaps else 0


if __name__ == '__main__':
    sys.exit(main())
