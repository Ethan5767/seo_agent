"""pipeline.generate — pass 3 of the 3-pass intake design: the data-gen emitter.

The pipeline could already INTAKE content and GATE it (21 gates, all proven).
This package is the missing middle: it GENERATES. One messy team DOCX becomes
clean, typed page data in the client repo that passes those gates by
construction rather than by audit-after-the-fact.

    pass 1  EXTRACT   docx/md -> blocks (title, meta, URL, H1, hero para, sections)
    pass 2  CLASSIFY  blocks -> taxonomy class + core_body flag + verdict
                      (KEEP/TRIM/OPTIMIZE/DROP/BANK) -> the ledger
    pass 3  EMIT      <- HERE. constraint-validate -> auto-fix the mechanical ->
                      flag the judgment calls -> write TS entry + registry row +
                      docs/briefs/<slug>.json + proof file, atomically.

`models.py` is the shared vocabulary every module in this package imports:
the PageDraft dataclass family, the enums lifted verbatim from the client repo's
TS types, and the two serialisers — `to_ts_entry()` and `to_brief()`.

Design rules this package is built on, in priority order:

  1. The gates are proven and are NOT modified. The emitter satisfies them; never
     the reverse. Every constant here is READ from real gate code or real client
     TS, never invented.
  2. The schema is the client repo's. `ServicePage` / `ServiceSection` are
     authoritative in acme-roofing-site/src/data/services.ts. A Section carries an
     ordered `props` dict keyed by real TS field names so services.ts stays the
     single source of truth.
  3. Refuse over guess, on THREE severities. A constraint whose violation would
     ship HARM (forbidden/legal phrase, S21 duplicate, out-of-topology URL,
     out-of-allow-list proprietary variable, structural/TS corruption) is a
     'block' ValidationFinding: refused, exit 9, never auto-fixed, never waivable.
     A constraint needing a human QUALITY decision (a hero that cannot be reduced
     mechanically, an over-length metaTitle, missing alt text, a missing capsule
     node) is 'curate': that page is HELD OUT of the cycle - it does not ship -
     but it does not stop any other page emitting, and it lands in
     docs/briefs/_curation.md with the offending text and a concrete proposed fix.
     A constraint worth the operator's attention but safe to ship (card-grid count,
     core-body band under builder-collapse, keyword frequency) is a 'warn' that
     reaches the ledger (exit 1) and is NEVER auto-fixed.
  4. Atomic and append-only. The TS entry and its `allLocationPages` registry row
     are one write — an entry without its row is exactly the orphan bug
     orphan_check.py exists to catch.

Exit codes used across the package (authoritative; docs/gate-reference.md and
SPEC-emitter.md §7 mirror this table):
    0  emitted clean
    1  emitted with curation flags for review. EVERYTHING SHIPPED - the warn
       flags ride along in the ledger and nothing was withheld.
    2  usage / dependency error
    9  refused to emit (a blocking finding, or an invalid brief). Also returned by
       every module's --self-test on failure.
   15  one or more pages HELD for curation. The emitter emitted what it could;
       the held pages did NOT ship. NOT green - each needs one human yes/no, and
       lands in docs/briefs/_curation.md with a concrete proposed fix.

Each outcome owns a DISTINCT code on purpose. An orchestrator branching on exit
status alone must be able to separate "shipped with flags" (1) from "did not
ship" (15) from "refused" (9); 1 previously meant both of the first two, which
is the same defect class as the retired 3-vs-9 refusal collision. Codes 1-10 are
the gate registry's and 11-14 are pipeline/audit/preflight.py's, so 15 is the
first free code in the fleet. Most severe wins: 9 > 15 > 1 > 0.
"""
from __future__ import annotations

from pipeline.generate.models import (
    # --- enums / constants lifted from the client repo and the gates ---------
    ANSWER_FIRST_MAX_SENTENCES,
    ANSWER_FIRST_MAX_WORDS,
    ANSWER_FIRST_MIN_WORDS,
    BRIEF_INTENT_ENUM,
    BRIEF_MIN_FANOUT,
    CORE_BODY_FIELDS,
    CORE_WORDS_MAX,
    CORE_WORDS_MIN,
    CORE_WORDS_SWEET_SPOT,
    CREDENTIALS_LABEL_RE,
    DECORATIVE_IMAGE_FIELDS,
    FINANCING_LABEL_RE,
    FORM_INJECTING_SLUG_WORDS,
    HERO_BUTTON_CLASSNAMES,
    HERO_MAX_CHARS,
    HERO_MAX_SENTENCES,
    HERO_MAX_WORDS,
    KNOWN_METRO_HUBS,
    META_TITLE_MAX_EFFECTIVE,
    MOSAIC_SIZES,
    NEW_SECTION_TYPES,
    PAGE_KINDS,
    ROUTE_ARRAY_BY_SEGMENTS,
    SECTION_TYPES,
    SEGMENTS_BY_KIND,
    SHARED_BUILDERS,
    SUBSERVICE_SUFFIX_RE,
    TIER1_ALT_FIELDS,
    TIER2_ALT_FIELDS,
    TIER3_TITLE_IS_ALT,
    VALID_CARD_GRID_COUNTS,
    # --- dataclasses ---------------------------------------------------------
    BuilderCall,
    Capsule,
    FaqItem,
    Hero,
    HeroButton,
    PageDraft,
    RawExpr,
    Section,
    SemanticTriple,
    ValidationFinding,
    # --- serialisers ---------------------------------------------------------
    brief_path,
    to_brief,
    to_brief_json,
    to_registry_row,
    to_ts_entry,
    to_ts_object_literal,
    ts_string,
    # --- shared helpers so every module counts the same way -------------------
    assert_balanced_ts,
    block,
    build_fixture,
    core_body_strings,
    count_sentences,
    count_words,
    derive_export_name,
    effective_len,
    recount_core_words,
    strip_tags,
    apply_severity_policy,
    check_proprietary_variable,
    resolve_brief_allowlist,
    structural_findings,
    warn,
)

__all__ = [
    'ANSWER_FIRST_MAX_SENTENCES',
    'ANSWER_FIRST_MAX_WORDS',
    'ANSWER_FIRST_MIN_WORDS',
    'BRIEF_INTENT_ENUM',
    'BRIEF_MIN_FANOUT',
    'CORE_BODY_FIELDS',
    'CORE_WORDS_MAX',
    'CORE_WORDS_MIN',
    'CORE_WORDS_SWEET_SPOT',
    'CREDENTIALS_LABEL_RE',
    'DECORATIVE_IMAGE_FIELDS',
    'FINANCING_LABEL_RE',
    'FORM_INJECTING_SLUG_WORDS',
    'HERO_BUTTON_CLASSNAMES',
    'HERO_MAX_CHARS',
    'HERO_MAX_SENTENCES',
    'HERO_MAX_WORDS',
    'KNOWN_METRO_HUBS',
    'META_TITLE_MAX_EFFECTIVE',
    'MOSAIC_SIZES',
    'NEW_SECTION_TYPES',
    'PAGE_KINDS',
    'ROUTE_ARRAY_BY_SEGMENTS',
    'SECTION_TYPES',
    'SEGMENTS_BY_KIND',
    'SHARED_BUILDERS',
    'SUBSERVICE_SUFFIX_RE',
    'TIER1_ALT_FIELDS',
    'TIER2_ALT_FIELDS',
    'TIER3_TITLE_IS_ALT',
    'VALID_CARD_GRID_COUNTS',
    'BuilderCall',
    'Capsule',
    'FaqItem',
    'Hero',
    'HeroButton',
    'PageDraft',
    'RawExpr',
    'Section',
    'SemanticTriple',
    'ValidationFinding',
    'brief_path',
    'to_brief',
    'to_brief_json',
    'to_registry_row',
    'to_ts_entry',
    'to_ts_object_literal',
    'ts_string',
    'assert_balanced_ts',
    'block',
    'build_fixture',
    'core_body_strings',
    'count_sentences',
    'count_words',
    'derive_export_name',
    'effective_len',
    'recount_core_words',
    'strip_tags',
    'apply_severity_policy',
    'check_proprietary_variable',
    'resolve_brief_allowlist',
    'structural_findings',
    'warn',
]
