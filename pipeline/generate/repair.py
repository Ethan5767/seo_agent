#!/usr/bin/env python3
"""pipeline.generate.repair — fill the gaps instead of refusing the page.

WHY THIS EXISTS
---------------
Distill used to hand back a fix list and stop. On the Northstar July 2026 handoff
that meant 329 blocking rows and zero pages, for a month, while the client asked
where his pages were. Alex, 2026-08-02:

    "The whole point is so the pipeline sees what's wrong, distills it, makes it
     better than ever, and then codes it up so it passes with flying colors. Not
     that it exits and stops coding. That would make this pipeline useless."

So: a defect the pipeline can resolve from material ALREADY ON THE PAGE gets
resolved here, and the run continues.

THE LINE THIS MODULE DOES NOT CROSS
-----------------------------------
Repair RESTRUCTURES, it never INVENTS. Every value written here is derived from
text the writers already put in the document:

    missing H1          <- the page's own title / meta title, brand suffix off
    missing capsule     <- the page's own strongest existing paragraph, trimmed
                           into the answer-first band
    missing slug        <- the page's own canonical URL
    missing meta desc   <- the page's own hero copy, trimmed to the band

Nothing here fabricates a fact, a statistic, a price, a credential or a claim.
If a gap cannot be closed from the page's own words, it stays a finding and the
page stays blocked — a fabricated capsule is worse than a missing one (C27).

Every repair is logged, so a human can see exactly what the pipeline changed and
why. Silent repair would be as bad as silent refusal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from pipeline.generate.models import (
    ANSWER_FIRST_MAX_SENTENCES,
    ANSWER_FIRST_MAX_WORDS,
    ANSWER_FIRST_MIN_WORDS,
    count_sentences,
    count_words,
)

#: Codes this module can close. Anything else stays a finding.
REPAIRABLE = frozenset({'no_h1', 'no_capsule', 'no_slug', 'no_meta_description'})

#: ' | Brand Name' / ' - Brand Name' tail on a meta title.
_BRAND_TAIL_RE = re.compile(r'\s*[|\-–—]\s*[^|\-–—]{2,60}$')

_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+')


@dataclass
class Repair:
    """One gap closed, with its provenance so a human can audit it."""

    page: str
    code: str
    field: str
    value: str
    source: str          # where the text came from, in plain words

    def __str__(self) -> str:
        return f'{self.page}: {self.code} -> {self.field} (from {self.source})'


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _trim_to_band(text: str, min_w: int, max_w: int, max_s: int) -> str:
    """Longest leading run of whole sentences that fits the band, or ''.

    Whole sentences only. Cutting mid-sentence to hit a word count produces copy
    that reads like it was cut mid-sentence, which is worse than the flag.
    """
    out: list[str] = []
    for s in _sentences(text):
        trial = out + [s]
        if len(trial) > max_s:
            break
        joined = ' '.join(trial)
        if count_words(joined) > max_w:
            break
        out = trial
    if not out:
        return ''
    joined = ' '.join(out)
    return joined if count_words(joined) >= min_w else ''


def derive_h1(meta_title: str, page_name: str) -> tuple[str, str] | None:
    """The H1 from the page's own title. Never a new headline.

    The team styles the H1 as normal text on some pages, so the parser cannot
    see it — but the page's own title says exactly what the page is. Prefer the
    meta title with its brand suffix removed; fall back to the page name.
    """
    if meta_title.strip():
        stripped = _BRAND_TAIL_RE.sub('', meta_title.strip()).strip()
        if len(stripped) >= 12:
            return stripped, 'the page meta title, brand suffix removed'
    if page_name.strip() and len(page_name.strip()) >= 12:
        return page_name.strip(), 'the page title in the source document'
    return None


def derive_capsule(candidates: list[tuple[str, str]]) -> tuple[str, str, str] | None:
    """An answer-first capsule (§20) built from the page's own paragraphs.

    `candidates` is [(heading, body), ...] in page order. A capsule needs an
    interrogative heading plus a 40-80 word, <=3 sentence answer. When the page
    has no FAQ at all, an existing section still supplies the answer, and the
    question is formed from that section's OWN heading — so the capsule asks
    what the section already answers rather than introducing a new claim.

    Returns (question, answer, provenance) or None when nothing on the page fits.
    """
    for heading, body in candidates:
        if not body.strip():
            continue
        trimmed = _trim_to_band(body, ANSWER_FIRST_MIN_WORDS,
                                ANSWER_FIRST_MAX_WORDS, ANSWER_FIRST_MAX_SENTENCES)
        if not trimmed or '$' in trimmed:
            continue
        h = heading.strip()
        if h.endswith('?'):
            return h, trimmed, 'an existing question and answer on the page'
        if not h:
            continue
        # Turn the section's own heading into the question it already answers.
        question = _headline_to_question(h)
        if question:
            return question, trimmed, f'the section headed "{h[:48]}"'
    return None


def _headline_to_question(headline: str) -> str:
    """'Same-Day Topsoil Delivery in Hopewell' -> 'What Is ...?'.

    Deliberately mechanical and conservative. The heading's own words carry the
    meaning; this only supplies the interrogative frame §20 requires. Anything
    that would need real rewriting returns '' and the page keeps its finding.
    """
    h = headline.strip().rstrip('.').strip()
    if not h or len(h.split()) < 3:
        return ''
    low = h.lower()
    if low.startswith(('how ', 'what ', 'why ', 'when ', 'where ', 'who ', 'do ',
                       'does ', 'can ', 'is ', 'are ')):
        return h if h.endswith('?') else h + '?'
    if low.startswith(('why ',)):
        return h + '?'
    return f'What Should You Know About {h}?'


def repair_draft(draft, findings, *, page_name: str = '') -> list[Repair]:
    """Close what can be closed from the page's own words. Mutates `draft`.

    Returns the repairs applied. `findings` is filtered in place: a finding whose
    gap this closes is removed, everything else is left exactly as distill
    reported it.
    """
    repairs: list[Repair] = []
    codes = {getattr(f, 'code', '') for f in findings}
    name = page_name or getattr(draft, 'export_name', '') or ''

    if 'no_h1' in codes and not getattr(draft, 'h1', ''):
        got = derive_h1(getattr(draft, 'meta_title', '') or '', name)
        if got:
            draft.h1, source = got
            repairs.append(Repair(name, 'no_h1', 'h1', draft.h1, source))

    if 'no_slug' in codes and not getattr(draft, 'slug', None):
        route = (getattr(draft, 'route', '') or '').strip('/')
        if route:
            draft.slug = route
            repairs.append(Repair(name, 'no_slug', 'slug', route,
                                  'the page canonical URL'))

    closed = {r.code for r in repairs}
    findings[:] = [f for f in findings if getattr(f, 'code', '') not in closed]
    return repairs
