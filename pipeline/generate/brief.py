#!/usr/bin/env python3
"""brief.py — emit `docs/briefs/<slug>.json`, the §19 artifact the pipeline has
never produced.

WHY THIS MODULE EXISTS
======================
`pipeline/gates/brief_fanout_check.py` (S19) is the pre-DRAFT producibility gate:
every page must start life as a machine-checkable *brief*, so the expensive
content gates (capsule §20, non-commodity §21) become producible-by-default
instead of audited-after. The gate has been shipped and correct for months and
has never once had input — `docs/briefs/` is emitter-produced, so the gate finds
zero files and exits 0 with a NOTE, forever. This module closes that loop.

    pass 1  EXTRACT   docx -> blocks
    pass 2  CLASSIFY  blocks -> taxonomy + verdict -> ledger
    pass 3  EMIT      TS entry + registry row + >>> docs/briefs/<slug>.json <<<
                                                    ^ this module

WHAT IT DOES NOT DO
-------------------
It does not write prose. A brief is a *contract*, not content: the capsule
strings (interrogative H2, answer-first block, TL;DR) are authored upstream and
carried on the PageDraft, because those exact strings must also be the
`editorial-split` title/lede in the TS entry (C1/C2 — one string, two gates). If
a draft reaches this module without a capsule, that is a BLOCKING finding, not
something to invent. Same for every number: anti-invention (C27) applies to the
brief as much as to the page.

WHAT IT DERIVES (and from what)
-------------------------------
  fanout               DERIVED when the draft is thin. S19 doctrine: engines
                       decompose a question into sub-queries before answering, so
                       the brief must target that decomposition, not the head
                       term. Built from the page's own service + city + state +
                       resolved intent, then unioned with the CLIENT CONFIG's
                       real `seed_queries` / `target_keywords` scoped to this
                       page's city. Nothing is pulled out of the air; every term
                       is a recombination of the page's identity and the client's
                       own configured query set.
  semantic_triples     DERIVED only from config-verifiable facts (legal_name,
                       certifications, states/cities actually served). The city
                       must be GROUNDED in the client's configured geography or
                       the derivation refuses (block) rather than asserting an
                       entity claim about a market the client never declared.
  intent               DERIVED from the page class + slug when blank. An intent
                       that is present but NOT in the enum is a BLOCK: the draft
                       asserted something wrong and silently rewriting it would
                       hide the upstream bug.
  proprietary_variable NEVER fabricated. See the policy block below.

PROPRIETARY-VARIABLE POLICY (the §21 moat, declared up front)
-------------------------------------------------------------
The gate resolves its allow-list from, in order: `brief.proprietary_variables`,
`brief.proprietary_variable_allowlist`, top-level `proprietary_variables`, or
`--allowlist`. This module resolves it IDENTICALLY (it calls the gate's own
`load_cfg`), then:

  * draft declares one AND an allow-list exists -> use the first declared value
    that is a member. If NONE of the declared values is a member -> BLOCK. The
    gate would fail it anyway; failing here means it never reaches the repo.
  * draft declares one AND no allow-list exists -> use it (the gate WARNs and
    skips membership). Warn if it is not evidenced anywhere in the page text.
  * draft declares none AND an allow-list exists -> BLOCK. The allow-list entries
    are variable NAMES ('neighborhoods', 'crew_size'); picking one the draft did
    not declare would be guessing which moat the page actually carries.
  * draft declares none AND no allow-list exists (Acme today) -> fall back to
    the §21 allow-list built by `noncommodity_check.build_allow_list(cfg)` from
    the client's own `required_phrases` + entity fields, and take the first token
    that ACTUALLY APPEARS in the projected page text. If no config-grounded token
    appears in the page -> BLOCK. A page with no proprietary token is exactly
    what §21 exists to catch; emitting a plausible-looking value would launder a
    commodity page past two gates at once.

In every branch the rule is the same: a value that is not both config-grounded
and page-evidenced is a blocking finding, never a bogus string.

CROSS-GATE DIVERGENCE (deliberate, do not "fix" either gate)
------------------------------------------------------------
S19 accepts `capsule.answer_first` at >= 8 words. `capsule_check` (S20) requires
the rendered answer block to be 40-80 words and <= 3 sentences. A brief that
passes S19 at 8 words yields a page that fails S20 at build. This module
validates against the STRICTER rule and warns (exit 1) when a capsule is S19-legal
but S20-doomed, so the divergence surfaces at brief time rather than at build.

VALIDATION AUTHORITY
--------------------
Every emitted brief is validated by importing and calling the REAL gate's
`validate_brief()` with the REAL resolved config, before the file is written. This
module never reimplements the gate's rules; if the gate changes, this follows.

INPUT
-----
`drafts.json`: one serialised PageDraft object, a list of them, or
`{"drafts": [...]}`. Only the brief-relevant fields are required; the loader is
tolerant of a partial draft because a missing field must become a REPORTED
finding, not a KeyError (same posture as the gate).

Exit codes:
    0  every brief emitted clean
    1  emitted, with curation flags for the operator's ledger (S20-divergent capsule,
       thin-but-legal fanout, unevidenced proprietary variable, ...)
    2  usage / dependency error
    9  refused to emit one or more briefs (a blocking finding, or a brief that
       the real gate rejects)

Usage:
    pipeline/generate/brief.py drafts.json --project PROJECT_DIR --out-dir docs/briefs
    pipeline/generate/brief.py drafts.json --project PROJECT_DIR --dry-run
    pipeline/generate/brief.py --self-test --project PROJECT_DIR
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in (None, ''):
    # Run as a plain script (`pipeline/generate/brief.py ...`) rather than
    # `-m pipeline.generate.brief`: the package __init__ re-exports models, so -m
    # would load models twice under two names and isinstance checks across the two
    # copies of Section/BuilderCall would fail. Bootstrap the repo root so the
    # absolute `pipeline.*` imports below resolve to a single module identity.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.generate.models import (  # noqa: E402
    ANSWER_FIRST_MAX_SENTENCES,
    ANSWER_FIRST_MAX_WORDS,
    ANSWER_FIRST_MIN_WORDS,
    BRIEF_INTENT_ENUM,
    BRIEF_MIN_FANOUT,
    BuilderCall,
    Capsule,
    FaqItem,
    Hero,
    HeroButton,
    PageDraft,
    Section,
    SemanticTriple,
    ValidationFinding,
    block,
    brief_path,
    check_proprietary_variable,
    count_sentences,
    count_words,
    resolve_brief_allowlist,
    strip_tags,
    to_brief,
    to_ts_entry,
    warn,
)

# The gate is the authority for schema + config resolution. Imported, never copied.
from pipeline.gates import brief_fanout_check as s19  # noqa: E402
from pipeline.gates import noncommodity_check as s21  # noqa: E402

DEFAULT_MAX_FANOUT = 12

# Intent classification (used ONLY when draft.intent is blank). Ordered: first
# match wins, most specific first. Keyed on the slug + service + page kind, all
# of which are the page's own identity, not a guess about its content.
_TRANSACTIONAL_RE = re.compile(r'\b(emergency|claims?|quote|estimate|financing|24[- ]?7)\b', re.I)
_INFORMATIONAL_RE = re.compile(r'\b(guide|cost|inspection|checklist|vs|how|what|why|faq)\b', re.I)

# Fan-out templates by intent. `{s}` service phrase, `{city}`, `{st}`, `{geo}`,
# `{trade}`, `{cert}`, `{brand}`. Every template is a real sub-intent an engine
# decomposes a local-service question into; none invent a fact.
_FANOUT_TEMPLATES: dict[str, tuple[str, ...]] = {
    'commercial': (
        '{s} {geo}',
        'best {s} companies {city} {st}',
        'licensed {trade} {city} {st}',
        '{cert} contractor {city}',
        '{s} cost {city} {st}',
        'how long does {s} take {city}',
        '{s} warranty options',
        'free {s} estimate {city}',
        '{s} near me {city} {st}',
        '{trade} reviews {city} {st}',
    ),
    'transactional': (
        'emergency {s} {city} {st}',
        'same day {s} {city}',
        '{s} quote {city} {st}',
        '24 hour {trade} {city}',
        '{s} financing {city}',
        'call {trade} {city} {st}',
        'free {s} estimate {city}',
        '{s} insurance claim {city}',
    ),
    'informational': (
        'what is {s}',
        'how does {s} work',
        'signs you need {s} {city}',
        '{s} materials compared',
        'how long does {s} last {city} {st}',
        '{s} cost factors {city}',
        '{s} permit requirements {city}',
        'diy vs professional {s}',
    ),
    'navigational': (
        '{brand} {city}',
        '{brand} {city} {st}',
        '{brand} phone number',
        '{brand} reviews',
        '{brand} service area',
        '{brand} {s}',
        '{trade} {city} {st}',
        '{brand} hours',
    ),
}


# ---------------------------------------------------------------------------
# drafts.json -> PageDraft
# ---------------------------------------------------------------------------

def _as_str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ''


def _hero_from(data: Any) -> Hero:
    """Tolerant. The hero is irrelevant to the brief but PageDraft requires one;
    a missing hero must not crash brief generation for an otherwise valid draft
    (the hero gates are a sibling module's job, not this one's)."""
    d = data if isinstance(data, dict) else {}
    buttons = []
    for b in d.get('buttons') or []:
        if isinstance(b, dict):
            buttons.append(HeroButton(
                text=_as_str(b.get('text')), url=_as_str(b.get('url')),
                class_name=_as_str(b.get('class_name') or b.get('className')) or 'btn-primary',
                icon_before=b.get('icon_before') or b.get('iconBefore'),
                icon_after=b.get('icon_after') or b.get('iconAfter'),
            ))
    return Hero(
        badge_icon=_as_str(d.get('badge_icon') or d.get('badgeIcon')),
        badge_text=_as_str(d.get('badge_text') or d.get('badgeText')),
        title=_as_str(d.get('title')),
        description=_as_str(d.get('description')),
        bg_image=d.get('bg_image') or d.get('bgImage'),
        buttons=buttons,
        features=[str(f) for f in (d.get('features') or []) if str(f).strip()],
    )


def _sections_from(items: Any) -> list[Section | BuilderCall]:
    out: list[Section | BuilderCall] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        if 'name' in it and 'type' not in it:            # BuilderCall
            out.append(BuilderCall(name=_as_str(it.get('name')), args=list(it.get('args') or [])))
            continue
        props = it.get('props')
        if not isinstance(props, dict):
            props = {k: v for k, v in it.items()
                     if k not in {'type', 'core_body', 'source_ref', 'verdict'}}
        out.append(Section(
            type=_as_str(it.get('type')), props=dict(props),
            core_body=bool(it.get('core_body')),
            source_ref=it.get('source_ref'), verdict=it.get('verdict'),
        ))
    return out


def draft_from_dict(data: dict[str, Any]) -> PageDraft:
    """Deserialise one PageDraft. Field names are the dataclass's own (snake_case).

    Deliberately tolerant: a partial draft must produce a REPORTED finding, not a
    KeyError, so the operator sees every problem in one run.
    """
    cap = data.get('capsule') if isinstance(data.get('capsule'), dict) else {}
    triples = []
    for t in data.get('semantic_triples') or []:
        if isinstance(t, dict):
            triples.append(SemanticTriple(_as_str(t.get('subject')), _as_str(t.get('predicate')),
                                          _as_str(t.get('object'))))
        elif isinstance(t, (list, tuple)) and len(t) == 3:
            triples.append(SemanticTriple(*[_as_str(x) if isinstance(x, str) else str(x) for x in t]))
    return PageDraft(
        url_path=_as_str(data.get('url_path')),
        page_kind=_as_str(data.get('page_kind')),
        city=_as_str(data.get('city')),
        state=_as_str(data.get('state')),
        service=_as_str(data.get('service')),
        h1=_as_str(data.get('h1')),
        meta_title=_as_str(data.get('meta_title')),
        meta_description=_as_str(data.get('meta_description')),
        hero=_hero_from(data.get('hero')),
        title=_as_str(data.get('title')),
        export_name=_as_str(data.get('export_name')),
        last_updated=_as_str(data.get('last_updated')),
        sections=_sections_from(data.get('sections')),
        faqs=[FaqItem(_as_str(f.get('question')), _as_str(f.get('answer')))
              for f in (data.get('faqs') or []) if isinstance(f, dict)],
        capsule=Capsule(
            interrogative_h2=_as_str(cap.get('interrogative_h2')),
            answer_first=_as_str(cap.get('answer_first')),
            tldr=_as_str(cap.get('tldr')),
        ),
        proprietary_variables=[str(p).strip() for p in (data.get('proprietary_variables') or [])
                               if str(p).strip()],
        fanout_queries=[str(q).strip() for q in (data.get('fanout_queries') or []) if str(q).strip()],
        semantic_triples=triples,
        intent=_as_str(data.get('intent')),
        core_body_words=int(data.get('core_body_words') or 0),
        source_ref=_as_str(data.get('source_ref')),
        coverage_method=_as_str(data.get('coverage_method')),
        related_links=[d for d in (data.get('related_links') or []) if isinstance(d, dict)],
        ledger=[d for d in (data.get('ledger') or []) if isinstance(d, dict)],
    )


def load_drafts(path: str) -> list[PageDraft]:
    """Accept one object, a list, or {"drafts": [...]}."""
    raw = json.loads(Path(path).read_text(encoding='utf-8', errors='replace'))
    if isinstance(raw, dict) and isinstance(raw.get('drafts'), list):
        raw = raw['drafts']
    items = raw if isinstance(raw, list) else [raw]
    out: list[PageDraft] = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f'drafts[{i}] is not an object')
        out.append(draft_from_dict(item))
    return out


# ---------------------------------------------------------------------------
# Config-grounded vocabularies
# ---------------------------------------------------------------------------

def _state_scoped(cfg: dict, *keys: str) -> list[Any]:
    """A config value under BOTH client schemas: the flat top-level block four
    clients use, PLUS the per-state nesting Crestline's multi-state states[] schema
    uses (target_keywords / target_cities / primary_metro live INSIDE each state
    entry there — `cfg.get('target_keywords')` is empty on Crestline, so reading
    only the top level silently ran briefs with no keyword pool: BUG-016's class,
    schema variance across clients). States with `seo_round_1: false` are
    excluded — their keywords are documented, not in active SEO scope."""
    vals: list[Any] = [cfg.get(k) for k in keys]
    for st in (cfg.get('states') or []):
        if isinstance(st, dict) and st.get('seo_round_1') is not False:
            vals += [st.get(k) for k in keys]
    return vals


def _flat_strings(value: Any) -> list[str]:
    """Flatten a config value to its non-empty strings (lists, dicts, scalars)."""
    out: list[str] = []
    if isinstance(value, str):
        if value.strip():
            out.append(value.strip())
    elif isinstance(value, dict):
        for v in value.values():
            out += _flat_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out += _flat_strings(v)
    return out


def grounded_geography(cfg: dict) -> set[str]:
    """Lowercased place tokens the CLIENT has actually declared it serves.

    Union of service_areas, service_area.cities + expansion_cities + primary_city,
    primary_metro, states_served, nap.address, and every target keyword (which is
    where the long tail of real spoke cities lives). A city outside this set means
    the page asserts a market the config never claimed — a triple about it would
    be an invented entity claim, so the derivation refuses instead.
    """
    tokens: list[str] = []
    tokens += _flat_strings(cfg.get('service_areas'))
    sa = cfg.get('service_area') or {}
    tokens += _flat_strings(sa.get('primary_city'))
    tokens += _flat_strings(sa.get('cities'))
    tokens += _flat_strings(sa.get('expansion_cities'))
    tokens += _flat_strings(cfg.get('primary_metro'))
    tokens += _flat_strings(cfg.get('states_served'))
    tokens += _flat_strings((cfg.get('nap') or {}).get('address'))
    tokens += _flat_strings((cfg.get('geo') or {}).get('city_label'))
    tokens += _flat_strings(_state_scoped(cfg, 'target_keywords',
                                          'target_cities', 'primary_metro'))
    return {t.lower() for t in tokens if t}


def is_grounded_city(city: str, geo_tokens: set[str]) -> bool:
    c = city.strip().lower()
    if not c:
        return False
    return any(c == t or c in t.split() or c in t for t in geo_tokens)


def client_brand(cfg: dict) -> str:
    biz = cfg.get('business') or {}
    nap = cfg.get('nap') or {}
    return (_as_str(biz.get('legal_name')) or _as_str(nap.get('name'))
            or _as_str(cfg.get('client_name')) or '')


def client_trade(cfg: dict) -> str:
    biz = cfg.get('business') or {}
    return (_as_str(biz.get('trade')) or _as_str(cfg.get('vertical'))
            or _as_str(cfg.get('industry')) or '')


def client_certification(cfg: dict) -> str:
    """First configured certification, verbatim (used as a triple object, so it must
    stay exactly as the client declared it)."""
    certs = _flat_strings((cfg.get('trust_signals') or {}).get('certifications'))
    return certs[0] if certs else ''


def _cert_query_form(cert: str) -> str:
    """The certification as it belongs in a QUERY, not in a claim.

    Acme's configured credential is 'GAF Master Elite Contractor'; the template
    '{cert} contractor {city}' would emit 'GAF Master Elite Contractor contractor
    Charlotte'. Strip a trailing role noun so the fan-out term reads like a real
    search, while `client_certification()` keeps the verbatim string for triples.
    """
    return re.sub(r'\s+(contractor|roofer|installer|company)s?\s*$', '', cert, flags=re.I).strip()


def page_text(draft: PageDraft) -> str:
    """The projected page text, taken from the SAME serialiser that writes the TS
    entry — so 'evidenced in the page' means evidenced in what actually ships,
    not in some parallel reconstruction that could drift."""
    try:
        return strip_tags(to_ts_entry(draft))
    except Exception:
        parts = [draft.h1, draft.meta_title, draft.meta_description, draft.title,
                 draft.hero.title, draft.hero.description, *draft.hero.features]
        for s in draft.real_sections():
            parts += _flat_strings(s.props)
        for f in draft.faqs:
            parts += [f.question, f.answer]
        parts += [draft.capsule.interrogative_h2, draft.capsule.answer_first, draft.capsule.tldr]
        return strip_tags(' '.join(p for p in parts if p))


# ---------------------------------------------------------------------------
# Derivations
# ---------------------------------------------------------------------------

def resolve_intent(draft: PageDraft, intent_enum: list[str]) -> tuple[str, list[ValidationFinding]]:
    """Blank -> derive from the page's own class + slug. Present-but-invalid ->
    BLOCK: the draft asserted something the enum does not contain, and quietly
    rewriting it would hide whatever upstream produced it."""
    allowed = {i.strip().lower() for i in intent_enum if str(i).strip()}
    declared = draft.intent.strip().lower()
    if declared:
        if declared in allowed:
            return declared, []
        return '', [block('intent_invalid',
                          f'intent {draft.intent!r} is not in the configured enum '
                          f'{sorted(allowed)}; refusing to silently rewrite an asserted value',
                          field_path='intent')]

    haystack = f'{draft.slug} {draft.service}'
    if _TRANSACTIONAL_RE.search(haystack):
        guess = 'transactional'
    elif _INFORMATIONAL_RE.search(haystack):
        guess = 'informational'
    else:
        guess = 'commercial'
    if guess not in allowed:
        guess = sorted(allowed)[0] if allowed else ''
    if not guess:
        return '', [block('intent_underivable',
                          'intent is blank and the configured intent_enum is empty',
                          field_path='intent')]
    return guess, [warn('intent_derived',
                        f'intent was blank; derived {guess!r} from page_kind/slug. Declare it '
                        'upstream if the page targets a different stage.', field_path='intent')]


def _config_seed_queries(cfg: dict, draft: PageDraft) -> list[str]:
    """Client-configured seed queries / target keywords, scoped to this page's city.

    These are the client's OWN query set (config `seed_queries`, `target_keywords`),
    so scoping them to the page's city is recombination, not invention.
    """
    service_words = {w for w in re.split(r'\W+', draft.service.lower()) if len(w) > 3}
    out: list[str] = []
    city = draft.city.strip()
    for seed in _flat_strings(cfg.get('seed_queries')):
        s_low = seed.lower()
        if not service_words or any(w in s_low for w in service_words):
            out.append(f'{seed} {city}'.strip())
    for kw in _flat_strings(_state_scoped(cfg, 'target_keywords')):
        if city and city.lower() in kw.lower():
            out.append(kw)
    return out


def derive_fanout(draft: PageDraft, cfg: dict, intent: str, *,
                  min_fanout: int, max_fanout: int) -> tuple[list[str], list[ValidationFinding]]:
    """S19 doctrine: an engine decomposes a question into sub-queries before it
    answers, so the brief must target that decomposition rather than the head term.

    Draft-declared terms always come first and are never dropped. Derived terms
    top up to `min_fanout` from the page's own service + city + state + intent,
    then from the client's configured seed queries scoped to this city.
    """
    findings: list[ValidationFinding] = []
    seen: set[str] = set()
    ordered: list[str] = []

    def add(term: str) -> None:
        t = ' '.join(str(term).split())
        if not t:
            return
        key = t.strip().lower()          # _distinct_ci semantics, verbatim
        if key in seen:
            return
        seen.add(key)
        ordered.append(t)

    for q in draft.fanout_queries:
        add(q)
    declared = len(ordered)

    trade = client_trade(cfg) or draft.service or 'contractor'
    service = draft.service or trade
    fields = {
        's': service,
        'trade': trade,
        'city': draft.city,
        'st': draft.state,
        'geo': f'{draft.city} {draft.state}'.strip(),
        'cert': _cert_query_form(client_certification(cfg)) or trade,
        'brand': client_brand(cfg) or trade,
    }
    templates = _FANOUT_TEMPLATES.get(intent, _FANOUT_TEMPLATES['commercial'])

    if len(ordered) < min_fanout:
        for tpl in templates:
            if len(ordered) >= min_fanout:
                break
            try:
                add(tpl.format(**fields))
            except (KeyError, IndexError):
                continue
    if len(ordered) < min_fanout:
        for seed in _config_seed_queries(cfg, draft):
            if len(ordered) >= min_fanout:
                break
            add(seed)

    if len(ordered) > max_fanout:
        ordered = ordered[:max_fanout]

    if len(ordered) < min_fanout:
        findings.append(block(
            'fanout_underivable',
            f'only {len(ordered)} distinct fanout term(s), need >= {min_fanout}; the page '
            f'declares service={draft.service!r} city={draft.city!r} and the client config '
            'supplied no usable seed queries. Declare sub-intents upstream.',
            field_path='fanout'))
    elif declared == 0:
        findings.append(warn(
            'fanout_fully_derived',
            f'all {len(ordered)} fanout terms were derived from service+city+intent and the '
            'client config; the dossier declared none. Review that they match the real '
            'sub-intents in the source material.', field_path='fanout'))
    elif declared < min_fanout:
        findings.append(warn(
            'fanout_topped_up',
            f'{declared} declared term(s) topped up to {len(ordered)} by derivation.',
            field_path='fanout'))
    return ordered, findings


def derive_triples(draft: PageDraft, cfg: dict,
                   geo_tokens: set[str]) -> tuple[list[SemanticTriple], list[ValidationFinding]]:
    """>=1 well-formed triple. Draft-declared wins. A derived triple is built ONLY
    from config-verifiable facts, and only when the page's city is grounded in the
    client's declared geography (C9/C27)."""
    declared = [t for t in draft.semantic_triples
                if t.subject.strip() and t.predicate.strip() and t.object.strip()]
    if declared:
        return declared, []

    brand = client_brand(cfg)
    if not brand:
        return [], [block('triple_underivable',
                          'no declared semantic_triples and the client config has no '
                          'business.legal_name / nap.name to use as the entity subject',
                          field_path='semantic_triples')]
    if not is_grounded_city(draft.city, geo_tokens):
        return [], [block('triple_ungrounded_geo',
                          f'no declared semantic_triples and city {draft.city!r} is not in the '
                          "client's configured geography (service_areas / service_area.cities / "
                          'target_keywords); refusing to assert an entity claim about an '
                          'undeclared market', field_path='semantic_triples')]
    service = draft.service or client_trade(cfg)
    if not service:
        return [], [block('triple_underivable',
                          'no declared semantic_triples and the draft declares no service and '
                          'the config no business.trade', field_path='semantic_triples')]
    loc = ', '.join(p for p in (draft.city, draft.state) if p)
    triples = [SemanticTriple(subject=brand, predicate='provides',
                              object=f'{service} in {loc}'.strip())]
    cert = client_certification(cfg)
    if cert:
        triples.append(SemanticTriple(subject=brand, predicate='is certified as', object=cert))
    return triples, [warn('triples_derived',
                          'semantic_triples were derived from config-verified facts '
                          '(legal_name + declared service + certification); the dossier declared '
                          'none. Prefer a page-specific claim from the source material.',
                          field_path='semantic_triples')]


def _is_geographic_token(token: str, draft: PageDraft, cfg: dict) -> bool:
    """True when a §21 token is nothing but a place name.

    `build_allow_list()` folds service_areas, service_area.cities and primary_metro
    into the §21 list, so a page's own city AND its parent metro are members. Neither
    is a moat: every sibling in the metro carries them, which is exactly the
    duplicate-of-sibling shape §21 also polices. Matching only against `draft.city`
    is not enough — on `/charlotte-nc/nowheresville/` the token 'Charlotte' is not
    the page's city but is still pure geography.
    """
    t = token.strip().lower()
    if not t:
        return True
    places = {draft.city.strip().lower(), draft.state.strip().lower(),
              f'{draft.city} {draft.state}'.strip().lower()}
    places |= {p.strip().lower() for p in _flat_strings(cfg.get('service_areas'))}
    sa = cfg.get('service_area') or {}
    places |= {p.strip().lower() for p in _flat_strings(sa.get('primary_city'))}
    places |= {p.strip().lower() for p in _flat_strings(sa.get('cities'))}
    places |= {p.strip().lower() for p in _flat_strings(sa.get('expansion_cities'))}
    places |= {p.strip().lower() for p in _flat_strings(cfg.get('primary_metro'))}
    places |= {p.strip().lower() for p in _flat_strings(cfg.get('states_served'))}
    places.discard('')
    # exact match, or the token is a bare place with a state suffix ('Charlotte, NC')
    bare = re.sub(r'[,\s]+(?:[A-Z]{2})$', '', token.strip(), flags=0).strip().lower()
    return t in places or bare in places


def resolve_proprietary_variable(draft: PageDraft, cfg: dict, allowlist: set[str],
                                 text: str) -> tuple[str, list[ValidationFinding]]:
    """The §21 moat, declared up front. See the module docstring for the full
    policy. Every branch that cannot produce a config-grounded, page-evidenced
    value returns a BLOCK — never a plausible-looking string."""
    declared = [p for p in draft.proprietary_variables if p.strip()]
    low = text.lower()

    # C10 membership is answered by ONE shared function (models.check_proprietary_variable)
    # so this module and emit_ts.py can never disagree again — that divergence let
    # emit_ts write a brief that brief_fanout_check then rejected with exit 9 (B2).
    if declared or allowlist:
        pv, findings = check_proprietary_variable(declared, allowlist)
        if findings:
            return '', findings
        if not allowlist and pv.lower() not in low:
            return pv, [warn('proprietary_variable_unevidenced',
                             f'{pv!r} is declared but does not appear in the projected page '
                             'text; §21 checks the PAGE, not the brief. Confirm the moat is '
                             'actually on the page.', field_path='proprietary_variable')]
        return pv, []

    # No allow-list AND nothing declared (Acme today). Fall back to the §21 list the non-commodity
    # gate itself builds from required_phrases + client entity fields, and take
    # the first token that is genuinely ON the page.
    try:
        tokens = s21.build_allow_list(cfg)
    except Exception:
        tokens = []
    # Prefer a NON-geographic token. build_allow_list() folds the client's service
    # areas and primary metro into the §21 list, so the page's own city name is a
    # member and would otherwise be picked first — but "Charlotte" on a Charlotte
    # page is not a moat, it is the slug. Every sibling page carries it, which is
    # exactly the duplicate-of-sibling shape §21 also polices.
    hits = [tok for tok, rx in s21.compile_token_matchers(tokens) if rx.search(text)]
    distinctive = [t for t in hits if not _is_geographic_token(t, draft, cfg)]
    if distinctive:
        tok = distinctive[0]
        return tok, [warn('proprietary_variable_derived',
                          f'no allow-list configured and none declared; used {tok!r}, a '
                          'config required_phrase/entity token that is evidenced in the page '
                          'text. Seed brief.proprietary_variables in client-config.yml to '
                          'turn the gate check from WARN into enforcement.',
                          field_path='proprietary_variable')]
    if hits:
        tok = hits[0]
        return tok, [warn('proprietary_variable_geographic_only',
                          f'the only §21 token evidenced on this page is {tok!r}, which is the '
                          "page's own geography. That is a weak moat: every sibling page in the "
                          'metro carries it, so it does not distinguish this page. Add a '
                          'page-unique fact (neighborhood, street, project count) to the core '
                          'body before this reaches §21.', field_path='proprietary_variable')]

    return '', [block(
        'proprietary_variable_ungrounded',
        'no proprietary_variable declared, no allow-list configured, and NO token from the '
        f'client\'s §21 list ({len(tokens)} candidates from required_phrases + entity fields) '
        'appears in the projected page text. That is a commodity page: emitting a plausible '
        'value here would launder it past §19 and §21 at once.',
        field_path='proprietary_variable')]


def check_capsule(draft: PageDraft) -> list[ValidationFinding]:
    """Blocking on ABSENCE (a capsule is authored upstream and must also be the
    editorial-split title/lede — this module does not write prose). Warning on the
    S19/S20 divergence: legal here at >= 8 words, doomed at build outside 40-80."""
    out: list[ValidationFinding] = []
    h2 = draft.capsule.interrogative_h2.strip()
    ans = draft.capsule.answer_first.strip()
    tldr = draft.capsule.tldr.strip()

    if not h2:
        out.append(block('capsule_h2_missing',
                         'capsule.interrogative_h2 is empty; the brief is the contract the draft '
                         'must satisfy and cannot be authored here',
                         field_path='capsule.interrogative_h2'))
    elif not strip_tags(h2).strip().endswith('?'):
        out.append(block('capsule_h2_not_interrogative',
                         f'capsule.interrogative_h2 must end in "?" (S19 does not accept a bare '
                         f'interrogative lead word, unlike S20): {h2[:60]!r}',
                         field_path='capsule.interrogative_h2'))
    if not ans:
        out.append(block('capsule_answer_missing', 'capsule.answer_first is empty',
                         field_path='capsule.answer_first'))
    else:
        words, sents = count_words(ans), count_sentences(ans)
        if not (ANSWER_FIRST_MIN_WORDS <= words <= ANSWER_FIRST_MAX_WORDS):
            out.append(warn('capsule_answer_words',
                            f'capsule.answer_first is {words}w. S19 passes it, but capsule_check '
                            f'(S20) requires {ANSWER_FIRST_MIN_WORDS}-{ANSWER_FIRST_MAX_WORDS}w '
                            'on the rendered block, so this page fails at build.',
                            field_path='capsule.answer_first'))
        if sents > ANSWER_FIRST_MAX_SENTENCES:
            out.append(warn('capsule_answer_sentences',
                            f'capsule.answer_first is {sents} sentences > '
                            f'{ANSWER_FIRST_MAX_SENTENCES} (S20 rule)',
                            field_path='capsule.answer_first'))
    if not tldr:
        out.append(block('capsule_tldr_missing',
                         'capsule.tldr is empty; ALWAYS emit a TL;DR node — S20\'s long-page '
                         'threshold counts the WHOLE page, not core_words',
                         field_path='capsule.tldr'))
    return out


# ---------------------------------------------------------------------------
# Build one brief
# ---------------------------------------------------------------------------

class BriefResult:
    """One draft's outcome: the brief dict (or None if refused) + its findings."""

    def __init__(self, draft: PageDraft, brief: dict | None,
                 findings: list[ValidationFinding], path: str) -> None:
        self.draft = draft
        self.brief = brief
        self.findings = findings
        self.path = path

    @property
    def refused(self) -> bool:
        return self.brief is None or any(f.blocking for f in self.findings)

    @property
    def flagged(self) -> bool:
        return any(not f.blocking for f in self.findings)


def build_brief(draft: PageDraft, cfg: dict, *, min_fanout: int, max_fanout: int,
                intent_enum: list[str], allowlist: set[str],
                min_answer_words: int) -> BriefResult:
    """Assemble one brief, then validate it with the REAL gate before returning."""
    findings: list[ValidationFinding] = []
    geo_tokens = grounded_geography(cfg)
    text = page_text(draft)

    if not draft.slug:
        findings.append(block('url_path_missing',
                              'draft has no url_path; the brief filename and route derive from it',
                              field_path='url_path'))
    elif re.search(r'^[a-z]+://|[?#]|\s', draft.slug):
        # brief_path() derives the FILENAME from the slug. An absolute URL, a query
        # string, a fragment or whitespace produces an unusable artifact name and a
        # slug that will not match the TS entry the sibling emitter writes.
        findings.append(block(
            'url_path_not_a_path',
            f'url_path {draft.url_path!r} is not a bare path; it must carry no scheme, host, '
            'query, fragment or whitespace (the brief filename and the TS entry slug both '
            'derive from it)', field_path='url_path'))

    intent, f = resolve_intent(draft, intent_enum)
    findings += f
    fanout, f = derive_fanout(draft, cfg, intent or 'commercial',
                              min_fanout=min_fanout, max_fanout=max_fanout)
    findings += f
    triples, f = derive_triples(draft, cfg, geo_tokens)
    findings += f
    pv, f = resolve_proprietary_variable(draft, cfg, allowlist, text)
    findings += f
    findings += check_capsule(draft)

    # Assemble via models.to_brief so the key set stays owned by one module, then
    # overlay the derived values.
    enriched = PageDraft(**{**draft.__dict__,
                            'fanout_queries': fanout,
                            'semantic_triples': triples,
                            'intent': intent,
                            'proprietary_variables': ([pv] + [p for p in draft.proprietary_variables
                                                              if p.strip() and p.strip() != pv])
                            if pv else list(draft.proprietary_variables)})
    brief = to_brief(enriched)

    # --- the gate is the authority: validate before writing ------------------
    gate_fails = s19.validate_brief(brief, min_fanout=min_fanout, intent_enum=intent_enum,
                                    allowlist=allowlist, min_answer_words=min_answer_words)
    for msg in gate_fails:
        findings.append(block('gate_would_reject', f'brief_fanout_check would fail: {msg}'))

    path = brief_path(enriched)
    return BriefResult(enriched, brief, findings, path)


# ---------------------------------------------------------------------------
# Atomic, idempotent write
# ---------------------------------------------------------------------------

def write_brief(brief: dict, dest: Path) -> str:
    """Atomic (tmp + os.replace) and idempotent. Returns 'written' | 'unchanged'."""
    payload = json.dumps(brief, indent=2, ensure_ascii=False) + '\n'
    if dest.is_file() and dest.read_text(encoding='utf-8') == payload:
        return 'unchanged'
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix='.brief-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(payload)
        os.replace(tmp, dest)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return 'written'


# ---------------------------------------------------------------------------
# Config resolution — identical to the gate's, by calling the gate's own loader
# ---------------------------------------------------------------------------

def resolve_settings(project: str, config_path: str | None, args: argparse.Namespace) -> dict:
    cfg = s19.load_cfg(project, config_path)
    brief_cfg = cfg.get('brief') or {}

    min_fanout = (args.min_fanout if args.min_fanout is not None
                  else int(brief_cfg.get('min_fanout', s19.DEFAULT_MIN_FANOUT)))
    min_answer_words = (args.min_answer_words if args.min_answer_words is not None
                        else int(brief_cfg.get('min_answer_words', s19.DEFAULT_MIN_ANSWER_WORDS)))
    if args.intent_enum:
        intent_enum = [s.strip() for s in args.intent_enum.split(',') if s.strip()]
    else:
        intent_enum = brief_cfg.get('intent_enum') or list(s19.DEFAULT_INTENT_ENUM)
    # ONE resolver, shared with emit_ts via models (B2). --allowlist overrides config.
    override = ([s.strip() for s in args.allowlist.split(',') if s.strip()]
                if args.allowlist is not None else None)
    allowlist = resolve_brief_allowlist(cfg, override)
    return {
        'cfg': cfg, 'min_fanout': min_fanout, 'min_answer_words': min_answer_words,
        'intent_enum': intent_enum, 'allowlist': allowlist,
        'max_fanout': max(args.max_fanout, min_fanout),
    }


# ---------------------------------------------------------------------------
# Self-test — real drafts, then the REAL gate
# ---------------------------------------------------------------------------

_REAL_ANSWER_FIRST = (
    'Matthews sits at the southeastern edge of Mecklenburg County, about eleven miles from '
    'Uptown Charlotte, close enough to take the full force of the spring and summer storm '
    'season that tracks northeast out of the southwest. Fast-moving cells drop hail and '
    'driving wind that lift shingles, push water behind siding, and overwhelm gutters in '
    'minutes. Acme has worked these neighborhoods for over two decades, from Sardis Forest '
    'to Providence Hills.'
)

_REAL_ANSWER_FIRST_2 = (
    'Fascia is the structural attachment point for the gutter system, and on a typical '
    'Charlotte home it carries the weight of tens of thousands of gallons of water flow every '
    'year. It also caps the exposed rafter ends, sealing them against the moisture and '
    'temperature cycling that Charlotte humidity drives. Substrate preparation, not material '
    'choice alone, is what determines how long that assembly lasts.'
)

_REAL_ANSWER_FIRST_3 = (
    'Acme Roofing has installed and repaired more than five thousand roofs across the '
    'Charlotte metro over twenty-six years in business. GAF Master Elite certification places '
    'the company in the top two percent of GAF contractors in North America, which is what '
    'unlocks the extended manufacturer warranty programs. That credential is held by very few '
    'roofers in the Charlotte market.'
)


def _real_drafts() -> list[dict[str, Any]]:
    """Three REAL Acme pages, transcribed from
    acme-roofing-site/src/data/location-pages.ts: one metro hub, one spoke, one
    sub-service. Copy is the shipped copy; nothing here is authored by this module.
    """
    return [
        {
            'url_path': 'charlotte-nc',
            'page_kind': 'hub',
            'city': 'Charlotte',
            'state': 'NC',
            'service': 'roofing and exterior services',
            'h1': 'Roofing Contractor in <span>Charlotte, NC</span>',
            'meta_title': 'Roofing Contractor Charlotte NC | Acme Roofing',
            'meta_description': (
                'GAF Master Elite roofing contractor serving Charlotte, NC. Roof replacement, '
                'repair, siding, and gutters. 5,000+ projects. Call (555) 555-0100.'),
            'title': 'Roofing Contractor in Charlotte, NC',
            'last_updated': '2026-04-30',
            'coverage_method': 'builder-collapse',
            'source_ref': 'docs/intake/2026-04-Hub-and-Suburb-Page-Content.docx#charlotte',
            'hero': {
                'badge_icon': 'fas fa-map-marker-alt',
                'badge_text': 'SERVING CHARLOTTE AND MECKLENBURG COUNTY',
                'title': 'Roofing Contractor in <span>Charlotte, NC</span>',
                'description': (
                    'GAF Master Elite certified. Roof replacement, repair, siding and gutters '
                    'across the Charlotte metro.'),
                'features': ['GAF Master Elite', '5,000+ Projects', '26+ Years', 'Licensed'],
            },
            'sections': [
                {'type': 'editorial-split',
                 'props': {'title': 'What Makes a Charlotte Roof Fail First?',
                           'lede': _REAL_ANSWER_FIRST_3}},
            ],
            'capsule': {
                'interrogative_h2': 'What Makes a Charlotte Roof Fail First?',
                'answer_first': _REAL_ANSWER_FIRST_3,
                'tldr': ('Key Takeaways: GAF Master Elite certification, 26 years in the '
                         'Charlotte metro, and 5,000+ completed projects. Licensed in NC, SC, VA '
                         'and WV. Call (555) 555-0100.'),
            },
            'intent': 'commercial',
        },
        {
            'url_path': 'charlotte-nc/matthews',
            'page_kind': 'spoke',
            'city': 'Matthews',
            'state': 'NC',
            'service': 'roofing and exterior services',
            'h1': 'Roofing Contractor in <span>Matthews, NC</span>',
            'meta_title': 'Roofing and Exterior Services Matthews NC | Acme',
            'meta_description': (
                'GAF Master Elite roofer serving Matthews, NC. Acme Roofing offers roof '
                'replacement, repair, siding, gutters and more. Free inspection. '
                'Call (555) 555-0100.'),
            'title': 'Roofing Contractor in Matthews, NC',
            'last_updated': '2026-04-30',
            'coverage_method': 'builder-collapse',
            'source_ref': 'docs/intake/2026-04-Hub-and-Suburb-Page-Content.docx#matthews',
            'hero': {
                'badge_icon': 'fas fa-map-marker-alt',
                'badge_text': 'SERVING MATTHEWS AND MECKLENBURG COUNTY',
                'title': 'Roofing Contractor in <span>Matthews, NC</span>',
                'description': ('GAF Master Elite roofer serving Matthews. Roof replacement, '
                                'repair, siding and gutters.'),
                'features': ['GAF Master Elite', '5,000+ Projects', '26+ Years', 'Licensed'],
            },
            'sections': [
                {'type': 'editorial-split',
                 'props': {'title': 'Why Do Matthews Roofs Take the Brunt of Storm Season?',
                           'lede': _REAL_ANSWER_FIRST}},
            ],
            'capsule': {
                'interrogative_h2': 'Why Do Matthews Roofs Take the Brunt of Storm Season?',
                'answer_first': _REAL_ANSWER_FIRST,
                'tldr': ('Key Takeaways: Matthews sits in the Charlotte storm corridor. Acme '
                         'is GAF Master Elite, licensed, and has served the town for over two '
                         'decades. Free inspection at (555) 555-0100.'),
            },
            'proprietary_variables': ['Providence Hills'],
            'intent': '',                       # exercise intent derivation
        },
        {
            'url_path': 'charlotte-nc/fascia-installation',
            'page_kind': 'subservice',
            'city': 'Charlotte',
            'state': 'NC',
            'service': 'fascia installation',
            'h1': 'Fascia Installation in <span>Charlotte, NC</span>',
            'meta_title': 'Fascia Installation Charlotte NC | GAF Master Elite',
            'meta_description': (
                'Professional fascia installation in Charlotte, NC. Aluminum wrap, PVC, wood, '
                'fiber cement. GAF Master Elite contractor. Free estimate. (555) 555-0100.'),
            'title': 'Fascia Installation in Charlotte, NC',
            'last_updated': '2026-05-22',
            'coverage_method': 'builder-collapse',
            'source_ref': 'docs/intake-archive/cycle-h-subservice.docx#charlotte-fascia',
            'hero': {
                'badge_icon': 'fas fa-hammer',
                'badge_text': 'CHARLOTTE FASCIA INSTALLATION',
                'title': 'Fascia Installation in <span>Charlotte, NC</span>',
                'description': ('Aluminum wrap, PVC, solid aluminum, fiber cement, and wood '
                                'fascia installation across Charlotte. GAF Master Elite '
                                'certified.'),
                'features': ['GAF Master Elite', '5,000+ Projects', '26+ Years',
                             'Free Estimates'],
            },
            'sections': [
                {'type': 'editorial-split',
                 'props': {'title': 'What Does Fascia Actually Do on a Charlotte Home?',
                           'lede': _REAL_ANSWER_FIRST_2}},
            ],
            'capsule': {
                'interrogative_h2': 'What Does Fascia Actually Do on a Charlotte Home?',
                'answer_first': _REAL_ANSWER_FIRST_2,
                'tldr': ('Key Takeaways: fascia carries the gutter load and seals the rafter '
                         'ends. Aluminum-wrapped wood is the Charlotte default; PVC and fiber '
                         'cement trade cost for service life. Substrate prep decides longevity.'),
            },
            'fanout_queries': ['aluminum wrapped fascia Charlotte', 'PVC fascia vs wood fascia'],
            'intent': 'commercial',
        },
    ]


_DEFICIENT_BRIEF = {
    'fanout': ['roofing charlotte', 'Roofing Charlotte', 'roof repair'],   # 2 distinct, need 6
    'capsule': {
        'interrogative_h2': 'How Charlotte Roofs Fail',                    # no '?'
        'answer_first': 'It depends.',                                     # 2 words
        'tldr': '',                                                        # empty
    },
    'semantic_triples': [{'subject': 'Acme Roofing', 'predicate': '', 'object': ''}],
    'proprietary_variable': '',
    'intent': 'promotional',                                               # not in enum
}


def self_test(project: str, verbose: bool = False) -> list[str]:
    """Generate briefs for 3 REAL drafts into a temp dir, run the REAL gate CLI
    over them (must PASS), then drop one deliberately deficient brief in and
    confirm the same gate REJECTS it with exit 9."""
    import subprocess

    fails: list[str] = []
    ns = argparse.Namespace(min_fanout=None, min_answer_words=None, intent_enum=None,
                            allowlist=None, max_fanout=DEFAULT_MAX_FANOUT)
    settings = resolve_settings(project, None, ns)

    with tempfile.TemporaryDirectory(prefix='wf-brief-selftest-') as tmp:
        briefs_dir = Path(tmp) / 'docs' / 'briefs'
        briefs_dir.mkdir(parents=True)
        results = []
        for data in _real_drafts():
            draft = draft_from_dict(data)
            res = build_brief(draft, settings['cfg'], min_fanout=settings['min_fanout'],
                              max_fanout=settings['max_fanout'],
                              intent_enum=settings['intent_enum'],
                              allowlist=settings['allowlist'],
                              min_answer_words=settings['min_answer_words'])
            results.append(res)
            if res.refused:
                fails.append(f'{draft.slug}: refused — '
                             f'{[f.code for f in res.findings if f.blocking]}')
                continue
            dest = briefs_dir / Path(res.path).name
            write_brief(res.brief, dest)
            if verbose:
                print(json.dumps(res.brief, indent=2, ensure_ascii=False))

        if len(list(briefs_dir.glob('*.json'))) < 3:
            fails.append(f'expected >= 3 briefs written, got '
                         f'{len(list(briefs_dir.glob("*.json")))}')

        # idempotence: a second write of the same payload must be a no-op
        for res in results:
            if res.brief is not None:
                if write_brief(res.brief, briefs_dir / Path(res.path).name) != 'unchanged':
                    fails.append(f'{res.draft.slug}: second write was not idempotent')

        env = dict(os.environ)
        repo_root = str(Path(__file__).resolve().parents[2])
        env['PYTHONPATH'] = repo_root + os.pathsep + env.get('PYTHONPATH', '')
        gate = [sys.executable, '-m', 'pipeline.gates.brief_fanout_check', tmp]

        ok = subprocess.run(gate, capture_output=True, text=True, env=env, cwd=repo_root)
        if ok.returncode != 0:
            fails.append(f'REAL gate rejected the generated briefs (exit {ok.returncode}):\n'
                         f'{ok.stdout}{ok.stderr}')
        elif verbose:
            print(ok.stdout)

        # --- negative control: a deliberately deficient brief must be REJECTED --
        (briefs_dir / 'deliberately-deficient.json').write_text(
            json.dumps(_DEFICIENT_BRIEF, indent=2) + '\n', encoding='utf-8')
        bad = subprocess.run(gate, capture_output=True, text=True, env=env, cwd=repo_root)
        if bad.returncode != 9:
            fails.append(f'negative control: gate returned {bad.returncode}, expected 9 on a '
                         f'deficient brief\n{bad.stdout}{bad.stderr}')
        else:
            expected = ['fanout:', 'capsule.interrogative_h2:', 'capsule.answer_first:',
                        'capsule.tldr:', 'semantic_triples:', 'proprietary_variable:', 'intent:']
            missing = [e for e in expected if e not in bad.stdout]
            if missing:
                fails.append(f'negative control: gate did not report {missing}\n{bad.stdout}')
            elif verbose:
                print(bad.stdout)

        # --- negative control: this module must refuse a capsule-less draft -----
        thin = dict(_real_drafts()[0])
        thin['capsule'] = {'interrogative_h2': '', 'answer_first': '', 'tldr': ''}
        thin_res = build_brief(draft_from_dict(thin), settings['cfg'],
                               min_fanout=settings['min_fanout'],
                               max_fanout=settings['max_fanout'],
                               intent_enum=settings['intent_enum'],
                               allowlist=settings['allowlist'],
                               min_answer_words=settings['min_answer_words'])
        if not thin_res.refused:
            fails.append('negative control: a draft with no capsule was not refused')

        # --- negative control: a bogus proprietary_variable is never invented ---
        bogus = dict(_real_drafts()[0])
        bogus['sections'] = []
        bogus['hero'] = {'badge_icon': '', 'badge_text': '', 'title': 'Roofing',
                         'description': 'Roofing.'}
        bogus['meta_description'] = 'Roofing services.'
        bogus['meta_title'] = 'Roofing'
        bogus['title'] = 'Roofing'
        bogus['h1'] = 'Roofing'
        bogus['capsule'] = {'interrogative_h2': 'What Is Roofing?',
                            'answer_first': _REAL_ANSWER_FIRST_3, 'tldr': 'Key Takeaways: none.'}
        bogus_res = build_brief(draft_from_dict(bogus), settings['cfg'],
                                min_fanout=settings['min_fanout'],
                                max_fanout=settings['max_fanout'],
                                intent_enum=settings['intent_enum'],
                                allowlist={'crew_size', 'neighborhoods'},
                                min_answer_words=settings['min_answer_words'])
        codes = [f.code for f in bogus_res.findings if f.blocking]
        if 'proprietary_variable_undeclared' not in codes:
            fails.append('negative control: an undeclared proprietary_variable under a '
                         f'configured allow-list was not blocked (got {codes})')
        if bogus_res.brief and bogus_res.brief.get('proprietary_variable'):
            fails.append('negative control: a proprietary_variable was invented '
                         f'({bogus_res.brief["proprietary_variable"]!r})')

    return fails


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_findings(res: BriefResult) -> None:
    for f in res.findings:
        tag = 'BLOCK' if f.blocking else 'WARN '
        loc = f' [{f.field_path}]' if f.field_path else ''
        print(f'    {tag} {f.code}{loc}: {f.message}')


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Emit docs/briefs/<slug>.json (§19) from emitter page drafts.')
    ap.add_argument('drafts', nargs='?', help='drafts.json (one draft, a list, or {"drafts":[...]})')
    ap.add_argument('--project', default='.', help='Client project dir (holds docs/client-config.yml)')
    ap.add_argument('--out-dir', default=None,
                    help='Brief output dir (default PROJECT/docs/briefs). Relative paths resolve '
                         'against PROJECT.')
    ap.add_argument('--config', default=None, help='Explicit client-config.yml path')
    ap.add_argument('--min-fanout', type=int, default=None)
    ap.add_argument('--max-fanout', type=int, default=DEFAULT_MAX_FANOUT)
    ap.add_argument('--min-answer-words', type=int, default=None)
    ap.add_argument('--intent-enum', default=None, help='Comma-separated intent enum override')
    ap.add_argument('--allowlist', default=None,
                    help='Comma-separated proprietary_variable allow-list override')
    ap.add_argument('--dry-run', action='store_true', help='Validate and report; write nothing')
    ap.add_argument('--self-test', action='store_true',
                    help='Generate briefs for 3 real drafts and run the REAL gate over them')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    project = os.path.abspath(args.project)

    if args.self_test:
        fails = self_test(project, verbose=args.verbose)
        if fails:
            print('FAIL: brief.py self-test')
            for f in fails:
                print(f'  {f}')
            return 9
        print('PASS: brief.py self-test — 3 real drafts emitted, real gate '
              '(brief_fanout_check) PASSED over them, deficient brief REJECTED with exit 9, '
              'capsule-less draft refused, no proprietary_variable invented.')
        return 0

    if not args.drafts:
        ap.print_help()
        return 2
    if not os.path.isfile(args.drafts):
        print(f'[ERROR] no such drafts file: {args.drafts}', file=sys.stderr)
        return 2

    try:
        drafts = load_drafts(args.drafts)
    except Exception as e:
        print(f'[ERROR] could not read {args.drafts}: {e}', file=sys.stderr)
        return 2
    if not drafts:
        print(f'[NOTE] {args.drafts} contains no drafts; nothing to emit.')
        return 0

    settings = resolve_settings(project, args.config, args)
    if not settings['allowlist']:
        print('[WARN] no proprietary_variable allow-list configured '
              '(brief.proprietary_variables / --allowlist) — the gate will SKIP membership with '
              'a WARN. This emitter still requires a config-grounded, page-evidenced value.',
              file=sys.stderr)

    out_dir = args.out_dir or os.path.join(project, 'docs', 'briefs')
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(project, out_dir)
    out_dir_p = Path(os.path.abspath(out_dir))

    refused = 0
    flagged = 0
    written = 0
    unchanged = 0
    for draft in drafts:
        res = build_brief(draft, settings['cfg'], min_fanout=settings['min_fanout'],
                          max_fanout=settings['max_fanout'],
                          intent_enum=settings['intent_enum'], allowlist=settings['allowlist'],
                          min_answer_words=settings['min_answer_words'])
        label = draft.slug or '<no url_path>'
        if res.refused:
            refused += 1
            print(f'  REFUSED {label}')
            _print_findings(res)
            continue
        name = Path(res.path).name
        if args.dry_run:
            print(f'  would write {out_dir_p / name}  '
                  f'(fanout={len(res.brief["fanout"])}, intent={res.brief["intent"]}, '
                  f'pv={res.brief["proprietary_variable"]!r})')
        else:
            state = write_brief(res.brief, out_dir_p / name)
            written += state == 'written'
            unchanged += state == 'unchanged'
            print(f'  {state:9s} {out_dir_p / name}  '
                  f'(fanout={len(res.brief["fanout"])}, intent={res.brief["intent"]}, '
                  f'pv={res.brief["proprietary_variable"]!r})')
        if res.flagged:
            flagged += 1
            _print_findings(res)

    verb = 'would write' if args.dry_run else 'written'
    print(f'brief: {len(drafts)} draft(s) — {written} {verb}, {unchanged} unchanged, '
          f'{refused} refused, {flagged} flagged for curation.'
          if not args.dry_run else
          f'brief: {len(drafts)} draft(s) — {len(drafts) - refused} would be written, '
          f'{refused} refused, {flagged} flagged for curation. (DRY RUN, nothing written)')
    if refused:
        print(f'REFUSED: {refused} brief(s) had a blocking finding and were NOT written. '
              'Fix the draft upstream (§19: the brief is the contract, not the output).')
        return 9
    if flagged:
        print(f'FLAGGED: {flagged} brief(s) carry curation flags for the ledger.')
        return 1
    print('PASS: every brief emitted clean and validates against brief_fanout_check.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
