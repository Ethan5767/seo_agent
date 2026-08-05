#!/usr/bin/env python3
"""pipeline.generate.distill — pass 1 (EXTRACT) + pass 2 (CLASSIFY / DISTILL).

    pass 1  EXTRACT   docx -> ordered RawBlocks -> per-page PageSegments
    pass 2  CLASSIFY  blocks -> Section / BuilderCall / Hero / FaqItem / Capsule
                      + a KEEP/TRIM/OPTIMIZE/DROP/BANK verdict per block (the ledger)
                      + CORE-BODY DISTILLATION to the 800-1500 band
    pass 3  EMIT      <- NOT here. `distill.py` produces List[PageDraft]; the
                      emitter serialises them with models.to_ts_entry().

Everything this module writes into a PageDraft is traceable to a DOCX block.
Nothing is invented: when the source cannot satisfy a constraint the module
records a ValidationFinding and moves on — it never fabricates a fact, a number,
an image path, or a sentence to make a gate go green.

The three deliberate NON-content exceptions, all presentational and all declared:
  * FontAwesome icon names (keyword map, safe default) — chrome, not copy.
  * The `<span>` wrapper the renderer needs around the H1 geo phrase.
  * Section `label` fallbacks when the DOCX omits `Section Label:`.

Usage
-----
    python3 pipeline/generate/distill.py DOCX --out drafts.json [--limit N]
    python3 pipeline/generate/distill.py DOCX --self-test

Exit codes
----------
    0  every page distilled clean
    1  distilled with curation flags for the operator's ledger (warn findings)
    2  usage / dependency error
    9  refused: at least one page carries a blocking finding
    16 refused: non-empty DOCX segmented to 0 pages — unrecognized handoff
       format (UnsegmentableDocxError); needs a parser update or template fix
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

if __name__ == '__main__' and __package__ is None:  # see models.py invocation caveat
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.generate.models import (  # noqa: E402
    ANSWER_FIRST_MAX_SENTENCES,
    ANSWER_FIRST_MAX_WORDS,
    ANSWER_FIRST_MIN_WORDS,
    BRIEF_MIN_FANOUT,
    BuilderCall,
    Capsule,
    CORE_WORDS_MAX,
    CORE_WORDS_MIN,
    CORE_WORDS_SWEET_SPOT,
    FaqItem,
    HERO_MAX_CHARS,
    HERO_MAX_SENTENCES,
    HERO_MAX_WORDS,
    Hero,
    HeroButton,
    KNOWN_METRO_HUBS,
    META_TITLE_MAX_EFFECTIVE,
    PageDraft,
    Section,
    SemanticTriple,
    SUBSERVICE_SUFFIX_RE,
    VALID_CARD_GRID_COUNTS,
    ValidationFinding,
    block,
    count_sentences,
    count_words,
    effective_len,
    recount_core_words,
    warn,
)
# TLDR_RE is defined once in validators.py, mirrored from capsule_check.TLDR_RE.
# Import it rather than restating the pattern so the emitter and the gate can
# never drift apart.
from pipeline.generate.validators import (  # noqa: E402
    META_DESC_MAX_EFFECTIVE as _META_DESC_MAX,
    META_DESC_MIN as _META_DESC_MIN,
    TLDR_RE,
)
from pipeline.generate.repo_layout import active as _rl_active  # noqa: E402

try:  # pipeline.lib.common is the config authority (C29). Optional at import time
    from pipeline.lib import common as _common
except Exception:  # pragma: no cover - only when run outside the repo
    _common = None


# ---------------------------------------------------------------------------
# Pass 1 — EXTRACT
# ---------------------------------------------------------------------------

#: DOCX `Title`-style paragraphs that are week separators, not pages.
_WEEK_RE = re.compile(r'^\W*week\s+\d+\W*$', re.I)

#: A standalone ALL-CAPS structural marker: 'HERO SECTION', 'ZIGZAG — RESIDENTIAL ROOFING'.
_MARKER_RE = re.compile(r"^[A-Z0-9 &/'\"\-–—:().]+$")

#: 'Label:' / 'Meta Title (58 chars):' / 'P (hero-sub):' prefixes the team uses.
#: The parenthetical is an author's note, never part of the field name.
_LABEL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /&'\-]{0,40}?)\s*(?:\([^)]{0,30}\))?\s*:\s*(.*)$")

#: 'Card 3 — Title  Body...' / 'Step 2 — Title  Body...' / 'Testimonial 1 — Title "..."'
_ENUM_RE = re.compile(r'^(Card|Step|Testimonial|Ext Card|ZZ Card)\s*(\d+)\s*[—–-]\s*(.*)$', re.I)

#: The team runs several labelled fields onto one line
#: ('H2: ... Subtitle: ...', 'Stat Badges: ... CTA Link: ...'). Split on this
#: CLOSED list only — a generic 'Word:' split would shred prose.
_INLINE_LABELS = (
    'Section Label', 'Subtitle', 'Hero Subheading', 'Trust Stats', 'Stats Block',
    'CTA Buttons', 'CTA Link', 'CTA', 'Stat Badges', 'Service Links', 'Service links',
    'Checklist', 'Perks', 'Military Note', 'Process Note', 'Why Stats', 'Finance Cards',
    'Area Cards', 'Featured Video', 'Badge', 'Body', 'Duration', 'Tag',
    'H1', 'H2', 'H3', 'P',
)
_INLINE_LABEL_RE = re.compile(
    r'(?<=[\s.!?)"”])(' + '|'.join(sorted((re.escape(l) for l in _INLINE_LABELS),
                                               key=len, reverse=True))
    + r'|Paragraph\s?\d?|Q\d)\s*(?:\(\d+\s*chars?\))?:\s'
)

#: 'Card 1 — 🏆 GAF Master Elite Contractor — body...'  (title/body em-dash split)
_ENUM_TITLE_SPLIT_RE = re.compile(r'\s+[—–]\s+')

#: Inline checklist / perk bullets: 'Checklist: ✅ a ✅ b ✅ c'
_BULLET_SPLIT_RE = re.compile(r'\s*(?:✅|✓|·|•)\s*')

_EMOJI_RE = re.compile(
    '[\U0001F000-\U0001FAFF←-⇿⌀-➿️⬀-⯿☀-⛿]'
)

#: forbidden_sweep hard blockers for Acme. Detected, never rewritten (C13).
_DOLLAR_RE = re.compile(r'\$\s?[0-9]')
_EMDASH_RE = re.compile(r'[—–]|&mdash;|&#8212;|&#x2014;', re.I)

#: fingerprint_check (C15) invisible codepoints.
_INVISIBLE_RE = re.compile(
    '[​-‏⁠-⁤­᠎؜‪-‮⁦-⁩﻿]'
)

#: Markers routed to the four shared builders under coverage_method builder-collapse.
_BUILDER_MARKERS = {
    'CERTIFICATIONS SECTION': 'certificationsSection',
    # Canonical, client-neutral marker (2026-08). The builder KEY stays
    # whyAcmeSection — it names Acme's shared builder component and only
    # Acme's emit consumes it; renaming the key is a client-repo migration,
    # not an engine decision. The legacy marker is kept as an alias because
    # existing Acme team docs write it explicitly.
    'WHY CHOOSE SECTION': 'whyAcmeSection',
    'WHY ACME SECTION': 'whyAcmeSection',
    'FINANCING SECTION': 'financingSection',
    'PROCESS SECTION': 'processSection',
    'OUR PROCESS SECTION': 'processSection',
}

#: Markers that carry no ServiceSection equivalent — banked with a reason.
_BANK_MARKERS = {
    'TOPBAR': 'site chrome, not page data',
    'FOOTER': 'site chrome, not page data',
    'VIDEO SECTION': 'no ServiceSection type for video; renderer has no video member',
    'VIDEO LIBRARY SECTION': 'no ServiceSection type for video',
    'SEO META TAGS': 'consumed as metaTitle / metaDescription / slug',
    'FULL PAGE CONTENT': 'structural divider',
    'CTA SECTION': 'CTA copy lives in hero.buttons; llms_sales_purge (C20) keeps it out of body',
}

_ICON_MAP = [
    ('inspect', 'fas fa-magnifying-glass'), ('emergency', 'fas fa-triangle-exclamation'),
    ('storm', 'fas fa-cloud-bolt'), ('insurance', 'fas fa-file-invoice'),
    ('replace', 'fas fa-arrows-rotate'), ('repair', 'fas fa-wrench'),
    ('siding', 'fas fa-house-chimney-window'), ('gutter', 'fas fa-cloud-rain'),
    ('soffit', 'fas fa-fan'), ('fascia', 'fas fa-ruler-horizontal'),
    ('commercial', 'fas fa-city'), ('financ', 'fas fa-credit-card'),
    ('warrant', 'fas fa-shield-halved'), ('certif', 'fas fa-award'),
    ('roof', 'fas fa-house'),
]
_ICON_DEFAULT = 'fas fa-house'


@dataclass
class RawBlock:
    """One body-order element of the DOCX, with its structural context resolved."""

    index: int                     # position in document body order
    kind: str                      # 'paragraph' | 'table'
    style: str                     # 'normal' | 'Title' | 'Heading 1'..
    text: str = ''
    rows: list[list[str]] = field(default_factory=list)
    marker: str = ''               # enclosing ALL-CAPS section marker
    label: str = ''                # 'Paragraph 1', 'H2', 'Q3', ...
    value: str = ''                # text after 'Label:'

    @property
    def body(self) -> str:
        return self.value if self.label else self.text


@dataclass
class PageSegment:
    """All RawBlocks belonging to one page, plus the DOCX heading that opened it."""

    name: str
    start: int
    blocks: list[RawBlock] = field(default_factory=list)

    def source_ref(self, docx_path: str) -> str:
        return f'{Path(docx_path).name}#{self.name}@p{self.start}'


def _clean(text: str) -> str:
    """Whitespace-normalise. Emoji and em dashes are LEFT IN so pass 2 can see
    and report them — scrubbing here would hide a real forbidden_sweep hit."""
    return re.sub(r'\s+', ' ', text.replace('\xa0', ' ')).strip()


#: Single-segment slugs that are pages about the SITE, not about a market.
#: These take the client's primary (HQ) state instead of blocking on
#: state-attribution, because they are not attributed to any market at all.
_SITE_LEVEL_SLUGS = frozenset({
    'faq', 'about', 'about-us', 'contact', 'contact-us', 'services', 'careers',
    'blog', 'gallery', 'reviews', 'testimonials', 'financing',
    'privacy-policy', 'terms', 'sitemap',
})

#: A bare URL or root-relative path alone on a line. `_LABEL_RE` matches
#: 'https://northstar.example.com/x/' as label='https', so a URL written on the
#: line below its 'URL:' label looked like the next labelled field and stopped
#: the continuation scan — the one value most likely to be written that way.
_BARE_URL_RE = re.compile(r'^(?:https?://|/)\S*$', re.I)


#: Word's built-in heading styles -> the label the marker vocabulary expects.
_STYLE_HEADING_LEVELS = {'Heading 1': 'H1', 'Heading 2': 'H2', 'Heading 3': 'H3'}


def _adopt_style_headings(blocks: list[RawBlock]) -> list[RawBlock]:
    """Treat Word's real heading STYLES as H1/H2/H3 when no `H1:` label exists.

    Writers using Word's heading styles never type the literal string 'H1:', so
    `h1` resolved empty and `no_h1` fired on every page. It cascades three ways:

      * hero resolution scans for the first unlabelled paragraph AFTER the H1,
        so a missed H1 produced a false `no_hero_copy` on the same page — the
        two findings always appeared together, 32 and 32 on the Northstar June doc;
      * `normalize_heading_page` only treats a heading as a SECTION BOUNDARY
        when it carries an H-level, so with H2/H3 unlabelled every block on the
        page stayed under the opening 'HERO SECTION' marker, `_grouped` found
        no INTRO or named sections, and the page distilled to ZERO sections;
      * with no sections there is no core body, so all 33 Northstar pages reported
        `core_words=0` against the 800-1500 band and distill exited 9.

    Only applied when the document labels NO h1 anywhere, so a handoff that
    genuinely uses 'H1:' (Acme) keeps its existing behaviour byte-for-byte.
    """
    if any(b.label.strip().lower() == 'h1' or b.text.startswith('H1:') for b in blocks):
        return blocks
    for b in blocks:
        level = _STYLE_HEADING_LEVELS.get(b.style)
        if level and b.kind == 'paragraph' and not b.label and b.text.strip():
            b.label, b.value = level, b.text.strip()
    return blocks


def read_docx_blocks(path: str) -> list[RawBlock]:
    """Pass 1. Walk the DOCX body in true document order (python-docx's
    `.paragraphs` silently omits tables, which is where every stats bar and
    service grid in this file lives)."""
    try:
        import docx  # type: ignore
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:  # pragma: no cover
        print('[ERROR] python-docx required. pip install "python-docx>=1.1"', file=sys.stderr)
        raise SystemExit(2)

    document = docx.Document(path)
    blocks: list[RawBlock] = []
    marker = ''
    for i, child in enumerate(document.element.body.iterchildren()):
        tag = child.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            para = Paragraph(child, document)
            text = _clean(para.text)
            if not text:
                continue
            style = para.style.name if para.style is not None else 'normal'
            probe = _EMOJI_RE.sub('', text).strip()
            if _is_marker(probe):
                marker = probe
                blocks.append(RawBlock(i, 'paragraph', style, text, marker=marker))
                continue
            inline = _split_inline_marker(text)
            if inline:
                marker, text = inline
            for chunk in _split_inline_labels(text):
                label, value = '', ''
                m = _LABEL_RE.match(chunk)
                if m and not _looks_like_prose_colon(m):
                    label, value = m.group(1).strip(), _clean(m.group(2))
                blocks.append(RawBlock(i, 'paragraph', style, chunk, marker=marker,
                                       label=label, value=value))
        elif tag == 'tbl':
            table = Table(child, document)
            rows = [[_clean(c.text) for c in r.cells] for r in table.rows]
            blocks.append(RawBlock(i, 'table', 'table', '', rows=rows, marker=marker))
    return _adopt_style_headings(blocks)


def _is_marker(text: str) -> bool:
    return (
        1 < len(text) < 60
        and bool(_MARKER_RE.match(text))
        and sum(c.isalpha() for c in text) > 3
        and not text.endswith(':')
    )


def _split_inline_marker(text: str) -> tuple[str, str] | None:
    """'HERO SECTION Badge: 📍 ...' — the team sometimes runs the marker into the
    first labelled line. Recover both halves."""
    for known in list(_BUILDER_MARKERS) + list(_BANK_MARKERS) + [
        'HERO SECTION', 'INTRO SECTION', 'EXTERIOR SERVICES SECTION',
        'STORM AND INSURANCE SECTION', 'STORM & INSURANCE SECTION',
        'TESTIMONIALS SECTION', 'FAQ SECTION', 'NEARBY AREAS SECTION',
        'ZIGZAG SERVICES SECTION',
    ]:
        if text.startswith(known + ' ') and len(text) > len(known) + 1:
            return known, text[len(known) + 1:].strip()
    # 'ZIGZAG — RESIDENTIAL ROOFING Section Label: Residential' — the zigzag
    # markers are open-ended, so match the family by prefix.
    m = re.match(r'^(ZIGZAG\s*[—–-]\s*[A-Z ]+?)\s+(?=[A-Z][a-z])', text)
    if m:
        return m.group(1).strip(), text[m.end():].strip()
    return None


def _split_inline_labels(text: str) -> list[str]:
    """'H2: Complete Exterior Services Subtitle: One contractor...' -> two chunks.

    Only the closed _INLINE_LABELS vocabulary triggers a split, and only when the
    label is not already at position 0."""
    cuts = [m.start() for m in _INLINE_LABEL_RE.finditer(text)]
    if not cuts:
        return [text]
    chunks: list[str] = []
    prev = 0
    for cut in cuts:
        piece = text[prev:cut].strip()
        if piece:
            chunks.append(piece)
        prev = cut
    tail = text[prev:].strip()
    if tail:
        chunks.append(tail)
    return chunks or [text]


def _looks_like_prose_colon(m: re.Match) -> bool:
    """'Paragraph 1: ...' is a label. 'Note that x: y' is prose. Labels are short,
    capitalised, and followed by content."""
    head = m.group(1)
    return len(head.split()) > 4


# ---------------------------------------------------------------------------
# PAGE-BOUNDARY CONVENTIONS  (the ONE place a new handoff format is taught)
# ---------------------------------------------------------------------------
# The content team's DOCX layout is NOT a stable contract — it has already
# drifted once (April 2026 -> July 2026) and will drift again. Every known way
# the team signals "a new page starts here" is registered here so that adding a
# future THIRD convention is a one-line addition, not a rewrite.
#
# Supported conventions, in the precedence order they are tried:
#
#   1. TITLE-STYLE            (April 2026)  -> _is_title_boundary
#      A paragraph in Word's built-in `Title` style, e.g. 'Matthews'. Week
#      dividers ('Week 1') share the style and are dropped by _WEEK_RE. The
#      Title block opens a page but is NOT part of the page's own blocks.
#
#   2. PAGE-TITLE marker     (July 2026)   -> _is_page_title_boundary
#      A plain-text line 'Page Title:' / 'Page Title (56 chars):'. The July doc
#      has NO `Title` style anywhere, so the page-title line is the only signal.
#      It IS part of the page (it carries the meta/page title value).
#
#   3. FULL-PAGE-CONTENT     (July 2026, structural backstop) -> _is_full_page_divider
#      The 'FULL PAGE CONTENT' divider, honoured as a boundary only when the doc
#      also carries an H1 and a canonical-URL line, so a stray divider cannot
#      mint an empty page.
#
# URL / slug LABEL SET — normalised so identity checks accept them
# interchangeably: 'Slug:', 'Canonical URL:', 'Canonical:', 'URL:' (see
# `_URL_LABELS`; build_draft's `_first_value(flat, 'canonical url', 'slug',
# 'url', 'canonical')` reads the same union).
#
# PRECEDENCE MATTERS — and is why this is not a naive "match ANY convention"
# OR. April ALSO contains a 'Page Title:' line immediately after each `Title`
# block; honouring PAGE-TITLE in a doc that already uses TITLE-STYLE would split
# every April page in two. So EXACTLY ONE convention is chosen per document: the
# first in this list that the document actually exhibits. That keeps April's
# output byte-for-byte identical while letting July (and future formats) parse.
_URL_LABELS = ('canonical url', 'canonical', 'slug', 'url')


def _is_title_boundary(b: RawBlock) -> bool:
    """Convention 1 — a `Title`-style paragraph that is not a week divider."""
    if not (b.kind == 'paragraph' and b.style == 'Title'):
        return False
    return not _WEEK_RE.match(_EMOJI_RE.sub('', b.text).strip())


def _is_page_title_boundary(b: RawBlock) -> bool:
    """Convention 2 — a 'Page Title:' / 'Page Title (NN chars):' marker line."""
    return b.kind == 'paragraph' and b.label.strip().lower() == 'page title'


def _is_full_page_divider(b: RawBlock) -> bool:
    """Convention 3 — the standalone 'FULL PAGE CONTENT' structural divider."""
    return (b.kind == 'paragraph'
            and _EMOJI_RE.sub('', b.text).strip().upper() == 'FULL PAGE CONTENT')


def _doc_has_h1_and_url(blocks: list[RawBlock]) -> bool:
    has_h1 = any(b.label.strip().lower() == 'h1' or b.text.startswith('H1:') for b in blocks)
    has_url = any(b.label.strip().lower() in _URL_LABELS for b in blocks)
    return has_h1 and has_url


def _page_name_after_divider(blocks: list[RawBlock], divider: RawBlock) -> str:
    """Convention 3 has no title of its own — name the page after the H1 that
    follows the divider."""
    seen = False
    for b in blocks:
        if b is divider:
            seen = True
            continue
        if not seen:
            continue
        if b.label.strip().lower() == 'h1' and b.value:
            return b.value.strip()
        if b.text.startswith('H1:'):
            return b.text[3:].strip()
    return 'Untitled Page'


def _segment_on_title_style(blocks: list[RawBlock]) -> list[PageSegment]:
    """Convention 1 (April 2026) — UNCHANGED from the original segment_pages, kept
    verbatim so April's segmentation is byte-for-byte identical. Split on
    `Title`-style paragraphs, dropping week dividers; the Title block opens a page
    and is not itself one of the page's blocks."""
    segments: list[PageSegment] = []
    current: PageSegment | None = None
    for b in blocks:
        if b.kind == 'paragraph' and b.style == 'Title':
            name = _EMOJI_RE.sub('', b.text).strip()
            if _WEEK_RE.match(name):
                current = None
                continue
            current = PageSegment(name=name, start=b.index)
            segments.append(current)
            continue
        if current is not None:
            current.blocks.append(b)
    return [s for s in segments if s.blocks]


def _segment_on_marker(blocks: list[RawBlock], is_boundary, name_of) -> list[PageSegment]:
    """Conventions 2 & 3 — the boundary is a marker line that lives INSIDE the
    page it opens (it carries the page title, or is the content divider), so
    unlike the Title-style path the boundary block IS added to its page."""
    segments: list[PageSegment] = []
    current: PageSegment | None = None
    for b in blocks:
        if is_boundary(b):
            current = PageSegment(name=name_of(b), start=b.index)
            segments.append(current)
        if current is not None:
            current.blocks.append(b)
    return [s for s in segments if s.blocks]


def segment_pages(blocks: list[RawBlock]) -> list[PageSegment]:
    """Split the block stream into per-page segments, tolerant of every handoff
    convention registered under PAGE-BOUNDARY CONVENTIONS above.

    EXACTLY ONE convention is applied per document — the first the document
    actually exhibits — so April's Title-style layout keeps segmenting
    byte-for-byte even though it also contains 'Page Title:' lines.

    Returns [] when NO convention matches. Callers MUST guard that with
    `assert_segmentable()` so a non-empty-but-unsegmentable DOCX fails loud
    instead of reporting a false all-clear (that was the July 2026 defect: a
    234-paragraph doc silently yielded 0 pages and every downstream stage called
    it 'clean')."""
    if any(_is_title_boundary(b) for b in blocks):
        return _drop_schema_segments(_segment_on_title_style(blocks))
    if any(_is_page_title_boundary(b) for b in blocks):
        return _drop_schema_segments(_segment_on_marker(
            blocks, _is_page_title_boundary, lambda b: (b.value or b.text).strip()))
    if any(_is_full_page_divider(b) for b in blocks) and _doc_has_h1_and_url(blocks):
        return _drop_schema_segments(_segment_on_marker(
            blocks, _is_full_page_divider,
            lambda b: _page_name_after_divider(blocks, b)))
    return []


#: A segment this JSON-dense is a pasted JSON-LD block, not a page.
_JSONLD_DENSITY = 0.5


def _is_schema_segment(segment: PageSegment) -> bool:
    """A pasted JSON-LD block that the Title-style splitter saw as a page.

    Northstar's handoff carries one 'Schema N' block per page — raw JSON-LD the
    writers include for reference. Sixteen of its thirty-three segments are
    these, and each one failed every page check it was never meant to face
    (no H1, no slug, no meta title, no capsule), so half the fix list described
    defects in something that is not a page. The emitted site builds its own
    schema from `src/schema/`, so the pasted copy is documentation.

    Identified by CONTENT, not by the name alone: a segment must both be named
    'Schema…' and actually be JSON-dense, so a real page that happens to be
    called 'Schema Markup Services' is never dropped.
    """
    name = segment.name.strip().lower()
    if not re.match(r'^schema\b', name):
        return False
    paras = [b for b in segment.blocks if b.kind == 'paragraph' and b.text.strip()]
    if len(paras) < 10:
        return False
    jsonish = sum(1 for b in paras
                  if re.match(r'^\s*[{\[\]}]|^\s*"[^"]+"\s*:', b.text))
    return jsonish / len(paras) >= _JSONLD_DENSITY


def _drop_schema_segments(segments: list[PageSegment]) -> list[PageSegment]:
    kept = [s for s in segments if not _is_schema_segment(s)]
    dropped = len(segments) - len(kept)
    if dropped:
        print(f'[SEGMENT] dropped {dropped} pasted JSON-LD block(s) — not pages '
              '(site builds its own schema)', file=sys.stderr)
    # Never let the filter empty the document: if every segment looked like
    # schema the detector is wrong, and assert_segmentable must still see them.
    return kept or segments


# ---------------------------------------------------------------------------
# FAIL-LOUD guard — a non-empty DOCX that segments to 0 pages is a PARSE FAILURE
# ---------------------------------------------------------------------------

#: Distinct exit code for an unrecognised handoff format (non-empty DOCX, 0
#: pages). 0-15 are claimed in docs/gate-reference.md's exit-code registry; 16
#: is the first free code above the fleet.
UNSEGMENTABLE_EXIT = 16

#: A document with at least this many non-empty paragraphs (or ANY heading) that
#: yields no pages is a parse failure, not a legitimately empty handoff.
_MIN_MEANINGFUL_PARAGRAPHS = 20


class UnsegmentableDocxError(RuntimeError):
    """A non-empty DOCX segmented to zero pages: its layout is not one that
    segment_pages recognises. Raised instead of silently returning [] so the
    pipeline FAILS LOUD (exit `UNSEGMENTABLE_EXIT`) rather than reporting a clean
    run that shipped nothing. Resolve by teaching segment_pages the new
    convention (see PAGE-BOUNDARY CONVENTIONS) or by fixing the DOCX template."""

    exit_code = UNSEGMENTABLE_EXIT


def assert_segmentable(blocks: list[RawBlock], segments: list[PageSegment], *,
                       source: str = '') -> None:
    """Refuse to treat a non-empty-but-unsegmentable DOCX as clean.

    A truly empty document (fewer than `_MIN_MEANINGFUL_PARAGRAPHS` non-empty
    paragraphs and no heading) still returns quietly — there is nothing to parse.
    Any richer document that produced 0 pages raises `UnsegmentableDocxError`."""
    if segments:
        return
    n_para = sum(1 for b in blocks
                 if b.kind == 'paragraph' and (b.body or b.text).strip())
    has_heading = any(b.kind == 'paragraph' and b.style.startswith('Heading')
                      for b in blocks)
    if n_para >= _MIN_MEANINGFUL_PARAGRAPHS or has_heading:
        where = f' ({Path(source).name})' if source else ''
        raise UnsegmentableDocxError(
            f'could not segment DOCX{where}: {n_para} non-empty paragraphs but 0 '
            'pages — unrecognized handoff format, needs a parser update or a '
            'template fix')


# ---------------------------------------------------------------------------
# Pass 2 helpers
# ---------------------------------------------------------------------------

def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s]


def hero_hook(paragraph: str) -> tuple[str, str]:
    """V1 / C21 hero-hook extraction (prototype emit_page.py, proven in Cycle H).

    Returns (hook, demoted). The hook satisfies <=25 words AND <=2 sentences AND
    <=160 chars; the remainder is demoted to body copy rather than deleted."""
    hook: list[str] = []
    rest: list[str] = []
    for s in _sentences(paragraph):
        candidate = ' '.join(hook + [s])
        if (not rest and len(hook) < HERO_MAX_SENTENCES
                and len(candidate) <= HERO_MAX_CHARS
                and count_words(candidate) <= HERO_MAX_WORDS):
            hook.append(s)
        else:
            rest.append(s)
    if not hook and _sentences(paragraph):
        # First sentence alone busts the rule: cut at the first clause boundary.
        # The team writes 'X trusts Acme for every project — from routine ...',
        # so an em/en dash is a clause boundary here as much as a comma is.
        first = _sentences(paragraph)[0]
        clause = re.split(r'\s+[—–]\s+|[,;:] ', first)[0]
        hook, rest = [clause.rstrip('.') + '.'], [first[len(clause):].strip()] + _sentences(paragraph)[1:]
    return ' '.join(hook), ' '.join(r for r in rest if r)


def _icon_for(text: str) -> str:
    low = text.lower()
    for needle, icon in _ICON_MAP:
        if needle in low:
            return icon
    return _ICON_DEFAULT


def _title_case_ok(heading: str) -> bool:
    small = {'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'in', 'nor', 'of',
             'on', 'or', 'the', 'to', 'up', 'vs', 'via', 'with', 'from'}
    words = re.findall(r"[A-Za-z']+", heading)
    return not [w for i, w in enumerate(words)
                if (i == 0 or w.lower() not in small) and w[0].islower()]


def _split_enum_title_body(rest: str) -> tuple[str, str]:
    """'GAF Master Elite Contractor GAF Master Elite status is awarded to...'
    The team runs card titles into card bodies. Two observed conventions:
      Week 1/2 : 'Card 1 — 🏆 Title — body'   (em-dash delimited)
      Week 3/4 : 'Card 1 — Title body'        (no delimiter)
    Prefer the explicit delimiter; fall back to the Title-Case run heuristic."""
    rest = _EMOJI_RE.sub('', rest).strip()
    delimited = _ENUM_TITLE_SPLIT_RE.split(rest, maxsplit=1)
    if len(delimited) == 2 and 0 < len(delimited[0].split()) <= 9 and delimited[1].strip():
        return delimited[0].strip(), delimited[1].strip()
    parts = _sentences(rest)
    if len(parts) > 1:
        head = parts[0]
        # Title + first body sentence share paragraph 0; cut at the first
        # lowercase-starting word that follows a capitalised run of <= 8 words.
        words = head.split()
        for i in range(1, min(len(words), 9)):
            if words[i][:1].islower() and i >= 2:
                return ' '.join(words[:i]), ' '.join(words[i:] + parts[1:])
        return head, ' '.join(parts[1:])
    words = rest.split()
    for i in range(1, min(len(words), 9)):
        if words[i][:1].islower() and i >= 2:
            return ' '.join(words[:i]), ' '.join(words[i:])
    return rest, ''


def _slug_from_url(url: str) -> str:
    url = url.strip()
    url = re.sub(r'^https?://', '', url)
    url = re.sub(r'^[^/]*', '', url)
    return url.strip('/')


def _states_served(config: dict | None) -> list[str]:
    """Every state this client operates in, from `client-config.yml`."""
    if isinstance(config, dict):
        v = config.get('states_served')
        if isinstance(v, list):
            return [str(s).strip().upper() for s in v if str(s).strip()]
    return []


def _primary_state(config: dict | None) -> str:
    """The client's first/home state. Empty when unconfigured — never a literal.

    BUG-016: this used to fall back to 'NC', Acme's home state, so every other
    client's pages were stamped with the pilot's geography.
    """
    served = _states_served(config)
    return served[0] if served else ''


def _service_label(config: dict | None) -> str:
    """Display service name: 'roofing-contractor' -> 'Roofing Contractor'.

    Read from the client's own config rather than hardcoded. `business.trade` may
    be a comma-separated list ("demolition, excavation, …"); the first entry is
    the headline service. Returns '' when unconfigured so the caller can fail
    loud instead of inventing one.
    """
    raw = _cfg(config or {}, 'trade', 'business.trade', 'primary_service', 'service_label')
    if not raw:
        return ''
    raw = raw.split(',')[0].strip()
    return ' '.join(w.capitalize() for w in re.split(r'[-_\s]+', raw) if w)


def _state_from_slug(slug: str, default: str = '') -> str:
    """State from a URL slug, falling back to the CLIENT's primary state.

    BUG-016: `default` used to be the literal 'NC'.
    """
    m = re.search(r'-([a-z]{2})(?:/|$)', slug)
    return m.group(1).upper() if m else default


def _spanned_h1(h1: str, city: str, state: str) -> str:
    """One <span> around the geo phrase — the only markup hero.title may carry."""
    geo = f'{city}, {state}'
    if geo in h1:
        return h1.replace(geo, f'<span>{geo}</span>', 1)
    if city in h1:
        return h1.replace(city, f'<span>{city}</span>', 1)
    return h1


# ---------------------------------------------------------------------------
# Pass 2 — CLASSIFY
# ---------------------------------------------------------------------------

class _Ledger:
    """Every source block leaves a verdict: KEEP | TRIM | OPTIMIZE | DROP | BANK."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, *, block_id: str, verdict: str, marker: str, words: int,
            reason: str = '', text: str = '') -> None:
        self.rows.append({
            'block_id': block_id, 'verdict': verdict, 'marker': marker,
            'words': words, 'reason': reason,
            'excerpt': text[:180],
        })

    def dropped_ratio(self) -> float:
        if not self.rows:
            return 0.0
        gone = sum(1 for r in self.rows if r['verdict'] in ('DROP', 'BANK'))
        return gone / len(self.rows)


#: Heading-driven hub pages (Charlotte, Asheville) carry no ALL-CAPS markers —
#: they use `Heading 2` paragraphs reading 'H2: <title>'. Map those titles onto
#: the same marker vocabulary so ONE classifier serves both authoring formats.
_HUB_TITLE_MARKERS: tuple[tuple[str, str], ...] = (
    # FAQ first, always. FAQ headings routinely embed the page's service name
    # ("Frequently Asked Questions About Storm Damage Restoration in
    # Parkville") — with topic patterns above it, 'storm damage' claimed the
    # heading and the FAQ section rode the wrong marker, so _faq_pairs found 0
    # pairs and the capsule check paired question-with-question. That broke
    # exactly the 8 Crestline storm pages in the 2026-08 cycle (ENGINE-FIXES
    # fix 4): a heading that says FAQ IS the FAQ section, whatever its topic.
    (r'frequently asked questions|\bfaqs?\b', 'FAQ SECTION'),
    (r'complete exterior contractor', 'INTRO SECTION'),
    (r'certification|credential', 'CERTIFICATIONS SECTION'),
    (r'residential .*roofing', 'ZIGZAG — RESIDENTIAL ROOFING'),
    (r'commercial .*roofing', 'ZIGZAG — COMMERCIAL ROOFING'),
    (r'exterior services', 'EXTERIOR SERVICES SECTION'),
    (r'why .*choose', 'WHY CHOOSE SECTION'),
    (r'storm damage', 'STORM AND INSURANCE SECTION'),
    (r'financing', 'FINANCING SECTION'),
    (r'process', 'PROCESS SECTION'),
    (r'review|testimonial', 'TESTIMONIALS SECTION'),
    (r'nearby areas', 'NEARBY AREAS SECTION'),
    (r'^ready to|protect your', 'CTA SECTION'),
)


def normalize_heading_page(segment: PageSegment) -> None:
    """In-place: give a heading-driven page the marker + label vocabulary the
    marker-driven pages already have. Nothing is added or removed — only the
    structural context each block already implies is made explicit."""
    if any(b.marker in ('INTRO SECTION', 'HERO SECTION') for b in segment.blocks):
        return
    marker = 'HERO SECTION'
    para_n = 0
    # Writers who use Word's heading STYLES never type the literal 'H1:' prefix,
    # so `_adopt_style_headings` labels those blocks during pass 1. Honour that
    # label here too: without it a style-only heading falls through to the
    # generic branch below, the hero paragraph under it gets relabelled
    # 'Paragraph 1', and `resolve_hero_source` then breaks on that label and
    # reports `no_hero_copy` for a page whose hero is plainly present.
    has_hero_label = any(b.label.strip().lower() in ('hero subheading', 'p', 'p1')
                         for b in segment.blocks)
    # A paragraph directly under a bare 'Label:' IS that label's value. Giving it
    # its own 'Paragraph N' label here would end label_value's continuation scan
    # and make the field read as missing — the exact regression that put
    # no_meta_title back on all 32 pages of the Northstar June doc.
    prev_dangling = False
    for b in segment.blocks:
        dangling_here = bool(b.label) and not b.value
        if prev_dangling and not b.label and b.kind == 'paragraph':
            prev_dangling = dangling_here
            continue
        prev_dangling = dangling_here
        heading = b.kind == 'paragraph' and b.style.startswith('Heading')
        h_prefixed = re.match(r'^H([123])\s*:\s*(.+)$', b.text)
        if heading and not h_prefixed and re.fullmatch(r'[Hh][123]', b.label.strip()):
            h_prefixed = re.match(r'^(?:H([123]))()$', b.label.strip().upper())
            title_override = (b.value or b.text).strip()
        else:
            title_override = ''
        if heading and h_prefixed:
            title = title_override or h_prefixed.group(2).strip()
            if h_prefixed.group(1) == '1':
                b.label, b.value, b.marker = 'H1', title, 'HERO SECTION'
                continue
            for pattern, name in _HUB_TITLE_MARKERS:
                if re.search(pattern, title, re.I):
                    marker = name
                    break
            else:
                marker = 'INTRO SECTION' if marker == 'HERO SECTION' else marker
            b.marker, b.label, b.value = marker, f'H{h_prefixed.group(1)}', title
            para_n = 0
            continue
        b.marker = marker
        if marker == 'HERO SECTION' and b.label.lower() in ('p', 'p1'):
            b.label = 'Hero Subheading'      # heading-driven hubs label the hero para 'P:'
            continue
        if not b.label and b.kind == 'paragraph' and not _is_marker(b.text):
            if marker == 'HERO SECTION' and b.text.startswith('P:'):
                b.label, b.value = 'Hero Subheading', b.text[2:].strip()
            elif marker == 'HERO SECTION' and para_n == 0 and not has_hero_label:
                # First prose paragraph under the hero on a page that labels its
                # hero nowhere: that IS the hero subheading. Guarded by
                # has_hero_label so any page using the 'P:'/'Hero Subheading'
                # convention keeps its existing resolution untouched.
                b.label, b.value = 'Hero Subheading', b.text
                para_n += 1
            elif marker == 'FAQ SECTION':
                para_n += 1
                b.label, b.value = f'Q{para_n}', b.text
            elif marker in ('CERTIFICATIONS SECTION', 'WHY CHOOSE SECTION',
                            'WHY ACME SECTION',
                            'FINANCING SECTION', 'PROCESS SECTION', 'CTA SECTION'):
                pass  # banked / builder-collapsed; no field extraction needed
            else:
                para_n += 1
                b.label, b.value = f'Paragraph {para_n}', b.text


def _cfg(config: dict, *paths: str, default: str = '') -> str:
    """C29 — read a real config value by dotted path; never hardcode client values.
    Acme nests coverage_method under `repo:`, other profiles put it at the root."""
    for path in paths:
        node: Any = config
        for part in path.split('.'):
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if isinstance(node, (str, int, float)) and str(node).strip():
            return str(node).strip()
    return default


def _grouped(segment: PageSegment) -> dict[str, list[RawBlock]]:
    groups: dict[str, list[RawBlock]] = {}
    for b in segment.blocks:
        groups.setdefault(b.marker, []).append(b)
    return groups


def _labelled(blocks: list[RawBlock], *labels: str) -> list[RawBlock]:
    want = {l.lower() for l in labels}
    return [b for b in blocks if b.label.lower() in want]


def _first_value(blocks: list[RawBlock], *labels: str) -> str:
    # Resolve through label_value, never `.value` directly: the label-on-its-own-
    # line convention leaves `.value` empty and the real text one paragraph down.
    # Reading `.value` here is what reported Meta Title / Meta Description / URL
    # as missing on documents that carried all three.
    hits = _labelled(blocks, *labels)
    for hit in hits:
        value = label_value(blocks, hit)
        if value:
            return value
    return ''


def _paragraph_values(blocks: list[RawBlock]) -> list[str]:
    """`Paragraph`, `Paragraph 1..N`, and `Body` blocks, in document order."""
    out = []
    for b in blocks:
        if re.fullmatch(r'paragraph(\s*\d+)?|body|p\d?', b.label.strip().lower()):
            if b.value:
                out.append(b.value)
    return out


def _continuation(blocks: list[RawBlock], anchor: RawBlock) -> list[str]:
    """Unlabelled lines that follow a bare 'Label:' with no inline value."""
    out: list[str] = []
    seen = False
    for b in blocks:
        if b is anchor:
            seen = True
            continue
        if not seen:
            continue
        # A bare URL parses as label='https' and would end the scan on the very
        # field ('URL:') most often written this way — take it as the value.
        if _BARE_URL_RE.match(b.text):
            out.append(b.text)
            break
        if b.label or b.kind == 'table' or _is_marker(b.text) or _ENUM_RE.match(b.text):
            break
        out.append(b.text)
    return out


def label_value(blocks: list[RawBlock], anchor: RawBlock) -> str:
    """The value of a labelled block, tolerant of BOTH handoff conventions.

    April runs the value inline ('Hero Subheading: <text>'), so `anchor.value` is
    populated. July 2026 puts the label on its own paragraph and the value on the
    NEXT one ('Hero Subheading:' then a separate paragraph). This helper reads the
    inline value when present and otherwise associates the following continuation
    paragraph(s) as the value, stopping at the next label / marker / table / enum.

    ADDITIVE: the continuation branch only fires when the label carries no inline
    value, so April's inline form resolves to exactly `anchor.value` unchanged.
    Both the emitter (via distill) and pre-flight (which imports this) benefit from
    the single implementation, so they can never drift apart.
    """
    if anchor.value:
        return anchor.value
    return ' '.join(_continuation(blocks, anchor)).strip()


def resolve_hero_source(flat: list[RawBlock],
                        hero_blocks: list[RawBlock] | None = None) -> str:
    """The hero paragraph, under EVERY known authoring convention.

    SINGLE SOURCE OF TRUTH: build_draft and preflight_docx both call this, so the
    fix-list a writer receives and the emit verdict can never disagree about
    whether hero copy exists (the exact drift that produced 20 false
    `no_hero_copy` blocks on the July Acme doc).

    The July 2026 Acme handoff alone writes the hero THREE ways in one file:
      labelled:    "H1: ..." / "Hero Subheading:" / "<text>"   (also 'P:'/'P1:' hubs)
      unlabelled:  "H1: ..." / "<text>"
      markerless:  no "HERO SECTION" heading at all — the hero sits unmarked
                   between the meta block and the first real section marker
                   (17 of its 24 pages).

    Resolution order: the labelled path wins (April's convention, unchanged);
    then the first unlabelled, non-marker paragraph after the H1 — scanned inside
    the HERO SECTION group when one exists, else across the flat stream.
    """
    if hero_blocks is None:
        hero_blocks = [b for b in flat if getattr(b, 'marker', '') == 'HERO SECTION']

    # Scan `flat` when no HERO SECTION marker exists, exactly as the unlabelled
    # pass below already does. Acme's July pages keep the hero inside the
    # SEO META TAGS block, so hero_blocks came back empty, this labelled pass
    # never ran, and the unlabelled pass then broke on the very 'Hero
    # Subheading:' label it was looking for — `no_hero_copy` on a page whose
    # hero is right there and correctly labelled.
    scope = hero_blocks or flat
    # Inside a real HERO SECTION a bare 'Subheading:' can only be the hero, so
    # accept it there (Acme writes both spellings across one document). When
    # falling back to the whole page it is NOT accepted, because a section
    # subheading further down would be grabbed as the hero.
    labels = (('hero subheading', 'subheading', 'p', 'p1') if hero_blocks
              else ('hero subheading', 'p', 'p1'))
    for b in scope:
        if b.label.strip().lower() in labels:
            value = label_value(scope, b)
            if value:
                return value

    seen_h1 = False
    for b in (hero_blocks or flat):
        if not seen_h1:
            if b.text.startswith('H1:') or b.label.lower() == 'h1':
                seen_h1 = True
            continue
        if b.label or _is_marker(b.text):   # next labelled field / section marker
            break
        cand = b.text.strip()
        if cand and not cand.endswith(':'):
            return cand
    return ''


def _enum_cards(blocks: list[RawBlock], kinds: tuple[str, ...]) -> list[tuple[str, str]]:
    """'Card N — ...' entries. The body is either inline on the same line
    (Week 1/2) or on the unlabelled paragraphs that follow (Week 3/4)."""
    cards: list[tuple[str, str]] = []
    open_card: int | None = None
    for b in blocks:
        m = _ENUM_RE.match(b.text)
        if m and m.group(1).lower().replace(' ', '') in kinds:
            title, body = _split_enum_title_body(m.group(3))
            cards.append((title.strip(), body.strip()))
            open_card = len(cards) - 1
            continue
        if open_card is None:
            continue
        if b.label or b.kind == 'table' or _is_marker(b.text):
            if b.label.lower().startswith('service link'):
                continue          # links belong to the card but are not body copy
            open_card = None
            continue
        title, body = cards[open_card]
        cards[open_card] = (title, (body + ' ' + b.text).strip())
    return cards


def _faq_pairs(blocks: list[RawBlock]) -> list[tuple[str, str]]:
    """Two conventions in the same file:
      Week 3/4 : 'Q1: question?'  then the answer on the NEXT paragraph
      Week 1/2 : 'Q1: question? answer answer answer'  all on one line
    """
    pairs: list[tuple[str, str]] = []
    pending: str | None = None
    for b in blocks:
        # A heading-styled question inside FAQ SECTION is a question — writers
        # using Word's heading styles get H2/H3 labels, never 'Q1:'. Without
        # this the pairing found nothing, `no_capsule` blocked all 33 Northstar
        # pages, and the FAQ content never reached the emitted page.
        if (re.fullmatch(r'h[23]', b.label.strip().lower())
                and (b.value or b.text).strip().endswith('?')):
            pending = (b.value or b.text).strip()
            continue
        # A Q-numbered block is normally the QUESTION. But on a heading-driven
        # page the question already arrived as an H2/H3 above, and this is the
        # ANSWER that normalize_heading_page happened to number — so when a
        # question is pending, fall through to the answer branch instead of
        # overwriting it.
        if re.fullmatch(r'(?:q|faq)\s?\d+', b.label.strip().lower()) and pending is None:
            raw = b.value or b.text
            head, sep, tail = raw.partition('?')
            if sep and tail.strip():
                pairs.append((head.strip() + '?', tail.strip()))
                pending = None
            else:
                pending = raw.strip()
            continue
        # The answer. Unlabelled in the original conventions; on a heading-driven
        # page `normalize_heading_page` has already numbered it 'Q1', 'Q2', ...
        # because it is a loose paragraph under FAQ SECTION. Accept both, so the
        # answer is not mistaken for the next question.
        answer_like = b.kind == 'paragraph' and (
            not b.label or re.fullmatch(r'(?:q|faq)\s?\d+', b.label.strip().lower()))
        if pending is not None and answer_like:
            body = (b.value or b.text).strip()
            if _is_marker(body) or body.startswith('<script') or not body:
                pending = None
                continue
            pairs.append((pending, body))
            pending = None
    return pairs


def _areas_from(blocks: list[RawBlock], default_state: str) -> list[dict[str, str]]:
    areas: list[dict[str, str]] = []
    seen: set[str] = set()
    for b in blocks:
        if b.kind == 'table':
            cells = [c for row in b.rows for c in row]
        elif b.label.lower().startswith('area'):
            cells = re.split(r'\s*[·|]\s*', b.value) if b.value else _continuation(blocks, b)
        else:
            cells = []
        for cell in cells:
            m = re.match(r'^([A-Za-z .\'\-]+?),\s*([A-Z]{2})$', cell.strip())
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                areas.append({'city': m.group(1).strip(), 'state': m.group(2)})
            elif cell.strip() and re.fullmatch(r"[A-Za-z .'\-]{3,28}", cell.strip()) \
                    and cell.strip() not in seen and len(cell.split()) <= 3:
                seen.add(cell.strip())
                areas.append({'city': cell.strip(), 'state': default_state})
    return areas


#: 'Siding Installation Flat Rock Siding Repair Flat Rock ...' — the team runs
#: every link of a card onto one line with no delimiter. The service noun is the
#: only reliable boundary, and it is the same closed set as SUBSERVICE_SUFFIX_RE.
_LINK_RUN_RE = re.compile(
    r'([A-Z][A-Za-z]*(?:\s[A-Z][A-Za-z]*)*?\s'
    r'(?:Installation|Repair|Replacement|Services|Claims|Roofing|Inspection))'
    r'\s+([A-Z][A-Za-z]*(?:\s[A-Z][a-z]+)?)')


def _service_links(blocks: list[RawBlock]) -> list[str]:
    out: list[str] = []
    for b in blocks:
        if b.label.lower() in ('service links', 'service link'):
            raw = [b.value] if b.value else _continuation(blocks, b)
            for line in raw:
                if not line:
                    continue
                hits = _LINK_RUN_RE.findall(line)
                if len(hits) > 1:
                    out.extend(f'{svc} {city}'.strip() for svc, city in hits)
                else:
                    out.append(line)
    seen: set[str] = set()
    clean: list[str] = []
    for s in out:
        s = re.sub(r'\s*[—–-]\s*(Siding|Gutter)\s+Services$', '', s).strip()
        # A link label is a service name, never a paragraph. Anything longer is
        # body copy the continuation scan over-collected — drop it, do not ship it.
        if len(s.split()) > 6:
            continue
        if s and s.lower() not in seen:
            seen.add(s.lower())
            clean.append(s)
    return clean


def _text_hazards(label: str, text: str) -> list[ValidationFinding]:
    """C12 / C13 / C15 detection. Detection only — this module never rewrites
    authored copy; the emitter's scrub pass owns the fix."""
    out: list[ValidationFinding] = []
    if _DOLLAR_RE.search(text):
        out.append(block('forbidden_phrase_dollar',
                         f'{label}: dollar figure present (config forbidden_phrases `\\$[0-9]`)',
                         field_path=label, detail=text[:120]))
    if _EMDASH_RE.search(text):
        out.append(warn('em_dash', f'{label}: em/en dash present (auto-fixable at emit)',
                        auto_fixable=True, field_path=label))
    if _INVISIBLE_RE.search(text):
        out.append(warn('invisible_codepoint', f'{label}: invisible codepoint present',
                        auto_fixable=True, field_path=label))
    return out


# ---------------------------------------------------------------------------
# Core-body distillation (build-plan 05 — band is settled, do not re-litigate)
# ---------------------------------------------------------------------------

#: Trim priority, lowest number = protect first. Distillation removes paragraphs
#: from the LEAST protected core section until the page is under CORE_WORDS_MAX.
_TRIM_PRIORITY = {
    'editorial-split': 0,     # carries the capsule — never trimmed
    'content-block': 2,
    'types': 3,
}


def distill_core_body(draft: PageDraft, ledger: _Ledger) -> list[ValidationFinding]:
    """Bring core_words into [800, 1500]. ~1200 is advisory, NEVER a pad target.

    Over the ceiling: drop whole paragraphs from the least-protected core section,
    banking each one with its text so nothing is lost silently.
    Under the floor: report. Padding would mean inventing copy (C27)."""
    findings: list[ValidationFinding] = []
    before = recount_core_words(draft)

    guard = 0
    while recount_core_words(draft) > CORE_WORDS_MAX and guard < 200:
        guard += 1
        candidates = [
            s for s in draft.real_sections()
            if s.type in _TRIM_PRIORITY and _TRIM_PRIORITY[s.type] > 0
            and _core_units(s)
        ]
        if not candidates:
            break
        victim = max(candidates, key=lambda s: (_TRIM_PRIORITY[s.type], _core_words_of(s)))
        removed = _pop_last_core_unit(victim)
        if removed is None:
            break
        ledger.add(block_id=victim.source_ref or victim.type, verdict='TRIM',
                   marker=victim.type, words=count_words(removed),
                   reason='core-body distillation: over 1500-word ceiling', text=removed)

    after = recount_core_words(draft)
    draft.core_body_words = after

    if after > CORE_WORDS_MAX:
        findings.append(warn('core_body_over_band',
                             f'core_words={after} > {CORE_WORDS_MAX} after distillation; '
                             'remaining copy is capsule-protected — curation call',
                             field_path='sections'))
    elif after < CORE_WORDS_MIN:
        findings.append(warn('core_body_under_band',
                             f'core_words={after} < {CORE_WORDS_MIN}; source DOCX does not '
                             'carry enough core body copy. NOT padded (C27).',
                             field_path='sections'))
    if before != after:
        ledger.add(block_id='core-body', verdict='TRIM', marker='core-body',
                   words=before - after,
                   reason=f'distilled {before} -> {after} words (band {CORE_WORDS_MIN}-{CORE_WORDS_MAX}, '
                          f'advisory {CORE_WORDS_SWEET_SPOT})')
    return findings


def _core_units(section: Section) -> list[str]:
    if section.type == 'content-block':
        return list(section.props.get('content', []))
    if section.type == 'editorial-split':
        return list(section.props.get('paragraphs', []))
    if section.type == 'types':
        return [c.get('description', '') for c in section.props.get('cards', [])]
    return []


def _core_words_of(section: Section) -> int:
    return sum(count_words(u) for u in _core_units(section))


def _pop_last_core_unit(section: Section) -> str | None:
    """Remove one countable unit. `types` cards keep their title+icon (the grid
    count is a curation constraint, C23) — only the description text is dropped."""
    if section.type == 'content-block':
        content = section.props.get('content') or []
        if len(content) > 1:
            return content.pop()
        return None
    if section.type == 'editorial-split':
        paragraphs = section.props.get('paragraphs') or []
        if len(paragraphs) > 1:
            return paragraphs.pop()
        return None
    if section.type == 'types':
        cards = section.props.get('cards') or []
        for card in reversed(cards):
            if card.get('description'):
                text = card['description']
                card['description'] = ''
                return text
    return None


# ---------------------------------------------------------------------------
# July 2026 — generic section markers + city-from-slug
# ---------------------------------------------------------------------------
# July's marker-driven pages reuse the April structure (ALL-CAPS '* SECTION'
# headings, 'Section Label:' / 'H2:' / 'Card N ...'), but the section VOCABULARY
# is page-specific (VENTILATION, WHY INSTALL, MATERIALS, HOA, SERVICE AREA, ...)
# and cannot be enumerated the way the fixed hub markers were. Any '* SECTION'
# marker that build_draft does not otherwise consume is turned into a
# content-block (prose) or a `types` grid (cards) so the section reaches the page
# instead of being silently dropped. April is untouched: every April marker is
# already in _HANDLED_MARKERS / the builder / bank sets, so this never fires there.

#: Markers with bespoke handling in build_draft (plus '' for un-markered blocks).
#: Builder-collapse and bank markers are excluded separately.
_HANDLED_MARKERS: frozenset[str] = frozenset({
    '', 'HERO SECTION', 'INTRO SECTION', 'FAQ SECTION',
    'EXTERIOR SERVICES SECTION', 'ZIGZAG SERVICES SECTION',
    'STORM AND INSURANCE SECTION', 'STORM & INSURANCE SECTION',
    'TESTIMONIALS SECTION', 'NEARBY AREAS SECTION',
})

#: A July card head: 'Card 1: Vinyl Soffit' (MATERIALS, colon) or
#: 'Card 1 Ventilation Upgrade on 1990s Homes' (WHY INSTALL, no delimiter). The
#: April delimiter form ('Card 1 — Title — body') is handled by _ENUM_RE and is
#: intentionally NOT touched — this pattern is only ever applied inside the
#: generic July handler, which April markers never reach.
_JULY_CARD_RE = re.compile(r'^card\s*\d+\s*[:\-—–]?\s+(.*\S)\s*$', re.I)
_JULY_CARD_LABEL_RE = re.compile(r'^card\s*\d+$', re.I)

#: Labels that are section chrome, never body prose, in the generic collector.
_STRUCT_LABELS: frozenset[str] = frozenset({
    'section label', 'h1', 'h2', 'h3', 'subtitle', 'badge', 'cta buttons', 'cta',
    'trust stats', 'stats', 'stats block', 'service links', 'service link',
})


def _city_from_slug(slug: str, page_kind: str, config: dict | None = None) -> str:
    """Derive the city from the slug, mirroring locationLabel() / derive_export_name.
    Used when the page NAME is a meta title (July) rather than a bare city (April).

    BUG-016 (residual): the trailing-state strip below was hardcoded to Acme's
    four states, so for an NJ/PA/MD client a segment like `princeton-nj` kept its
    suffix and became the city "Princeton Nj". Read the client's own
    states_served, and fall back to a generic two-letter suffix when the config
    has none, so no client's home state is ever assumed.
    """
    segs = [s for s in slug.split('/') if s]
    if not segs:
        return ''
    if page_kind == 'hub' or len(segs) < 2:
        return segs[0].split('-')[0].capitalize()
    cand = segs[1]
    if SUBSERVICE_SUFFIX_RE.search(cand):            # metro-level sub-service
        return segs[0].split('-')[0].capitalize()
    served = _states_served(config)
    if served:
        cand = re.sub(r'-(' + '|'.join(re.escape(s) for s in served) + r')$',
                      '', cand, flags=re.I)
    else:
        cand = re.sub(r'-[a-z]{2}$', '', cand, flags=re.I)
    return ' '.join(w.capitalize() for w in cand.split('-') if w)


def _july_cards(blocks: list[RawBlock]) -> list[tuple[str, str]]:
    """'Card N ...' entries under a July section, with the body on the following
    unlabelled paragraph(s). Handles both the colon form ('Card 1: Vinyl Soffit',
    read as label 'Card 1' + value title) and the bare form ('Card 1 Ventilation
    Upgrade ...', a plain paragraph)."""
    cards: list[list[str]] = []
    open_i: int | None = None
    for b in blocks:
        lab = b.label.strip()
        if _JULY_CARD_LABEL_RE.match(lab) and b.value:      # colon form (MATERIALS)
            cards.append([b.value.strip(), ''])
            open_i = len(cards) - 1
            continue
        if not lab and b.kind == 'paragraph':
            m = _JULY_CARD_RE.match(b.text)
            if m:                                            # bare form (WHY INSTALL)
                cards.append([m.group(1).strip(), ''])
                open_i = len(cards) - 1
                continue
        if open_i is None:
            continue
        if lab or b.kind == 'table' or _is_marker(b.text):
            open_i = None
            continue
        cards[open_i][1] = (cards[open_i][1] + ' ' + b.text).strip()
    return [(t, body) for t, body in cards if t]


def _generic_paragraphs(blocks: list[RawBlock]) -> list[str]:
    """Body prose under a generic July section: labelled 'Paragraph N:'/'Body:'
    values (inline OR continuation) and bare body paragraphs, in document order.
    Section chrome (Section Label / H2 / Subtitle) and card heads are excluded."""
    out: list[str] = []
    for b in blocks:
        if b.kind == 'table':
            continue
        lab = b.label.strip().lower()
        if _is_marker(b.text) or lab in _STRUCT_LABELS or _JULY_CARD_LABEL_RE.match(lab):
            continue
        if not lab and _JULY_CARD_RE.match(b.text):
            continue
        if lab:
            if re.fullmatch(r'paragraph(\s*\d+)?|body|p\d?', lab):
                v = label_value(blocks, b)
                if v:
                    out.append(v)
        elif b.text.strip():
            out.append(b.text.strip())
    return out


def _derive_types_subtitle(label: str, title: str) -> str:
    """A `types` grid REQUIRES a non-empty `subtitle`: TypesSection (acme
    src/data/services.ts) makes the field MANDATORY, so a card grid without one
    emits TS that fails `tsc` and kills the whole build. When the DOCX carries no
    'Subtitle:' line, fall back to the section's own authored framing — the section
    label when it says something the H2 does not, else the H2 itself. This is
    VERBATIM authored text from the source: it introduces no claim the DOCX did not
    already make. A curator may refine the wording later, but the field is never
    empty and the page always builds.
    """
    lab = (label or '').strip()
    ttl = (title or '').strip()
    if lab and lab.lower() != ttl.lower():
        return lab
    return ttl


def _generic_section(marker: str, blocks: list[RawBlock], source_ref: str,
                     city: str) -> Section | None:
    """One unrecognized July '* SECTION' -> a `types` grid (if it carries cards)
    or a `content-block` (if it carries prose). None when it carries neither."""
    label = _first_value(blocks, 'section label') or marker.title()
    title = _first_value(blocks, 'h2') or _first_value(blocks, 'h3') or marker.title()
    subtitle = _first_value(blocks, 'subtitle')
    cards = _july_cards(blocks)
    if len(cards) >= 2:
        # subtitle is MANDATORY on a `types` grid — guarantee it (never conditional).
        props: dict[str, Any] = {
            'label': label,
            'title': title,
            'subtitle': subtitle or _derive_types_subtitle(label, title),
        }
        props['cards'] = [{'icon': _icon_for(f'{t} {city}'), 'title': t, 'description': d}
                          for t, d in cards]
        return Section('types', props, core_body=True,
                       source_ref=f'{source_ref}/{marker}', verdict='KEEP')
    paras = _generic_paragraphs(blocks)
    if paras:
        return Section('content-block', {'label': label, 'title': title, 'content': paras},
                       core_body=True, source_ref=f'{source_ref}/{marker}', verdict='KEEP')
    return None


# ---------------------------------------------------------------------------
# Pass 2 — the page builder
# ---------------------------------------------------------------------------

def build_draft(segment: PageSegment, docx_path: str, *, config: dict | None = None,
                mode: str = 'a', image_map: dict[str, dict[str, str]] | None = None) -> PageDraft:
    """One PageSegment -> one PageDraft, with a ledger row per source block."""
    config = config or {}
    image_map = image_map or {}
    normalize_heading_page(segment)
    groups = _grouped(segment)
    flat = segment.blocks
    ledger = _Ledger()
    findings: list[ValidationFinding] = []
    source_ref = segment.source_ref(docx_path)

    # ---- identity ---------------------------------------------------------
    url = (_first_value(flat, 'canonical url', 'slug', 'url')
           or _first_value(flat, 'canonical'))
    slug = _slug_from_url(url)
    if not slug:
        findings.append(block('no_slug', f'{segment.name}: no Slug / URL / Canonical URL block',
                              field_path='url_path'))
        slug = re.sub(r'[^a-z0-9]+', '-', segment.name.lower()).strip('-')
    slug_segments = [s for s in slug.split('/') if s]
    segments_n = len(slug_segments)
    if segments_n == 1:
        page_kind = 'hub'
    elif segments_n == 2:
        # A 2-segment slug is a city spoke UNLESS its leaf is a service noun
        # (charlotte-nc/fascia-installation), which is a metro-level sub-service.
        page_kind = ('subservice'
                     if SUBSERVICE_SUFFIX_RE.search(slug_segments[-1]) else 'spoke')
    else:
        page_kind = 'subservice'
    # The page NAME is the city under April's Title-style convention, but the full
    # meta title under July's 'Page Title:' convention. Fall back to the
    # slug-derived city whenever the name is clearly not a bare city (a pipe/comma
    # or a long run). April's short city names are left untouched -> additive.
    city = segment.name.strip()
    slug_city = _city_from_slug(slug, page_kind, config)
    if slug_city and ('|' in city or ',' in city or len(city.split()) > 3):
        city = slug_city
    state = _state_from_slug(slug)
    if not state:
        # FAIL LOUD, never guess. The 2026-07-31 SC verification caught the old
        # fallback stamping "Charlotte-class" pages as `state: NC` and
        # synthesising "Roofing Contractor in Charleston, NC" for a South
        # Carolina doc whose slugs (/south-carolina/charleston/) carry no state
        # suffix — confident, well-formed, wrong (BUG-016's class). A
        # single-state client is unambiguous; a multi-state client is not, so
        # the page is BLOCKED with the reason instead of silently mislabelled.
        served = _states_served(config)
        state = _primary_state(config)
        # A SITE-LEVEL page (/faq/, /about/ — one bare segment naming no city)
        # is not attributed to a market at all; it belongs to the business,
        # which is headquartered in the primary state. The mislabelling risk
        # this block exists for (BUG-016: a Charleston page stamped NC) only
        # arises on LOCATION pages, where the slug names a place. Explicit
        # vocabulary, not inference — _city_from_slug happily reads 'faq' as a
        # city, which is exactly the guessing this block bans.
        site_level = page_kind == 'hub' and slug in _SITE_LEVEL_SLUGS
        if len(served) > 1 and not site_level:
            findings.append(block(
                'state_unresolved',
                f'{segment.name}: slug {slug!r} carries no state suffix and the '
                f'client serves {len(served)} states ({", ".join(served)}) — '
                f'cannot attribute the page to a state. Slugs must follow the '
                f'/[metro]-[st]/ pattern (e.g. charlotte-nc, columbia-sc). '
                f'Placeholder {state!r} is NOT shippable.',
                field_path='state'))

    leaf = (slug.split('/')[-1] or '').replace('-', ' ')
    # Strip a trailing state abbreviation from the leaf. BUG-016: this was
    # hardcoded to Acme's four states (nc|sc|va|wv), so an NJ or PA suffix
    # survived into the city name on every other client.
    _served = _states_served(config)
    if _served:
        leaf = re.sub(r'\s+(' + '|'.join(re.escape(s) for s in _served) + r')$',
                      '', leaf, flags=re.I).strip()
    else:
        leaf = re.sub(r'\s+[a-z]{2}$', '', leaf, flags=re.I).strip()
    # Only a 2-segment spoke has its city in the slug LEAF; on a sub-service page
    # the leaf is the service noun, so this comparison would false-positive.
    if page_kind == 'spoke' and leaf and city and leaf.lower() != city.lower():
        findings.append(warn('city_slug_mismatch',
                             f'DOCX page title "{city}" does not match its own slug leaf '
                             f'"{leaf}" — check the source spelling before the slug is minted',
                             field_path='url_path'))

    if page_kind == 'hub' and slug not in KNOWN_METRO_HUBS:
        findings.append(warn('new_metro_hub',
                             f'{slug} is a 1-segment hub not in isLocationPage() '
                             f'({sorted(KNOWN_METRO_HUBS)}) — needs a code edit',
                             field_path='url_path'))

    meta_title = _first_value(flat, 'meta title', 'page title', 'title')
    meta_description = _first_value(flat, 'meta description')
    if not meta_title:
        findings.append(block('no_meta_title', f'{segment.name}: no Meta Title block',
                              field_path='meta_title'))
    elif effective_len(meta_title) > META_TITLE_MAX_EFFECTIVE:
        findings.append(warn('meta_title_long',
                             f'metaTitle {effective_len(meta_title)} effective chars > '
                             f'{META_TITLE_MAX_EFFECTIVE} — rewrite, never truncate (C22)',
                             field_path='meta_title'))
    if not meta_description:
        findings.append(block('no_meta_description', f'{segment.name}: no Meta Description block',
                              field_path='meta_description'))
    elif not _META_DESC_MIN <= effective_len(meta_description) <= _META_DESC_MAX:
        # &-expansion aware. ONE band across the whole chain (the 2026-08 cycle
        # found three gates with three answers — 150-160 here, 130-150 at emit,
        # 120-155 in the distiller — where only exactly 150 satisfied all):
        # the band is validators.META_DESC_MIN..MAX_EFFECTIVE (Content Team
        # Operating Standard §04, 130-150 never outside), imported so this
        # check can never drift from the gate that holds pages. audit_built's
        # 120-160 stays the deliberately-wider BUILT-html outer rail.
        findings.append(warn('meta_description_length',
                             f'metaDescription {effective_len(meta_description)} effective '
                             f'chars (raw {len(meta_description)}), want '
                             f'{_META_DESC_MIN}-{_META_DESC_MAX}',
                             field_path='meta_description'))

    # ---- hero -------------------------------------------------------------
    hero_blocks = groups.get('HERO SECTION', [])
    h1 = _first_value(flat, 'h1') or next(
        (b.text[3:].strip() for b in flat if b.text.startswith('H1:')), '')
    if not h1:
        findings.append(block('no_h1', f'{segment.name}: no H1 block', field_path='h1'))

    hero_source = resolve_hero_source(flat, hero_blocks=hero_blocks)

    hook, demoted = hero_hook(hero_source) if hero_source else ('', '')
    if not hero_source:
        findings.append(block('no_hero_copy', f'{segment.name}: no Hero Subheading',
                              field_path='hero.description'))
    if hook and (count_words(hook) > HERO_MAX_WORDS
                 or count_sentences(hook) > HERO_MAX_SENTENCES
                 or len(hook) > HERO_MAX_CHARS):
        findings.append(block('hero_v1_residual',
                              f'hero.description still {count_words(hook)}w/'
                              f'{count_sentences(hook)}s/{len(hook)}ch after hook extraction',
                              field_path='hero.description'))
    if demoted:
        ledger.add(block_id='hero-subheading', verdict='OPTIMIZE', marker='HERO SECTION',
                   words=count_words(demoted),
                   reason='V1 hero-hook extraction: remainder demoted to body (C21)',
                   text=demoted)

    badge = _first_value(hero_blocks, 'badge')
    badge_text = _EMOJI_RE.sub('', badge).strip().upper() or f'SERVING {city.upper()}'
    features = _trust_stats(hero_blocks)
    phone = _cfg(config, 'nap.phone', 'gbp.phone', 'company.phone')
    phone_tel = _cfg(config, 'nap.phone_tel', 'company.phone_tel',
                     default=re.sub(r'\D', '', phone))
    if not phone:
        findings.append(warn('no_phone_in_config',
                             'no nap.phone in docs/client-config.yml; hero CTA button omitted '
                             'rather than guessed (C29)', field_path='hero.buttons'))
    cta = _cta_texts(hero_blocks)
    hero = Hero(
        badge_icon='fas fa-map-marker-alt',
        badge_text=badge_text,
        title=_spanned_h1(h1, city, state),
        description=hook,
        buttons=[
            HeroButton(cta[0] if cta else f'Get Free {city} Inspection', '/contact/',
                       'btn-primary', icon_after='fas fa-arrow-right'),
        ] + ([HeroButton(f'Call: {phone}', f'tel:{phone_tel}', 'btn-ghost-white',
                         icon_before='fas fa-phone')] if phone else []),
        features=features,
    )
    ledger.add(block_id='hero', verdict='KEEP', marker='HERO SECTION',
               words=count_words(hook), text=hook)

    # ---- capsule: promote the first band-compliant FAQ ---------------------
    # Heading-driven pages carry their FAQs as H3 questions with no FAQ SECTION
    # marker at all (all four Northstar landscape-material-supply pages). The
    # questions and in-band answers are on the page; only the marker is absent.
    # Scan the whole page in that case — _faq_pairs only pairs headings that end
    # in '?', so ordinary section headings are never mistaken for questions.
    faq_pairs = _faq_pairs(groups.get('FAQ SECTION', []) or flat)
    capsule = Capsule()
    capsule_pair: tuple[str, str] | None = None
    for question, answer in faq_pairs:
        if not question.strip().endswith('?'):
            continue
        trimmed = ' '.join(_sentences(answer)[:ANSWER_FIRST_MAX_SENTENCES])
        if (ANSWER_FIRST_MIN_WORDS <= count_words(trimmed) <= ANSWER_FIRST_MAX_WORDS
                and not _DOLLAR_RE.search(trimmed)):
            capsule_pair = (question.strip(), trimmed)
            break
    if capsule_pair is None:
        findings.append(block('no_capsule',
                              f'{segment.name}: no FAQ answer fits '
                              f'{ANSWER_FIRST_MIN_WORDS}-{ANSWER_FIRST_MAX_WORDS}w / '
                              f'<={ANSWER_FIRST_MAX_SENTENCES} sentences and is dollar-free; '
                              'capsule NOT fabricated (C27)',
                              field_path='capsule'))

    # ---- sections ---------------------------------------------------------
    sections: list[Section | BuilderCall] = []
    intro = groups.get('INTRO SECTION', [])
    intro_paras = _paragraph_values(intro)
    intro_label = _first_value(intro, 'section label') or 'Trusted Since 2000'
    intro_title = _first_value(intro, 'h2') or f"{city}'s Complete Exterior Contractor"

    if capsule_pair:
        question, answer = capsule_pair
        capsule.interrogative_h2 = question
        capsule.answer_first = answer
        capsule.tldr = intro_paras[0] if intro_paras else answer
        tail = [intro_paras[-1]] if len(intro_paras) > 1 else ([demoted] if demoted else [])
        if len(intro_paras) > 1:
            intro_paras = intro_paras[:-1]
        elif demoted:
            demoted = ''
        cap_props: dict[str, Any] = {
            'label': f'{city}, {state}',
            'title': question,
            'lede': answer,
            'paragraphs': tail,
        }
        img = image_map.get(slug, {})
        if img.get('image') and img.get('imageAlt'):
            cap_props['image'] = img['image']
            cap_props['imageAlt'] = img['imageAlt']
        else:
            findings.append(block('editorial_split_image_required',
                                  f'{slug}: editorial-split requires image + imageAlt (tsc-enforced, '
                                  'Tier-1 alt). No verified image on disk — pass --image-map. '
                                  'Image paths are never invented (C18/C24).',
                                  field_path='sections[editorial-split].image'))
        sections.append(Section('editorial-split', cap_props, core_body=True,
                                source_ref=f'{source_ref}/FAQ', verdict='OPTIMIZE'))
        faq_pairs = [p for p in faq_pairs if p[0].strip() != question]
        ledger.add(block_id='capsule', verdict='OPTIMIZE', marker='FAQ SECTION',
                   words=count_words(answer),
                   reason='FAQ promoted to editorial-split capsule carrier (C1/C2/C28)',
                   text=question)

    if intro_paras:
        sections.append(Section('content-block', {
            'label': intro_label, 'title': intro_title,
            'content': intro_paras + ([demoted] if demoted else []),
        }, core_body=True, source_ref=f'{source_ref}/INTRO', verdict='KEEP'))
        ledger.add(block_id='intro', verdict='KEEP', marker='INTRO SECTION',
                   words=sum(count_words(p) for p in intro_paras))
    else:
        findings.append(warn('no_intro', f'{segment.name}: no INTRO SECTION paragraphs',
                             field_path='sections'))

    # generic July section markers (VENTILATION / WHY INSTALL / MATERIALS / HOA /
    # SERVICE AREA / ...) — any '* SECTION' the fixed vocabulary does not name.
    # Appended in document order so the page reads top-to-bottom as authored.
    for marker in list(groups):
        if (marker in _HANDLED_MARKERS or marker.startswith('ZIGZAG')
                or marker in _BUILDER_MARKERS or marker in _BANK_MARKERS):
            continue
        gsec = _generic_section(marker, groups[marker], source_ref, city)
        if gsec is not None:
            sections.append(gsec)
            ledger.add(block_id=marker, verdict='KEEP', marker=marker,
                       words=_core_words_of(gsec),
                       reason='generic July section marker -> ' + gsec.type)
        else:
            ledger.add(block_id=marker, verdict='BANK', marker=marker, words=0,
                       reason='unrecognized July marker with no extractable body/cards')

    # zigzag residential / commercial -> content-block each
    related_link_names: list[str] = []
    for marker in [m for m in groups if m.startswith('ZIGZAG')]:
        zz = groups[marker]
        body = _paragraph_values(zz)
        title = _first_value(zz, 'h3', 'h2') or marker.title()
        if body:
            sections.append(Section('content-block', {
                'label': _first_value(zz, 'section label') or 'Services',
                'title': title, 'content': body,
            }, core_body=True, source_ref=f'{source_ref}/{marker}', verdict='KEEP'))
            ledger.add(block_id=marker, verdict='KEEP', marker=marker,
                       words=sum(count_words(p) for p in body))
        related_link_names.extend(_service_links(zz))

    # exterior services -> types grid
    ext = groups.get('EXTERIOR SERVICES SECTION', []) or groups.get('ZIGZAG SERVICES SECTION', [])
    ext_cards = _enum_cards(ext, ('card', 'extcard'))
    if ext_cards:
        cards = [{'icon': _icon_for(t), 'title': t, 'description': d} for t, d in ext_cards]
        if len(cards) not in VALID_CARD_GRID_COUNTS:
            findings.append(warn('card_grid_count',
                                 f'types grid has {len(cards)} cards; renderer supports '
                                 f'{sorted(VALID_CARD_GRID_COUNTS)} '
                                 f'(>6 silently discards 7+). Curation call (C23).',
                                 field_path='sections[types].cards'))
        sections.append(Section('types', {
            'label': _first_value(ext, 'section label') or 'Full Exterior',
            'title': _first_value(ext, 'h2') or f'Complete Exterior Services in {city}, {state}',
            'subtitle': _first_value(ext, 'subtitle') or
                        'One contractor, one call, every exterior surface covered.',
            'cards': cards,
        }, core_body=True, source_ref=f'{source_ref}/EXTERIOR', verdict='KEEP'))
        ledger.add(block_id='exterior-services', verdict='KEEP',
                   marker='EXTERIOR SERVICES SECTION',
                   words=sum(count_words(d) for _, d in ext_cards))
    related_link_names.extend(_service_links(ext))

    # shared builders (coverage_method: builder-collapse)
    neighborhoods = _neighborhood_prose(intro_paras, city)
    for marker, builder in _BUILDER_MARKERS.items():
        if marker not in groups:
            continue
        args: list[Any] = {'certificationsSection': [city, neighborhoods],
                           'whyAcmeSection': [city],
                           'financingSection': [city],
                           'processSection': []}[builder]
        if not any(isinstance(s, BuilderCall) and s.name == builder for s in sections):
            sections.append(BuilderCall(builder, args))
        banked = sum(count_words(b.text) for b in groups[marker])
        ledger.add(block_id=marker, verdict='BANK', marker=marker, words=banked,
                   reason=f'coverage_method=builder-collapse -> {builder}(); '
                          'city-specific card copy banked, not shipped')

    # storm + insurance -> dark content-block
    storm = groups.get('STORM AND INSURANCE SECTION', []) or groups.get('STORM & INSURANCE SECTION', [])
    if storm:
        content = _paragraph_values(storm)
        checklist_anchor = next((b for b in storm if b.label.lower() == 'checklist'), None)
        if checklist_anchor is not None:
            if checklist_anchor.value:
                items = [i for i in _BULLET_SPLIT_RE.split(checklist_anchor.value) if i.strip()]
            else:
                items = _continuation(storm, checklist_anchor)
            content = content + items
        if content:
            sections.append(Section('content-block', {
                'label': _first_value(storm, 'section label') or 'Storm Damage',
                'title': _first_value(storm, 'h2') or f'{city} Storm Damage and Insurance Claims',
                'content': content, 'dark': True,
            }, core_body=True, source_ref=f'{source_ref}/STORM', verdict='KEEP'))
            ledger.add(block_id='storm', verdict='KEEP', marker='STORM AND INSURANCE SECTION',
                       words=sum(count_words(c) for c in content))

    # testimonials -> one testimonial section, the rest banked
    tst = groups.get('TESTIMONIALS SECTION', [])
    quotes = _enum_cards(tst, ('testimonial',))
    if quotes:
        head, body = quotes[0]
        text = re.sub(r'^[“"]|[”"]$', '', body or head).strip()
        sections.append(Section('testimonial', {
            'label': _first_value(tst, 'section label') or 'Real Reviews',
            'title': _first_value(tst, 'h2') or f'Real Reviews from {city} Homeowners',
            'text': text, 'name': 'Verified Customer', 'initials': 'VC',
            'location': f'{city}, {state}',
        }, source_ref=f'{source_ref}/TESTIMONIAL', verdict='KEEP'))
        findings.append(warn('testimonial_attribution_missing',
                             f'{segment.name}: DOCX testimonials carry no reviewer name; '
                             'placeholder attribution emitted — needs a real name before ship',
                             field_path='sections[testimonial].name'))
        for h, b in quotes[1:]:
            ledger.add(block_id=f'testimonial:{h[:40]}', verdict='BANK',
                       marker='TESTIMONIALS SECTION', words=count_words(b),
                       reason='TestimonialSection holds one quote', text=b)

    # nearby areas -> service-areas
    nearby = groups.get('NEARBY AREAS SECTION', [])
    areas = _areas_from(nearby, state)
    if areas:
        sections.append(Section('service-areas', {
            'label': _first_value(nearby, 'section label') or 'Service Area',
            'title': _first_value(nearby, 'h2') or 'Nearby Areas We Serve',
            'subtitle': _first_value(nearby, 'subtitle') or
                        f'Acme serves {city} and the surrounding communities.',
            'areas': areas,
        }, source_ref=f'{source_ref}/NEARBY', verdict='KEEP'))
        ledger.add(block_id='nearby-areas', verdict='KEEP', marker='NEARBY AREAS SECTION',
                   words=0)
    elif nearby:
        findings.append(warn('no_service_areas',
                             f'{segment.name}: NEARBY AREAS SECTION present but no parseable '
                             'city/state cells', field_path='sections'))

    # related-services from the DOCX's own service links (C16 inbound links)
    related_links: list[dict[str, str]] = []
    if related_link_names:
        services = []
        for name in related_link_names:
            leaf = _service_slug(name, city)
            if not leaf:
                continue
            url_path = f'/{slug}/{leaf}/'
            services.append({'title': name, 'description': '', 'url': url_path,
                             'icon': _icon_for(name)})
            related_links.append({'title': name, 'url': url_path})
        if services:
            if len(services) not in VALID_CARD_GRID_COUNTS:
                findings.append(warn('card_grid_count_related',
                                     f'related-services has {len(services)} entries; renderer '
                                     f'supports {sorted(VALID_CARD_GRID_COUNTS)}. Curation call.',
                                     field_path='sections[related-services].services'))
            findings.append(warn('related_services_descriptions_empty',
                                 'related-services descriptions are empty: the DOCX ships bare '
                                 'link labels. Not fabricated (C27).',
                                 field_path='sections[related-services]'))
            sections.append(Section('related-services', {
                'label': f'{city} Services',
                'title': f'Specialized Exterior Work in {city}',
                'subtitle': f'Explore the specific service your {city} project needs.',
                'services': services,
            }, source_ref=f'{source_ref}/LINKS', verdict='KEEP'))

    for marker, reason in _BANK_MARKERS.items():
        if marker in groups:
            ledger.add(block_id=marker, verdict='BANK', marker=marker,
                       words=sum(count_words(b.text) for b in groups[marker]), reason=reason)

    # ---- brief payload ----------------------------------------------------
    fanout = _fanout(groups, related_link_names, city)
    if len(fanout) < BRIEF_MIN_FANOUT:
        findings.append(block('brief_fanout_short',
                              f'{len(fanout)} distinct fanout terms < {BRIEF_MIN_FANOUT}',
                              field_path='fanout_queries'))
    triples = _triples(flat, city, state)
    if not triples:
        findings.append(block('brief_no_triples', 'no grounded semantic triple in source',
                              field_path='semantic_triples'))

    # ---- assemble ---------------------------------------------------------
    # BUG-016: service and title were hardcoded to 'Roofing Contractor', the
    # pilot client's trade, so every other client's pages were emitted with the
    # wrong business described. Read the client's own trade, and fail LOUD when
    # it is missing rather than inventing one — a confident wrong label sails
    # through every gate that only checks shape.
    service_label = _service_label(config)
    if not service_label:
        findings.append(block(
            'no_service_label',
            "client-config.yml has no `trade` / `business.trade` / `primary_service`, "
            "so the page's service cannot be named. Set it — do not let this default.",
            field_path='service'))
    if not state:
        findings.append(block(
            'no_state',
            "client-config.yml has no `states_served`, and the slug carries no state "
            "suffix, so the page's state cannot be resolved.",
            field_path='state'))

    draft = PageDraft(
        url_path=slug,
        page_kind=page_kind,
        city=city,
        state=state,
        service='' if page_kind == 'hub' else service_label,
        h1=h1,
        meta_title=meta_title,
        meta_description=meta_description,
        hero=hero,
        title=f'{service_label} in {city}, {state}' if service_label else f'{city}, {state}',
        sections=sections,
        faqs=[FaqItem(q, a) for q, a in faq_pairs],
        capsule=capsule,
        proprietary_variables=['neighborhoods'],
        fanout_queries=fanout,
        semantic_triples=triples,
        intent='commercial',
        source_ref=source_ref,
        coverage_method=_cfg(config, 'repo.coverage_method', 'content.coverage_method',
                             'coverage_method'),
        related_links=related_links,
    )

    # ---- distillation + text hazards + structural checks -------------------
    findings.extend(distill_core_body(draft, ledger))

    for label, text in _all_strings(draft):
        findings.extend(_text_hazards(label, text))
    for label, heading in _all_headings(draft):
        # Interrogative headings (FAQ questions) are natural-language sentences
        # feeding FAQPage schema and AI extraction — Title-casing them degrades
        # both. Same exemption as the distiller (v1.3) and the engine preflight's
        # CURATE rating; Acme alone ships 428 live FAQ questions in sentence
        # case through its own gates.
        if heading and not heading.rstrip('*_ \t').endswith('?') \
                and not _title_case_ok(heading):
            findings.append(warn('heading_case', f'{label}: not strict Title Case',
                                 field_path=label, detail=heading[:90]))

    # transformLocationSections is a ACME renderer internal (see repo_layout).
    # On any other renderer this fired categorically — no_new_type x24 on
    # Crestline, x16 on Northstar in the 2026-08 cycle — for a transform those
    # renderers never call.
    if _rl_active().is_acme_renderer and not draft.has_new_type():
        findings.append(block('no_new_type',
                              'sections[] carries no "new" editorial type: '
                              'transformLocationSections() would rewrite this page and void '
                              'every preceding assertion (C28)', field_path='sections'))

    ratio = ledger.dropped_ratio()
    if ratio > 0.40:
        findings.append(warn('ledger_drop_circuit_breaker',
                             f'{ratio:.0%} of source blocks DROP/BANK (> 40%): needs explicit '
                             'acknowledgement before emit (C26)', field_path='ledger'))

    if mode == 'b':
        legal = {'content-block', 'types', 'benefits', 'process-steps',
                 'service-areas', 'related-services'}
        keep: list[Section | BuilderCall] = []
        seen_content_block = False
        for s in draft.sections:
            if isinstance(s, BuilderCall):
                keep.append(s)
                continue
            if s.type not in legal or (s.type == 'content-block' and seen_content_block):
                ledger.add(block_id=s.source_ref or s.type, verdict='DROP', marker=s.type,
                           words=_core_words_of(s),
                           reason='Mode B: transformLocationSections() silently drops this')
                continue
            seen_content_block = seen_content_block or s.type == 'content-block'
            keep.append(s)
        draft.sections = keep
        draft.core_body_words = recount_core_words(draft)

    # ---- C3: render capsule.tldr as a real NODE ---------------------------
    # Declaring `capsule.tldr` in the brief is NOT the same as shipping it in the
    # copy: capsule_check reads the BUILT html and matches TLDR_RE against real
    # prose. Without this, every page whose body clears
    # content.long_page_threshold (default 1200w) is refused `tldr_node_missing`
    # — which is exactly what happened to all 25 real Acme drafts.
    #
    # A `content-block` titled 'Key Takeaways' is the cheapest carrier that
    # reaches the built HTML, and it is appended LAST so it can never become the
    # page's first interrogative H2 and hijack the capsule (C1/C2).
    #
    # core_body=False: a summary restates core prose that is already counted, so
    # counting it again would inflate core_words against the module-05 band.
    #
    # Appended AFTER the Mode B filter on purpose. In Mode B the filter keeps
    # only the FIRST content-block, so adding it earlier would silently drop it.
    # NOTE (Mode B limitation): transformLocationSections() synthesises its own
    # section list at render time, so this node does not reach the HTML on a
    # Mode B page. Mode B pages over the long-page threshold therefore still need
    # a TL;DR carrier the renderer preserves — tracked, not silently ignored.
    if not TLDR_RE.search(' '.join(t for _, t in _all_strings(draft))):
        tldr_text = (draft.capsule.tldr or '').strip()
        if tldr_text:
            draft.sections = list(draft.sections) + [Section(
                'content-block',
                {'label': 'Summary', 'title': 'Key Takeaways', 'content': [tldr_text]},
                core_body=False, source_ref=f'{source_ref}/TLDR', verdict='KEEP',
            )]
            ledger.add(block_id='tldr', verdict='KEEP', marker='SUMMARY',
                       words=count_words(tldr_text),
                       reason='capsule.tldr rendered as a Key Takeaways node (C3)')
            # recount_core_words() keys off section TYPE, not Section.core_body:
            # per module 05 `content-block.content[]` counts, so this node moves
            # the number. Restate it here or emit_ts fires a spurious
            # core_words_reported_mismatch warn on every long page.
            draft.core_body_words = recount_core_words(draft)
        else:
            # Only a BLOCK when the built gate would actually fail. capsule_check
            # demands a TL;DR ONLY above content.long_page_threshold (default 1500
            # per the Content Team Operating Standard §01 Gate 1: "On pages over
            # 1,500 words, add a TL;DR"). This used to block UNCONDITIONALLY, so
            # 456-word pages were refused for lacking a TL;DR the standard — and
            # the gate itself — never asked them to carry. Produce-by-construction
            # must never be stricter than the gate it protects.
            _long = ((config or {}).get('content') or {}).get('long_page_threshold', 1500)
            if (draft.core_body_words or 0) > _long:
                findings.append(block('tldr_text_missing',
                                      f'capsule.tldr is empty on a long page '
                                      f'({draft.core_body_words}w > {_long}w); no Key Takeaways '
                                      'node can be rendered and capsule_check would exit 6 (C3)',
                                      field_path='capsule.tldr'))

    draft.ledger = ledger.rows
    draft.findings = findings
    return draft


def _trust_stats(hero_blocks: list[RawBlock]) -> list[str]:
    anchor = next((b for b in hero_blocks if b.label.lower() in ('trust stats', 'stats')), None)
    if anchor is None:
        return []
    raw = anchor.value or ' '.join(_continuation(hero_blocks, anchor))
    for b in hero_blocks:
        if b.kind == 'table' and b.rows:
            cols = list(zip(*b.rows))
            return [' '.join(c).strip() for c in cols][:4]
    parts = [p.strip() for p in re.split(r'\s*\|\s*', raw) if p.strip()]
    if len(parts) >= 8:
        half = len(parts) // 2
        return [f'{a} {b}'.strip() for a, b in zip(parts[:half], parts[half:])][:4]
    return parts[:4]


def _cta_texts(hero_blocks: list[RawBlock]) -> list[str]:
    anchor = next((b for b in hero_blocks if b.label.lower().startswith('cta button')), None)
    if anchor is None:
        return []
    if anchor.value:
        return [_EMOJI_RE.sub('', p).strip()
                for p in re.split(r'\s*(?:→|\|)\s*', anchor.value) if p.strip()]
    return [_EMOJI_RE.sub('', t).strip() for t in _continuation(hero_blocks, anchor)]


def _neighborhood_prose(paragraphs: list[str], city: str) -> str:
    """certificationsSection(city, neighborhoods) — the second argument is real
    neighbourhood names lifted from the DOCX intro, never invented."""
    text = ' '.join(paragraphs)
    names: list[str] = []
    for m in re.finditer(r'\b(?:in|near|around|like|from)\s+((?:[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)'
                         r'(?:,\s(?:[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)){0,3})', text):
        for part in m.group(1).split(','):
            part = part.strip()
            if part and part != city and part not in names and len(part) > 3:
                names.append(part)
    return ', '.join(names[:4])


def _service_slug(name: str, city: str) -> str:
    """'Gutter Repair Kannapolis' -> 'gutter-repair'. Must end in a suffix
    locationLabel() understands (SUBSERVICE_SUFFIX_RE)."""
    stem = re.sub(re.escape(city), '', name, flags=re.I).strip()
    stem = re.sub(r'[^A-Za-z0-9]+', '-', stem).strip('-').lower()
    if not re.search(r'-(installation|repair|replacement|services|claims)$', stem):
        return ''
    return stem


def _fanout(groups: dict[str, list[RawBlock]], link_names: list[str], city: str) -> list[str]:
    terms: list[str] = []
    for name in link_names:
        terms.append(name.strip())
    for marker, blocks in groups.items():
        for b in blocks:
            if b.label.lower() in ('h2', 'h3') and b.value:
                terms.append(b.value.strip())
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        key = t.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(t.strip())
    return out


def _triples(flat: list[RawBlock], city: str, state: str) -> list[SemanticTriple]:
    """Only assert what the DOCX itself states."""
    blob = ' '.join(b.text for b in flat)
    triples: list[SemanticTriple] = []
    if re.search(r'GAF Master Elite', blob, re.I):
        triples.append(SemanticTriple('Acme Roofing', 'holds certification',
                                      'GAF Master Elite Contractor'))
    if re.search(r'North Carolina, South Carolina, Virginia, and West Virginia', blob):
        triples.append(SemanticTriple('Acme Roofing', 'is licensed in',
                                      'North Carolina, South Carolina, Virginia, and West Virginia'))
    if city:
        triples.append(SemanticTriple('Acme Roofing', 'serves', f'{city}, {state}'))
    return triples


def _all_strings(draft: PageDraft) -> Iterator[tuple[str, str]]:
    yield 'metaTitle', draft.meta_title
    yield 'metaDescription', draft.meta_description
    yield 'hero.title', draft.hero.title
    yield 'hero.description', draft.hero.description
    for i, f in enumerate(draft.hero.features):
        yield f'hero.features[{i}]', f
    for si, s in enumerate(draft.real_sections()):
        for key, value in s.props.items():
            for label, text in _walk(f'sections[{si}].{key}', value):
                yield label, text
    for i, faq in enumerate(draft.faqs):
        yield f'faqs[{i}].question', faq.question
        yield f'faqs[{i}].answer', faq.answer
    yield 'capsule.answer_first', draft.capsule.answer_first
    yield 'capsule.interrogative_h2', draft.capsule.interrogative_h2


def _walk(prefix: str, value: Any) -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield prefix, value
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _walk(f'{prefix}[{i}]', v)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _walk(f'{prefix}.{k}', v)


def _all_headings(draft: PageDraft) -> Iterator[tuple[str, str]]:
    for si, s in enumerate(draft.real_sections()):
        for key in ('title', 'headline'):
            if isinstance(s.props.get(key), str):
                yield f'sections[{si}].{key}', s.props[key]
        for coll in ('cards', 'items', 'steps', 'services'):
            for ci, entry in enumerate(s.props.get(coll, []) or []):
                if isinstance(entry, dict) and isinstance(entry.get('title'), str):
                    yield f'sections[{si}].{coll}[{ci}].title', entry['title']
    for i, faq in enumerate(draft.faqs):
        yield f'faqs[{i}].question', faq.question


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def draft_to_json(draft: PageDraft) -> dict[str, Any]:
    """A rehydratable dict. Sections keep a `_node` discriminator so the emitter
    can tell a Section from a BuilderCall without guessing."""
    sections: list[dict[str, Any]] = []
    for s in draft.sections:
        if isinstance(s, BuilderCall):
            sections.append({'_node': 'builder', 'name': s.name, 'args': s.args})
        else:
            sections.append({'_node': 'section', 'type': s.type, 'props': s.props,
                             'core_body': s.core_body, 'source_ref': s.source_ref,
                             'verdict': s.verdict})
    return {
        'url_path': draft.url_path, 'page_kind': draft.page_kind,
        'city': draft.city, 'state': draft.state, 'service': draft.service,
        'h1': draft.h1, 'meta_title': draft.meta_title,
        'meta_description': draft.meta_description,
        'title': draft.title, 'export_name': draft.resolved_export_name,
        'last_updated': draft.resolved_last_updated,
        'route': draft.route, 'route_array': draft.route_array,
        'hero': {
            'badge_icon': draft.hero.badge_icon, 'badge_text': draft.hero.badge_text,
            'title': draft.hero.title, 'description': draft.hero.description,
            'bg_image': draft.hero.bg_image, 'features': draft.hero.features,
            'buttons': [b.to_props() for b in draft.hero.buttons],
        },
        'sections': sections,
        'faqs': [f.to_props() for f in draft.faqs],
        'capsule': draft.capsule.to_dict(),
        'proprietary_variables': draft.proprietary_variables,
        'fanout_queries': draft.fanout_queries,
        'semantic_triples': [t.to_dict() for t in draft.semantic_triples],
        'intent': draft.intent,
        'core_body_words': draft.core_body_words,
        'source_ref': draft.source_ref,
        'coverage_method': draft.coverage_method,
        'related_links': draft.related_links,
        'ledger': draft.ledger,
        'findings': [f.as_dict() for f in draft.findings],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def distill(docx_path: str, *, limit: int | None = None, config: dict | None = None,
            mode: str = 'a', image_map: dict[str, dict[str, str]] | None = None
            ) -> list[PageDraft]:
    """Pass 1 + pass 2. DOCX in, List[PageDraft] out."""
    blocks = read_docx_blocks(docx_path)
    segments = segment_pages(blocks)
    # FAIL LOUD before doing any work: a non-empty DOCX that segments to 0 pages
    # is a parse failure, never a clean-but-empty run (raises UnsegmentableDocxError).
    assert_segmentable(blocks, segments, source=docx_path)
    if limit:
        segments = segments[:limit]
    return [build_draft(s, docx_path, config=config, mode=mode, image_map=image_map)
            for s in segments]


def load_client_config(project_dir: str | None) -> dict:
    """C29 — read the client's real config; never hardcode client values."""
    if not project_dir or _common is None:
        return {}
    try:
        return _common.load_config(project_dir) or {}
    except SystemExit:
        return {}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _report(drafts: list[PageDraft], verbose: bool = False) -> int:
    counts = sorted(d.core_body_words for d in drafts)
    n = len(counts)
    if n:
        median = counts[n // 2] if n % 2 else (counts[n // 2 - 1] + counts[n // 2]) / 2
        low = [d for d in drafts if d.core_body_words < CORE_WORDS_MIN]
        high = [d for d in drafts if d.core_body_words > CORE_WORDS_MAX]
        print(f'pages segmented : {n}')
        print(f'core_words      : min={counts[0]} median={median:g} max={counts[-1]} '
              f'(band {CORE_WORDS_MIN}-{CORE_WORDS_MAX}, advisory {CORE_WORDS_SWEET_SPOT})')
        print(f'outside band    : {len(low) + len(high)}  '
              f'(under={len(low)}, over={len(high)})')
        if low:
            print('  under: ' + ', '.join(f'{d.slug}={d.core_body_words}' for d in low))
        if high:
            print('  over : ' + ', '.join(f'{d.slug}={d.core_body_words}' for d in high))

    blocking = [f for d in drafts for f in d.findings if f.blocking]
    warns = [f for d in drafts for f in d.findings if not f.blocking]
    print(f'findings        : {len(blocking)} blocking, {len(warns)} warn')
    by_code: dict[str, int] = {}
    for f in blocking + warns:
        by_code[f'{f.severity}:{f.code}'] = by_code.get(f'{f.severity}:{f.code}', 0) + 1
    for code, count in sorted(by_code.items(), key=lambda kv: -kv[1]):
        print(f'  {count:>4}  {code}')
    if verbose:
        for d in drafts:
            print(f'\n--- {d.slug} ({d.page_kind}) core={d.core_body_words} '
                  f'sections={len(d.sections)} faqs={len(d.faqs)}')
            for f in d.findings:
                print(f'      [{f.severity}] {f.code}: {f.message}')
    return 9 if blocking else (1 if warns else 0)


def main() -> int:
    ap = argparse.ArgumentParser(
        prog='wf-distill',
        description='Pass 1+2: a team DOCX becomes structured, gate-aware PageDrafts.')
    ap.add_argument('docx', help='source DOCX (docs/intake/*.docx)')
    ap.add_argument('--out', help='write drafts JSON here')
    ap.add_argument('--limit', type=int, help='only distill the first N pages')
    ap.add_argument('--project-dir', help='client repo root, for docs/client-config.yml (C29)')
    ap.add_argument('--mode', choices=('a', 'b'), default='a',
                    help="a = author editorial sections (transform suppressed, default); "
                         "b = repo-parity Mode B (renderer synthesises; extra sections dropped)")
    ap.add_argument('--image-map', help='JSON {slug: {image, imageAlt}} of VERIFIED image paths')
    ap.add_argument('--self-test', action='store_true',
                    help='distill the DOCX and print the distribution report')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    if not Path(args.docx).exists():
        print(f'[ERROR] no such DOCX: {args.docx}', file=sys.stderr)
        return 2

    image_map = {}
    if args.image_map:
        image_map = json.loads(Path(args.image_map).read_text())

    config = load_client_config(args.project_dir)
    from pipeline.generate import repo_layout as _rl
    _rl.activate(config)
    try:
        drafts = distill(args.docx, limit=args.limit, config=config, mode=args.mode,
                         image_map=image_map)
    except UnsegmentableDocxError as exc:
        # Refuse rather than write an empty drafts.json the emitter would silently
        # accept. Nothing is written; the chain stops here with a distinct code.
        print(f'[REFUSED] {exc}', file=sys.stderr)
        return exc.exit_code

    if args.out:
        payload = [draft_to_json(d) for d in drafts]
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f'wrote {len(payload)} drafts -> {args.out}')

    return _report(drafts, verbose=args.verbose or args.self_test)


if __name__ == '__main__':
    raise SystemExit(main())
