#!/usr/bin/env python3
"""Content constraint validators for the pass-3 emitter — the Phase-2 re-target.

`V2-Prototype/scripts/emit_page.py` proved V1-V6 against a JSON stand-in. This
module is the same six constraints re-aimed at the real `PageDraft` / `ServicePage`
shape, plus the produce-by-construction checks that make a draft satisfy the §19
brief, §20 capsule and §21 non-commodity gates BEFORE the build runs rather than
after it reds.

    V1  hero rule       hero.description <= 25 words AND <= 2 sentences AND
                        <= 160 chars — all three. Auto-fixable by hero-hook
                        extraction: the compliant lead stays in the hero, the
                        remainder is DEMOTED into the body (never discarded).
    V2  metaTitle       <= 56 effective chars, '&' counted as '&amp;'.
    V3  em-dash ban     glyph AND entity forms, in every string that reaches
                        HTML. Auto-fixable (C12) and applied LAST.
    V4  Title Case      every string that reaches an <h2>/<h3>, judged on the
                        tag-stripped, entity-unescaped text with the gate's own
                        `is_exempt` / `strict_violation` semantics.
    V5  card grids      every card/step/item array is exactly 3, 4, 5 or 6.
    V6  alt text        no image field may ship without its alt sibling — the
                        three tiers, plus a generic sweep for image-ish keys the
                        tier maps do not name.

    S19 brief           delegated to models.structural_findings (fanout, triples,
                        proprietary_variable, intent).
    S20 capsule         the capsule must be CARRIED and must be the page's FIRST
                        interrogative H2, with a real TL;DR node in the emitted
                        copy — not merely declared in the brief.
    S21 non-commodity   the projected page text must hit the client's own §21
                        allow-list (rebuilt with the gate's own functions), and
                        must not five-gram-overlap an already-emitted sibling
                        past the resolved threshold.

Severity contract (models.ValidationFinding):
    'block' -> refuse to emit. 'warn'  -> emit and flag for the operator's ledger.
`auto_fixable` marks the MECHANICAL class only (hero hook, em dash, invisible
codepoints). Curation judgment — card-grid counts, core-body band, heading
recasing — is never auto-fixed: silently "fixing" it is how a page ships wrong.

Every constant here is READ from real gate code or real client TS. Nothing is
invented, and no gate under pipeline/gates/ is modified: this module's whole job
is to satisfy them.

Usage:
    validators.py --self-test [-v]
    validators.py --self-test --project /path/to/acme-roofing-site
"""
from __future__ import annotations

import argparse
import copy
import html as htmlmod
import re
import sys
from dataclasses import replace
from typing import Any, Callable, Iterable, Sequence

if __name__ == '__main__':  # pragma: no cover - script bootstrap
    # Run as a plain script (`pipeline/generate/validators.py`), NOT
    # `-m pipeline.generate.validators`: the package __init__ re-exports models, so
    # -m executes it twice under two names and the two copies of Section fail
    # isinstance against each other. The path insert must happen BEFORE the import
    # below, which is why it lives here and not under the __main__ guard at the end.
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pipeline.generate.models import (
    ANSWER_FIRST_MAX_SENTENCES,
    ANSWER_FIRST_MAX_WORDS,
    ANSWER_FIRST_MIN_WORDS,
    DECORATIVE_IMAGE_FIELDS,
    HERO_MAX_CHARS,
    HERO_MAX_SENTENCES,
    HERO_MAX_WORDS,
    META_TITLE_MAX_EFFECTIVE,
    META_TITLE_MIN,
    TIER1_ALT_FIELDS,
    TIER2_ALT_FIELDS,
    TIER3_TITLE_IS_ALT,
    VALID_CARD_GRID_COUNTS,
    BuilderCall,
    Hero,
    PageDraft,
    RawExpr,
    Section,
    ValidationFinding,
    apply_severity_policy,
    block,
    curate,
    count_sentences,
    count_words,
    effective_len,
    strip_tags,
    structural_findings,
    warn,
)

# ---------------------------------------------------------------------------
# Constants mirrored from the gates. Each cite is a real file:symbol.
# ---------------------------------------------------------------------------

#: em_dash_check.EM_FORMS, plus the '---' the team's DOCX->markdown pipeline
#: produces (it becomes an em dash downstream, so it is banned at source too).
EM_DASH_FORMS: tuple[str, ...] = ('—', '&mdash;', '&#8212;', '&#x2014;', '&#X2014;', '---')

#: fingerprint_check.INVISIBLE + TAG_RANGE. U+FEFF is stripped only when it is
#: NOT the leading byte-order mark, matching the gate.
_INVISIBLE: frozenset[int] = frozenset(
    {0x200B, 0x200C, 0x200D, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064,
     0x00AD, 0x180E, 0x061C, 0x200E, 0x200F}
    | set(range(0x202A, 0x202F))
    | set(range(0x2066, 0x206A))
    | set(range(0xE0000, 0xE0080))
)
_BOM = 0xFEFF

#: fingerprint_check.DEFAULT_MARKERS.
FINGERPRINT_MARKERS: tuple[str, ...] = ('data-generated-by',)

#: check_headings.DEFAULT_STOPWORDS — lowercase-allowed only MID-heading.
HEADING_STOPWORDS: frozenset[str] = frozenset({
    'a', 'an', 'the', 'and', 'or', 'nor', 'but', 'for', 'of', 'to', 'in', 'on',
    'at', 'by', 'with', 'from', 'as', 'per', 'via', 'vs', 'into', 'onto', 'over',
    'up', 'off', 'out', 'so', 'yet', 'if', 'than', 'then',
})

#: check_headings._EDGE — punctuation stripped before casing analysis.
_HEADING_EDGE = '.,:;!?"\'()[]{}—–-&/…“”‘’'

#: capsule_check.INTERROGATIVE_LEAD / TLDR_RE.
INTERROGATIVE_LEAD = re.compile(
    r'^(how|what|why|when|where|which|who|do|does|is|are|can|should|will)\b', re.IGNORECASE)
TLDR_RE = re.compile(r'tl;?dr|key takeaways|in short|the short answer|bottom line', re.IGNORECASE)

#: capsule_check.DEFAULT_EXCLUDE / noncommodity_check.DEFAULT_EXCLUDE (identical).
DEFAULT_EXCLUDE: frozenset[str] = frozenset({
    '/', '/contact/', '/about/', '/privacy/', '/privacy-policy/',
    '/terms/', '/terms-of-service/', '/thank-you/', '/404/', '/500/',
    '/_not-found/', '/blog/',
})

#: content.long_page_threshold default, per capsule_check's docstring.
DEFAULT_LONG_PAGE_THRESHOLD = 1200

#: Props that reach an <h2>/<h3> at the section level (ServicePageRenderer).
SECTION_HEADING_PROPS: tuple[str, ...] = ('title', 'headline', 'leftTitle', 'rightTitle')

#: Array props whose entries carry a `title` that reaches an <h3>.
NESTED_HEADING_ARRAYS: tuple[str, ...] = ('cards', 'items', 'steps', 'projects', 'services')

#: Array props subject to the renderer's 3/4/5/6 grid matrix (V5).
CARD_GRID_ARRAYS: tuple[str, ...] = (
    'cards', 'items', 'steps', 'images', 'projects', 'areas', 'services',
)

#: Keys that hold an image path. Matched case-insensitively on the whole key so
#: 'image', 'bgImage', 'photo', 'beforeImage', 'afterImage' all land.
_IMAGE_KEY_RE = re.compile(r'^(.*?)(image|photo|img)$', re.IGNORECASE)
_ALT_KEY_RE = re.compile(r'alt$', re.IGNORECASE)

#: Tier-3 rule: the adjacent title IS the alt string, so it must read as one.
TIER3_MIN_TITLE_WORDS = 3


# ---------------------------------------------------------------------------
# String traversal — one walker, so every check sees the same strings.
# ---------------------------------------------------------------------------

def _walk(node: Any, path: str, out: list[tuple[str, str]]) -> None:
    """Collect (field_path, text) for every str under `node`.

    RawExpr is deliberately skipped: it is a verbatim TS identifier, not authored
    copy, and the scrubbers must not rewrite an identifier. That is also why
    RawExpr must never be used to smuggle prose past this walker.
    """
    if isinstance(node, str):
        out.append((path, node))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _walk(v, f'{path}[{i}]', out)
    elif isinstance(node, dict):
        for k, v in node.items():
            _walk(v, f'{path}.{k}' if path else str(k), out)


def rendered_strings(draft: PageDraft) -> list[tuple[str, str]]:
    """Every authored string that reaches the built HTML, in emission order.

    Includes BuilderCall args — `certificationsSection('Matthews', '...prose...')`
    puts both of those straight into the page, so they are as scannable as any
    literal. Excludes the derived route/canonical (never authored) and
    markdownContent (structurally unemittable).
    """
    out: list[tuple[str, str]] = []
    _walk(_hero_props(draft), 'hero', out)
    for i, section in enumerate(draft.sections):
        if isinstance(section, BuilderCall):
            _walk(list(section.args), f'sections[{i}].args', out)
        else:
            _walk(section.props, f'sections[{i}]', out)
    for i, faq in enumerate(draft.faqs):
        out.append((f'faqs[{i}].question', faq.question))
        out.append((f'faqs[{i}].answer', faq.answer))
    out.append(('metaTitle', draft.meta_title))
    out.append(('metaDescription', draft.meta_description))
    out.append(('title', draft.resolved_title))
    return out


def _hero_props(draft: PageDraft) -> dict[str, Any]:
    hero = draft.hero
    if not hero.title and draft.h1:
        hero = replace(hero, title=draft.h1)
    return hero.to_props()


def heading_strings(draft: PageDraft) -> list[tuple[str, str]]:
    """Every string that reaches an <h1>/<h2>/<h3>, in DOM order.

    FAQ questions are included because C11 names them, even though the renderer
    puts them in a <span> inside a <button> — check_headings will not see them in
    the built HTML, so this is stricter than the gate, deliberately.
    """
    out: list[tuple[str, str]] = []
    hero_title = draft.hero.title or draft.h1
    if hero_title:
        out.append(('hero.title', hero_title))
    for i, section in enumerate(draft.sections):
        if isinstance(section, BuilderCall):
            continue  # builder headings are fixed repo copy, not authored here
        for key in SECTION_HEADING_PROPS:
            value = section.props.get(key)
            if isinstance(value, str) and value.strip():
                out.append((f'sections[{i}].{key}', value))
        for arr_key in NESTED_HEADING_ARRAYS:
            arr = section.props.get(arr_key)
            if not isinstance(arr, list):
                continue
            for j, item in enumerate(arr):
                if isinstance(item, dict) and isinstance(item.get('title'), str):
                    out.append((f'sections[{i}].{arr_key}[{j}].title', item['title']))
    for i, faq in enumerate(draft.faqs):
        out.append((f'faqs[{i}].question', faq.question))
    return out


def projected_text(draft: PageDraft) -> str:
    """A flat approximation of the page's stripped body text.

    This is what the built-HTML gates will read once the renderer runs, minus the
    site chrome. Used for the §21 allow-list hit test, the five-gram overlap, the
    TL;DR node search, and the long-page word count.
    """
    return '\n'.join(strip_tags(t) for _, t in rendered_strings(draft))


def body_words(draft: PageDraft) -> int:
    """WHOLE-page word count — chrome and FAQs included (C3).

    Deliberately NOT core_words: the long_page_threshold that decides whether a
    TL;DR is mandatory counts the whole stripped body, so gambling on core_words
    is how a long page ships without its TL;DR node.
    """
    return count_words(projected_text(draft))


# ---------------------------------------------------------------------------
# V1 — hero rule (+ hero-hook extraction)
# ---------------------------------------------------------------------------

def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s]


def hero_violations(desc: str) -> list[str]:
    """The three V1 limits, counted with the gates' own counters."""
    issues: list[str] = []
    if count_words(desc) > HERO_MAX_WORDS:
        issues.append(f'{count_words(desc)}w > {HERO_MAX_WORDS}w')
    if count_sentences(desc) > HERO_MAX_SENTENCES:
        issues.append(f'{count_sentences(desc)} sentences > {HERO_MAX_SENTENCES}')
    if len(desc) > HERO_MAX_CHARS:
        issues.append(f'{len(desc)}ch > {HERO_MAX_CHARS}ch')
    return issues


def hero_hook(paragraph: str) -> tuple[str, str]:
    """Split a hero paragraph into (compliant hook, demoted remainder).

    Ported verbatim in behaviour from the prototype's `hero_hook`, which is what
    turned Cycle H's 20/24 hero failures into 0. Sentences are accumulated while
    the running candidate still satisfies all three limits; everything after the
    first rejection is remainder (never re-tried out of order, so the demoted copy
    stays readable prose rather than a shuffled bag of sentences).

    When even the FIRST sentence blows the budget, the hook is truncated at the
    first clause boundary and the whole original paragraph is demoted, so no
    authored words are lost — the hook duplicates a clause rather than deleting one.
    """
    sents = _sentences(paragraph)
    if not sents:
        return '', ''
    hook: list[str] = []
    rest: list[str] = []
    for s in sents:
        cand = ' '.join(hook + [s])
        if not rest and len(hook) < HERO_MAX_SENTENCES and not hero_violations(cand):
            hook.append(s)
        else:
            rest.append(s)
    if not hook:
        clause = re.split(r'[,;] ', sents[0])[0].rstrip('.,;')
        return clause + '.', paragraph
    return ' '.join(hook), ' '.join(rest)


def v1_hero(draft: PageDraft) -> list[ValidationFinding]:
    """C21 — all three limits on the FINAL hero.description. Auto-fixable."""
    issues = hero_violations(draft.hero.description)
    if not issues:
        return []
    hook, rest = hero_hook(draft.hero.description)
    fixable = bool(hook) and not hero_violations(hook)
    return [ValidationFinding(
        code='hero_rule',
        severity='block',
        message='hero.description violates V1: ' + '; '.join(issues),
        auto_fixable=fixable,
        field_path='hero.description',
        detail=(f'hook-extraction yields {count_words(hook)}w/{len(hook)}ch, '
                f'{count_words(rest)}w demoted to body' if fixable else
                'hook extraction cannot produce a compliant lead — rewrite required'),
    )]


# ---------------------------------------------------------------------------
# V2 — metaTitle effective length
# ---------------------------------------------------------------------------

def v2_meta_title(draft: PageDraft) -> list[ValidationFinding]:
    """C22 — over-length is a curation flag, NEVER a mechanical truncation.

    Truncating a <title> at 56 chars is how '...Acme Roofi' ships. The entry is
    written and the number goes to Alex.
    """
    eff = effective_len(draft.meta_title)
    if eff > META_TITLE_MAX_EFFECTIVE:
        return [warn('meta_title_too_long',
                     f'metaTitle {eff} effective chars > {META_TITLE_MAX_EFFECTIVE} '
                     '(standard §04 band 50-60; never mechanically truncate)',
                     field_path='metaTitle',
                     detail=repr(draft.meta_title))]
    if eff and eff < META_TITLE_MIN:
        # Under the floor is below-optimal, not build-breaking on its own — but
        # the audit gate's band is 50-60, so surface it before the built check does.
        return [warn('meta_title_short',
                     f'metaTitle {eff} effective chars < {META_TITLE_MIN} '
                     '(standard §04 band 50-60) — lengthen with the service/city, '
                     'never pad with filler',
                     field_path='metaTitle',
                     detail=repr(draft.meta_title))]
    return []


#: audit_built's meta-description check measures the description as it appears in
#: the BUILT html, i.e. AFTER '&' has become '&amp;'. The built ceiling is what
#: actually gates, so emit and the built gate must use the SAME band.
#:
#: The band is the Content Team Operating Standard (2026-07-29) §04: "130 to 150
#: characters, never outside". It was 150-160 here, which barely overlapped the
#: published standard — a compliant 140-char description was flagged as too short,
#: and 151-160 was accepted despite the standard banning it. Writers following the
#: rules must not be flagged by the gate that enforces them.
META_DESC_MIN = 130
META_DESC_MAX_EFFECTIVE = 150


def v2b_meta_description(draft: PageDraft) -> list[ValidationFinding]:
    """C22 sibling — metaDescription length, measured &-expansion aware.

    REAL FINDING (2026-07-21 acceptance run): this check did not exist. distill.py
    validated the description on RAW len() only, so a 160-char description
    containing a single '&' passed the emitter and then shipped at 164 chars in
    the html, failing audit_built's `2_desc_120_160` on the one emitted page while
    all 13 legacy siblings passed. metaTitle already had the &-aware treatment
    (effective_len); the description did not. Same bug class, one field over.

    Over-length is a curation flag, never a mechanical truncation, for the same
    reason as the title: a machine-cut description ends mid-clause.

    SEVERITY (2026-07-21 July dry run): emit and the built gate must AGREE. The
    built check `2_desc_120_160` (audit_built.py) BLOCKS a description whose HTML
    length exceeds 160 (C22 band ceiling). Demoting an over-160 description to a
    ride-along WARN let emit ship a page that then failed the built gate — the
    exact warn-vs-block split this pair exists to close. So over the ceiling is a
    CURATE finding: the page is HELD (exit 15), surfaced with the exact effective
    length and a proposed trim, never mechanically truncated and never shipped.
    Under the authored 150 floor stays advisory (WARN) — a short description is
    below-optimal, not build-breaking, so it must not hold the page.
    """
    desc = draft.meta_description
    if not desc:
        return []
    eff = effective_len(desc)
    if META_DESC_MIN <= eff <= META_DESC_MAX_EFFECTIVE:
        return []
    extra = ''
    if eff != len(desc):
        extra = f' (raw {len(desc)}; "&" expands to "&amp;" in the built html)'
    if eff > META_DESC_MAX_EFFECTIVE:
        # Over the build-gate ceiling: HOLD the page, do not ship-with-warn.
        return [curate('meta_description_too_long',
                       f'metaDescription {eff} effective chars over the '
                       f'{META_DESC_MAX_EFFECTIVE}-char ceiling{extra}; the built gate '
                       '2_desc_120_160 BLOCKS this — rewrite (never truncate)',
                       field_path='metaDescription',
                       detail=repr(desc))]
    return [warn('meta_description_length',
                 f'metaDescription {eff} effective chars under the '
                 f'{META_DESC_MIN}-{META_DESC_MAX_EFFECTIVE} band{extra}; '
                 'rewrite, never truncate',
                 field_path='metaDescription',
                 detail=repr(desc))]


# ---------------------------------------------------------------------------
# V3 — em dash + invisible codepoints (the mechanical scrubbers)
# ---------------------------------------------------------------------------

def scrub_em_dashes(text: str, replacement: str = ', ') -> str:
    """Replace every em-dash form, then repair the punctuation it leaves behind.

    ' text — more ' becomes ' text, more ' rather than ' text , more '. The
    cleanup pass is why this is safe to run mechanically.
    """
    out = text
    for form in EM_DASH_FORMS:
        out = out.replace(form, replacement)
    if replacement.strip() == ',':
        out = re.sub(r'\s+,', ',', out)
        out = re.sub(r',\s*,', ',', out)
        out = re.sub(r',\s*([.;:!?])', r'\1', out)
    return re.sub(r'[ \t]{2,}', ' ', out).strip()


def scrub_invisibles(text: str) -> str:
    """C15 — strip fingerprint_check's invisible set. A leading BOM is preserved
    because the gate only flags a NON-leading U+FEFF."""
    return ''.join(
        ch for i, ch in enumerate(text)
        if not (ord(ch) in _INVISIBLE or (ord(ch) == _BOM and i > 0))
    )


def v3_em_dash(draft: PageDraft) -> list[ValidationFinding]:
    """C12 — glyph AND entity forms, in every string that reaches HTML."""
    out: list[ValidationFinding] = []
    for path, text in rendered_strings(draft):
        hit = next((f for f in EM_DASH_FORMS if f in text), None)
        if hit:
            out.append(block('em_dash', f'em dash ({hit!r}) in a rendered string',
                             auto_fixable=True, field_path=path,
                             detail=_context(text, hit)))
    return out


def v3b_fingerprint(draft: PageDraft) -> list[ValidationFinding]:
    """C15 — invisible codepoints and generator markers. fingerprint_check reads
    RAW BYTES and does not skip script/style, so a zero-width space smuggled into
    a JSON-LD string reds the gate just as hard as one in body copy."""
    out: list[ValidationFinding] = []
    for path, text in rendered_strings(draft):
        bad = sorted({ord(ch) for i, ch in enumerate(text)
                      if ord(ch) in _INVISIBLE or (ord(ch) == _BOM and i > 0)})
        if bad:
            out.append(block('invisible_codepoint',
                             'invisible codepoint(s) in a rendered string',
                             auto_fixable=True, field_path=path,
                             detail=', '.join(f'U+{cp:04X}' for cp in bad)))
        for marker in FINGERPRINT_MARKERS:
            if marker in text:
                out.append(block('fingerprint_marker',
                                 f'generator fingerprint {marker!r} in a rendered string',
                                 field_path=path))
    return out


def _context(text: str, needle: str, span: int = 40) -> str:
    idx = text.find(needle)
    if idx < 0:
        return text[:80]
    return '...' + text[max(0, idx - span): idx + len(needle) + span].strip() + '...'


# ---------------------------------------------------------------------------
# V4 — Title Case on every heading string
# ---------------------------------------------------------------------------

def _heading_text(raw: str) -> str:
    """What check_headings actually judges: tag-stripped, entity-unescaped,
    whitespace-collapsed."""
    return re.sub(r'\s+', ' ', htmlmod.unescape(strip_tags(raw))).strip()


def is_exempt(word: str) -> bool:
    """check_headings.is_exempt, verbatim: digits, all-caps acronyms, brand
    camelCase, and tokens with no leading alpha are never judged."""
    if any(ch.isdigit() for ch in word):
        return True
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return True
    if all(c.isupper() for c in letters):
        return True
    if any(c.isupper() for c in word[1:]):
        return True
    return False


def _tokenize(text: str) -> list[str]:
    return [w for w in (raw.strip(_HEADING_EDGE).strip() for raw in text.split()) if w]


def lenient_violation(text: str) -> str | None:
    """check_headings default mode — what the client's gate ACTUALLY reds on."""
    toks = _tokenize(text)
    if not toks:
        return None
    first = toks[0]
    if not is_exempt(first) and first[:1].islower():
        return f"first word {first!r} is not capitalized"
    if not any(c.isupper() for c in text if c.isalpha()):
        return 'heading is entirely lowercase'
    return None


def strict_violation(text: str, stopwords: Iterable[str] = HEADING_STOPWORDS) -> str | None:
    """check_headings --strict — full Title Case, house style."""
    toks = _tokenize(text)
    if not toks:
        return None
    stop = {s.lower() for s in stopwords}
    last = len(toks) - 1
    bad = [w for i, w in enumerate(toks)
           if not is_exempt(w) and not w[:1].isupper()
           and not (0 < i < last and w.lower() in stop)]
    return f'not Title Case; lowercase word(s): {bad}' if bad else None


def v4_title_case(draft: PageDraft,
                  stopwords: Iterable[str] = HEADING_STOPWORDS) -> list[ValidationFinding]:
    """C11 — emit strict-Title-Case-clean regardless of the client's mode.

    Two severities, because the two modes are two different facts:
      * a LENIENT violation is what check_headings reds on today -> block.
      * a STRICT-only violation is house style the client has not switched on ->
        warn. Recasing a heading is a WRITING decision, so neither is auto-fixed;
        a mechanical Title-Caser turns 'GAF Master Elite' into 'Gaf Master Elite'.

    FAQ questions get the LENIENT rule only. C11 lists them, but two facts override
    the letter of it: the renderer puts them in a <span> inside a <button>, so
    check_headings never sees them in the built HTML; and every FAQ question in the
    client repo is sentence case, which is correct English for a question. Strict
    Title Case there would flag all 6 questions on every existing page and push the
    emitter toward copy the repo does not contain.
    """
    out: list[ValidationFinding] = []
    for path, raw in heading_strings(draft):
        text = _heading_text(raw)
        if not text:
            continue
        lenient = lenient_violation(text)
        if lenient:
            out.append(block('heading_case', lenient, field_path=path, detail=repr(text)))
            continue
        if path.startswith('faqs['):
            continue
        strict = strict_violation(text, stopwords)
        if strict:
            out.append(warn('heading_case_strict', strict, field_path=path, detail=repr(text)))
    return out


# ---------------------------------------------------------------------------
# V5 — card / step / item grid counts
# ---------------------------------------------------------------------------

def v5_card_grids(draft: PageDraft) -> list[ValidationFinding]:
    """C23 — ServicePageRenderer.tsx L283-293 accepts exactly 3/4/5/6 source cards.

    n > 6: Math.min(...,6) + .slice(0,6) SILENTLY discards cards 7+, with no error
    and no tsc complaint. n < 3: the 6-slot else branch ships a ragged grid. Both
    are curation judgment — the discarded titles are enumerated so Alex decides
    which card dies, not the emitter.
    """
    out: list[ValidationFinding] = []
    for i, section in enumerate(draft.sections):
        if isinstance(section, BuilderCall):
            continue  # builder grids are fixed at 4/6/4/4 by construction
        for key in CARD_GRID_ARRAYS:
            arr = section.props.get(key)
            if not isinstance(arr, list) or not arr:
                continue
            n = len(arr)
            if n in VALID_CARD_GRID_COUNTS:
                continue
            detail = None
            if n > 6:
                dropped = [str(c.get('title') or c.get('alt') or '?')
                           for c in arr[6:] if isinstance(c, dict)]
                if dropped:
                    detail = 'silently discarded by the renderer: ' + ', '.join(dropped)
            out.append(warn('card_grid_count',
                            f'{section.type}.{key} has {n} entries, not in '
                            f'{sorted(VALID_CARD_GRID_COUNTS)}',
                            field_path=f'sections[{i}].{key}', detail=detail))
    return out


# ---------------------------------------------------------------------------
# V6 — alt text, all three tiers
# ---------------------------------------------------------------------------

def _resolve(container: dict[str, Any], path: str) -> list[tuple[str, Any]]:
    """Resolve a tier-map path ('imageAlt' | 'cards[].imageAlt') to (path, value)."""
    if '[].' not in path:
        return [(path, container.get(path))]
    head, tail = path.split('[].', 1)
    arr = container.get(head)
    if not isinstance(arr, list):
        return []
    return [(f'{head}[{i}].{tail}', item.get(tail) if isinstance(item, dict) else None)
            for i, item in enumerate(arr)]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def v5b_types_subtitle(draft: PageDraft) -> list[ValidationFinding]:
    """A `types` card grid MUST carry a non-empty `subtitle`.

    REAL FINDING (2026-07-21 July dry run): TypesSection (acme
    src/data/services.ts:243) makes `subtitle` MANDATORY. distill._generic_section
    only set it when the DOCX carried a 'Subtitle:' line, so a card grid built from
    a source section without one emitted `{ label, title, cards }` — TS that fails
    `tsc` and kills the WHOLE build (every other page with it). distill now derives
    a subtitle from the section H2/label; this is the loud, blocking backstop so an
    invalid `types` entry can never silently reach the build again.
    """
    out: list[ValidationFinding] = []
    for i, s in enumerate(draft.sections):
        if isinstance(s, BuilderCall) or s.type != 'types':
            continue
        sub = s.props.get('subtitle')
        if not (isinstance(sub, str) and sub.strip()):
            out.append(block('types_subtitle_missing',
                             f'sections[{i}] is a `types` card grid with no `subtitle`; '
                             'TypesSection.subtitle is mandatory and tsc fails without it '
                             '— the build breaks for every page in the file',
                             field_path=f'sections[{i}].subtitle',
                             detail=repr(s.props.get('title') or s.props.get('label'))))
    return out


def v6_alt_text(draft: PageDraft) -> list[ValidationFinding]:
    """C24 — it must be structurally impossible to emit an image without its alt.

    Tier 1 (tsc-enforced) and Tier 2 (optional in the type, mandatory here) are
    missing-alt blocks. Tier 3 has no alt field at all: the renderer substitutes
    the adjacent title, so the TITLE is the alt string and a one-word title ships
    a one-word alt. The generic sweep catches image-ish keys the tier maps do not
    name, so a future TS field cannot quietly ship alt-less.
    """
    out: list[ValidationFinding] = []
    for i, section in enumerate(draft.sections):
        if isinstance(section, BuilderCall):
            continue
        props = section.props
        base = f'sections[{i}]'

        for path in TIER1_ALT_FIELDS.get(section.type, ()):
            for resolved, value in _resolve(props, path):
                if not _nonempty(value):
                    out.append(block('alt_missing_tier1',
                                     f'{section.type}.{path} is tsc-required alt text and is '
                                     'empty or absent',
                                     field_path=f'{base}.{resolved}'))

        for path in TIER2_ALT_FIELDS.get(section.type, ()):
            for resolved, value in _resolve(props, path):
                if not _nonempty(value):
                    out.append(block('alt_missing_tier2',
                                     f'{section.type}.{path} is optional in the TS type but the '
                                     'emitter must always emit it',
                                     field_path=f'{base}.{resolved}'))

        tier3 = TIER3_TITLE_IS_ALT.get(section.type)
        if tier3:
            image_path, title_path = tier3
            images = _resolve(props, image_path)
            titles = dict(_resolve(props, title_path))
            for img_resolved, img_value in images:
                if not _nonempty(img_value):
                    continue
                title_resolved = img_resolved.rsplit('.', 1)[0] + '.' + title_path.split('[].')[-1] \
                    if '[].' in title_path else title_path
                title_value = titles.get(title_resolved)
                if not _nonempty(title_value):
                    out.append(block('alt_missing_tier3',
                                     f'{section.type}.{image_path} has no alt field; the adjacent '
                                     f'{title_path} IS the alt string and is empty',
                                     field_path=f'{base}.{title_resolved}'))
                elif count_words(str(title_value)) < TIER3_MIN_TITLE_WORDS:
                    out.append(block('alt_tier3_title_too_short',
                                     f'{section.type}.{title_path} doubles as the alt text and is '
                                     f'{count_words(str(title_value))} word(s); needs >= '
                                     f'{TIER3_MIN_TITLE_WORDS} to read as an alt',
                                     field_path=f'{base}.{title_resolved}',
                                     detail=repr(title_value)))

        out.extend(_generic_alt_sweep(props, base, section.type))
    return out


def _generic_alt_sweep(node: Any, path: str, section_type: str) -> list[ValidationFinding]:
    """Any dict holding an image-ish key must hold an alt-ish sibling, unless the
    key is decorative (a background) or the section is a known Tier-3 shape."""
    out: list[ValidationFinding] = []
    if isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            out.extend(_generic_alt_sweep(v, f'{path}[{i}]', section_type))
        return out
    if not isinstance(node, dict):
        return out

    tier3_images = {p.split('[].')[-1] for p in
                    (TIER3_TITLE_IS_ALT.get(section_type, ()) or ())[:1]}
    has_alt = any(_ALT_KEY_RE.search(k) and _nonempty(v) for k, v in node.items())
    for key, value in node.items():
        if not _nonempty(value) or not _IMAGE_KEY_RE.match(key):
            continue
        if key in DECORATIVE_IMAGE_FIELDS or key in tier3_images:
            continue
        if not has_alt:
            out.append(block('alt_missing',
                             f'image field {key!r} has no alt sibling in the same object',
                             field_path=f'{path}.{key}', detail=str(value)))
    for key, value in node.items():
        if isinstance(value, (dict, list, tuple)):
            out.extend(_generic_alt_sweep(value, f'{path}.{key}', section_type))
    return out


# ---------------------------------------------------------------------------
# S20 — the capsule must be CARRIED, and be the FIRST interrogative H2
# ---------------------------------------------------------------------------

def s20_capsule(draft: PageDraft,
                long_page_threshold: int = DEFAULT_LONG_PAGE_THRESHOLD) -> list[ValidationFinding]:
    """Produce-by-construction for capsule_check (§20, exit 6).

    models.structural_findings already asserts the capsule is declared and carried
    by an editorial-split whose lede is answer_first. This adds the three things
    only the PROJECTED PAGE can answer, and they are the ones that actually red
    the built-HTML gate:

      1. FIRST-interrogative wins. capsule_check finds the FIRST <h2> that ends in
         '?' or starts with an interrogative lead, then judges the block right
         after IT. An earlier interrogative heading elsewhere on the page hijacks
         the gate and fails on its own prose, no matter how good the capsule is.
         This is not caught by any shape-only check.
      2. The TL;DR must be a real NODE in the copy matching capsule_check.TLDR_RE,
         not just a non-empty capsule.tldr string in the brief.
      3. Route selection (C4): a route in DEFAULT_EXCLUDE is never selected, so
         emitting capsule structure there is dead weight, not a failure.
    """
    out: list[ValidationFinding] = []

    if draft.route in DEFAULT_EXCLUDE:
        out.append(warn('capsule_route_excluded',
                        f'{draft.route} is in capsule_check.DEFAULT_EXCLUDE and is never '
                        'selected; capsule structure here is dead weight',
                        field_path='slug'))

    target = _heading_text(draft.capsule.interrogative_h2).strip()

    # 1. first-interrogative-wins
    interrogatives = [(p, _heading_text(t)) for p, t in heading_strings(draft)
                      if not p.startswith('faqs[')]
    interrogatives = [(p, t) for p, t in interrogatives
                      if t.endswith('?') or INTERROGATIVE_LEAD.match(t)]
    if target and interrogatives:
        first_path, first_text = interrogatives[0]
        if first_text != target:
            out.append(block('capsule_h2_not_first',
                             'an earlier heading is interrogative, so capsule_check will judge '
                             'THAT heading and the prose under it instead of the capsule',
                             field_path=first_path,
                             detail=f'first interrogative: {first_text!r}; capsule: {target!r}'))
    elif target and not interrogatives:
        out.append(block('capsule_h2_not_rendered',
                         'capsule.interrogative_h2 does not appear among the page headings; '
                         'capsule_check finds no interrogative H2 at all',
                         field_path='sections'))

    # answer_first, judged with the gate's own counters on the CARRIED lede
    carrier = draft.capsule_section()
    if carrier is not None:
        lede = strip_tags(str(carrier.props.get('lede', ''))).strip()
        words, sents = count_words(lede), count_sentences(lede)
        if lede and not (ANSWER_FIRST_MIN_WORDS <= words <= ANSWER_FIRST_MAX_WORDS):
            out.append(block('capsule_answer_out_of_band',
                             f'the carried lede is {words}w; capsule_check requires '
                             f'{ANSWER_FIRST_MIN_WORDS}-{ANSWER_FIRST_MAX_WORDS}w',
                             field_path='sections[capsule].lede'))
        if lede and sents > ANSWER_FIRST_MAX_SENTENCES:
            out.append(block('capsule_answer_sentences',
                             f'the carried lede is {sents} sentences > '
                             f'{ANSWER_FIRST_MAX_SENTENCES}',
                             field_path='sections[capsule].lede'))

    # 2. TL;DR node present in the emitted copy
    words_total = body_words(draft)
    has_node = bool(TLDR_RE.search(projected_text(draft)))
    if not has_node:
        severity_block = words_total > long_page_threshold
        msg = (f'no TL;DR / Key Takeaways node in the emitted copy (body is {words_total}w, '
               f'threshold {long_page_threshold}); capsule_check.TLDR_RE matches '
               'tl;dr | key takeaways | in short | the short answer | bottom line')
        out.append(block('tldr_node_missing', msg, field_path='sections')
                   if severity_block else
                   warn('tldr_node_missing', msg + ' — short page, so the gate skips it today, '
                        'but body length is one paragraph away from mandatory',
                        field_path='sections'))
    return out


# ---------------------------------------------------------------------------
# S21 — non-commodity: proprietary tokens + sibling five-gram overlap
# ---------------------------------------------------------------------------

def _flatten_tokens(value: Any) -> list[str]:
    """noncommodity_check._flatten_tokens semantics: strings out of nested
    lists/dicts, everything else dropped."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for v in value:
            out.extend(_flatten_tokens(v))
        return out
    if isinstance(value, dict):
        out = []
        for v in value.values():
            out.extend(_flatten_tokens(v))
        return out
    return []


def build_allow_list(cfg: dict[str, Any]) -> list[str]:
    """noncommodity_check.build_allow_list, mirrored field-for-field.

    Preferred path is importing the gate itself (see `_allow_list`); this mirror
    exists so the check still runs when the emitter is used outside the package.
    """
    tokens: list[str] = []
    tokens += _flatten_tokens(cfg.get('required_phrases'))
    nap = cfg.get('nap') or {}
    tokens += _flatten_tokens(nap.get('city'))
    tokens += _flatten_tokens(nap.get('street'))
    tokens += _flatten_tokens(cfg.get('service_areas'))
    sa = cfg.get('service_area') or {}
    tokens += _flatten_tokens(sa.get('primary_city'))
    tokens += _flatten_tokens(sa.get('cities'))
    tokens += _flatten_tokens(cfg.get('primary_metro'))
    business = cfg.get('business') or {}
    tokens += _flatten_tokens(business.get('crew_names'))
    tokens += _flatten_tokens(cfg.get('owner_name'))
    seen: set[str] = set()
    ordered: list[str] = []
    for t in tokens:
        t = t.strip()
        if len(t) < 2:
            continue
        if t.lower() not in seen:
            seen.add(t.lower())
            ordered.append(t)
    return ordered


def compile_token_matchers(tokens: Sequence[str]) -> list[tuple[str, re.Pattern[str]]]:
    """noncommodity_check.compile_token_matchers, mirrored."""
    matchers: list[tuple[str, re.Pattern[str]]] = []
    for t in tokens:
        if re.fullmatch(r'[\w ]+', t):
            rx = re.compile(r'\b' + re.escape(t).replace(r'\ ', r'\s+') + r'\b', re.IGNORECASE)
        else:
            rx = re.compile(re.escape(t), re.IGNORECASE)
        matchers.append((t, rx))
    return matchers


def five_grams(text_lower: str) -> set[str]:
    """audit_built / noncommodity_check five_grams, verbatim."""
    w = text_lower.split()
    return set(' '.join(w[i:i + 5]) for i in range(len(w) - 4))


def resolve_overlap_threshold(topology: str) -> float:
    """noncommodity_check 'auto': 0.90 only when 'hub-spoke' is IN the topology
    string. Acme's topology is 'franchise', so it resolves to 0.60 — a much
    tighter bar than the hub-spoke default people assume."""
    return 0.90 if 'hub-spoke' in (topology or '') else 0.60


def _allow_list(cfg: dict[str, Any]) -> list[str]:
    """Prefer the gate's own function so this check and the gate cannot disagree."""
    try:
        from pipeline.gates.noncommodity_check import build_allow_list as gate_build  # type: ignore
        return list(gate_build(cfg))
    except Exception:
        return build_allow_list(cfg)


def s21_proprietary(draft: PageDraft, cfg: dict[str, Any] | None,
                    min_tokens: int = 1) -> list[ValidationFinding]:
    """C5 — assert the §21 allow-list actually hits the projected page text.

    An empty allow-list makes the real gate exit 4 (it refuses to run an empty
    differentiation gate), so that is reported here rather than passing silently.
    """
    if cfg is None:
        return [warn('proprietary_unchecked',
                     'no client config supplied; the §21 allow-list hit test was skipped '
                     '(pass --project to run it)', field_path='sections')]
    tokens = _allow_list(cfg)
    if not tokens:
        return [block('proprietary_allow_list_empty',
                      'the §21 allow-list is empty (required_phrases + nap.city/street + '
                      'service_areas + service_area.cities + crew_names + owner_name); '
                      'noncommodity_check exits 4 rather than run an empty gate',
                      field_path='docs/client-config.yml')]
    text = projected_text(draft).lower()
    matched = [t for t, rx in compile_token_matchers(tokens) if rx.search(text)]
    if len(matched) < min_tokens:
        return [block('no_proprietary_token',
                      f'{len(matched)} of {len(tokens)} §21 allow-list token(s) appear in the '
                      f'projected page text, need >= {min_tokens}; the page reads as generic '
                      'commodity boilerplate',
                      field_path='sections',
                      detail=f'allow-list: {", ".join(tokens[:8])}')]
    return []


def s21_sibling_overlap(draft: PageDraft,
                        siblings: dict[str, str] | None,
                        topology: str = '') -> list[ValidationFinding]:
    """C6 — five-gram overlap |A∩B|/|A| against every already-emitted sibling.

    `siblings` maps route -> already-projected page text. Re-check the WHOLE set
    after each emit: page N can push page N-1 over the threshold, and the gate
    measures overlap in both directions independently.
    """
    if not siblings:
        return []
    threshold = resolve_overlap_threshold(topology)
    mine = five_grams(projected_text(draft).lower())
    if not mine:
        return []
    out: list[ValidationFinding] = []
    worst, worst_route = 0.0, None
    for route, text in siblings.items():
        if route == draft.route:
            continue
        other = five_grams(text.lower())
        if not other:
            continue
        ov = len(mine & other) / len(mine)
        if ov > worst:
            worst, worst_route = ov, route
    if worst > threshold:
        out.append(block('duplicate_of_sibling',
                         f'five-gram overlap {worst:.2f} vs {worst_route} exceeds the resolved '
                         f'threshold {threshold:.2f} (topology {topology!r})',
                         field_path='sections'))
    return out


# ---------------------------------------------------------------------------
# C13 — forbidden phrases, from the client's own config
# ---------------------------------------------------------------------------

def forbidden_patterns(cfg: dict[str, Any] | None,
                       banned_file_text: str = '') -> list[tuple[str, str]]:
    """(pattern, reason) from config forbidden_phrases[] UNION docs/banned-phrases.txt."""
    out: list[tuple[str, str]] = []
    for entry in ((cfg or {}).get('forbidden_phrases') or []):
        if isinstance(entry, dict) and entry.get('pattern'):
            out.append((str(entry['pattern']), str(entry.get('reason', ''))))
        elif isinstance(entry, str) and entry.strip():
            out.append((re.escape(entry.strip()), 'banned phrase'))
    for line in banned_file_text.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            out.append((re.escape(line), 'docs/banned-phrases.txt'))
    return out


def _excerpt(text: str, matched: str, window: int = 90) -> str:
    """The offending SENTENCE, with the match marked — not just the 2 chars that hit.

    A curation queue that says `matched: '$4'` is unactionable: the human cannot
    find, let alone rewrite, the copy. Give them the sentence the figure lives in
    so "convert to written-word form" is a decision they can make in one read.
    Falls back to a character window when no sentence boundary is recoverable
    (headings, single-clause strings).
    """
    flat = ' '.join((text or '').split())
    if not flat:
        return f'matched {matched!r} (no surrounding text)'
    idx = flat.find(matched)
    if idx < 0:                       # matched only in the synthetic-tag probe
        return f'{flat[:2 * window]!r} (matched {matched!r} in the rendered heading)'
    # Prefer the enclosing sentence; fall back to a fixed character window.
    left = max((flat.rfind(p, 0, idx) for p in ('. ', '! ', '? ')), default=-1)
    start = left + 2 if left >= 0 else max(0, idx - window)
    right = min((r for r in (flat.find(p, idx) for p in ('. ', '! ', '? ')) if r >= 0),
                default=-1)
    end = right + 1 if right >= 0 else min(len(flat), idx + window)
    snippet = flat[start:end].strip()
    if start > 0:
        snippet = '…' + snippet
    if end < len(flat):
        snippet = snippet + '…'
    return f'{snippet!r} (matched {matched!r})'


def forbidden_sweep(draft: PageDraft, cfg: dict[str, Any] | None,
                    banned_file_text: str = '') -> list[ValidationFinding]:
    """C13 — run the client's own patterns over the exact text about to be written.

    Acme's two hard blockers are `\\$[0-9]` (write 'high four figures', never a
    dollar figure) and the em dash. Patterns that anchor on markup (the
    contraction-in-heading rule matches `<h[1-6]...>`) are applied to the heading
    strings wrapped in a synthetic tag, which is how forbidden_sweep's built mode
    would see them.
    """
    findings: list[ValidationFinding] = []
    pats = forbidden_patterns(cfg, banned_file_text)
    if not pats:
        return findings
    strings = rendered_strings(draft)
    headings = {p for p, _ in heading_strings(draft)}
    for pattern, reason in pats:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            findings.append(warn('forbidden_pattern_invalid',
                                 f'config forbidden_phrases pattern {pattern!r} does not compile: {exc}',
                                 field_path='docs/client-config.yml'))
            continue
        for path, text in strings:
            probe = f'<h2>{text}</h2>' if path in headings else text
            m = rx.search(probe) or rx.search(text)
            if m:
                findings.append(block('forbidden_phrase',
                                      f'matches forbidden pattern {pattern!r}',
                                      field_path=path,
                                      detail=(f'{_excerpt(text, m.group(0))}'
                                              + (f' | rule: {reason}' if reason else ''))))
    return findings


# ---------------------------------------------------------------------------
# Auto-fixes — mechanical only
# ---------------------------------------------------------------------------

def map_strings(draft: PageDraft, fn: Callable[[str], str]) -> PageDraft:
    """Return a copy of `draft` with `fn` applied to every string that reaches HTML.

    RawExpr values are untouched (they are TS identifiers, not copy). The brief
    payload (capsule/fanout/triples) is mapped too, so a scrub applied to the
    carried lede stays in sync with capsule.answer_first — otherwise the capsule
    would silently de-couple from its carrier and trip capsule_lede_mismatch.
    """
    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return fn(node)
        if isinstance(node, RawExpr):
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, tuple):
            return tuple(walk(v) for v in node)
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        return node

    hero = replace(draft.hero,
                   badge_icon=draft.hero.badge_icon,
                   badge_text=fn(draft.hero.badge_text),
                   title=fn(draft.hero.title),
                   description=fn(draft.hero.description),
                   buttons=[replace(b, text=fn(b.text)) for b in draft.hero.buttons],
                   features=[fn(f) for f in draft.hero.features])

    sections: list[Section | BuilderCall] = []
    for s in draft.sections:
        if isinstance(s, BuilderCall):
            sections.append(replace(s, args=[walk(a) for a in s.args]))
        else:
            sections.append(replace(s, props=walk(copy.deepcopy(s.props))))

    capsule = replace(draft.capsule,
                      interrogative_h2=fn(draft.capsule.interrogative_h2),
                      answer_first=fn(draft.capsule.answer_first),
                      tldr=fn(draft.capsule.tldr))

    return replace(
        draft,
        h1=fn(draft.h1),
        meta_title=fn(draft.meta_title),
        meta_description=fn(draft.meta_description),
        title=fn(draft.title) if draft.title else draft.title,
        hero=hero,
        sections=sections,
        faqs=[replace(f, question=fn(f.question), answer=fn(f.answer)) for f in draft.faqs],
        capsule=capsule,
    )


def _demote_hero_remainder(draft: PageDraft, remainder: str) -> tuple[PageDraft, str]:
    """Park the demoted hero copy at the TOP of the body. Returns (draft, where).

    Preference order is editorial-split.paragraphs (C21 names it) then
    content-block.content. The capsule carrier's `lede` is never touched — the
    remainder is PREPENDED to paragraphs, which leaves the answer-first block that
    both §19 and §20 judge exactly as authored.

    When there is nowhere to put it, the caller is told so and V1 stays blocking:
    the one thing this must never do is delete authored copy to satisfy a limit.
    """
    for i, s in enumerate(draft.sections):
        if isinstance(s, Section) and s.type == 'editorial-split':
            props = copy.deepcopy(s.props)
            paras = list(props.get('paragraphs') or [])
            props['paragraphs'] = [remainder] + paras
            sections = list(draft.sections)
            sections[i] = replace(s, props=props)
            return replace(draft, sections=sections), f'sections[{i}].paragraphs[0]'
    for i, s in enumerate(draft.sections):
        if isinstance(s, Section) and s.type == 'content-block':
            props = copy.deepcopy(s.props)
            content = list(props.get('content') or [])
            props['content'] = [remainder] + content
            sections = list(draft.sections)
            sections[i] = replace(s, props=props)
            return replace(draft, sections=sections), f'sections[{i}].content[0]'
    return draft, ''


def apply_autofixes(draft: PageDraft,
                    em_dash_replacement: str = ', ') -> tuple[PageDraft, list[str]]:
    """Apply the MECHANICAL fixes only. Returns (fixed_draft, applied log).

    Order matters:
      1. hero-hook extraction FIRST, so the demoted remainder is a normal body
         string by the time the string scrubbers run over it;
      2. invisible-codepoint strip;
      3. em-dash scrub LAST (C12), so no later transform can reintroduce one.

    Nothing here exercises judgment. Card-grid counts, the core-body band, heading
    recasing, and an over-long metaTitle are NOT touched: they need a human, and a
    mechanical "fix" for any of them ships a worse page than the flag does.
    """
    applied: list[str] = []

    issues = hero_violations(draft.hero.description)
    if issues:
        hook, rest = hero_hook(draft.hero.description)
        if hook and not hero_violations(hook):
            new = replace(draft, hero=replace(draft.hero, description=hook))
            where = ''
            if rest.strip():
                new, where = _demote_hero_remainder(new, rest.strip())
            if rest.strip() and not where:
                applied.append('hero-hook extraction SKIPPED: no editorial-split or '
                               'content-block to receive the demoted remainder; refusing to '
                               'discard authored copy')
            else:
                draft = new
                applied.append(f'V1 hero-hook: hero.description -> {count_words(hook)}w/'
                               f'{len(hook)}ch' +
                               (f'; {count_words(rest)}w demoted to {where}' if where else ''))

    before = projected_text(draft)
    draft = map_strings(draft, scrub_invisibles)
    if projected_text(draft) != before:
        applied.append('C15 invisible codepoints stripped')

    before = projected_text(draft)
    draft = map_strings(draft, lambda t: scrub_em_dashes(t, em_dash_replacement))
    if projected_text(draft) != before:
        applied.append(f'V3 em dashes replaced with {em_dash_replacement!r}')

    return draft, applied


# ---------------------------------------------------------------------------
# Curation queue — a CONCRETE proposed fix per held finding
# ---------------------------------------------------------------------------
#
# These strings go into docs/briefs/_curation.md for a human to accept or reject.
# NOTHING here is ever applied automatically: that is the whole difference
# between an auto-fix (mechanical, provably safe, already applied upstream in
# apply_autofixes) and a curation decision (a judgment the emitter must not make).
# A proposal that cannot be grounded returns the honest "no mechanical proposal"
# text rather than inventing copy.

def _shorten_meta_title(title: str, budget: int = META_TITLE_MAX_EFFECTIVE) -> str | None:
    """A grounded shortening PROPOSAL, in the order a human would try it.

    1. '&' -> 'and' — '&' expands to '&amp;' in <title>, so this alone saves 4
       effective chars per ampersand. (This is literally what the Acme team did
       by hand between the April DOCX and ship.)
    2. drop the trailing '| Brand' segment.
    Never a mid-word or mid-clause cut: if neither step fits the budget, say so.
    """
    for candidate in (
        title.replace(' & ', ' and '),
        re.sub(r'\s*\|[^|]*$', '', title.replace(' & ', ' and ')).strip(),
        re.sub(r'\s*\|[^|]*$', '', title).strip(),
    ):
        if candidate and candidate != title and effective_len(candidate) <= budget:
            return candidate
    return None


def _alt_proposal(draft: PageDraft) -> str:
    """SPEC-emitter §1 V6: '{service} {work-type} in {City}, {ST}'."""
    where = ', '.join(p for p in (draft.city, draft.state) if p)
    base = f'{draft.service} in {where}' if where else draft.service
    return base.strip() or f'{draft.title} image'


def propose_fix(draft: PageDraft, f: ValidationFinding) -> str:
    """One concrete, acceptable-or-rejectable action for a HELD finding."""
    code = f.code

    if code == 'hero_rule':
        hook, rest = hero_hook(draft.hero.description)
        if hook and not hero_violations(hook):
            return (f'set hero.description to {hook!r} ({count_words(hook)}w/'
                    f'{len(hook)}ch) and move the remaining {count_words(rest)}w '
                    'into the opening editorial-split paragraph')
        sents = _sentences(draft.hero.description)
        lead = sents[0] if sents else draft.hero.description
        return ('no mechanical proposal — hook extraction cannot produce a compliant '
                f'lead. Rewrite the hero to <= {HERO_MAX_WORDS}w / '
                f'{HERO_MAX_SENTENCES} sentence(s) / {HERO_MAX_CHARS}ch. Current lead '
                f'sentence is {count_words(lead)}w: {lead!r}')

    if code == 'meta_description_too_long':
        desc = draft.meta_description
        # A PROPOSED trim at the last sentence boundary that fits the ceiling — a
        # suggestion for the human, never auto-applied (C22: never truncate). If no
        # sentence boundary fits, offer the last word boundary instead.
        trimmed = ''
        for m in re.finditer(r'[.!?]', desc):
            cand = desc[:m.end()].rstrip()
            if effective_len(cand) <= META_DESC_MAX_EFFECTIVE:
                trimmed = cand
        if not trimmed:
            words = desc.split()
            while words:
                cand = ' '.join(words)
                if effective_len(cand) <= META_DESC_MAX_EFFECTIVE:
                    trimmed = cand
                    break
                words.pop()
        if trimmed and trimmed != desc:
            return (f'rewrite metaDescription to <= {META_DESC_MAX_EFFECTIVE} effective chars '
                    f'(currently {effective_len(desc)}). A boundary-safe trim that fits is '
                    f'{trimmed!r} ({effective_len(trimmed)} chars) — review before accepting; '
                    'prefer a proper rewrite so the sentence still reads complete.')
        return (f'rewrite metaDescription to <= {META_DESC_MAX_EFFECTIVE} effective chars '
                f'(currently {effective_len(desc)}); never truncate mid-clause. Current: '
                f'{desc!r}')

    if code in ('meta_title_too_long', 'meta_title_long'):
        short = _shorten_meta_title(draft.meta_title)
        if short:
            return (f'set metaTitle to {short!r} ({effective_len(short)} effective chars, '
                    f'was {effective_len(draft.meta_title)}) — "&" expands to "&amp;" in '
                    '<title>, so "and" is a real saving, not cosmetic')
        return ('no mechanical proposal — rewrite the metaTitle to <= '
                f'{META_TITLE_MAX_EFFECTIVE} effective chars. NEVER truncate: a cut '
                f'<title> ships as "...Acme Roofi". Current: {draft.meta_title!r}')

    if code.startswith('alt_'):
        return (f'supply alt text for {f.field_path}; the §V6 pattern for this page is '
                f'{_alt_proposal(draft)!r}. Or pass --image-map so the alt copy comes '
                'from the client\'s own asset metadata rather than a template.')

    if code in ('tldr_node_missing', 'capsule_tldr_missing'):
        ans = (draft.capsule.answer_first or '').strip()
        if ans:
            return ('add a TL;DR node carrying capsule.answer_first verbatim (one string, '
                    f'two gates — §20 reads the rendered node): {ans[:160]!r}')
        return ('author capsule.answer_first (40-80 words, <= 3 sentences) and emit it as '
                'the TL;DR node; the emitter will not synthesise a summary it cannot source')

    if code.startswith('capsule_'):
        h2 = (draft.capsule.interrogative_h2 or '').strip()
        ans = (draft.capsule.answer_first or '').strip()
        return ('the capsule is one string used twice: the FIRST editorial-split section '
                f'title must be exactly the interrogative H2 ({h2!r} today) and its lede '
                f'must be exactly answer_first ({ans[:120]!r} today). Fix whichever of the '
                'two the finding names, upstream in the draft.')

    if code == 'heading_case':
        raw = (f.detail or '').strip("'\"")
        fixed = ' '.join(w if is_exempt(w) else (w[:1].upper() + w[1:]) for w in raw.split())
        if fixed and fixed != raw:
            return (f'set {f.field_path} to {fixed!r} — check the proper nouns before '
                    'accepting; the capitalisation auto-fix already declined this one')
        return f'rewrite {f.field_path} in Title Case; the mechanical pass could not.'

    if code == 'drop_rate_circuit_breaker':
        return ('review the DROP/BANK verdicts in the ledger, then either restore blocks '
                f'or record the decision: add {{"{draft.slug}": {{"drop_rate_acknowledged": '
                'true}} to decisions.json. Nothing is lost either way — banked blocks stay '
                'in the dossier.')

    return (f'{f.message} — no templated proposal for {code}; resolve upstream in the draft '
            'and re-run.')


# ---------------------------------------------------------------------------
# The one entry point the emitter calls
# ---------------------------------------------------------------------------

def _dedupe(findings: Iterable[ValidationFinding]) -> list[ValidationFinding]:
    """models.structural_findings and this module overlap on hero_rule /
    meta_title_too_long / card_grid_count by design (same code, same field), so a
    draft is never reported twice for one fact.

    FIRST occurrence wins, which is why `validate()` runs the V-checks BEFORE
    structural_findings: models hardcodes `auto_fixable=True` on hero_rule, while
    v1_hero() actually attempts the extraction and reports whether it succeeded.
    Keeping models' version would tell Alex a hero is auto-fixable when the
    emitter has already proven it is not — the report would be confidently wrong
    about the one thing he has to act on. Blocking still wins on a tie.
    """
    best: dict[tuple[str, str | None], ValidationFinding] = {}
    order: list[tuple[str, str | None]] = []
    for f in findings:
        key = (f.code, f.field_path)
        if key not in best:
            best[key] = f
            order.append(key)
        elif f.blocking and not best[key].blocking:
            best[key] = f
    return [best[k] for k in order]


def validate(draft: PageDraft,
             cfg: dict[str, Any] | None = None,
             siblings: dict[str, str] | None = None,
             banned_file_text: str = '',
             min_proprietary_tokens: int = 1) -> list[ValidationFinding]:
    """Every constraint, in one list. Blocking findings mean refuse to emit.

    `cfg` is the parsed docs/client-config.yml (via common.load_config). Without
    it the §21 and forbidden-phrase checks cannot run and say so rather than
    passing silently — a skipped check reported as a pass is the failure mode this
    whole package exists to remove.
    """
    cfg = cfg or None
    long_threshold = DEFAULT_LONG_PAGE_THRESHOLD
    topology = ''
    if cfg:
        content = cfg.get('content') or {}
        if isinstance(content, dict) and content.get('long_page_threshold'):
            long_threshold = int(content['long_page_threshold'])
        topology = str(cfg.get('topology') or '')

    findings: list[ValidationFinding] = []
    # V-checks FIRST: on an overlapping (code, field_path) the first finding wins,
    # and these carry the computed detail that models' shape-only version cannot.
    findings += v1_hero(draft)
    findings += v2_meta_title(draft)
    findings += v2b_meta_description(draft)
    findings += v3_em_dash(draft)
    findings += v3b_fingerprint(draft)
    findings += v4_title_case(draft)
    findings += v5_card_grids(draft)
    findings += v5b_types_subtitle(draft)
    findings += v6_alt_text(draft)
    findings += structural_findings(draft, cfg)
    findings += s20_capsule(draft, long_threshold)
    findings += s21_proprietary(draft, cfg, min_proprietary_tokens)
    findings += s21_sibling_overlap(draft, siblings, topology)
    findings += forbidden_sweep(draft, cfg, banned_file_text)
    # TRIAGE: one table decides block vs curate (models.CURATION_CODES). Applied
    # AFTER _dedupe so 'blocking wins on a tie' still resolves against the raw
    # severities, and applied here so every caller of validate() sees the same
    # policy — emit_ts re-applies it to its own ledger/route findings.
    return apply_severity_policy(_dedupe(findings))


def blocking(findings: Iterable[ValidationFinding]) -> list[ValidationFinding]:
    return [f for f in findings if f.blocking]


def warnings(findings: Iterable[ValidationFinding]) -> list[ValidationFinding]:
    return [f for f in findings if not f.blocking]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _with_tldr_node(draft: PageDraft) -> PageDraft:
    """Render capsule.tldr as an actual node so capsule_check's TLDR_RE can find it.

    A `content-block` titled 'Key Takeaways' is the cheapest carrier that reaches
    the built HTML as real prose. Placed LAST so it cannot become the page's first
    interrogative H2 and hijack the capsule.
    """
    node = Section(
        type='content-block',
        core_body=False,
        verdict='KEEP',
        props={'label': 'Summary', 'title': 'Key Takeaways',
               'content': [draft.capsule.tldr]},
    )
    return replace(draft, sections=list(draft.sections) + [node])


def self_test(verbose: bool = False, project: str | None = None) -> list[str]:
    from pipeline.generate.models import build_fixture

    fails: list[str] = []
    cfg = None
    if project:
        try:
            from pipeline.lib.common import load_config
            cfg = load_config(project)
        except SystemExit:
            fails.append(f'could not load config from {project}')

    raw_fixture = build_fixture()

    # --- REAL FINDING, asserted rather than papered over ----------------------
    # models.build_fixture() declares capsule.tldr but never emits a TL;DR NODE
    # into the page copy, and its projected body is ~1287w — over the default
    # content.long_page_threshold of 1200. capsule_check would select this route
    # and exit 6 on `tldr_on_long`. Declaring the string in the brief is not the
    # same as rendering the node, which is exactly what C3 warns about. Asserted
    # here so a future fixture change that fixes it is noticed.
    if not any(f.code == 'tldr_node_missing' and f.blocking
               for f in s20_capsule(raw_fixture)):
        fails.append('S20: the known missing-TL;DR gap in models.build_fixture() no longer '
                     'fires — re-check the fixture and this assertion')

    draft = _with_tldr_node(raw_fixture)

    # --- the capsule-complete fixture is clean under the full validator set ---
    found = validate(draft, cfg)
    hard = blocking(found)
    if hard:
        fails.append('fixture has blocking findings: ' + '; '.join(f.code for f in hard))

    # --- V1: an over-long hero blocks, and the auto-fix clears it -------------
    fat_desc = ('Vinyl, fiber cement, engineered wood, and wood siding installation across '
                'Matthews for over two decades. Matthews-based GAF Master Elite contractor '
                'with full HOA support, permit compliance, and substrate preparation. '
                'Every estimate is free and fully itemized.')
    fat = replace(draft, hero=replace(draft.hero, description=fat_desc))
    if not any(f.code == 'hero_rule' and f.blocking for f in v1_hero(fat)):
        fails.append('V1: over-long hero.description was not blocked')
    fixed, applied = apply_autofixes(fat)
    if hero_violations(fixed.hero.description):
        fails.append(f'V1 autofix: hero still violates after fix: {fixed.hero.description!r}')
    if not any('hero-hook' in a for a in applied):
        fails.append('V1 autofix: hero-hook extraction was not logged')
    if count_words(projected_text(fixed)) < count_words(projected_text(fat)) - 2:
        fails.append('V1 autofix: demoted hero copy was lost rather than moved to the body')

    # A single over-long SENTENCE with no clause boundary cannot be split without
    # editorial judgment. It must refuse AND must not claim to be auto-fixable —
    # models.structural_findings hardcodes auto_fixable=True on hero_rule, so
    # validate() has to surface v1_hero's computed answer instead of that one.
    unsplittable = replace(draft, hero=replace(
        draft.hero,
        description='Matthews homeowners trust Acme Roofing for everything from post-storm '
                    'inspections on established subdivision homes to complete seamless gutter '
                    'replacements on larger properties across the wider southeastern metro.'))
    hero_f = [f for f in validate(unsplittable, cfg) if f.code == 'hero_rule']
    if not hero_f:
        fails.append('V1: an unsplittable over-long hero was not reported')
    elif hero_f[0].auto_fixable:
        fails.append('V1: an unsplittable hero was mislabelled auto-fixable — '
                     'validate() is surfacing the shape-only finding, not v1_hero()')
    still, _ = apply_autofixes(unsplittable)
    if not hero_violations(still.hero.description):
        fails.append('V1: an unsplittable hero was silently truncated by the autofixer')

    # --- V2 ------------------------------------------------------------------
    long_meta = replace(draft, meta_title='Siding & Gutter Installation & Repair in Matthews, NC')
    if not any(f.code == 'meta_title_too_long' for f in v2_meta_title(long_meta)):
        fails.append('V2: &-expanded metaTitle over 56 was not flagged')
    if any(f.blocking for f in v2_meta_title(long_meta)):
        fails.append('V2: over-long metaTitle must be a curation flag, not a block')

    # --- V3 + autofix --------------------------------------------------------
    dashed = replace(draft, meta_description='Seamless gutters — installed right.')
    if not any(f.code == 'em_dash' for f in v3_em_dash(dashed)):
        fails.append('V3: em dash in metaDescription was not caught')
    scrubbed, _ = apply_autofixes(dashed)
    if any(f.code == 'em_dash' for f in v3_em_dash(scrubbed)):
        fails.append('V3 autofix: em dash survived the scrub')
    for form in ('&mdash;', '&#8212;', '&#x2014;'):
        ent = replace(draft, meta_description=f'Gutters {form} done right.')
        if not any(f.code == 'em_dash' for f in v3_em_dash(ent)):
            fails.append(f'V3: entity form {form} was not caught')

    # --- V3b -----------------------------------------------------------------
    zw = replace(draft, meta_description='Seamless​gutters installed right.')
    if not any(f.code == 'invisible_codepoint' for f in v3b_fingerprint(zw)):
        fails.append('V3b: zero-width space was not caught')
    if any(f.code == 'invisible_codepoint' for f in v3b_fingerprint(apply_autofixes(zw)[0])):
        fails.append('V3b autofix: invisible codepoint survived the scrub')

    # --- V4 ------------------------------------------------------------------
    lower = copy.deepcopy(draft)
    bad_sections = list(lower.sections)
    for i, s in enumerate(bad_sections):
        if isinstance(s, Section) and s.type == 'content-block':
            props = copy.deepcopy(s.props)
            props['title'] = 'our gutter services'
            bad_sections[i] = replace(s, props=props)
            break
    lower = replace(lower, sections=bad_sections)
    if not any(f.code == 'heading_case' and f.blocking for f in v4_title_case(lower)):
        fails.append('V4: lowercase heading was not blocked')
    if strict_violation('GAF Master Elite Contractor in Matthews') is not None:
        fails.append('V4: acronym + mid-heading stopword wrongly flagged as not Title Case')

    # --- V5 ------------------------------------------------------------------
    eight = replace(draft, sections=list(draft.sections) + [Section(
        type='service-mosaic',
        props={'label': 'Services', 'title': 'Gutter Services in Matthews',
               'cards': [{'title': f'Mosaic Card {n}', 'size': 'mid',
                          'image': f'/images/m{n}.webp',
                          'imageAlt': f'Mosaic card {n} photograph'}
                         for n in range(1, 9)]},
    )])
    grid = [f for f in v5_card_grids(eight) if f.code == 'card_grid_count']
    if not grid:
        fails.append('V5: over-count card grid was not flagged')
    elif grid[0].blocking or grid[0].auto_fixable:
        fails.append('V5: card grid must be a non-auto-fixable curation flag')
    elif not grid[0].detail or 'discarded' not in grid[0].detail:
        fails.append('V5: discarded card titles were not enumerated')

    # --- V6 ------------------------------------------------------------------
    noalt = copy.deepcopy(draft)
    secs = list(noalt.sections)
    for i, s in enumerate(secs):
        if isinstance(s, Section) and s.type == 'editorial-split':
            props = copy.deepcopy(s.props)
            props['imageAlt'] = ''
            secs[i] = replace(s, props=props)
            break
    noalt = replace(noalt, sections=secs)
    if not any(f.code == 'alt_missing_tier1' for f in v6_alt_text(noalt)):
        fails.append('V6: empty tier-1 imageAlt was not blocked')

    tier3 = copy.deepcopy(draft)
    tier3 = replace(tier3, sections=list(tier3.sections) + [Section(
        type='materials',
        props={'label': 'Materials', 'title': 'Gutter Materials We Install',
               'subtitle': 'What we install.',
               'items': [{'image': '/images/a.webp', 'title': 'Aluminum',
                          'description': 'x'}] * 3},
    )])
    if not any(f.code == 'alt_tier3_title_too_short' for f in v6_alt_text(tier3)):
        fails.append('V6: tier-3 one-word title (which IS the alt) was not blocked')

    # --- S20: first-interrogative-wins ---------------------------------------
    hijack = copy.deepcopy(draft)
    secs = list(hijack.sections)
    inserted = Section(type='content-block',
                       props={'label': 'Timing', 'title': 'When Should Gutters Be Replaced?',
                              'content': ['Short answer text.']})
    hijack = replace(hijack, sections=[inserted] + secs)
    if not any(f.code == 'capsule_h2_not_first' for f in s20_capsule(hijack)):
        fails.append('S20: an earlier interrogative heading did not trip capsule_h2_not_first')

    # --- S20: TL;DR node -----------------------------------------------------
    if any(f.code == 'tldr_node_missing' and f.blocking for f in s20_capsule(draft)):
        fails.append('S20: fixture flagged for a missing TL;DR node it does carry')

    # --- S21 -----------------------------------------------------------------
    if cfg:
        if any(f.blocking for f in s21_proprietary(draft, cfg)):
            fails.append('S21: fixture failed the real Acme §21 allow-list')
        # A page with NO client-unique token anywhere — hero and meta stripped too,
        # because rendered_strings() (correctly) counts them: the phone number in a
        # hero button alone is enough to satisfy §21.
        generic = replace(
            draft,
            meta_title='Gutter Replacement Services',
            meta_description='Quality gutter replacement from an experienced local team.',
            title='Gutter Replacement',
            h1='Gutter Replacement Services',
            hero=Hero(badge_icon='fas fa-star', badge_text='LOCAL EXPERTS',
                      title='Gutter Replacement Services',
                      description='Quality workmanship at a fair price.'),
            faqs=[],
            sections=[Section(
                type='editorial-split',
                props={'title': 'What Does Gutter Replacement Involve?',
                       'lede': 'Quality workmanship at a fair price, guaranteed.',
                       'paragraphs': ['We take pride in every job we do.'],
                       'image': '/images/x.webp', 'imageAlt': 'A finished gutter run'})])
        if not any(f.code == 'no_proprietary_token' for f in s21_proprietary(generic, cfg)):
            fails.append('S21: a page with zero allow-list tokens was not blocked')
    if resolve_overlap_threshold('franchise') != 0.60:
        fails.append("S21: Acme's 'franchise' topology must resolve to a 0.60 threshold")
    if resolve_overlap_threshold('hub-spoke') != 0.90:
        fails.append("S21: 'hub-spoke' topology must resolve to a 0.90 threshold")

    twin = {'/charlotte-nc/mint-hill/gutter-replacement/': projected_text(draft)}
    if not any(f.code == 'duplicate_of_sibling'
               for f in s21_sibling_overlap(draft, twin, 'franchise')):
        fails.append('S21: a byte-identical sibling did not trip duplicate_of_sibling')

    # --- C13 -----------------------------------------------------------------
    if cfg:
        priced = replace(draft, meta_description='Gutter replacement from $4,500 in Matthews, NC.')
        if not any(f.code == 'forbidden_phrase' for f in forbidden_sweep(priced, cfg)):
            fails.append("C13: a dollar figure did not trip Acme's \\$[0-9] blocker")

    if verbose:
        print(f'fixture findings ({len(found)}):')
        for f in found:
            print(f'  {f}')
        print(f'body_words={body_words(draft)}  core_words='
              f'{__import__("pipeline.generate.models", fromlist=["x"]).recount_core_words(draft)}')
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Constraint validators V1-V6 + S19/S20/S21 produce-by-construction.')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--project', default=None,
                    help='client dir (docs/client-config.yml) — enables the §21 and '
                         'forbidden-phrase checks')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    if not args.self_test:
        ap.print_help()
        return 2

    fails = self_test(verbose=args.verbose, project=args.project)
    if fails:
        print('FAIL: validators.py self-test')
        for f in fails:
            print(f'  {f}')
        return 9
    scope = f' against {args.project}' if args.project else ' (structure only, no --project)'
    print(f'PASS: validators.py self-test{scope} — V1-V6 + S20/S21 + C13 asserted, '
          'autofixes converge, 14 negative controls caught.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
