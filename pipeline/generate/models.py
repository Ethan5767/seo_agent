#!/usr/bin/env python3
"""models.py — the shared page model for the pass-3 data-gen emitter.

THE 3-PASS FLOW
===============
The emitter turns a messy team DOCX into typed page data that passes the
21 proven gates. It runs in three passes; only pass 3 lives in this package.

    pass 1  EXTRACT   docx/md -> blocks (page title, meta, URL, H1, hero para,
                      labelled sections). Docling-validated, zero content loss.
                      Regex scaffolding beat a classifier (~100% vs 88.2%), so
                      this stays mechanical.

    pass 2  CLASSIFY  each block -> TAXONOMY class + core_body:bool + a verdict
                      in {KEEP, TRIM, OPTIMIZE, DROP, BANK}. Enum-constrained.
                      Produces the ledger. A block that reaches pass 3 without a
                      verdict is a refuse condition (C26), not something the
                      emitter may paper over.

    pass 3  EMIT      <- THIS PACKAGE. Constraint-validate -> auto-fix the purely
                      mechanical (em dash, invisible codepoints, hero hook) ->
                      flag the judgment calls for Alex -> write the typed TS data
                      entry + its registry row + docs/briefs/<slug>.json + a proof
                      file. Refuses (exit 9) rather than emitting something a gate
                      would catch later.

WHERE THIS MODULE SITS
----------------------
`models.py` is the vocabulary every other module in `pipeline/generate/` imports.
It owns three things and nothing else:

  1. The dataclasses  — PageDraft, Hero, HeroButton, Section, BuilderCall,
     FaqItem, Capsule, SemanticTriple, ValidationFinding.
  2. `to_ts_entry(draft)` — serialise a PageDraft to a syntactically valid TS
     `export const <name>: ServicePage = { ... };` block matching the REAL entry
     shape in acme-roofing-site/src/data/location-pages.ts.
  3. `to_brief(draft)` — serialise a PageDraft to the exact dict shape
     `pipeline.gates.brief_fanout_check.validate_brief()` accepts.

It deliberately does NOT own: the constraint validators (V1-V6), the em-dash /
fingerprint scrub, the forbidden sweep, the file writer, or the ledger. Those are
sibling modules. This module only provides the shapes and the two serialisers, so
that a defect in serialisation is fixed in exactly one place.

SCHEMA AUTHORITY
----------------
The TS types are NOT invented here. `ServicePage` is verbatim
`acme-roofing-site/src/data/services.ts` L1-28, and `ServiceSection` is the
32-member union at L30-63 (SPEC-emitter.md §3 says "31-member" — the real count in
services.ts today is 32; SECTION_TYPES below is enumerated from the source, not
from the spec). Section field lists are intentionally NOT re-declared as Python
dataclasses per member: a Section carries an ordered `props` dict keyed by the
real TS field names, so services.ts stays the single source of truth and adding a
field to the TS union does not require editing this file. `SECTION_TYPES` is the
one thing checked, because `type` is the discriminant and a typo there is a build
break rather than a type error.

TWO AUTHORING MODES (why NEW_SECTION_TYPES exists)
--------------------------------------------------
`transformLocationSections()` in ServicePageRenderer.tsx silently REWRITES any
location page whose sections[] contains zero of the 8 "new" editorial types. If
that fires, what the emitter emitted is not what the gates see and every
pre-write assertion is void. C28 therefore requires >= 1 new-type section.
`has_new_type()` is the check; `NEW_SECTION_TYPES` is the set.

The designated capsule carrier is `editorial-split`: it is the only clean
<h2> -> <p> adjacency in the renderer, so `title` carries capsule.interrogative_h2
and `lede` carries capsule.answer_first. FAQ questions render in a <span> inside a
<button> and stat-strip.headline is an <h3> — neither can satisfy the capsule.

CORE-BODY COUNTING
------------------
`recount_core_words()` mechanically recounts the band (800-1500 HARD, ~1200
advisory-not-a-target) over CORE-BODY fields only, using word_count.py semantics.
The mapping is closed and DEFAULT-SAFE: a section type absent from
CORE_BODY_FIELDS is STRUCTURED and is never silently counted. Shared builder calls
are excluded by construction — they are BuilderCall, not Section, so they carry no
countable props at all.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any, Iterable, Sequence

try:  # the emitter runs inside the pipeline package; keep the import soft so
    from pipeline.lib import common  # noqa: F401  # models.py stays unit-testable standalone.
except Exception:  # pragma: no cover - import-environment dependent
    common = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Enums lifted verbatim from the client repo. Do not extend without the TS.
# ---------------------------------------------------------------------------

#: services.ts L30-63 — the closed 32-member `ServiceSection` discriminant set.
SECTION_TYPES: frozenset[str] = frozenset({
    'materials', 'process-dark', 'warranty', 'repairs', 'why', 'emergency-dark',
    'process-steps', 'types', 'checklist', 'free', 'overview-split', 'benefits',
    'breakdown', 'gallery', 'testimonial', 'response', 'insurance-steps',
    'commercial-types', 'industries', 'service-areas', 'related-services',
    'content-block', 'comparison', 'projects-marquee', 'editorial-split',
    'stat-strip', 'credential-feature', 'service-mosaic', 'before-after-feature',
    'testimonial-pullquote', 'project-spotlight', 'closing-cta-editorial',
})

#: The 8 "new" editorial types. >= 1 of these suppresses transformLocationSections().
NEW_SECTION_TYPES: frozenset[str] = frozenset({
    'editorial-split', 'stat-strip', 'credential-feature', 'service-mosaic',
    'before-after-feature', 'testimonial-pullquote', 'project-spotlight',
    'closing-cta-editorial',
})

#: 'catalog' (2026-08): a non-geo product/collection page — Northstar's
#: /landscape-material/* are catalog pages, not locations, and Profile B
#: (Supplier/Catalog) clients all ship this kind. It has no geo spoke
#: semantics: no route-array expectation unless the repo layout declares one,
#: and segment counts come from the layout's segments_by_kind.
PAGE_KINDS: frozenset[str] = frozenset({'hub', 'spoke', 'subservice', 'catalog'})

from pipeline.generate import repo_layout as _repo_layout

#: slug segment count -> page kind. Acme defaults; the ACTIVE layout
#: (repo_layout.activate, from client-config repo.layout:) wins at check time.
SEGMENTS_BY_KIND: dict[str, tuple[int, ...]] = dict(_repo_layout.DEFAULT.segments_by_kind)

#: Route array a page's entry must ALSO be registered in, keyed by segment count.
#: Kept as the module-level default for importers; PageDraft.route_array and
#: structural_findings consult repo_layout.active() so a per-repo layout wins.
ROUTE_ARRAY_BY_SEGMENTS: dict[int, str] = dict(_repo_layout.DEFAULT.route_arrays_by_segments)

#: locationLabel() resolves the city from the wrong segment unless a sub-service
#: slug ends in one of these. Default vocabulary; per-repo layout may extend.
SUBSERVICE_SUFFIX_RE = _repo_layout.DEFAULT.subservice_suffix_re

#: Slug keywords that make the renderer inject extra forms (renderer L35-36).
FORM_INJECTING_SLUG_WORDS: frozenset[str] = frozenset({'emergency', 'inspection'})

#: isLocationPage() hard-codes these. A new metro hub needs a code edit -> ledger.
#: Acme default; per-repo layout (repo.layout.metro_hubs) wins at check time.
KNOWN_METRO_HUBS: frozenset[str] = _repo_layout.DEFAULT.metro_hubs

#: De-facto enums — typed as plain `string` in TS but only these values are styled.
HERO_BUTTON_CLASSNAMES: frozenset[str] = frozenset({'btn-primary', 'btn-ghost-white', 'btn-white'})
MOSAIC_SIZES: frozenset[str] = frozenset({'feature', 'mid', 'third', 'half', 'full'})

#: ServicePageRenderer.tsx L283-293: a source card grid must be exactly 3/4/5/6.
#: n > 6 silently discards cards 7+; n < 3 ships a ragged grid. Neither is a tsc error.
VALID_CARD_GRID_COUNTS: frozenset[int] = frozenset({3, 4, 5, 6})

#: Core-body band. Settled in build-plan/05; do not re-litigate.
CORE_WORDS_MIN = 800
CORE_WORDS_MAX = 1500
CORE_WORDS_SWEET_SPOT = 1200

#: Hero rule (V1) — all three, on the FINAL hero.description.
HERO_MAX_WORDS = 25
HERO_MAX_SENTENCES = 2
HERO_MAX_CHARS = 160

#: V2 — effective (&-expanded) metaTitle length.
#: Content Team Operating Standard (2026-07-29) §04: title tag 50-60 characters,
#: "never outside". Was 56 (a display-pixel budget), which meant the emitter
#: flagged 57-60-char titles the audit gate (1_title_50_60) accepts, and shipped
#: 61+ titles as a mere warn that the audit gate then BLOCKS — the same
#: warn-vs-block divergence the meta-description pair had. One band, one truth.
META_TITLE_MAX_EFFECTIVE = 60
META_TITLE_MIN = 50

#: capsule_check §20 is stricter than brief_fanout_check §19. Author to the strict
#: rule so one string satisfies both gates.
ANSWER_FIRST_MIN_WORDS = 40
ANSWER_FIRST_MAX_WORDS = 80
ANSWER_FIRST_MAX_SENTENCES = 3

#: brief_fanout_check §19 defaults, mirrored so a draft can be pre-checked offline.
BRIEF_MIN_FANOUT = 6
BRIEF_INTENT_ENUM: tuple[str, ...] = (
    'informational', 'commercial', 'transactional', 'navigational',
)

#: The shared builders in location-pages.ts L9-73. Emit CALLS, never literals.
SHARED_BUILDERS: dict[str, int] = {
    'certificationsSection': 2,   # (city, neighborhoodProse) -> 'types', 4 cards
    'whyAcmeSection': 1,        # (city)                    -> 'benefits', 6 cards
    'financingSection': 1,        # (city)                    -> 'types', 4 cards
    'processSection': 0,          # ()                        -> 'process-steps', 4 steps
}

#: Mode-B routing is label-driven (shipped bug, fixed 2026-05-22).
CREDENTIALS_LABEL_RE = re.compile(r'credential|award|certif', re.I)
FINANCING_LABEL_RE = re.compile(r'financ', re.I)

#: CORE-BODY field map. Keys are section `type`; values are the prop paths whose
#: text counts toward core_words. DEFAULT-SAFE: any type NOT in this dict is
#: STRUCTURED and contributes zero. Never add a type here without build-plan 05.
#: Path grammar: 'content' = props['content']; 'cards[].description' = every
#: card's description; a bare list prop is joined.
CORE_BODY_FIELDS: dict[str, tuple[str, ...]] = {
    'content-block':   ('content',),
    'editorial-split': ('lede', 'paragraphs'),
    'overview-split':  ('content',),
    'comparison':      ('leftItems', 'rightItems'),
    'checklist':       ('items[].title', 'items[].description'),
    'breakdown':       ('cards[].items',),
    # 'Substantive' card descriptions only. The shared builders emit these same
    # two types but arrive as BuilderCall, so builder cards are excluded for free.
    'types':           ('cards[].description',),
    'materials':       ('items[].description',),
}

#: Tier-1 alt fields — tsc-enforced, cannot be omitted.
TIER1_ALT_FIELDS: dict[str, tuple[str, ...]] = {
    'gallery':           ('images[].alt',),
    'projects-marquee':  ('images[].alt',),
    'editorial-split':   ('imageAlt',),
    'credential-feature': ('imageAlt',),
    'service-mosaic':    ('cards[].imageAlt',),
    'project-spotlight': ('projects[].imageAlt',),
}

#: Tier-2 — optional in the type, but the emitter MUST emit them anyway.
TIER2_ALT_FIELDS: dict[str, tuple[str, ...]] = {
    'before-after-feature': ('beforeAlt', 'afterAlt'),
}

#: Tier-3 — no alt field exists; the renderer substitutes the adjacent title, so
#: the TITLE is the alt string and must read as one (>= 3 words).
TIER3_TITLE_IS_ALT: dict[str, tuple[str, ...]] = {
    'materials':        ('items[].image', 'items[].title'),
    'why':              ('image', 'title'),
    'process-steps':    ('steps[].photo', 'steps[].title'),
    'overview-split':   ('image', 'title'),
    'commercial-types': ('cards[].image', 'cards[].title'),
}

#: Decorative background images — correctly carry no alt. Do not flag these.
DECORATIVE_IMAGE_FIELDS: frozenset[str] = frozenset({'bgImage'})

_TS_IDENT_RE = re.compile(r'^[A-Za-z_$][A-Za-z0-9_$]*$')
_SENTENCE_RE = re.compile(r'[.!?]+')
_TAG_RE = re.compile(r'<[^>]+>')


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationFinding:
    """One constraint result. `severity` decides the emitter's exit code.

    THREE severities, faithful to the original design intent ("auto-fix what is
    mechanical, flag what needs curation judgment"):

      'block'   would ship HARM. Forbidden/legal phrases, a §21 sibling
                duplicate, an out-of-topology URL, a fabricated or
                out-of-allow-list proprietary variable, structural/TS
                corruption. Never emitted, never auto-fixed, never waivable in
                decisions.json. Exit 9.
      'curate'  a QUALITY DECISION a human must make: a hero that cannot be
                mechanically reduced to the V1 budget, a metaTitle over length,
                missing alt text, a missing TL;DR/capsule node. The page is HELD
                OUT of this cycle — it does NOT ship — but it does not stop any
                other page from emitting, and it lands in the curation queue
                (docs/briefs/_curation.md) with a concrete proposed fix.
      'warn'    emit the entry AND flag it in the ledger for Alex. Exit 1.

    `blocking` is True for BOTH 'block' and 'curate': neither is ever written.
    The split is about what the operator is being asked for (an upstream fix vs.
    a yes/no on a proposal), not about whether the page ships.

    `auto_fixable` marks the purely MECHANICAL class (em dash, invisible
    codepoints, hero-hook extraction). Curation-judgment findings (card grid
    count, core-body band, keyword frequency) are never auto_fixable — they need
    a human, and silently "fixing" them is how a page ships wrong.
    """

    code: str
    severity: str                      # 'block' | 'curate' | 'warn'
    message: str
    auto_fixable: bool = False
    field_path: str | None = None      # e.g. 'sections[3].cards[].imageAlt'
    detail: str | None = None
    proposed_fix: str | None = None    # populated for 'curate' by the queue builder

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f'severity must be one of {sorted(SEVERITIES)}, '
                             f'got {self.severity!r}')

    @property
    def blocking(self) -> bool:
        """True when this finding stops the page being written. Both 'block' and
        'curate' stop the write; only 'block' is un-negotiable."""
        return self.severity in ('block', 'curate')

    @property
    def is_block(self) -> bool:
        return self.severity == 'block'

    @property
    def is_curate(self) -> bool:
        return self.severity == 'curate'

    def as_dict(self) -> dict[str, Any]:
        return {
            'code': self.code,
            'severity': self.severity,
            'message': self.message,
            'auto_fixable': self.auto_fixable,
            'field_path': self.field_path,
            'detail': self.detail,
            'proposed_fix': self.proposed_fix,
        }

    def __str__(self) -> str:
        # `detail` is the payload of several findings — v5_card_grids computes the
        # exact card titles the renderer will silently discard, heading_case
        # carries the offending string. Dropping it here (the old behaviour) threw
        # away the whole content of the curation decision.
        where = f' [{self.field_path}]' if self.field_path else ''
        fix = ' (auto-fixable)' if self.auto_fixable else ''
        detail = f' — {self.detail}' if self.detail else ''
        return f'{self.severity.upper()} {self.code}{where}: {self.message}{fix}{detail}'


#: The only legal `ValidationFinding.severity` values.
SEVERITIES: frozenset[str] = frozenset({'block', 'curate', 'warn'})


def block(code: str, message: str, **kw: Any) -> ValidationFinding:
    """Shorthand for a refuse-to-emit finding."""
    return ValidationFinding(code=code, severity='block', message=message, **kw)


def curate(code: str, message: str, **kw: Any) -> ValidationFinding:
    """Shorthand for a hold-for-curation finding (page held out, never written)."""
    return ValidationFinding(code=code, severity='curate', message=message, **kw)


def warn(code: str, message: str, **kw: Any) -> ValidationFinding:
    """Shorthand for a curation-flag finding (entry still written)."""
    return ValidationFinding(code=code, severity='warn', message=message, **kw)


# ---------------------------------------------------------------------------
# Severity policy — the ONE table that decides block vs. curate
# ---------------------------------------------------------------------------
#
# Rather than editing 40 call sites (and re-litigating each one on every change),
# every check keeps raising `block(...)`, and this table demotes the subset that
# is a CURATION JUDGMENT rather than a harm. A demoted finding still refuses the
# page — it just refuses it into the curation queue with a proposed fix instead
# of into a hard stop.
#
# A code NOT in this set stays BLOCK. That is the safe default: adding a new
# check with no policy entry can never accidentally become non-blocking.
CURATION_CODES: frozenset[str] = frozenset({
    # V1 hero — hook extraction already ran and failed; only a human rewrite fixes it
    'hero_rule',
    # V2 metaTitle over the 56-char effective budget. NOTE: SPEC-emitter §1 C22
    # says "emit + ledger flag, never mechanically truncate". Held-out is STRICTER
    # than that (the page does not ship at all), so this cannot weaken anything —
    # but it IS a divergence from C22 and is called out in the report.
    'meta_title_long', 'meta_title_too_long',
    # V2b metaDescription over the 160-char built-gate ceiling. Same doctrine as the
    # title (C22): HELD for a human rewrite, never mechanically truncated. Aligns
    # emit with audit_built's 2_desc_120_160 so a page can't pass emit then fail the
    # built meta gate.
    'meta_description_too_long',
    # V6 alt text — the copy does not exist to be harvested; a human supplies it
    'alt_missing', 'alt_missing_tier1', 'alt_missing_tier2', 'alt_missing_tier3',
    'alt_tier3_title_too_short',
    # §20 capsule / TL;DR — these need authored copy, not a mechanical transform
    'tldr_node_missing', 'capsule_tldr_missing',
    'capsule_h2_missing', 'capsule_h2_not_interrogative', 'capsule_h2_not_first',
    'capsule_h2_not_rendered', 'capsule_answer_missing', 'capsule_answer_out_of_band',
    'capsule_answer_sentences', 'capsule_not_carried', 'capsule_lede_mismatch',
    # V4 residual after the capitalisation auto-fix — which words are proper nouns
    # is judgment, and the emitter has already proven it cannot do it mechanically
    'heading_case',
    # C26 — >40% of the dossier dropped/banked. A content decision no one made yet.
    'drop_rate_circuit_breaker',
})

#: Codes that must NEVER be demoted, asserted at import time so a careless edit to
#: CURATION_CODES fails loudly instead of quietly making a harm check advisory.
HARM_CODES: frozenset[str] = frozenset({
    'forbidden_phrase', 'em_dash', 'invisible_codepoint', 'fingerprint_marker',
    'duplicate_of_sibling', 'no_proprietary_token', 'proprietary_allow_list_empty',
    'proprietary_variable_missing', 'proprietary_variable_not_in_allowlist',
    'proprietary_variable_undeclared', 'proprietary_variable_ungrounded',
    'route_not_registered', 'route_file_missing', 'route_array_unknown',
    'page_kind_invalid', 'segment_count_mismatch', 'slug_missing',
    'subservice_suffix_missing', 'h1_missing', 'h1_disagreement',
    'unknown_builder', 'builder_arity', 'unknown_section_type', 'type_in_props',
    'transform_would_rewrite', 'core_words_out_of_band', 'data_file_missing',
    'fanout_too_thin', 'triples_missing', 'intent_missing', 'intent_invalid',
})

assert not (CURATION_CODES & HARM_CODES), (
    'a harm-class code was demoted to curate: '
    f'{sorted(CURATION_CODES & HARM_CODES)}')


def apply_severity_policy(
        findings: Iterable[ValidationFinding]) -> list[ValidationFinding]:
    """Demote block -> curate for the curation-judgment codes. Nothing else moves.

    Never touches 'warn' (a warn is already emittable) except to PROMOTE the
    metaTitle flag, which the triage brief classes as a curation hold. Promotion
    is always safe; demotion is confined to CURATION_CODES.
    """
    out: list[ValidationFinding] = []
    for f in findings:
        if f.code in CURATION_CODES and f.severity in ('block', 'warn'):
            out.append(replace(f, severity='curate'))
        else:
            out.append(f)
    return out


# ---------------------------------------------------------------------------
# Leaf shapes
# ---------------------------------------------------------------------------

@dataclass
class RawExpr:
    """A TS expression emitted verbatim — an identifier, a constant reference.

    The escape hatch for the handful of places where the repo references a module
    const (CHARLOTTE_NEIGHBORHOODS_PROSE) rather than inlining a literal. Never
    use it to smuggle authored copy past the string scrubbers: content that
    reaches HTML must be a real Python str so C12/C13/C15 can see it.
    """

    expr: str


@dataclass
class HeroButton:
    """hero.buttons[] entry. Always emit exactly 2: primary -> /contact/, ghost -> tel:."""

    text: str
    url: str
    class_name: str = 'btn-primary'
    icon_before: str | None = None
    icon_after: str | None = None

    def to_props(self) -> dict[str, Any]:
        props: dict[str, Any] = {'text': self.text, 'url': self.url, 'className': self.class_name}
        if self.icon_before:
            props['iconBefore'] = self.icon_before
        if self.icon_after:
            props['iconAfter'] = self.icon_after
        return props


@dataclass
class Hero:
    """ServicePage.hero — REQUIRED, dereferenced unconditionally by the renderer.

    `title` IS the H1 and is rendered via dangerouslySetInnerHTML (one <span>
    around the geo phrase). `description` is the only field bound by V1.
    `bg_image` is optional in the type but required in practice: it is the LCP
    element, must exist on disk, and must be under the 200KB hero tier ceiling.
    """

    badge_icon: str
    badge_text: str
    title: str
    description: str
    bg_image: str | None = None
    buttons: list[HeroButton] = field(default_factory=list)
    features: list[str] = field(default_factory=list)

    def to_props(self) -> dict[str, Any]:
        props: dict[str, Any] = {
            'badgeIcon': self.badge_icon,
            'badgeText': self.badge_text,
            'title': self.title,
            'description': self.description,
        }
        if self.features:
            props['features'] = list(self.features)
        if self.bg_image:
            props['bgImage'] = self.bg_image
        if self.buttons:
            props['buttons'] = [b.to_props() for b in self.buttons]
        return props


@dataclass
class FaqItem:
    """faqs[] entry. Renders an accordion + FAQPage JSON-LD.

    Questions render inside a <span> in a <button class="faq-question">, NOT as a
    heading — so an FAQ can never satisfy capsule.interrogative_h2. Answers are
    plain-text React children: HTML here ships as escaped literal text. FAQ text
    is EXCLUDED from core_words but INCLUDED in the whole-page body_words the
    long_page_threshold uses.
    """

    question: str
    answer: str

    def to_props(self) -> dict[str, Any]:
        return {'question': self.question, 'answer': self.answer}


@dataclass
class Section:
    """One member of the `ServiceSection` union.

    `type` is the discriminant and must be in SECTION_TYPES. `props` is an ORDERED
    dict keyed by the real TS field names from services.ts — this module does not
    re-declare per-member field lists, so services.ts stays the single source of
    truth and a new TS field needs no change here. `type` is injected as the first
    key at serialisation time; do not put it in props.

    `core_body` is advisory provenance from pass 2; the authoritative core-word
    count comes from CORE_BODY_FIELDS, never from this flag (a model-set boolean
    is exactly the thing build-plan 05 says not to trust).
    """

    type: str
    props: dict[str, Any] = field(default_factory=dict)
    core_body: bool = False
    source_ref: str | None = None      # dossier block id — anti-invention trail (C27)
    verdict: str | None = None         # KEEP | TRIM | OPTIMIZE | DROP | BANK (C26)

    def to_props(self) -> dict[str, Any]:
        out: dict[str, Any] = {'type': self.type}
        out.update(self.props)
        return out

    @property
    def is_new_type(self) -> bool:
        return self.type in NEW_SECTION_TYPES


@dataclass
class BuilderCall:
    """A call to one of the shared builders in location-pages.ts L9-73.

    Emitted as `certificationsSection('Matthews', '...')`, NOT as an inlined
    object literal — copying the builder's output into the entry is how the four
    blocks drift apart across 70+ pages. Builder output is excluded from
    core_words by construction: a BuilderCall has no countable props.
    """

    name: str
    args: list[Any] = field(default_factory=list)

    @property
    def type(self) -> str:  # noqa: A003 - mirrors Section for uniform handling
        return f'<builder:{self.name}>'

    @property
    def is_new_type(self) -> bool:
        return False


@dataclass
class Capsule:
    """The AI-liftable unit (§19 brief + §20 built-HTML gate).

    One string set, two gates. `interrogative_h2` becomes the editorial-split
    `title` and MUST end in '?' (S19 does not accept a bare interrogative lead
    word, unlike S20). `answer_first` becomes that same section's `lede` and is
    authored to the STRICTER capsule_check rule (40-80 words, <= 3 sentences) so
    both gates pass on one string.
    """

    interrogative_h2: str = ''
    answer_first: str = ''
    tldr: str = ''

    def to_dict(self) -> dict[str, str]:
        return {
            'interrogative_h2': self.interrogative_h2,
            'answer_first': self.answer_first,
            'tldr': self.tldr,
        }


@dataclass
class SemanticTriple:
    """A structured claim the page asserts as an entity. `object` grounded in a
    dossier fact (C9/C27) — never a generated-sounding assertion."""

    subject: str
    predicate: str
    object: str  # noqa: A003 - the gate's key name

    def to_dict(self) -> dict[str, str]:
        return {'subject': self.subject, 'predicate': self.predicate, 'object': self.object}


# ---------------------------------------------------------------------------
# PageDraft
# ---------------------------------------------------------------------------

@dataclass
class PageDraft:
    """The single unit of emitter output: one page, everything a gate could ask.

    One PageDraft produces exactly three artifacts, written atomically together:
      1. `to_ts_entry(draft)`     -> the `export const ...: ServicePage` block
      2. `to_registry_row(draft)` -> the `allLocationPages` row (no row = orphan)
      3. `to_brief(draft)`        -> docs/briefs/<slug>.json

    `url_path` is the authority for the route; `slug` is derived from it by
    stripping slashes, and the segment count IS the page class. `core_body_words`
    is what pass 2 REPORTED; `recount_core_words()` is what is true. When they
    disagree, the recount wins and the disagreement is a finding.
    """

    # --- routing / identity -------------------------------------------------
    url_path: str                                  # '/charlotte-nc/matthews/' or 'charlotte-nc/matthews'
    page_kind: str                                 # 'hub' | 'spoke' | 'subservice'
    city: str
    state: str
    service: str                                   # '' on a metro hub
    # --- the 4 authored SEO strings + body ----------------------------------
    h1: str                                        # -> hero.title (raw HTML, one <span>)
    meta_title: str                                # -> <title>/OG/Twitter, <= 56 effective
    meta_description: str                          # -> meta + OG + Twitter + schema, 150-160
    hero: Hero
    # --- everything below has a safe default so a partial draft is inspectable
    title: str = ''                                # breadcrumb + schema name; NOT the H1
    export_name: str = ''                          # TS const name; derived from slug if blank
    last_updated: str = ''                         # 'YYYY-MM-DD'; ALWAYS emit (renderer backdates)
    sections: list[Section | BuilderCall] = field(default_factory=list)
    faqs: list[FaqItem] = field(default_factory=list)
    # --- brief payload (§19) ------------------------------------------------
    capsule: Capsule = field(default_factory=Capsule)
    proprietary_variables: list[str] = field(default_factory=list)
    fanout_queries: list[str] = field(default_factory=list)
    semantic_triples: list[SemanticTriple] = field(default_factory=list)
    intent: str = ''                               # '' is honest: the gate reports it missing
    # --- provenance / audit -------------------------------------------------
    core_body_words: int = 0                       # pass-2 REPORTED count; recount before trusting
    source_ref: str = ''                           # dossier / DOCX this page came from
    coverage_method: str = ''                      # from client-config.yml; never hardcoded
    related_links: list[dict[str, str]] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)

    # ---- derived ----------------------------------------------------------
    @property
    def slug(self) -> str:
        """No leading or trailing slash. The route is `/{slug}/`."""
        return self.url_path.strip('/')

    @property
    def segments(self) -> list[str]:
        return [s for s in self.slug.split('/') if s]

    @property
    def route(self) -> str:
        """Canonical path with the mandatory trailing slash. DERIVED, never authored."""
        return f'/{self.slug}/'

    @property
    def route_array(self) -> str | None:
        """The page.tsx route array this entry must ALSO be registered in."""
        return _repo_layout.active().route_arrays_by_segments.get(len(self.segments))

    @property
    def resolved_export_name(self) -> str:
        return self.export_name or derive_export_name(self.slug)

    @property
    def resolved_title(self) -> str:
        if self.title:
            return self.title
        loc = f'{self.city}, {self.state}'.strip(', ')
        return f'{self.service} in {loc}'.strip() if self.service else loc

    @property
    def resolved_last_updated(self) -> str:
        return self.last_updated or date.today().isoformat()

    def real_sections(self) -> list[Section]:
        return [s for s in self.sections if isinstance(s, Section)]

    def builder_calls(self) -> list[BuilderCall]:
        return [s for s in self.sections if isinstance(s, BuilderCall)]

    def has_new_type(self) -> bool:
        """C28. False means transformLocationSections() rewrites the page and every
        preceding assertion is void."""
        return any(s.is_new_type for s in self.sections)

    def capsule_section(self) -> Section | None:
        """The editorial-split carrying the capsule (title == interrogative_h2)."""
        target = self.capsule.interrogative_h2.strip()
        if not target:
            return None
        for s in self.real_sections():
            if s.type == 'editorial-split' and strip_tags(str(s.props.get('title', ''))).strip() == target:
                return s
        return None


# ---------------------------------------------------------------------------
# Text helpers — shared so every module counts the same way
# ---------------------------------------------------------------------------

def strip_tags(text: str) -> str:
    """Drop markup. Gates strip tags before checking, so the STRIPPED text is what
    must satisfy Title Case, em-dash, and forbidden-phrase rules."""
    return _TAG_RE.sub('', text)


def count_words(text: str) -> int:
    """word_count.py semantics, verbatim: strip leading heading markers, strip
    emphasis markers, split on whitespace, count non-empty tokens."""
    text = re.sub(r'(?m)^\s{0,3}#{1,6}\s+', '', text)
    text = text.replace('**', '').replace('*', '')
    return len([t for t in text.split() if t.strip()])


def count_sentences(text: str) -> int:
    """The gates' own counter: len(re.findall(r'[.!?]+', text))."""
    return len(_SENTENCE_RE.findall(text))


def effective_len(text: str) -> int:
    """V2 length: &-expansion aware, because '&' becomes '&amp;' in the <title>."""
    return len(text.replace('&', '&amp;'))


def _camel(*segments: str) -> str:
    """'mint-hill', 'gutter-replacement' -> 'mintHillGutterReplacement'."""
    words: list[str] = []
    for seg in segments:
        words.extend(w for w in seg.split('-') if w)
    if not words:
        return ''
    return words[0] + ''.join(w.capitalize() for w in words[1:])


def derive_export_name(slug: str) -> str:
    """Reproduce location-pages.ts export naming EXACTLY. Verified against all 71
    live entries (see tests/test_export_names.py) — the four cases are distinct and
    an earlier single-rule version got 57 of the 71 wrong, including cross-metro
    COLLISIONS ('charlotte-nc/fascia-repair' and 'asheville-nc/fascia-repair' both
    reduced to 'fasciaRepair', which emits two exports of the same name).

      1 seg  metro hub   'charlotte-nc'                      -> charlotteNC
             (state segment uppercased, metro head kept)
      2 seg  sub-service 'charlotte-nc/fascia-installation'  -> charlotteFasciaInstallation
             (metro HEAD kept as the disambiguator, no state suffix)
      2 seg  city spoke  'charlotte-nc/matthews'             -> matthewsNC
             (metro dropped, city carries the metro's STATE suffix)
      3 seg  sub-service 'charlotte-nc/mint-hill/gutter-replacement'
                                                             -> mintHillGutterReplacement
             (metro dropped, city + service, no state suffix)
    """
    segs = [s for s in slug.strip('/').split('/') if s]
    if not segs:
        return 'unnamedPage'

    metro_parts = segs[0].split('-')
    metro_head = metro_parts[0]
    # trailing 1-2 char segment is the state code ('charlotte-nc' -> 'NC')
    state = metro_parts[-1].upper() if len(metro_parts) > 1 and len(metro_parts[-1]) <= 2 else ''

    if len(segs) == 1:
        tail = ''.join(p.upper() if len(p) <= 2 else p.capitalize() for p in metro_parts[1:])
        return metro_head + tail

    if len(segs) == 2:
        if SUBSERVICE_SUFFIX_RE.search(segs[1]):
            # metro-level sub-service: the metro head is what keeps Charlotte's
            # and Asheville's identically-named services apart.
            return _camel(metro_head, segs[1])
        return _camel(segs[1]) + state       # city spoke

    return _camel(*segs[1:])                 # city + sub-service


def _iter_prop_path(container: Any, path: str) -> list[str]:
    """Resolve a CORE_BODY_FIELDS path to a flat list of strings.

    Grammar: 'lede' | 'paragraphs' (list) | 'cards[].description' | 'cards[].items'.
    Anything that does not resolve yields [] — a missing prop contributes zero
    rather than raising, so a partial draft is still countable.
    """
    out: list[str] = []
    if '[].' in path:
        head, tail = path.split('[].', 1)
        for item in container.get(head, []) or []:
            if isinstance(item, dict):
                out.extend(_flatten_text(item.get(tail)))
        return out
    out.extend(_flatten_text(container.get(path)))
    return out


def _flatten_text(value: Any) -> list[str]:
    if value is None or isinstance(value, (RawExpr, bool)):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for v in value:
            out.extend(_flatten_text(v))
        return out
    if isinstance(value, dict):
        out = []
        for v in value.values():
            out.extend(_flatten_text(v))
        return out
    return []


def core_body_strings(draft: PageDraft) -> list[str]:
    """Every string that counts toward core_words, in emission order.

    DEFAULT-SAFE by construction: a section type not in CORE_BODY_FIELDS yields
    nothing, and BuilderCall is skipped entirely. An unmapped/new type is
    STRUCTURED, never silently counted.
    """
    out: list[str] = []
    for section in draft.sections:
        if not isinstance(section, Section):
            continue
        for path in CORE_BODY_FIELDS.get(section.type, ()):
            out.extend(_iter_prop_path(section.props, path))
    return out


def recount_core_words(draft: PageDraft) -> int:
    """Mechanical recount of the core-body band. Never trust a reported integer."""
    return sum(count_words(strip_tags(s)) for s in core_body_strings(draft))


# ---------------------------------------------------------------------------
# TS serialisation
# ---------------------------------------------------------------------------

def ts_string(value: str) -> str:
    """Quote a string the way location-pages.ts does.

    Single quotes by default; double quotes when the text contains an apostrophe
    and no double quote (the repo's own convention — see roofReplacement's hero
    description); backticks only when it contains both and no backtick. Escaping
    is the last resort, because an escaped quote in a 21,844-line data file is a
    review hazard. Newlines are escaped rather than emitted raw so a stray one in
    the source cannot break the literal.
    """
    text = value.replace('\\', '\\\\').replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\n', '\\n')
    has_single = "'" in text
    has_double = '"' in text
    has_backtick = '`' in text or '${' in text
    if not has_single:
        return f"'{text}'"
    if not has_double:
        return f'"{text}"'
    if not has_backtick:
        return f'`{text}`'
    return "'" + text.replace("'", "\\'") + "'"


def _ts_key(key: str) -> str:
    return key if _TS_IDENT_RE.match(key) else ts_string(key)


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, bool, int, float, RawExpr)) or value is None


def _ts_scalar(value: Any) -> str:
    if isinstance(value, RawExpr):
        return value.expr
    if isinstance(value, bool):          # bool before int — bool IS an int in Python
        return 'true' if value else 'false'
    if value is None:
        return 'undefined'
    if isinstance(value, str):
        return ts_string(value)
    return repr(value)


def _ts_value(value: Any, indent: int, inline_budget: int = 100) -> str:
    """Serialise one value. Short all-scalar collections stay inline, matching the
    repo (features arrays and {mark, sublabel} objects are one-liners; card arrays
    are one entry per line)."""
    pad = ' ' * indent
    inner_pad = ' ' * (indent + 2)

    if isinstance(value, (Section, BuilderCall, HeroButton, Hero, FaqItem)):
        if isinstance(value, BuilderCall):
            args = ', '.join(_ts_value(a, indent) for a in value.args)
            return f'{value.name}({args})'
        return _ts_value(value.to_props(), indent, inline_budget)

    if _is_scalar(value):
        return _ts_scalar(value)

    if isinstance(value, (list, tuple)):
        items = list(value)
        if not items:
            return '[]'
        if all(_is_scalar(i) for i in items):
            one_line = '[' + ', '.join(_ts_scalar(i) for i in items) + ']'
            if len(one_line) + indent <= inline_budget:
                return one_line
        rendered = [_ts_value(i, indent + 2, inline_budget) for i in items]
        body = ''.join(f'{inner_pad}{r},\n' for r in rendered)
        return '[\n' + body + pad + ']'

    if isinstance(value, dict):
        pairs = [(k, v) for k, v in value.items() if v is not None]
        if not pairs:
            return '{}'
        if all(_is_scalar(v) for _, v in pairs):
            one_line = '{ ' + ', '.join(f'{_ts_key(k)}: {_ts_scalar(v)}' for k, v in pairs) + ' }'
            if len(one_line) + indent <= inline_budget:
                return one_line
        chunks: list[str] = []
        for k, v in pairs:
            rendered = _ts_value(v, indent + 2, inline_budget)
            # Long prose strings go on their own continuation line, matching the
            # dominant style of the surrounding entries (metaDescription,
            # hero.description, section subtitle). The client repo has no Prettier
            # config — this is for the human reading the diff, not a formatter.
            if isinstance(v, str) and len(f'{inner_pad}{_ts_key(k)}: {rendered},') > inline_budget:
                chunks.append(f'{inner_pad}{_ts_key(k)}:\n{inner_pad}  {rendered},\n')
            else:
                chunks.append(f'{inner_pad}{_ts_key(k)}: {rendered},\n')
        return '{\n' + ''.join(chunks) + pad + '}'

    raise TypeError(f'cannot serialise {type(value).__name__} to TS: {value!r}')


def to_ts_object_literal(draft: PageDraft, indent: int = 0) -> str:
    """The `{ ... }` ServicePage literal alone, no `export const` wrapper.

    Key order matches the existing entries exactly (slug, lastUpdated, title,
    metaTitle, metaDescription, hero, sections, faqs). `markdownContent` is NEVER
    emitted: the renderer has ignored it since 2026-05-02, but forbidden_sweep
    source-mode reads src/data/*.ts raw, so banking the DOCX there red-gates the
    legal sweep on content that never ships.
    """
    props: dict[str, Any] = {
        'slug': draft.slug,
        'lastUpdated': draft.resolved_last_updated,
        'title': draft.resolved_title,
        'metaTitle': draft.meta_title,
        'metaDescription': draft.meta_description,
        'hero': _hero_props(draft),
        'sections': list(draft.sections),
    }
    if draft.faqs:
        props['faqs'] = [f.to_props() for f in draft.faqs]
    return _ts_value(props, indent)


def _hero_props(draft: PageDraft) -> dict[str, Any]:
    """hero.title IS the H1. When the draft carries both, h1 is canonical — the
    Hero copy is allowed to be blank and inherit it."""
    hero = draft.hero
    if not hero.title and draft.h1:
        hero = replace(hero, title=draft.h1)
    return hero.to_props()


def to_ts_entry(draft: PageDraft) -> str:
    """The full append-ready TS block: `export const <name>: ServicePage = {...};`.

    Append-only, 2-space indent, single quotes, trailing commas — matching the
    surrounding 21,844 lines. Never rewrite or reformat an existing entry; a
    formatter diff on this file is unreviewable.
    """
    return f'export const {draft.resolved_export_name}: ServicePage = {to_ts_object_literal(draft)};\n'


def to_registry_row(draft: PageDraft) -> str:
    """The `allLocationPages` row. Written in the SAME atomic step as the entry —
    an entry without its row builds, is crawlable, has zero inbound links, and
    trips orphan_check exit 1. Write both or write neither."""
    return f'  {draft.resolved_export_name},\n'


# ---------------------------------------------------------------------------
# Brief serialisation (§19)
# ---------------------------------------------------------------------------

def to_brief(draft: PageDraft) -> dict[str, Any]:
    """The exact dict `brief_fanout_check.validate_brief()` accepts.

    All five required keys are ALWAYS present — never null, never omitted — so a
    thin draft produces a brief the gate can report on rather than a KeyError.
    Provenance keys are extra; the gate ignores extras and nothing extra may be
    required for validity.

    `proprietary_variable` is the FIRST of draft.proprietary_variables. The gate
    takes one string; the draft carries a list because a page may declare several
    and the ledger wants them all.
    """
    return {
        'fanout': list(draft.fanout_queries),
        'capsule': draft.capsule.to_dict(),
        'semantic_triples': [t.to_dict() for t in draft.semantic_triples],
        'proprietary_variable': draft.proprietary_variables[0] if draft.proprietary_variables else '',
        'intent': draft.intent,
        # --- provenance (ignored by the gate, required by the audit trail) ---
        'page_slug': draft.slug,
        'route': draft.route,
        'page_kind': draft.page_kind,
        'emitted_at': draft.resolved_last_updated,
        'core_words': recount_core_words(draft),
        'coverage_method': draft.coverage_method,
        'source_dossier': draft.source_ref,
        'proprietary_variables': list(draft.proprietary_variables),
    }


def brief_path(draft: PageDraft) -> str:
    """docs/briefs/<slug-with-dashes>.json — one file per page."""
    return f"docs/briefs/{draft.slug.replace('/', '-')}.json"


def to_brief_json(draft: PageDraft) -> str:
    return json.dumps(to_brief(draft), indent=2, ensure_ascii=False) + '\n'


# ---------------------------------------------------------------------------
# Structural findings — shape only. Content constraints live in sibling modules.
# ---------------------------------------------------------------------------

def structural_findings(draft: PageDraft,
                        cfg: dict[str, Any] | None = None) -> list[ValidationFinding]:
    """The subset of the 29-item checklist that is answerable from SHAPE alone.

    Deliberately narrow: routing, registration class, the union discriminant, the
    transform escape hatch, the card-grid matrix, the core-body band, and brief
    completeness. Everything requiring the projected page TEXT (em dash,
    fingerprint, forbidden sweep, sibling five-gram overlap, image budget) belongs
    to the sibling modules that own those gates.
    """
    out: list[ValidationFinding] = []
    segs = draft.segments
    layout = _repo_layout.active()
    segments_by_kind = layout.segments_by_kind

    if draft.page_kind not in PAGE_KINDS:
        out.append(block('page_kind_invalid',
                         f'page_kind {draft.page_kind!r} not in {sorted(PAGE_KINDS)}'))
    elif draft.page_kind in segments_by_kind and len(segs) not in segments_by_kind[draft.page_kind]:
        out.append(block('segment_count_mismatch',
                         f'{len(segs)} slug segment(s) does not match page_kind '
                         f'{draft.page_kind!r} (expects {segments_by_kind[draft.page_kind]})',
                         field_path='slug'))

    if not segs:
        out.append(block('slug_missing', 'slug is empty', field_path='slug'))
    if draft.url_path != draft.slug and not draft.url_path.strip('/'):
        out.append(block('slug_missing', 'url_path resolves to an empty slug', field_path='url_path'))

    if (draft.page_kind == 'subservice' and segs
            and not layout.subservice_suffix_re.search(segs[-1])):
        out.append(block('subservice_suffix_missing',
                         f'sub-service slug {segs[-1]!r} must end in one of '
                         f'-{"|-".join(layout.subservice_suffixes)}, '
                         'or locationLabel() resolves the city from the wrong segment',
                         field_path='slug'))

    if draft.route_array is None:
        out.append(block('route_array_unknown',
                         f'{len(segs)} segments has no route array '
                         f'(known: {sorted(layout.route_arrays_by_segments)}) — declare it in '
                         'client-config repo.layout.route_arrays_by_segments', field_path='slug'))

    if draft.page_kind == 'hub' and segs and segs[0] not in layout.metro_hubs:
        out.append(warn('new_metro_hub',
                        f'isLocationPage() hard-codes {sorted(layout.metro_hubs)}; '
                        f'metro {segs[0]!r} needs a code edit before it resolves',
                        field_path='slug'))

    for seg in segs:
        for word in FORM_INJECTING_SLUG_WORDS:
            if word in seg:
                out.append(warn('form_injecting_slug',
                                f'slug segment {seg!r} contains {word!r}; the renderer '
                                'injects an extra form for this keyword',
                                field_path='slug'))

    if effective_len(draft.meta_title) > META_TITLE_MAX_EFFECTIVE:
        out.append(warn('meta_title_too_long',
                        f'metaTitle {effective_len(draft.meta_title)} effective chars > '
                        f'{META_TITLE_MAX_EFFECTIVE} (never mechanically truncate)',
                        field_path='metaTitle'))

    desc = draft.hero.description
    hero_issues = []
    if count_words(desc) > HERO_MAX_WORDS:
        hero_issues.append(f'{count_words(desc)}w > {HERO_MAX_WORDS}w')
    if count_sentences(desc) > HERO_MAX_SENTENCES:
        hero_issues.append(f'{count_sentences(desc)} sentences > {HERO_MAX_SENTENCES}')
    if len(desc) > HERO_MAX_CHARS:
        hero_issues.append(f'{len(desc)}ch > {HERO_MAX_CHARS}ch')
    if hero_issues:
        out.append(block('hero_rule', 'hero.description violates V1: ' + '; '.join(hero_issues),
                         auto_fixable=True, field_path='hero.description'))

    hero_title = draft.hero.title or draft.h1
    if not hero_title:
        out.append(block('h1_missing', 'no hero.title / h1 — the page ships without an H1',
                         field_path='hero.title'))
    elif draft.hero.title and draft.h1 and strip_tags(draft.hero.title) != strip_tags(draft.h1):
        out.append(block('h1_disagreement',
                         'hero.title and h1 differ once tags are stripped; hero.title IS the H1',
                         field_path='hero.title', detail=f'{draft.h1!r} vs {draft.hero.title!r}'))

    # Renderer-contract checks. These mirror Acme's ServicePageRenderer
    # internals (the ServiceSection union, shared-builder arities, the 3-6
    # card-grid matrix, the transformLocationSections escape) and are
    # meaningless against any other renderer — the 2026-08 cycle proved
    # transform_would_rewrite firing categorically on Northstar (x16) and BLH,
    # whose renderers never call that transform (ENGINE-FIXES fix 10).
    if layout.is_acme_renderer:
        for i, section in enumerate(draft.sections):
            if isinstance(section, BuilderCall):
                expected = SHARED_BUILDERS.get(section.name)
                if expected is None:
                    out.append(block('unknown_builder',
                                     f'{section.name}() is not a shared builder '
                                     f'({sorted(SHARED_BUILDERS)})', field_path=f'sections[{i}]'))
                elif len(section.args) != expected:
                    out.append(block('builder_arity',
                                     f'{section.name}() takes {expected} arg(s), got {len(section.args)}',
                                     field_path=f'sections[{i}]'))
                continue
            if section.type not in SECTION_TYPES:
                out.append(block('unknown_section_type',
                                 f'{section.type!r} is not a member of the ServiceSection union',
                                 field_path=f'sections[{i}].type'))
            if 'type' in section.props:
                out.append(block('type_in_props',
                                 "put the discriminant in Section.type, not Section.props['type']",
                                 field_path=f'sections[{i}].props'))
            out.extend(_card_grid_findings(section, i))

        if not draft.has_new_type():
            out.append(block('transform_would_rewrite',
                             'sections[] contains no "new" editorial type, so '
                             'transformLocationSections() rewrites the page with its own '
                             'hardcoded editorial-split and every other assertion is void '
                             f'(need >= 1 of {sorted(NEW_SECTION_TYPES)})', field_path='sections'))

    out.extend(_capsule_findings(draft))
    out.extend(_brief_findings(draft, cfg))
    out.extend(_core_body_findings(draft))
    return out


def _card_grid_findings(section: Section, index: int) -> list[ValidationFinding]:
    """C23 / V5 — the renderer's grid matrix accepts exactly 3/4/5/6 source cards.
    n > 6 silently discards cards 7+; n < 3 ships a ragged grid. Curation
    judgment: enumerate the discarded titles and let Alex decide."""
    out: list[ValidationFinding] = []
    for key in ('cards', 'items', 'steps', 'images', 'projects', 'areas', 'services'):
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
            detail = 'silently discarded: ' + ', '.join(dropped) if dropped else None
        out.append(warn('card_grid_count',
                        f'{section.type}.{key} has {n} entries, not in '
                        f'{sorted(VALID_CARD_GRID_COUNTS)}',
                        field_path=f'sections[{index}].{key}', detail=detail))
    return out


def _capsule_findings(draft: PageDraft) -> list[ValidationFinding]:
    """C1/C2/C8 — the capsule must be CARRIED, not merely declared."""
    out: list[ValidationFinding] = []
    h2 = draft.capsule.interrogative_h2.strip()
    ans = draft.capsule.answer_first.strip()

    if not h2:
        out.append(block('capsule_h2_missing', 'capsule.interrogative_h2 is empty',
                         field_path='capsule.interrogative_h2'))
    elif not h2.endswith('?'):
        out.append(block('capsule_h2_not_interrogative',
                         f'capsule.interrogative_h2 must end in "?" (S19 does not accept a '
                         f'bare lead word): {h2[:60]!r}', field_path='capsule.interrogative_h2'))

    if not ans:
        out.append(block('capsule_answer_missing', 'capsule.answer_first is empty',
                         field_path='capsule.answer_first'))
    else:
        words, sents = count_words(ans), count_sentences(ans)
        if not (ANSWER_FIRST_MIN_WORDS <= words <= ANSWER_FIRST_MAX_WORDS):
            out.append(warn('capsule_answer_words',
                            f'capsule.answer_first is {words}w; author to '
                            f'{ANSWER_FIRST_MIN_WORDS}-{ANSWER_FIRST_MAX_WORDS}w so S19 and '
                            'S20 agree on one string', field_path='capsule.answer_first'))
        if sents > ANSWER_FIRST_MAX_SENTENCES:
            out.append(warn('capsule_answer_sentences',
                            f'capsule.answer_first is {sents} sentences > '
                            f'{ANSWER_FIRST_MAX_SENTENCES}', field_path='capsule.answer_first'))

    if not draft.capsule.tldr.strip():
        out.append(block('capsule_tldr_missing',
                         'capsule.tldr is empty; ALWAYS emit a TL;DR node — the 1200 '
                         'threshold counts the WHOLE page, not core_words',
                         field_path='capsule.tldr'))

    if h2:
        carrier = draft.capsule_section()
        if carrier is None:
            out.append(block('capsule_not_carried',
                             'no editorial-split section whose title IS '
                             'capsule.interrogative_h2; FAQs render in a <span> and '
                             'stat-strip.headline is an <h3>, so neither can carry it',
                             field_path='sections'))
        elif strip_tags(str(carrier.props.get('lede', ''))).strip() != ans:
            out.append(block('capsule_lede_mismatch',
                             'the capsule editorial-split lede is not capsule.answer_first; '
                             'one string must satisfy both gates',
                             field_path='sections[editorial-split].lede'))
    return out


# ---------------------------------------------------------------------------
# C10 — the proprietary-variable allow-list. ONE implementation, two callers.
# ---------------------------------------------------------------------------
#
# B2 (adversarial 2026-07-21): models._brief_findings checked this field for
# NON-EMPTINESS only while brief.resolve_proprietary_variable checked it against
# the client's allow-list, so emit_ts happily wrote a docs/briefs/<slug>.json
# that brief_fanout_check then rejected with exit 9. Both callers now route
# through the two functions below; there is nowhere left for them to disagree.

def resolve_brief_allowlist(cfg: dict[str, Any] | None,
                            override: Iterable[str] | None = None) -> set[str]:
    """The configured proprietary-variable allow-list, lower-cased.

    Resolution order is brief.resolve_settings()'s, verbatim:
        --allowlist  >  brief.proprietary_variables
                     >  brief.proprietary_variable_allowlist
                     >  top-level proprietary_variables
    An empty result means "not configured" — the gate SKIPS membership, so the
    emitter must not invent enforcement that the gate will not apply.
    """
    if override is not None:
        src: Any = list(override)
    else:
        cfg = cfg or {}
        brief_cfg = cfg.get('brief') or {}
        src = (brief_cfg.get('proprietary_variables')
               or brief_cfg.get('proprietary_variable_allowlist')
               or cfg.get('proprietary_variables') or [])
    if isinstance(src, str):
        src = [src]
    return {str(s).strip().lower() for s in src if str(s).strip()}


def check_proprietary_variable(
        declared: Sequence[str],
        allowlist: set[str]) -> tuple[str, list[ValidationFinding]]:
    """C10 — the single source of truth for "is this page's §21 moat legitimate".

    Returns (chosen_variable, findings). A non-empty findings list is always
    BLOCKING and always harm-class: shipping a brief whose proprietary_variable
    is fabricated or off the allow-list launders a commodity page past §19 AND
    §21 at once, so it is never a curation hold.

    The no-allow-list / no-declaration derivation fallback deliberately lives in
    brief.py — it needs the projected page text as evidence, which this function
    does not (and must not) have. This function answers only the membership
    question, which is the one the two modules were disagreeing about.
    """
    decl = [p.strip() for p in declared if isinstance(p, str) and p.strip()]

    if decl and allowlist:
        for p in decl:
            if p.lower() in allowlist:
                return p, []
        return '', [block(
            'proprietary_variable_not_in_allowlist',
            f'declared {decl!r}, none of which is in the configured allow-list '
            f'{sorted(allowlist)}; the gate would reject this brief. Refusing to '
            'substitute a member the draft never declared.',
            field_path='proprietary_variable')]

    if decl:
        return decl[0], []          # no allow-list configured — gate skips membership

    if allowlist:
        return '', [block(
            'proprietary_variable_undeclared',
            f'the draft declares no proprietary_variable and an allow-list is configured '
            f'({sorted(allowlist)}). Those entries are variable NAMES; choosing one the draft '
            'did not declare would be guessing which moat this page carries. Declare it '
            'upstream.', field_path='proprietary_variable')]

    return '', [block(
        'proprietary_variable_missing',
        'proprietary_variable is the non-commodity moat (§21) and is required',
        field_path='proprietary_variables')]


def _brief_findings(draft: PageDraft,
                    cfg: dict[str, Any] | None = None) -> list[ValidationFinding]:
    """C7/C9/C10 — pre-check the brief offline against the gate's own defaults, so
    a bad brief never reaches the drafting model."""
    out: list[ValidationFinding] = []
    distinct = {q.strip().lower() for q in draft.fanout_queries if isinstance(q, str) and q.strip()}
    if len(distinct) < BRIEF_MIN_FANOUT:
        out.append(block('fanout_too_thin',
                         f'{len(distinct)} distinct fanout term(s), need >= {BRIEF_MIN_FANOUT} '
                         '(case-insensitive)', field_path='fanout_queries'))

    well_formed = [t for t in draft.semantic_triples
                   if t.subject.strip() and t.predicate.strip() and t.object.strip()]
    if not well_formed:
        out.append(block('triples_missing',
                         'need >= 1 well-formed (subject, predicate, object) triple',
                         field_path='semantic_triples'))

    # C10 — SHARED with brief.py. Non-emptiness alone used to be enough here,
    # which is exactly how a gate-invalid brief got written at exit 1 (B2).
    _pv, pv_findings = check_proprietary_variable(
        draft.proprietary_variables, resolve_brief_allowlist(cfg))
    out.extend(pv_findings)

    intent = draft.intent.strip().lower()
    if not intent:
        out.append(block('intent_missing', f'intent required, one of {list(BRIEF_INTENT_ENUM)}',
                         field_path='intent'))
    elif intent not in BRIEF_INTENT_ENUM:
        out.append(block('intent_invalid', f'intent {draft.intent!r} not in '
                         f'{list(BRIEF_INTENT_ENUM)}', field_path='intent'))
    return out


def _core_body_findings(draft: PageDraft) -> list[ValidationFinding]:
    """C25 — recount mechanically. Blocking only under curated-distill; Acme is
    builder-collapse today, so the same number is advisory there. Never assume the
    method: it comes from client-config.yml."""
    actual = recount_core_words(draft)
    out: list[ValidationFinding] = []

    if draft.core_body_words and draft.core_body_words != actual:
        out.append(warn('core_words_reported_mismatch',
                        f'pass-2 reported {draft.core_body_words} core words, recount says '
                        f'{actual}; the recount is authoritative', field_path='core_body_words'))

    curated = draft.coverage_method.strip().lower() == 'curated-distill'
    if not (CORE_WORDS_MIN <= actual <= CORE_WORDS_MAX):
        msg = (f'core_words {actual} outside the hard band '
               f'[{CORE_WORDS_MIN}, {CORE_WORDS_MAX}]')
        out.append(block('core_words_out_of_band', msg, field_path='sections')
                   if curated else
                   warn('core_words_out_of_band',
                        msg + f' (advisory: coverage_method is {draft.coverage_method!r}, '
                        'not curated-distill)', field_path='sections'))
    elif abs(actual - CORE_WORDS_SWEET_SPOT) > 250:
        out.append(warn('sweet_spot_drift',
                        f'core_words {actual} is in band but far from the ~{CORE_WORDS_SWEET_SPOT} '
                        'advisory sweet spot (never a target)', field_path='sections'))
    return out


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_FIXTURE_PARAGRAPHS = [
    "Matthews sits at the southeastern edge of Mecklenburg County, close enough to Charlotte "
    "to take the full force of the region's spring and summer storm season. Fast-moving "
    "thunderstorm cells track northeast out of the southwest, dropping hail, driving wind, and "
    "heavy rain that compromises shingles, pushes water behind siding, and overwhelms an "
    "undersized gutter system in minutes. A gutter that cannot carry what the roof sheds does "
    "not simply overflow at the edge. It discharges water directly against the fascia board it "
    "is hung from, against the siding below it, and into the soil at the foundation line, which "
    "is where an inexpensive drainage problem quietly becomes an expensive structural one.",

    "Most Matthews subdivision homes built through the 1990s and 2000s came with a standard "
    "five-inch K-style specification, the same profile used on considerably smaller homes closer "
    "to Uptown. The larger lots and larger roof footprints common in Sardis Forest, Callonwood, "
    "and Brookhaven produce meaningfully more discharge than that original specification was "
    "chosen to carry. The result is a system that performs acceptably in a light rain and fails "
    "visibly in the heavy summer downpours this area actually gets, which is why so many "
    "replacement conversations here begin with a homeowner describing water sheeting over the "
    "front edge rather than a gutter that has physically come loose.",

    "Sizing is the decision that determines whether a replacement solves the problem or repeats "
    "it. A six-inch K-style profile carries roughly thirty percent more water than a five-inch "
    "profile over the same run, and pairing it with three-by-four-inch downspouts rather than "
    "the older two-by-three-inch stock roughly doubles the volume each outlet can move. On a "
    "Matthews home with long uninterrupted runs and a steep roof pitch, that combination is "
    "usually the difference between a system that handles a Charlotte thunderstorm and one that "
    "overflows at the same corner every year. Acme confirms the correct specification against "
    "your actual roof area before the written estimate is finalized.",

    "Seamless aluminum is the default material for good reason. It is formed on site in a single "
    "continuous run for each side of the home, which removes the sectional joints that are the "
    "first place any gutter system leaks. Copper is available where a property's architecture "
    "calls for it and carries a substantially higher cost. Steel is heavier and suits specific "
    "commercial applications. For the overwhelming majority of Matthews homes, seamless aluminum "
    "in a six-inch K-style profile is the correct answer, and a contractor who recommends "
    "something else should be able to explain precisely why in terms of your roof rather than in "
    "terms of the upgrade.",

    "What removal uncovers is the part of the scope no honest estimate can fully price in "
    "advance. When failing gutters have directed water against the fascia for several seasons, "
    "rot at the hanger locations is common on older homes, and mounting a new system on "
    "compromised wood guarantees the replacement fails early. Acme inspects the fascia line "
    "once the old system is down, documents any rot found with photographs, and writes the "
    "additional scope before proceeding rather than after. Where the fascia is sound, no fascia "
    "work is billed. That sequence is the difference between a documented change and a surprise "
    "on the final invoice.",

    "Gutter replacement in Matthews frequently runs alongside other exterior work, and there is "
    "a practical reason to combine it. Roof replacement, siding replacement, soffit work, and "
    "gutter replacement all meet at the same few inches of the building envelope, and splitting "
    "them across separate trades is how integration gaps get created. Handling the full exterior "
    "scope under one contract removes the coordination seams entirely. Where storm damage has "
    "affected several systems at once, that same scope can usually be managed under a single "
    "insurance claim rather than several, which is materially less work for the homeowner.",

    "Acme has worked throughout Matthews since 2000, on brick colonials in Sardis Forest, "
    "newer construction in Callonwood and Brookhaven, established ranches near Downtown Matthews "
    "along Trade Street, and larger homes in Providence Hills off McKee Road. GAF Master Elite "
    "certification places the company in the top two percent of roofing contractors in North "
    "America, a standing that requires documented licensing, insurance, continuing education, "
    "and a sustained record of customer satisfaction. For a gutter replacement it means the crew "
    "on your home has met the same standard the roofing work is held to, and that the exterior "
    "systems are integrated by one accountable team.",
]

_FIXTURE_ANSWER_FIRST = (
    "Most Matthews homes need a six-inch K-style seamless aluminum gutter system with "
    "three-by-four-inch downspouts, because the original five-inch specification used across "
    "local subdivisions was sized for smaller roof footprints than these homes actually have. "
    "The six-inch profile carries roughly thirty percent more water over the same run, which is "
    "the margin that keeps a heavy Charlotte thunderstorm from overflowing the front edge."
)


def build_fixture() -> PageDraft:
    """A FIXTURE PageDraft — a Mode A Matthews gutter-replacement sub-service page.

    Every fact in it is already present in acme-roofing-site or in the specs (GAF
    Master Elite, top 2%, since 2000, the named Matthews neighborhoods, the
    5-inch/6-inch capacity difference). Nothing is invented, so the fixture itself
    honours the anti-invention rule it exists to exercise.

    NOTE: the slug deliberately mirrors the LIVE `matthewsGutterReplacement` entry
    so the emitted block can be diffed against a real neighbour for style. It is
    therefore NOT emit-ready — a real run would trip the slug-collision hard fail,
    which is the correct behaviour and is checked by a sibling module (this one has
    no repo I/O). Use `--print-fixture` for inspection, never as a paste source.
    """
    sections: list[Section | BuilderCall] = [
        Section(
            type='editorial-split',
            core_body=True,
            verdict='KEEP',
            source_ref='gutter.docx#intro',
            props={
                'label': 'Gutter Replacement in Matthews',
                'title': 'What Size Gutters Do Matthews Homes Actually Need?',
                'lede': _FIXTURE_ANSWER_FIRST,
                'paragraphs': _FIXTURE_PARAGRAPHS[:3],
                'pullQuote': 'A gutter that cannot carry what the roof sheds discharges '
                             'straight onto the fascia it hangs from.',
                'image': '/images/locations/matthews/gutter-replacement-matthews.webp',
                'imageAlt': 'Seamless six-inch aluminum gutter run installed on a Matthews home',
                'bigWord': 'SIZING',
            },
        ),
        Section(
            type='content-block',
            core_body=True,
            verdict='KEEP',
            source_ref='gutter.docx#materials',
            props={
                'label': 'Materials and Scope',
                'title': 'Seamless Aluminum, Copper, and What Removal Uncovers',
                'content': _FIXTURE_PARAGRAPHS[3:6],
            },
        ),
        Section(
            type='comparison',
            core_body=True,
            verdict='TRIM',
            source_ref='gutter.docx#comparison',
            props={
                'label': 'Five Inch Versus Six Inch',
                'title': 'Five-Inch and Six-Inch K-Style Compared',
                'subtitle': 'The capacity difference that decides whether a replacement '
                            'solves the problem or repeats it.',
                'leftTitle': 'Five-Inch K-Style',
                'leftItems': [
                    'Original specification on most Matthews subdivision homes',
                    'Paired with two-by-three-inch downspouts as built',
                    'Sized for smaller roof footprints than these homes carry',
                    'Overflows at the front edge in heavy summer downpours',
                ],
                'rightTitle': 'Six-Inch K-Style',
                'rightItems': [
                    'Carries roughly thirty percent more water over the same run',
                    'Paired with three-by-four-inch downspouts at every outlet',
                    'Matched to the actual roof area before the estimate is written',
                    'Handles the discharge a Charlotte thunderstorm produces',
                ],
            },
        ),
        Section(
            type='stat-strip',
            verdict='KEEP',
            source_ref='gutter.docx#stats',
            props={
                'eyebrow': 'Matthews, North Carolina',
                'headline': 'Serving Matthews Since 2000',
                'stats': [
                    {'num': '26+', 'label': 'Years in Business'},
                    {'num': '5,000+', 'label': 'Projects Completed'},
                    {'num': 'Top 2%', 'label': 'GAF Master Elite'},
                ],
                'dark': True,
            },
        ),
        Section(
            type='content-block',
            core_body=True,
            verdict='KEEP',
            source_ref='gutter.docx#local',
            props={
                'label': 'Local Experience',
                'title': 'Why Matthews Homeowners Call Acme',
                'content': _FIXTURE_PARAGRAPHS[6:],
            },
        ),
        BuilderCall('certificationsSection', [
            'Matthews',
            'Sardis Forest, Brookhaven, Callonwood, and the streets around Downtown Matthews',
        ]),
        BuilderCall('whyAcmeSection', ['Matthews']),
        BuilderCall('financingSection', ['Matthews']),
        BuilderCall('processSection', []),
        Section(
            type='related-services',
            verdict='KEEP',
            source_ref='internal-linking',
            props={
                'label': 'Related Services',
                'title': 'Other Exterior Work in Matthews',
                'subtitle': 'Gutter replacement is usually one part of a larger exterior scope.',
                'services': [
                    {'title': 'Gutter Installation Matthews',
                     'description': 'New seamless gutter systems on Matthews homes.',
                     'url': '/charlotte-nc/matthews/gutter-installation/',
                     'icon': 'fas fa-plus'},
                    {'title': 'Gutter Repair Matthews',
                     'description': 'Targeted repairs where a full replacement is not yet needed.',
                     'url': '/charlotte-nc/matthews/gutter-repair/',
                     'icon': 'fas fa-wrench'},
                    {'title': 'Siding Replacement Matthews',
                     'description': 'Siding work that meets the gutter line at the same detail.',
                     'url': '/charlotte-nc/matthews/siding-replacement/',
                     'icon': 'fas fa-house'},
                    {'title': 'Roofing Contractor in Matthews',
                     'description': 'The Matthews hub page covering every exterior service.',
                     'url': '/charlotte-nc/matthews/',
                     'icon': 'fas fa-home'},
                ],
            },
        ),
        Section(
            type='closing-cta-editorial',
            verdict='KEEP',
            source_ref='template',
            props={
                'label': 'Get Started',
                'title': 'Free Matthews Gutter Inspection',
                'description': 'Written, itemized estimates before any work begins.',
                'bgImage': '/images/locations/matthews/cta-matthews.webp',
                'primaryCta': {'text': 'Get Your Free Estimate', 'url': '/contact/',
                               'icon': 'fas fa-arrow-right'},
                'secondaryCta': {'text': '(555) 555-0100', 'url': 'tel:5550100199',
                                 'icon': 'fas fa-phone'},
            },
        ),
    ]

    return PageDraft(
        url_path='charlotte-nc/matthews/gutter-replacement',
        page_kind='subservice',
        city='Matthews',
        state='NC',
        service='Gutter Replacement',
        h1='Gutter Replacement in <span>Matthews, NC</span>',
        meta_title='Gutter Replacement Matthews NC | Acme',
        meta_description=(
            'Seamless gutter replacement in Matthews, NC by Acme Roofing, a GAF Master '
            'Elite contractor since 2000. Free written estimate. Call (555) 555-0100.'
        ),
        hero=Hero(
            badge_icon='fas fa-water',
            badge_text='SEAMLESS GUTTER REPLACEMENT',
            title='Gutter Replacement in <span>Matthews, NC</span>',
            description=(
                'Undersized gutters overflow onto the fascia they hang from. '
                'Acme replaces them with correctly sized seamless systems.'
            ),
            bg_image='/images/locations/matthews/hero-gutter-replacement.webp',
            features=['Seamless Aluminum', 'Six-Inch K-Style', 'Free Written Estimate',
                      'Licensed and Insured'],
            buttons=[
                HeroButton('Get Your Free Estimate', '/contact/', 'btn-primary',
                           icon_after='fas fa-arrow-right'),
                HeroButton('(555) 555-0100', 'tel:5550100199', 'btn-ghost-white',
                           icon_before='fas fa-phone'),
            ],
        ),
        title='Gutter Replacement in Matthews, NC',
        last_updated='2026-07-21',
        sections=sections,
        faqs=[
            FaqItem('How much does gutter replacement cost in Matthews, NC?',
                    'Pricing depends on linear footage, profile and material, home height, '
                    'the fascia repair scope found during removal, and whether guards are '
                    'included. Acme provides free, fully itemized written estimates before '
                    'any work begins. Call (555) 555-0100.'),
            FaqItem('Should I upgrade to six-inch gutters in Matthews?',
                    'For most Matthews homes, yes. The original five-inch specification was '
                    'sized for smaller roof footprints, and a six-inch profile carries roughly '
                    'thirty percent more water over the same run.'),
            FaqItem('Does gutter replacement include fascia repair?',
                    'Only where the fascia is compromised. Acme documents any rot found '
                    'during removal with photographs and writes the additional scope before '
                    'proceeding, so nothing appears on the invoice unannounced.'),
        ],
        capsule=Capsule(
            interrogative_h2='What Size Gutters Do Matthews Homes Actually Need?',
            answer_first=_FIXTURE_ANSWER_FIRST,
            tldr='Six-inch K-style seamless aluminum with three-by-four-inch downspouts is '
                 'the correct default for Matthews homes; the original five-inch '
                 'specification was undersized for these roof footprints.',
        ),
        proprietary_variables=['neighborhoods'],
        fanout_queries=[
            'gutter replacement cost Matthews NC',
            'seamless vs sectional gutters',
            'six-inch vs five-inch gutter sizing',
            'downspout sizing',
            'fascia repair during gutter replacement',
            'gutter guards Matthews',
            'copper vs aluminum gutters',
        ],
        semantic_triples=[
            SemanticTriple('Acme Roofing', 'installs',
                           'seamless six-inch K-style aluminum gutters in Matthews, NC'),
            SemanticTriple('Acme Roofing', 'holds',
                           'GAF Master Elite certification, the top 2% of North American roofers'),
        ],
        intent='commercial',
        coverage_method='builder-collapse',
        source_ref='docs/intake-archive/2026-05-22/gutter.docx',
        related_links=[
            {'anchor': 'Gutter Repair Matthews',
             'target': '/charlotte-nc/matthews/gutter-repair/',
             'source_section': 'related-services', 'intent': 'sibling'},
        ],
        ledger=[{'block': 'gutter.docx#intro', 'verdict': 'KEEP'},
                {'block': 'gutter.docx#comparison', 'verdict': 'TRIM'}],
    )


def assert_balanced_ts(text: str) -> None:
    """String-aware brace/bracket/paren balance check over the emitted TS.

    Not a TypeScript parser — it is the cheap invariant that catches the failure
    mode a serialiser actually has: an unclosed collection or a quote that ate the
    rest of the file. Quoted regions are skipped so an apostrophe inside "…" or a
    brace inside a string cannot throw the count off.
    """
    stack: list[str] = []
    pairs = {')': '(', ']': '[', '}': '{'}
    quote: str | None = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'", '`'):
            quote = ch
        elif ch in '([{':
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack[-1] != pairs[ch]:
                raise AssertionError(f'unbalanced {ch!r} at offset {i}')
            stack.pop()
        i += 1
    if quote:
        raise AssertionError(f'unterminated {quote!r} string literal')
    if stack:
        raise AssertionError(f'unclosed {stack!r}')


def _validate_brief_via_gate(brief: dict) -> list[str]:
    """Run the REAL gate validator when importable; otherwise mirror its defaults.

    The mirror exists so the self-test still means something outside the package,
    but the gate's own function is preferred — the point of this check is that
    to_brief() satisfies the code that will actually judge it.
    """
    try:
        from pipeline.gates.brief_fanout_check import validate_brief  # type: ignore
        return validate_brief(brief, min_fanout=BRIEF_MIN_FANOUT,
                              intent_enum=list(BRIEF_INTENT_ENUM),
                              allowlist=set(), min_answer_words=8)
    except Exception:
        fails: list[str] = []
        fanout = brief.get('fanout')
        if not isinstance(fanout, list):
            fails.append('fanout: missing or not a list')
        elif len({f.strip().lower() for f in fanout if isinstance(f, str) and f.strip()}) < BRIEF_MIN_FANOUT:
            fails.append('fanout: too few distinct terms')
        capsule = brief.get('capsule')
        if not isinstance(capsule, dict):
            fails.append('capsule: missing')
        else:
            h2 = str(capsule.get('interrogative_h2') or '').strip()
            if not h2 or not h2.endswith('?'):
                fails.append('capsule.interrogative_h2: missing or not interrogative')
            if count_words(str(capsule.get('answer_first') or '')) < 8:
                fails.append('capsule.answer_first: missing or fragment')
            if not str(capsule.get('tldr') or '').strip():
                fails.append('capsule.tldr: missing')
        triples = brief.get('semantic_triples')
        if not isinstance(triples, list) or not any(
            isinstance(t, dict) and all(str(t.get(k) or '').strip()
                                        for k in ('subject', 'predicate', 'object'))
            for t in triples or []
        ):
            fails.append('semantic_triples: no well-formed triple')
        if not str(brief.get('proprietary_variable') or '').strip():
            fails.append('proprietary_variable: missing')
        if str(brief.get('intent') or '').strip().lower() not in BRIEF_INTENT_ENUM:
            fails.append('intent: missing or not in enum')
        return fails


def self_test(verbose: bool = False) -> list[str]:
    """Round-trip the fixture through both serialisers. Returns failure strings."""
    fails: list[str] = []
    draft = build_fixture()

    # --- severity model: a demotion must never make a page emittable ---------
    # This is the load-bearing safety property of the TRIAGE change. 'curate' is a
    # softer REPORT, never a softer GATE: a curated page is still never written.
    for code in sorted(CURATION_CODES):
        f = curate(code, 'probe')
        if not f.blocking:
            fails.append(f'severity: {code} demoted to curate is NOT blocking — a '
                         'curation hold must still refuse the write')
        if f.severity == 'warn':
            fails.append(f'severity: {code} landed on warn (emittable), not curate')
    for code in sorted(HARM_CODES):
        if code in CURATION_CODES:
            fails.append(f'severity: harm-class {code} was demoted to curate')
        if not block(code, 'probe').is_block:
            fails.append(f'severity: harm-class {code} is not BLOCK')
    # policy is idempotent and never promotes a block to something softer
    probes = [block('forbidden_phrase', 'x'), block('hero_rule', 'x'),
              warn('card_grid_count', 'x'), warn('core_words_out_of_band', 'x')]
    once = apply_severity_policy(probes)
    if [f.severity for f in once] != ['block', 'curate', 'warn', 'warn']:
        fails.append(f'severity: policy gave {[f.severity for f in once]}, expected '
                     "['block', 'curate', 'warn', 'warn'] — the 7-card grid and the "
                     'builder-collapse core band must stay WARN (Alex sign-off pending)')
    if [f.severity for f in apply_severity_policy(once)] != [f.severity for f in once]:
        fails.append('severity: apply_severity_policy is not idempotent')

    # --- MINOR-2: __str__ must render `detail` ------------------------------
    if 'CARD SEVEN' not in str(warn('card_grid_count', 'msg', detail='CARD SEVEN')):
        fails.append('finding __str__ drops `detail` — the discarded card titles are '
                     'computed and then thrown away')

    # --- B2: one allow-list check, shared with brief.py ---------------------
    allow = resolve_brief_allowlist({'brief': {'proprietary_variables': ['Neighborhoods']}})
    if allow != {'neighborhoods'}:
        fails.append(f'allow-list resolution: got {allow!r}')
    _, bad = check_proprietary_variable(['nonsense'], allow)
    if not bad or bad[0].code != 'proprietary_variable_not_in_allowlist' or not bad[0].is_block:
        fails.append('allow-list: an off-list proprietary variable was not BLOCKED')
    if check_proprietary_variable(['neighborhoods'], allow) != ('neighborhoods', []):
        fails.append('allow-list: an allow-listed variable was rejected')
    if check_proprietary_variable([], set())[1][0].code != 'proprietary_variable_missing':
        fails.append('allow-list: an undeclared variable with no allow-list was not blocked')

    # --- TS side ---------------------------------------------------------
    ts = to_ts_entry(draft)
    try:
        assert_balanced_ts(ts)
    except AssertionError as exc:
        fails.append(f'ts: {exc}')

    if not ts.startswith('export const matthewsGutterReplacement: ServicePage = {'):
        fails.append(f'ts: unexpected export header: {ts[:70]!r}')
    if not ts.rstrip().endswith('};'):
        fails.append('ts: entry does not terminate with "};"')
    if 'markdownContent' in ts:
        fails.append('ts: markdownContent emitted — forbidden_sweep source-mode reads this file raw')
    for needle in ("slug: 'charlotte-nc/matthews/gutter-replacement',",
                   "type: 'editorial-split',",
                   "certificationsSection('Matthews',",
                   'processSection()',
                   "className: 'btn-ghost-white'"):
        if needle not in ts:
            fails.append(f'ts: missing expected fragment {needle!r}')
    if ts.count('\n  slug:') != 1:
        fails.append('ts: slug key not emitted exactly once at depth 1')

    registry = to_registry_row(draft)
    if registry != '  matthewsGutterReplacement,\n':
        fails.append(f'registry: unexpected row {registry!r}')

    # quoting: a string with an apostrophe must not be single-quoted
    apostrophe = ts_string("the region's storm season")
    if not apostrophe.startswith('"'):
        fails.append(f'ts_string: apostrophe case not double-quoted: {apostrophe}')
    both = ts_string("""it's a "quote" """)
    if not both.startswith('`'):
        fails.append(f'ts_string: mixed-quote case not backticked: {both}')

    # --- brief side ------------------------------------------------------
    brief = to_brief(draft)
    for key in ('fanout', 'capsule', 'semantic_triples', 'proprietary_variable', 'intent'):
        if key not in brief:
            fails.append(f'brief: required key {key!r} absent (a missing field is a gate failure)')
    gate_fails = _validate_brief_via_gate(brief)
    if gate_fails:
        fails.extend(f'brief: {m}' for m in gate_fails)
    try:
        json.loads(to_brief_json(draft))
    except Exception as exc:
        fails.append(f'brief: not JSON-serialisable: {exc}')
    if brief_path(draft) != 'docs/briefs/charlotte-nc-matthews-gutter-replacement.json':
        fails.append(f'brief: unexpected path {brief_path(draft)}')

    # capsule is the same string in both artifacts
    if brief['capsule']['answer_first'] not in ts:
        fails.append('capsule: answer_first is not present verbatim in the TS lede')
    if brief['capsule']['interrogative_h2'] not in ts:
        fails.append('capsule: interrogative_h2 is not present verbatim as a section title')

    # --- structural findings --------------------------------------------
    core = recount_core_words(draft)
    if not (CORE_WORDS_MIN <= core <= CORE_WORDS_MAX):
        fails.append(f'fixture: core_words {core} outside [{CORE_WORDS_MIN}, {CORE_WORDS_MAX}]')
    findings = structural_findings(draft)
    blocking = [f for f in findings if f.blocking]
    if blocking:
        fails.extend(f'structural: {f}' for f in blocking)

    # negative control: a draft with no "new" type MUST be blocked (C28)
    stripped = replace(draft, sections=[s for s in draft.sections
                                        if not (isinstance(s, Section) and s.is_new_type)])
    if not any(f.code == 'transform_would_rewrite' for f in structural_findings(stripped)):
        fails.append('negative control: a page with no new-type section was not blocked')

    # negative control: an over-long hero MUST be blocked and marked auto-fixable
    fat = replace(draft, hero=replace(draft.hero, description=' '.join(['word'] * 40) + '.'))
    hero_finding = next((f for f in structural_findings(fat) if f.code == 'hero_rule'), None)
    if hero_finding is None or not hero_finding.auto_fixable:
        fails.append('negative control: over-long hero.description not blocked as auto-fixable')

    if verbose:
        print(ts)
        print(to_brief_json(draft))
        print(f'core_words = {core}')
        for f in findings:
            print(f'  {f}')
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description='Shared page model for the pass-3 emitter.')
    ap.add_argument('--self-test', action='store_true',
                    help='round-trip the fixture through to_ts_entry and to_brief')
    ap.add_argument('--print-fixture', action='store_true',
                    help='print the fixture TS entry, registry row, and brief JSON')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    if args.print_fixture:
        draft = build_fixture()
        sys.stdout.write(to_ts_entry(draft))
        sys.stdout.write(to_registry_row(draft))
        sys.stdout.write(to_brief_json(draft))
        return 0

    if not args.self_test:
        ap.print_help()
        return 2

    fails = self_test(verbose=args.verbose)
    if fails:
        print('FAIL: models.py self-test')
        for f in fails:
            print(f'  {f}')
        return 9
    draft = build_fixture()
    print(f'PASS: models.py self-test — TS entry balanced, brief valid per '
          f'brief_fanout_check, core_words={recount_core_words(draft)} in band '
          f'[{CORE_WORDS_MIN}, {CORE_WORDS_MAX}], 2 negative controls blocked.')
    return 0


if __name__ == '__main__':
    # Run as a plain script (`pipeline/generate/models.py --self-test`) rather than
    # `-m pipeline.generate.models`: the package __init__ re-exports this module, so
    # -m would execute the body twice under two names and the two copies of Section
    # would fail isinstance against each other. Bootstrapping the repo root here
    # keeps `from pipeline.gates...` resolvable with a single module identity.
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    sys.exit(main())
