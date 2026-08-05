#!/usr/bin/env python3
"""pipeline.intake.preflight_docx — the INTAKE PRE-FLIGHT gate.

The feedback loop that was missing: catch content-team defects at HANDOFF instead
of at emit time.

WHY THIS EXISTS
---------------
On 2026-07-21 the emitter was run against the real April team DOCX
(`docs/intake/2026-04-Hub-and-Suburb-Page-Content.docx`) and emitted 0 of 25
pages. 23 of the 24 refusals were ONE rule: the client's `\\$[0-9]`
forbidden-phrase rule firing on real dollar figures the writers put in the source
("$12,000 and $22,000", "a projected $500-million redevelopment"). The content
was defective on HANDOFF, but nobody found out until the emitter refused — by
which point the cycle is already blocked and the content team has moved on.

This module moves that discovery to the front of the cycle and hands the content
team an actionable fix-list instead of a stack trace.

CONTRACT: pre-flight must PREDICT emit-time refusals, not diverge from them.
That is the whole point, so every check here is the emitter's own code:

    * DOCX parsing + page segmentation  -> pipeline.generate.distill
    * forbidden-phrase rule loading     -> pipeline.gates.forbidden_sweep.load_phrases
      (the UNION of config `forbidden_phrases` and docs/banned-phrases.txt, so
      pre-flight and the build gate can never disagree about what is banned)
    * text-level constraints V1/V2/V3/V4 -> pipeline.generate.validators
    * client config                     -> pipeline.lib.common.load_config

Nothing under `pipeline/gates/` is modified, and no client file is ever written:
this module is strictly read-only.

WHAT IS DELIBERATELY *NOT* BLOCKING
-----------------------------------
Two classes of finding exist in the source but never refuse a page at emit, so
reporting them as BLOCKING would make pre-flight LOUDER than the emitter and
train the content team to ignore it:

  1. MECHANICALLY AUTO-FIXED. `emit_ts` calls `validators.apply_autofixes()`
     BEFORE `validators.validate()`, so em dashes and invisible codepoints are
     scrubbed and never reach the gate. Every page in the April DOCX carries em
     dashes; calling that "blocking" would bury the 23 real defects under 25
     fake ones. Reported as INFO.
  2. BANKED SECTIONS. Content under a banked or builder-collapsed marker
     (TOPBAR, FOOTER, CTA SECTION, CERTIFICATIONS SECTION, ...) never reaches the
     emitted page, so a violation there cannot refuse it. Reported as INFO with
     the reason attached.

CLASSIFICATION
--------------
    BLOCKING  the emitter will refuse this page (forbidden phrase, missing
              required field). The cycle stops until it is fixed.
    CURATE    a human decision is required but the page can still ship
              (`models.CURATION_CODES`: hero with no extractable hook, over-long
              metaTitle, heading case).
    INFO      visible in the source, resolved before it can block.

Usage
-----
    preflight_docx.py DOCX --project PROJECT_DIR [--out REPORT.md] [--json OUT.json]

Exit codes
----------
    0  clean — no findings that need a human
    1  curate-only findings
    2  usage / dependency error
    3  BLOCKING findings present — the emitter would refuse these pages
    16 non-empty DOCX segmented to 0 pages — unrecognized handoff format
       (never reported as clean); needs a parser update or a template fix
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

if __name__ == '__main__' and __package__ is None:  # see distill.py invocation caveat
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.gates.forbidden_sweep import load_phrases  # noqa: E402
from pipeline.generate.distill import (  # noqa: E402
    _BANK_MARKERS,
    _BUILDER_MARKERS,
    PageSegment,
    RawBlock,
    UnsegmentableDocxError,
    assert_segmentable,
    label_value,
    resolve_hero_source,
    normalize_heading_page,
    read_docx_blocks,
    segment_pages,
)
from pipeline.generate.models import (  # noqa: E402
    HERO_MAX_CHARS,
    HERO_MAX_SENTENCES,
    HERO_MAX_WORDS,
    META_TITLE_MAX_EFFECTIVE,
    count_sentences,
    count_words,
    effective_len,
)
from pipeline.generate.validators import (  # noqa: E402
    EM_DASH_FORMS,
    META_DESC_MAX_EFFECTIVE,
    META_DESC_MIN,
    _excerpt,
    _heading_text,
    hero_hook,
    hero_violations,
    lenient_violation,
    scrub_invisibles,
    strict_violation,
)

BLOCKING, CURATE, INFO = 'BLOCKING', 'CURATE', 'INFO'

#: Markers whose copy is banked or builder-collapsed by distill and therefore
#: never reaches the emitted page. A violation here cannot refuse the page.
_NON_SHIPPING_MARKERS: dict[str, str] = dict(_BANK_MARKERS)
_NON_SHIPPING_MARKERS.update(
    {m: f'collapsed into the shared {b}() builder; the city-specific copy is banked'
     for m, b in _BUILDER_MARKERS.items()})

#: Labels whose text reaches an <h1>/<h2>/<h3>. Used for the Title-Case check and
#: for the synthetic-tag probe that markup-anchored rules (the
#: contraction-in-heading rule) need in order to fire the way built mode sees them.
_HEADING_LABELS = frozenset({'h1', 'h2', 'h3'})

#: A dollar figure, with its optional scale word: '$22,000', '$500-million', '$1.2M'.
#: The trailing `(?<![,.])` keeps sentence punctuation out of the captured
#: figure, so '$485,000, even minor...' yields '485,000' and not '485,000,'.
_MONEY_RE = re.compile(
    r'\$\s?([0-9][0-9,]*(?:\.[0-9]+)?(?<![,.]))\s*[-–— ]?\s*'
    r'(million|billion|thousand|m|b|k)?\b', re.IGNORECASE)

#: The sentence is quoting a PRICE for the client's own work (-> phone CTA)
#: rather than market context (-> written-word form). Both branches come straight
#: out of the client's own rule text in docs/client-config.yml.
_PRICING_CONTEXT_RE = re.compile(
    r'\b(cost|costs|costing|price|priced|pricing|runs?\s+between|ranges?\s+from|'
    r'quote|quoted|estimate|average\s+(?:cost|price)|typically\s+runs?|runs?\s+\$|'
    r'replacement\s+(?:runs?|costs?)|per\s+square|budget)\b', re.IGNORECASE)

_SCALE = {'k': 1_000, 'thousand': 1_000, 'm': 1_000_000, 'million': 1_000_000,
          'b': 1_000_000_000, 'billion': 1_000_000_000}


@dataclass
class Finding:
    """One defect, located precisely enough for a non-engineer to act on it."""

    page: str
    severity: str
    code: str
    where: str            # human-readable location: 'FAQ SECTION / Q1'
    offending: str        # the exact offending text
    context: str          # the surrounding sentence, with the match marked
    why: str              # one plain sentence
    fix: str              # a concrete suggested rewrite
    rule: str = ''        # the client's own rule text, verbatim

    def as_dict(self) -> dict[str, Any]:
        return {'page': self.page, 'severity': self.severity, 'code': self.code,
                'where': self.where, 'offending': self.offending,
                'context': self.context, 'why': self.why, 'fix': self.fix,
                'rule': self.rule}


@dataclass
class PageReport:
    name: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == BLOCKING]

    @property
    def curate(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == CURATE]

    @property
    def info(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == INFO]

    @property
    def ready(self) -> bool:
        return not self.blocking and not self.curate


# ---------------------------------------------------------------------------
# Text extraction — every authored string on the page, with its location
# ---------------------------------------------------------------------------

def page_strings(segment: PageSegment) -> list[tuple[str, str, str, bool]]:
    """(where, text, marker, is_heading) for every authored string on the page.

    A superset of what the emitter ships, which is the safe direction: pre-flight
    may warn about a string the emitter would have dropped, but it can never miss
    one the emitter would have refused. Strings under a non-shipping marker are
    tagged via `marker` so the caller can down-rank them to INFO.
    """
    out: list[tuple[str, str, str, bool]] = []
    for b in segment.blocks:
        marker = b.marker or 'PAGE'
        if b.kind == 'table':
            for r, row in enumerate(b.rows):
                for c, cell in enumerate(row):
                    if cell.strip():
                        out.append((f'{marker} / table r{r + 1}c{c + 1}', cell, marker, False))
            continue
        text = b.body
        if not text or not text.strip():
            continue
        label = b.label.strip()
        where = f'{marker} / {label}' if label else marker
        out.append((where, text, marker, label.lower() in _HEADING_LABELS))
    return out


def _first_value(segment: PageSegment, *labels: str) -> str:
    """Resolve through distill.label_value so pre-flight and the emitter agree.

    Requiring `b.value` here meant the label-on-its-own-line convention (value in
    the NEXT paragraph) read as a missing field, and pre-flight reported
    no_meta_title / no_meta_description / no_url_path on pages that had all
    three. Pre-flight's contract is to predict emit exactly, so it has to use the
    emitter's resolver, not a second copy of the lookup.
    """
    want = {l.lower() for l in labels}
    for b in segment.blocks:
        if b.label.strip().lower() in want:
            value = label_value(segment.blocks, b)
            if value:
                return value
    return ''


def _hero_source(segment: PageSegment) -> str:
    """The hero paragraph — delegated to distill.resolve_hero_source, the single
    source of truth across all three known authoring conventions (labelled,
    unlabelled-after-H1, and markerless — no HERO SECTION heading at all).
    Pre-flight and the emitter MUST share this resolution: when they diverged,
    pre-flight kept reporting `no_hero_copy` on 17 pages the emitter could read,
    which is exactly the false-alarm class this tool exists to prevent."""
    return resolve_hero_source(segment.blocks)


# ---------------------------------------------------------------------------
# Plain-language explanations + concrete rewrites
# ---------------------------------------------------------------------------

def _magnitude_words(raw: str, scale: str | None) -> str:
    """A dollar figure -> the written-word form the client's own rule asks for.

    The rule text names 'millions of dollars' and 'high six figures' as the two
    acceptable shapes, so that is exactly what this produces: a magnitude band,
    never a number. Grounded in the figure that is actually on the page — this
    invents no new fact, it only restates the one the writer already committed to.
    """
    try:
        value = float(raw.replace(',', ''))
    except ValueError:
        return 'a written-word magnitude'
    value *= _SCALE.get((scale or '').lower(), 1)
    if value >= 1_000_000_000:
        return 'billions of dollars'
    if value >= 1_000_000:
        return 'millions of dollars'
    digits = len(str(int(value)))
    band = {4: 'four figures', 5: 'five figures', 6: 'six figures'}.get(digits)
    if not band:
        return 'a written-word magnitude'
    lead = int(str(int(value))[0])
    tier = 'low' if lead <= 3 else ('mid' if lead <= 6 else 'high')
    return f'{tier} {band}'


def _dollar_fix(text: str, matched: str, where: str = '') -> str:
    """The concrete rewrite for a dollar figure, branched exactly the way the
    client's rule branches: service pricing gets the phone CTA, market context
    gets the written-word form."""
    figures = _MONEY_RE.findall(text)
    shown = ', '.join(f'${n}{" " + s if s else ""}' for n, s in figures[:3]) or matched
    if _PRICING_CONTEXT_RE.search(text) or 'COST' in where.upper():
        return (f'This is a price for our own work. Delete the figure(s) ({shown}) and '
                'point the reader at the phone instead, e.g. rewrite as "...call for a '
                'free estimate." Say what is INCLUDED in the work rather than what it costs.')
    words = [_magnitude_words(n, s) for n, s in figures[:3]] or ['a written-word magnitude']
    pairs = ', '.join(f'"{f}" -> "{w}"'
                      for f, w in zip(shown.split(', '), words))
    return (f'This is market context, not our pricing, so convert the figure to written-word '
            f'form and keep the point: {pairs}. Example: "a projected $500-million '
            'redevelopment" becomes "a redevelopment projected in the millions of dollars".')


def _quoted_phrases(text: str) -> list[str]:
    """Single-quoted phrases inside a config rule/reason string, e.g. the
    replacements the operator's fleet_phrasing_rule names verbatim."""
    return re.findall(r"'([^']+)'", text or '')


def _fleet_fix(reason: str, matched: str, cfg: dict | None) -> tuple[str, str]:
    """Fleet-size overcounts (Northstar '50+ trucks' / '25+ trucks'). The suggested
    replacements come from the client config's own trust_signals.fleet_phrasing_rule
    when present — never re-ask the client, never hardcode one client's fleet."""
    rule_txt = ((cfg or {}).get('trust_signals') or {}).get('fleet_phrasing_rule') or ''
    source = rule_txt or reason
    # Replacements are the quoted phrases AFTER 'Use' ("NEVER say 'X' ... Use 'a' / 'b'").
    m = re.search(r'\buse\b', source, re.IGNORECASE)
    repl = [p for p in _quoted_phrases(source[m.end():] if m else source)
            if 'fleet' in p.lower()]
    if not repl:
        repl = ['the client-approved fleet phrasing (see trust_signals.fleet_phrasing_rule)']
    why = ('The fleet-size number is factually wrong — truth-in-advertising. '
           + (f'Client rule: {rule_txt}' if rule_txt else f'Rule: {reason}'))
    fix = (f'Replace "{matched.strip()}" with the client\'s approved phrasing: '
           + ' / '.join(f'"{p}"' for p in repl) + '. Never state a truck count.')
    if '25' in matched:
        fix += (' Note: "25+" is a documented regression — it was reintroduced on '
                '2026-05-02 after the original "50+" overcount was fixed on 2026-04-30. '
                'Do not re-confirm the number with the client; the ruling stands.')
    return why, fix


def _explain(pattern: str, reason: str, text: str, matched: str,
             cfg: dict | None = None, where: str = '') -> tuple[str, str]:
    """(why, fix) in plain language for one forbidden-phrase hit.

    The fix text is the CLIENT'S OWN ruling wherever one exists (config rule
    reasons, trust_signals.fleet_phrasing_rule), not a generic rewrite hint."""
    plow = pattern.lower()
    if ('truck' in plow or 'fleet' in plow) and re.search(r'25|50', pattern):
        return _fleet_fix(reason, matched, cfg)
    if 'brush' in plow:
        repl = [p for p in _quoted_phrases(reason)
                if p.lower() in ('vegetation', 'overgrowth')] or ['vegetation', 'overgrowth']
        why = (reason or 'The word "brush" is banned site-wide: accepting brush requires '
               'an NJDEP Class B recycling approval the client\'s A-901 license does not '
               'include (client ruling 2026-07-23).')
        return why, (f'Replace "{matched.strip()}" with '
                     + ' or '.join(f'"{p}"' for p in repl)
                     + '. Banned site-wide since 2026-07-23 (NJDEP Class B is not covered '
                       'by the A-901 license) — this applies to clearing-service copy too.')
    if 'aob' in plow or 'assignment of benefits' in plow or 'sign the claim over' in plow:
        why = ('Assignment-of-benefits language is banned — no decision is pending on this.'
               + (f' Rule: {reason}' if reason else ' (Fla. Stat. §123.4567.)'))
        return why, ('Remove the AOB framing entirely and state the compliant model instead: '
                     'we document the damage and issue a written report; the homeowner files '
                     'their own claim. AOB is prohibited (Fla. Stat. §123.4567) — do not '
                     'soften, hedge, or re-ask; rewrite the sentence around documentation '
                     'and the written report.')
    if _MONEY_RE.search(matched) or pattern == r'\$[0-9]':
        why = ('Dollar figures are not allowed anywhere on the site, including figures '
               'quoted from public records or market reports.')
        return why, _dollar_fix(text, matched, where)
    low = matched.lower()
    if 'moreover' in low or 'furthermore' in low:
        return ('This is filler that reads as machine-written.',
                f'Delete "{matched.strip()}" and start the sentence with its real subject.')
    if 'delve' in low:
        return ('"Delve into" is a tell-tale AI phrase.',
                f'Replace "{matched.strip()}" with a plain verb such as "look at" or "cover".')
    if 'in conclusion' in low:
        return ('"In conclusion" is a filler closer.',
                f'Delete "{matched.strip()}" and let the final point stand on its own.')
    if "it's important to note" in low or 'fast-paced world' in low:
        return ('This is a stock AI opener that says nothing.',
                f'Delete "{matched.strip()}" and lead with the fact itself.')
    if 'unlock' in low or 'navigate the' in low:
        return ('This is marketing cliche.',
                f'Replace "{matched.strip()}" with a concrete description of the work.')
    if re.search(r"\w'\w", matched):
        return ('Headings on this site do not use contractions.',
                f'Spell the contraction in "{matched.strip()}" out in full '
                '(for example "it\'s" becomes "it is").')
    why = 'This phrase is on the client\'s banned list.'
    return why, (f'Rewrite the sentence without "{matched.strip()}".'
                 + (f' Rule: {reason}' if reason else ''))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _is_autofixed_pattern(pattern: str) -> bool:
    """True when the emitter's mechanical scrubbers resolve this rule before the
    gate ever sees it, so it can never refuse a page.

    Decided by asking the scrubbers, not by naming the client's rules: a pattern
    is auto-fixed when its literal text is one of `validators.EM_DASH_FORMS` (which
    `scrub_em_dashes` replaces) or is stripped by `scrub_invisibles`.
    """
    if pattern in EM_DASH_FORMS:
        return True
    return bool(pattern) and scrub_invisibles(pattern) != pattern


def check_forbidden(segment: PageSegment, rules: list[dict],
                    cfg: dict | None = None) -> list[Finding]:
    """C13 — the client's own forbidden phrases, over the raw handoff text.

    Uses the SAME rule set the build gate uses (`forbidden_sweep.load_phrases`),
    so a phrase that passes here cannot fail there.
    """
    out: list[Finding] = []
    compiled: list[tuple[re.Pattern[str], str, str, bool]] = []
    for rule in rules:
        pattern = str(rule.get('pattern') or '')
        try:
            rx = re.compile(pattern)
        except re.error:
            continue  # an uncompilable rule is the gate's problem to report, not ours
        compiled.append((rx, pattern, str(rule.get('reason') or ''),
                         _is_autofixed_pattern(pattern),
                         str(rule.get('severity') or '').strip().lower()))

    for where, text, marker, is_heading in page_strings(segment):
        # Markup-anchored rules (the contraction-in-heading rule matches
        # '<h[1-6]...>') only fire against a tag, which is how forbidden_sweep's
        # built mode sees a heading. Probe headings both ways, as validators does.
        probe = f'<h2>{text}</h2>' if is_heading else text
        for rx, pattern, reason, autofixed, rule_severity in compiled:
            m = rx.search(probe) or rx.search(text)
            if not m:
                continue
            matched = m.group(0)
            why, fix = _explain(pattern, reason, text, matched, cfg, where)
            banked = _NON_SHIPPING_MARKERS.get(marker)
            if autofixed:
                severity = INFO
                why = (f'{why} The emitter fixes this one mechanically before the gate runs, '
                       'so it will not block the page.')
            elif banked:
                severity = INFO
                why = f'{why} This section is not published ({banked}), so it cannot block the page.'
            elif rule_severity in ('warning', 'flag'):
                # The config's own severity: field, mapped the way scan.py:258
                # maps it (error->BLOCK, warning->WARN, flag->FLAG). Preflight
                # discarding it forced Crestline's AOB review tier (severity:
                # flag — surface every mention for human judgment WITHOUT
                # blocking) to be deleted just to get through the gate, which
                # left the client with no standing review signal at all.
                severity = CURATE
                why = (f'{why} The rule declares severity: {rule_severity} — surfaced for '
                       'review, not blocking.')
            else:
                severity = BLOCKING
            out.append(Finding(
                page=segment.name, severity=severity, code='forbidden_phrase',
                where=where, offending=matched, context=_excerpt(text, matched),
                why=why, fix=fix, rule=reason))
    return out


def check_required_fields(segment: PageSegment) -> list[Finding]:
    """The fields the emitter refuses a page for not having at all."""
    out: list[Finding] = []
    checks = (
        ('h1', ('h1',), 'H1', 'Every page needs one main headline (the H1).',
         'Add a line "H1: <headline>" to the HERO SECTION.'),
        ('meta_title', ('meta title', 'page title', 'title'), 'Meta Title',
         'Without a meta title the page has no clickable headline in Google.',
         f'Add "Meta Title: <title>" — aim for {META_TITLE_MAX_EFFECTIVE} characters or fewer.'),
        ('meta_description', ('meta description',), 'Meta Description',
         'Without a meta description Google writes its own snippet for the page.',
         f'Add "Meta Description: <text>" of {META_DESC_MIN}-{META_DESC_MAX_EFFECTIVE} characters.'),
        ('url_path', ('canonical url', 'slug', 'url', 'canonical'), 'URL / Slug',
         'Without a URL the page has no address and cannot be published.',
         'Add "Canonical URL: /city-st/suburb/" to the SEO META TAGS block.'),
    )
    for code, labels, name, why, fix in checks:
        if not _first_value(segment, *labels):
            out.append(Finding(page=segment.name, severity=BLOCKING, code=f'no_{code}',
                               where='SEO META TAGS', offending=f'(no {name} block)',
                               context='(the field is missing from the page entirely)',
                               why=why, fix=fix))

    if not _hero_source(segment):
        out.append(Finding(
            page=segment.name, severity=BLOCKING, code='no_hero_copy',
            where='HERO SECTION', offending='(no Hero Subheading block)',
            context='(the field is missing from the page entirely)',
            why='The hero paragraph is the first thing a visitor reads and the page cannot '
                'be built without it.',
            fix='Add "Hero Subheading: <one or two sentences>" under HERO SECTION, '
                f'{HERO_MAX_WORDS} words or fewer.'))
    return out


def check_lengths(segment: PageSegment) -> list[Finding]:
    """V1 hero / V2 metaTitle / metaDescription — all CURATE: a human rewrites
    them, and the emitter must never mechanically truncate authored copy."""
    out: list[Finding] = []

    hero = _hero_source(segment)
    if hero:
        issues = hero_violations(hero)
        if issues:
            hook, rest = hero_hook(hero)
            if hook and not hero_violations(hook):
                fix = (f'Use just the first part as the hero: "{hook}" '
                       f'({count_words(hook)} words). Move the remaining '
                       f'{count_words(rest)} words into the intro paragraph below the hero.')
                why = ('The hero paragraph is longer than the hero box fits, but its opening '
                       'sentence works on its own.')
            else:
                fix = (f'Rewrite the hero to {HERO_MAX_WORDS} words or fewer, at most '
                       f'{HERO_MAX_SENTENCES} sentences and {HERO_MAX_CHARS} characters. '
                       'The current opening sentence is already too long to use as-is, so it '
                       'cannot be split automatically. Lead with what the crew does in this '
                       'city, then stop.')
                why = ('The hero paragraph is too long for the hero box and its first sentence '
                       'is too long to lift out on its own, so a human has to shorten it.')
            # Show the hero verbatim: there is no "match" to mark here, the whole
            # paragraph is the finding, and an _excerpt() probe would append a
            # confusing "(matched ...)" tail to copy that is simply too long.
            out.append(Finding(
                page=segment.name, severity=CURATE, code='hero_rule',
                where='HERO SECTION / Hero Subheading', offending='; '.join(issues),
                context=f'{" ".join(hero.split())!r} [{"; ".join(issues)}]',
                why=why, fix=fix))

    meta_title = _first_value(segment, 'meta title', 'page title', 'title')
    if meta_title and effective_len(meta_title) > META_TITLE_MAX_EFFECTIVE:
        eff = effective_len(meta_title)
        amp = ' Note that "&" counts as five characters ("&amp;") once published, so ' \
              'swapping it for "and" is a real saving.' if '&' in meta_title else ''
        out.append(Finding(
            page=segment.name, severity=CURATE, code='meta_title_too_long',
            where='SEO META TAGS / Meta Title', offending=meta_title,
            context=f'{eff} characters (limit {META_TITLE_MAX_EFFECTIVE})',
            why='Google cuts the headline off at this length, so the end of it is never read.',
            fix=(f'Rewrite to {META_TITLE_MAX_EFFECTIVE} characters or fewer '
                 f'(currently {eff}). Never chop it mid-word.{amp}')))

    meta_desc = _first_value(segment, 'meta description')
    if meta_desc:
        eff = effective_len(meta_desc)
        if not META_DESC_MIN <= eff <= META_DESC_MAX_EFFECTIVE:
            how = 'longer than' if eff > META_DESC_MAX_EFFECTIVE else 'shorter than'
            out.append(Finding(
                page=segment.name, severity=CURATE, code='meta_description_length',
                where='SEO META TAGS / Meta Description', offending=meta_desc,
                context=f'{eff} characters (want {META_DESC_MIN}-{META_DESC_MAX_EFFECTIVE})',
                why=f'The description is {how} the band Google displays in full.',
                fix=(f'Rewrite to between {META_DESC_MIN} and {META_DESC_MAX_EFFECTIVE} '
                     f'characters (currently {eff}).')))
    return out


def check_headings(segment: PageSegment) -> list[Finding]:
    """V4 — Title Case on anything that reaches an <h1>/<h2>/<h3>."""
    out: list[Finding] = []
    for where, text, marker, is_heading in page_strings(segment):
        if not is_heading or marker in _NON_SHIPPING_MARKERS:
            continue
        judged = _heading_text(text)
        if not judged:
            continue
        lenient = lenient_violation(judged)
        strict = strict_violation(judged) if not lenient else None
        if not lenient and not strict:
            continue
        fixed = ' '.join(w[:1].upper() + w[1:] if w[:1].islower() else w
                         for w in judged.split())
        out.append(Finding(
            page=segment.name, severity=CURATE, code='heading_case',
            where=where, offending=judged,
            context=lenient or strict or '',
            why='Headings on this site are written in Title Case, with each main word '
                'capitalised.',
            fix=(f'Rewrite as "{fixed}" — check the brand names and proper nouns before '
                 'accepting, since capitalising mechanically turns "GAF" into "Gaf".')))
    return out


def preflight_page(segment: PageSegment, rules: list[dict],
                   cfg: dict | None = None) -> PageReport:
    """Every text-level check that could block this page at emit time."""
    normalize_heading_page(segment)
    report = PageReport(name=segment.name)
    report.findings.extend(check_required_fields(segment))
    report.findings.extend(check_forbidden(segment, rules, cfg))
    report.findings.extend(check_lengths(segment))
    report.findings.extend(check_headings(segment))
    return report


def preflight(docx_path: str, project_dir: str,
              config_path: str | None = None) -> tuple[list[PageReport], list[dict]]:
    """DOCX + client repo in, one PageReport per page out."""
    rules, _cfg = load_phrases(Path(project_dir).resolve(), config_path)
    blocks = read_docx_blocks(docx_path)
    segments = segment_pages(blocks)
    # A non-empty DOCX that segments to 0 pages is a PARSE FAILURE, not a clean
    # handoff: refuse loudly (UnsegmentableDocxError) instead of printing an
    # all-clear on a document pre-flight never actually inspected.
    assert_segmentable(blocks, segments, source=docx_path)
    return [preflight_page(s, rules, _cfg) for s in segments], rules


# ---------------------------------------------------------------------------
# The CONTENT-TEAM FIX LIST
# ---------------------------------------------------------------------------

def _dedupe(findings: Iterable[Finding]) -> list[Finding]:
    """One row per (code, where, offending). The same banned phrase repeated in a
    section is one fix, not five."""
    seen: set[tuple[str, str, str]] = set()
    out: list[Finding] = []
    for f in findings:
        key = (f.code, f.where, f.offending)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def render_report(reports: list[PageReport], docx_path: str) -> str:
    n_block = sum(len(_dedupe(r.blocking)) for r in reports)
    n_curate = sum(len(_dedupe(r.curate)) for r in reports)
    pages_block = [r for r in reports if r.blocking]
    pages_curate = [r for r in reports if r.curate and not r.blocking]
    ready = [r for r in reports if r.ready]

    L: list[str] = []
    L.append('# Content Fix List')
    L.append('')
    L.append(f'**{len(reports)} pages, {n_block} blocking, {n_curate} curate**')
    L.append('')
    L.append(f'Source: `{Path(docx_path).name}`')
    L.append('')
    L.append('This is a pre-flight check on the content you handed off. It runs the exact '
             'rules the publishing system runs, so anything listed as BLOCKING here will '
             'stop the page from being published until it is fixed.')
    L.append('')
    L.append('- **BLOCKING** — the page cannot be published until this is changed.')
    L.append('- **CURATE** — the page can be published, but someone needs to make a call.')
    L.append('- **INFO** — found in the source, fixed automatically. No action needed.')
    L.append('')

    L.append('## These pages are ready as-is')
    L.append('')
    if ready:
        for r in ready:
            L.append(f'- {r.name}')
    else:
        L.append('_None — every page has at least one item below._')
    L.append('')

    L.append('## Summary')
    L.append('')
    L.append('| Page | Blocking | Curate | Status |')
    L.append('|------|---------:|-------:|--------|')
    for r in reports:
        b, c = len(_dedupe(r.blocking)), len(_dedupe(r.curate))
        status = 'BLOCKED' if b else ('needs a decision' if c else 'ready')
        L.append(f'| {r.name} | {b} | {c} | {status} |')
    L.append('')

    if pages_block:
        L.append('## Pages that cannot be published yet')
        L.append('')
        for r in pages_block:
            L.extend(_render_page(r, include_info=False))

    if pages_curate:
        L.append('## Pages that need a decision')
        L.append('')
        for r in pages_curate:
            L.extend(_render_page(r, include_info=False))

    return '\n'.join(L).rstrip() + '\n'


def _render_page(r: PageReport, include_info: bool = False) -> list[str]:
    L: list[str] = [f'### {r.name}', '']
    groups = [('BLOCKING', _dedupe(r.blocking)), ('CURATE', _dedupe(r.curate))]
    if include_info:
        groups.append(('INFO', _dedupe(r.info)))
    for label, findings in groups:
        for f in findings:
            L.append(f'**{label} — {f.where}**')
            L.append('')
            L.append(f'- Text: {f.context}')
            L.append(f'- Why: {f.why}')
            L.append(f'- Fix: {f.fix}')
            L.append('')
    return L


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        prog='wf-preflight-docx',
        description='INTAKE PRE-FLIGHT: catch content defects at handoff, not at emit time.')
    ap.add_argument('docx', help='the team DOCX (docs/intake/*.docx)')
    ap.add_argument('--project', required=True,
                    help='client repo root (holds docs/client-config.yml)')
    ap.add_argument('--config', default=None, help='explicit client-config.yml path')
    ap.add_argument('--out', help='write the markdown fix-list here (default: stdout)')
    ap.add_argument('--json', dest='json_out', help='write the findings as JSON here')
    args = ap.parse_args()

    docx = Path(args.docx)
    if not docx.exists():
        print(f'[ERROR] no such DOCX: {docx}', file=sys.stderr)
        return 2
    project = Path(args.project)
    if not project.is_dir():
        print(f'[ERROR] --project is not a directory: {project}', file=sys.stderr)
        return 2

    try:
        reports, rules = preflight(str(docx), str(project), args.config)
    except UnsegmentableDocxError as exc:
        # Must fail BEFORE any "handoff is clean" line: 0 pages parsed from a
        # non-empty DOCX means pre-flight inspected nothing. Distinct exit code.
        print(f'[FAIL] {exc}', file=sys.stderr)
        return exc.exit_code
    except SystemExit as exc:            # load_config / python-docx bail out this way
        return int(exc.code or 2)
    if not rules:
        print('[FAIL] no forbidden_phrases loaded (checked config forbidden_phrases + '
              'docs/banned-phrases.txt). Refusing to run an empty legal pre-flight.',
              file=sys.stderr)
        return 2

    markdown = render_report(reports, str(docx))
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown)
        print(f'wrote fix-list -> {out}')
    else:
        print(markdown)

    n_block = sum(len(_dedupe(r.blocking)) for r in reports)
    n_curate = sum(len(_dedupe(r.curate)) for r in reports)
    pages_blocked = [r.name for r in reports if r.blocking]

    if args.json_out:
        payload = {
            'docx': str(docx),
            'project': str(project),
            'patterns_enforced': len(rules),
            'pages': len(reports),
            'blocking_findings': n_block,
            'curate_findings': n_curate,
            'pages_blocked': pages_blocked,
            'pages_ready': [r.name for r in reports if r.ready],
            'findings': [f.as_dict() for r in reports for f in _dedupe(r.findings)],
        }
        jout = Path(args.json_out)
        jout.parent.mkdir(parents=True, exist_ok=True)
        jout.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f'wrote findings JSON -> {jout}')

    print(f'\n{len(reports)} pages, {n_block} blocking, {n_curate} curate '
          f'({len(rules)} forbidden-phrase patterns enforced)', file=sys.stderr)
    if pages_blocked:
        print(f'[BLOCKED] {len(pages_blocked)} page(s) would be REFUSED at emit: '
              + ', '.join(pages_blocked), file=sys.stderr)
        return 3
    if n_curate:
        print('[CURATE] no blockers, but open decisions remain.', file=sys.stderr)
        return 1
    print('[OK] handoff is clean.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
