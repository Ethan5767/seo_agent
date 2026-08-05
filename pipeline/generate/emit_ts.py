#!/usr/bin/env python3
"""Write validated PageDrafts into the client's REAL typed data files.

This is the last pass of the 3-pass intake design and the only module in the
package that touches the client repo. Everything upstream produces a PageDraft;
this turns one into the three artifacts that must land together:

    1. the `export const <name>: ServicePage = {...};` entry, spliced into
       src/data/location-pages.ts (or services.ts) ahead of the registry array;
    2. its row in `allLocationPages` / `allServices` — an entry without its row
       builds, is crawlable, has zero inbound links, and is exactly the orphan
       orphan_check.py exists to catch (C16);
    3. docs/briefs/<slug>.json, the §19 brief the gate validates.

Design rules, in the order they win:

  REFUSE OVER GUESS. A BLOCK finding (forbidden/legal phrase, §21 duplicate,
  out-of-topology URL, out-of-allow-list proprietary variable, structural/TS
  corruption) refuses that page: no entry, no registry row, no brief, exit 9.

  HOLD, DON'T STALL. A CURATE finding (a hero that cannot be reduced
  mechanically, an over-length metaTitle, missing alt text, a missing capsule
  node) is a quality decision a human must make. That page is HELD — it does NOT
  ship — but it does not stop any other page emitting, and it lands in
  docs/briefs/_curation.md with the offending text and a concrete proposed fix.
  A cycle's output is "N emitted, M awaiting a yes/no", never "0, do it by hand".

  PER-PAGE INDEPENDENCE. One page's finding never suppresses another's emission.

  ATOMIC. The entry, the row and the brief are staged in memory, then written
  together via a temp-file + os.replace per file. A crash mid-run cannot leave an
  entry without its registry row.

  IDEMPOTENT. Re-running the same drafts produces a byte-identical file. An entry
  already present is REPLACED in place (same position, same surrounding
  formatting); a registry row already present is not re-added. `--dry-run` twice,
  then a real write, then a re-run, is a no-op by construction.

  APPEND-ONLY IN SPIRIT. Existing entries are never reformatted. The splice is
  anchor-based on the registry declaration, so the 21,844 surrounding lines are
  byte-preserved and the diff is reviewable.

  NEVER GIT. This writes the working tree and nothing else. No add, no commit, no
  push, no branch — in this repo or the client's.

Exit codes (the DOCUMENTED registry — pipeline/generate/__init__.py, SPEC §7,
docs/gate-reference.md, brief.py — after the emitter's old, undocumented 3 was
retired and its overloaded 1 was split):
    0  every draft emitted clean
    1  emitted with curation flags — EVERYTHING SHIPPED, warn flags ride along
       in the ledger. Nothing was withheld.
    2  usage / input error
    9  refused to emit — at least one BLOCK finding. Nothing written for it.
   15  one or more pages HELD for curation — the emitter emitted what it could,
       the held pages did NOT ship. NOT green. Needs one human yes/no per page;
       see docs/briefs/_curation.md for the finding and a proposed fix.

Distinct codes matter: an orchestrator branching on exit status alone must be
able to tell "shipped with flags" (1) from "did not ship" (15) from "refused"
(9). Collapsing any two of those is the 3-vs-9 defect class all over again.

Usage:
    emit_ts.py drafts.json decisions.json --project PROJECT_DIR [--dry-run] [--limit N]
    emit_ts.py --self-test --project PROJECT_DIR
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, Iterable

if __name__ == '__main__':  # pragma: no cover - script bootstrap
    # Plain script, NOT `-m pipeline.generate.emit_ts`. The package __init__
    # re-exports models, so -m loads it twice under two names and the two copies
    # of Section fail isinstance against each other. Must precede the import below.
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from pipeline.generate import validators
from pipeline.generate.classify import (
    _skip_balanced,
    parse_identifier_array,
    parse_service_pages,
)
from pipeline.generate.models import (
    ROUTE_ARRAY_BY_SEGMENTS,
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
    apply_severity_policy,
    assert_balanced_ts,
    brief_path,
    recount_core_words,
    to_brief_json,
    to_registry_row,
    to_ts_entry,
    warn,
)

# ---------------------------------------------------------------------------
# Target files. Keyed by the registry array the entries feed.
# Acme defaults, kept as module names for importers; every use site reads the
# ACTIVE per-repo layout (repo_layout.activate from client-config repo.layout:)
# so a non-default repo shape is data, not a refusal (P0-2).
# ---------------------------------------------------------------------------

from pipeline.generate import repo_layout as _repo_layout

#: data file -> the `export const <registry>: ServicePage[] = [` it ends with.
DATA_FILE_REGISTRY: dict[str, str] = dict(_repo_layout.DEFAULT.data_file_registry)

DEFAULT_DATA_FILE = _repo_layout.DEFAULT.default_data_file

#: The dynamic route file each segment count's route array lives in. Registration
#: there is what makes the page BUILD (dynamicParams=false -> 404 without it).
ROUTE_FILES: dict[str, str] = dict(_repo_layout.DEFAULT.route_files)

BANNER = '// Emitted {date} by pipeline/generate/emit_ts.py'

# ---------------------------------------------------------------------------
# Exit codes — every outcome owns a DISTINCT one
# ---------------------------------------------------------------------------

#: "The emitter emitted what it could; N pages were HELD for curation and did NOT
#: ship." Distinct from 1 (everything shipped, warn flags attached) and from 9
#: (refused, blocking finding) so an orchestrator can branch on status alone.
#:
#: Why 15: codes 1-10 belong to the gate registry (docs/gate-reference.md) and
#: 11-14 to pipeline/audit/preflight.py. 15 is the first genuinely unclaimed code
#: in the fleet. Do NOT reuse a lower one — that is the 3-vs-9 bug's whole shape.
HELD_FOR_CURATION_EXIT = 15


# ---------------------------------------------------------------------------
# Deserialisation — drafts.json -> PageDraft
# ---------------------------------------------------------------------------

def _snake(key: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', key).lower()


def _get(d: dict[str, Any], *names: str, default: Any = None) -> Any:
    """Accept snake_case or the TS camelCase spelling for the same field, so a
    draft hand-written against services.ts field names still loads."""
    for n in names:
        if n in d:
            return d[n]
        snake = _snake(n)
        if snake in d:
            return d[snake]
    return default


def _revive_props(node: Any) -> Any:
    """Rebuild RawExpr from its JSON marker: {"__raw__": "processSection()"}."""
    if isinstance(node, dict):
        if set(node) == {'__raw__'}:
            return RawExpr(str(node['__raw__']))
        return {k: _revive_props(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_revive_props(v) for v in node]
    return node


def section_from_dict(d: dict[str, Any]) -> Section | BuilderCall:
    if 'builder' in d or 'name' in d and 'type' not in d:
        name = str(_get(d, 'builder', 'name'))
        return BuilderCall(name=name, args=_revive_props(list(d.get('args') or [])))
    props = _revive_props(dict(d.get('props') or {}))
    if not props:
        # Tolerate a flat section object ({"type": "...", "label": "...", ...}),
        # which is how a section reads in the TS. `type` is lifted out; putting it
        # back in props is a structural finding in models.
        props = {k: _revive_props(v) for k, v in d.items()
                 if k not in ('type', 'core_body', 'coreBody', 'source_ref',
                              'sourceRef', 'verdict')}
    return Section(
        type=str(d.get('type', '')),
        props=props,
        core_body=bool(_get(d, 'core_body', 'coreBody', default=False)),
        source_ref=_get(d, 'source_ref', 'sourceRef'),
        verdict=d.get('verdict'),
    )


def hero_from_dict(d: dict[str, Any]) -> Hero:
    buttons = []
    for b in (d.get('buttons') or []):
        buttons.append(HeroButton(
            text=str(_get(b, 'text', default='')),
            url=str(_get(b, 'url', default='')),
            class_name=str(_get(b, 'class_name', 'className', default='btn-primary')),
            icon_before=_get(b, 'icon_before', 'iconBefore'),
            icon_after=_get(b, 'icon_after', 'iconAfter'),
        ))
    return Hero(
        badge_icon=str(_get(d, 'badge_icon', 'badgeIcon', default='')),
        badge_text=str(_get(d, 'badge_text', 'badgeText', default='')),
        title=str(_get(d, 'title', default='')),
        description=str(_get(d, 'description', default='')),
        bg_image=_get(d, 'bg_image', 'bgImage'),
        buttons=buttons,
        features=[str(f) for f in (d.get('features') or [])],
    )


def draft_from_dict(d: dict[str, Any]) -> PageDraft:
    """Build a PageDraft from one drafts.json object.

    Missing REQUIRED fields raise here rather than defaulting: a page with no
    url_path or no hero is an upstream bug, and quietly inventing one is how a
    wrong page ships. Optional fields fall back to the dataclass defaults.
    """
    hero_raw = _get(d, 'hero')
    if not isinstance(hero_raw, dict):
        raise ValueError(f'draft {d.get("url_path") or d.get("slug")!r}: hero is required')

    capsule_raw = d.get('capsule') or {}
    triples = []
    for t in (_get(d, 'semantic_triples', 'semanticTriples') or []):
        if isinstance(t, dict):
            triples.append(SemanticTriple(str(t.get('subject', '')),
                                          str(t.get('predicate', '')),
                                          str(t.get('object', ''))))
        elif isinstance(t, (list, tuple)) and len(t) == 3:
            triples.append(SemanticTriple(str(t[0]), str(t[1]), str(t[2])))

    url_path = _get(d, 'url_path', 'urlPath', 'route', 'slug')
    if not url_path:
        raise ValueError('draft is missing url_path/slug')

    return PageDraft(
        url_path=str(url_path),
        page_kind=str(_get(d, 'page_kind', 'pageKind', default='')),
        city=str(_get(d, 'city', default='')),
        state=str(_get(d, 'state', default='')),
        service=str(_get(d, 'service', default='')),
        h1=str(_get(d, 'h1', default='')),
        meta_title=str(_get(d, 'meta_title', 'metaTitle', default='')),
        meta_description=str(_get(d, 'meta_description', 'metaDescription', default='')),
        hero=hero_from_dict(hero_raw),
        title=str(_get(d, 'title', default='')),
        export_name=str(_get(d, 'export_name', 'exportName', default='')),
        last_updated=str(_get(d, 'last_updated', 'lastUpdated', default='')),
        sections=[section_from_dict(s) for s in (d.get('sections') or [])],
        faqs=[FaqItem(str(f.get('question', '')), str(f.get('answer', '')))
              for f in (d.get('faqs') or [])],
        capsule=Capsule(
            interrogative_h2=str(_get(capsule_raw, 'interrogative_h2', 'interrogativeH2',
                                      default='')),
            answer_first=str(_get(capsule_raw, 'answer_first', 'answerFirst', default='')),
            tldr=str(capsule_raw.get('tldr', '')),
        ),
        proprietary_variables=[str(p) for p in
                               (_get(d, 'proprietary_variables', 'proprietaryVariables')
                                or ([d['proprietary_variable']] if d.get('proprietary_variable')
                                    else []))],
        fanout_queries=[str(q) for q in (_get(d, 'fanout_queries', 'fanoutQueries', 'fanout')
                                         or [])],
        semantic_triples=triples,
        intent=str(d.get('intent', '')),
        core_body_words=int(_get(d, 'core_body_words', 'coreBodyWords', default=0) or 0),
        source_ref=str(_get(d, 'source_ref', 'sourceRef', default='')),
        coverage_method=str(_get(d, 'coverage_method', 'coverageMethod', default='')),
        related_links=list(_get(d, 'related_links', 'relatedLinks') or []),
        ledger=list(d.get('ledger') or []),
    )


def load_drafts(path: Path) -> list[tuple[PageDraft, str]]:
    """Return [(draft, target data file)]. Accepts a list or a {"drafts": [...]}."""
    payload = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(payload, dict):
        payload = payload.get('drafts') or payload.get('pages') or [payload]
    if not isinstance(payload, list):
        raise ValueError('drafts.json must be a list of draft objects')
    out: list[tuple[PageDraft, str]] = []
    for item in payload:
        target = str(_get(item, 'target_file', 'targetFile',
                          default=_repo_layout.active().default_data_file))
        registry = _repo_layout.active().data_file_registry
        if target not in registry:
            raise ValueError(f'unknown target_file {target!r}; known: '
                             f'{sorted(registry)}')
        out.append((draft_from_dict(item), target))
    return out


# ---------------------------------------------------------------------------
# decisions.json — the operator's curation record
# ---------------------------------------------------------------------------

class Decisions:
    """Per-slug curation record. Waives WARN findings only — never a block.

    Shape (all keys optional):
        {
          "defaults": {"acknowledged_flags": ["sweet_spot_drift"]},
          "charlotte-nc/matthews/gutter-guards": {
            "acknowledged_flags": ["card_grid_count"],
            "verdicts": {"gutter.docx#intro": "KEEP"},
            "drop_rate_acknowledged": true,
            "note": "6-card mosaic approved 2026-07-20"
          }
        }

    A blocking finding is NEVER waivable. That is the whole point of the
    severity split: 'block' means the emitter cannot produce correct output, and
    a human saying "ship it anyway" would just move the failure to the build.
    """

    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self._raw = payload or {}
        self._defaults = self._raw.get('defaults') or {}

    @classmethod
    def load(cls, path: Path | None) -> 'Decisions':
        if path is None:
            return cls({})
        if not path.exists():
            raise FileNotFoundError(f'decisions file not found: {path}')
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('decisions.json must be an object keyed by page slug')
        return cls(cls._normalise(payload))

    @staticmethod
    def _normalise(payload: dict[str, Any]) -> dict[str, Any]:
        """Accept BOTH curation-record shapes and key everything by slug.

        classify.py writes a *report*: {"generated_at":..., "decisions": [ {...} ]}
        where each element carries its own "slug". This class was written against a
        flat {slug: {...}} map. Feeding the report shape in used to be a SILENT
        no-op — every `_for(slug)` lookup missed, so acknowledged_flags,
        drop_rate_acknowledged and verdict overrides were all quietly ignored and
        the emitter refused pages a human had already signed off. Nothing errored,
        which is the dangerous part. Normalise instead, and refuse a payload that
        matches neither shape rather than degrading to {} again.
        """
        rows = payload.get('decisions')
        if not isinstance(rows, list):
            return payload  # already the flat {slug: {...}} shape

        flat: dict[str, Any] = {}
        if isinstance(payload.get('defaults'), dict):
            flat['defaults'] = payload['defaults']
        for row in rows:
            if not isinstance(row, dict):
                continue
            slug = (row.get('slug') or '').strip().strip('/')
            if not slug:
                continue
            flat[slug] = {k: v for k, v in row.items() if k != 'slug'}
        if not flat:
            raise ValueError(
                'decisions.json has a "decisions" list but no element carried a '
                '"slug" — cannot key the curation record. Expected either '
                'classify.py report shape or a flat {slug: {...}} map.')
        return flat

    def _for(self, slug: str) -> dict[str, Any]:
        entry = self._raw.get(slug)
        return entry if isinstance(entry, dict) else {}

    def acknowledged(self, slug: str, code: str) -> bool:
        flags = set(self._defaults.get('acknowledged_flags') or [])
        flags |= set(self._for(slug).get('acknowledged_flags') or [])
        return code in flags

    def verdict_for(self, slug: str, block_id: str) -> str | None:
        return (self._for(slug).get('verdicts') or {}).get(block_id)

    def drop_rate_acknowledged(self, slug: str) -> bool:
        return bool(self._for(slug).get('drop_rate_acknowledged')
                    or self._defaults.get('drop_rate_acknowledged'))


VALID_VERDICTS = frozenset({'KEEP', 'TRIM', 'OPTIMIZE', 'DROP', 'BANK'})


def ledger_findings(draft: PageDraft, decisions: Decisions) -> list[ValidationFinding]:
    """C26 — every dossier block carries a verdict, and the >40% dropped/banked
    circuit breaker is acknowledged.

    Verdicts come from the draft's own ledger, with decisions.json able to supply
    one that pass 2 left blank. A block with no verdict anywhere is a warn, not a
    block: the emitter cannot tell an un-triaged block from a deliberately silent
    one, and refusing the page would punish the wrong thing. The circuit breaker
    IS blocking, because a page that dropped 40% of its source is a content
    decision no one made.
    """
    out: list[ValidationFinding] = []
    entries = list(draft.ledger)
    if not entries:
        return [warn('ledger_empty',
                     'no dossier ledger on this draft; provenance for Alex is unverifiable',
                     field_path='ledger')]
    verdicts: list[str] = []
    for i, row in enumerate(entries):
        block_id = str(row.get('block') or row.get('id') or f'#{i}')
        verdict = row.get('verdict') or decisions.verdict_for(draft.slug, block_id)
        if not verdict:
            out.append(warn('ledger_verdict_missing',
                            f'dossier block {block_id!r} has no verdict '
                            f'({sorted(VALID_VERDICTS)})', field_path=f'ledger[{i}]'))
            continue
        if verdict not in VALID_VERDICTS:
            out.append(warn('ledger_verdict_invalid',
                            f'block {block_id!r} verdict {verdict!r} not in '
                            f'{sorted(VALID_VERDICTS)}', field_path=f'ledger[{i}]'))
        verdicts.append(str(verdict))
    if verdicts:
        shed = sum(1 for v in verdicts if v in ('DROP', 'BANK')) / len(verdicts)
        if shed > 0.40 and not decisions.drop_rate_acknowledged(draft.slug):
            out.append(ValidationFinding(
                code='drop_rate_circuit_breaker', severity='block',
                message=f'{shed:.0%} of dossier blocks are DROP/BANK (> 40%); acknowledge in '
                        'decisions.json with "drop_rate_acknowledged": true before emitting',
                field_path='ledger'))
    return out


# ---------------------------------------------------------------------------
# B1 — the LIVE sibling corpus (§21 / C6)
# ---------------------------------------------------------------------------
#
# The emitter used to seed `siblings` EMPTY and only ever add pages emitted in
# the current process. Under the natural workflow (emit a page, review it, emit
# the next) every already-shipped page was invisible, so two sequential runs
# wrote a 0.99-overlap duplicate at exit 1 and the defect only surfaced later,
# post-build, when noncommodity_check read the built HTML.
#
# The corpus below is the client's REAL live pages, parsed out of the same typed
# data files the emitter writes into, UNIONED with the current batch. Thresholds
# are untouched (0.90 hub-spoke / 0.60 default) and the comparison runs through
# validators.s21_sibling_overlap — the same five-gram engine the gate uses — so
# the emitter and the gate cannot disagree about what a duplicate is.
#
# NOT used as a source: the built `out/**/index.html`. Those documents carry the
# site chrome (nav, footer, CTA blocks) that `projected_text()` deliberately
# excludes, so overlap against them measures the template, not the page — that is
# precisely why the Run #1 gate reported 31/61 pages `duplicate_of_sibling` on a
# site whose page bodies genuinely differ. Comparing content strings to content
# strings is the apples-to-apples test, and it is the one a draft can act on.

def live_sibling_corpus(project: Path,
                        data_files: Iterable[str] = ()) -> dict[str, str]:
    """route -> projected text, for every ServicePage already live in the repo.

    Missing/unparseable data files degrade to "no siblings from that file" and are
    reported by the caller — never to a silent empty corpus, which is the bug.
    """
    corpus: dict[str, str] = {}
    rels = list(data_files) or list(_repo_layout.active().data_file_registry)
    for rel in rels:
        path = project / rel
        if not path.is_file():
            continue
        src = path.read_text(encoding='utf-8', errors='replace')
        for entry in parse_service_pages(src, rel):
            if not entry.slug:
                continue
            route = f'/{entry.slug}/'
            text = '\n'.join(entry.raw_content_strings)
            if text.strip():
                corpus[route] = text
    return corpus


# ---------------------------------------------------------------------------
# Anchor-based splicing
# ---------------------------------------------------------------------------

def _entry_span(text: str, export_name: str) -> tuple[int, int] | None:
    """(start, end) of an existing `export const <name>: ServicePage = {...};`.

    Brace matching is string-aware, so an apostrophe or a brace inside a template
    literal cannot swallow the rest of a 21,844-line file. Returns None when the
    entry is not present.
    """
    m = re.search(rf'(?m)^export const {re.escape(export_name)}\s*:\s*ServicePage\s*=\s*\{{',
                  text)
    if not m:
        return None
    i = m.end() - 1          # the '{' the regex just consumed, not a later one
    depth, quote = 0, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'", '`'):
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                if text[end:end + 1] == ';':
                    end += 1
                if text[end:end + 1] == '\n':
                    end += 1
                return m.start(), end
        i += 1
    raise ValueError(f'unterminated entry literal for {export_name}')


def _registry_span(text: str, registry: str) -> tuple[int, int, int]:
    """(decl_start, body_start, body_end) for `export const <registry>: ServicePage[] = [`.

    body_end is the index of the closing `]` of the array.
    """
    m = re.search(rf'(?m)^export const {re.escape(registry)}\s*:\s*ServicePage\[\]\s*=\s*\[',
                  text)
    if not m:
        raise ValueError(f'registry array {registry!r} not found — refusing to guess where '
                         'the entries go')
    # m.end() is just past the array's opening '[', NOT the '[' in 'ServicePage[]'.
    # Searching for the first '[' after m.start() finds the type's bracket pair and
    # closes the span immediately, which splices the registry row into the type
    # annotation: `ServicePage[  charlotteNC,` — invalid TS that still balances.
    body_start = m.end()
    depth, i, quote = 1, body_start, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ('"', "'", '`'):
            quote = ch
        elif ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return m.start(), body_start, i
        i += 1
    raise ValueError(f'unterminated {registry} array literal')


def splice_entry(text: str, draft: PageDraft, registry: str, banner: str) -> str:
    """Insert or replace one entry + its registry row. Idempotent.

    New entries are inserted immediately BEFORE the registry declaration, which
    is the file's natural append point and keeps every existing line byte-identical.
    An entry that already exists is replaced IN PLACE, so a re-emit does not move
    the page to the bottom of the file and produce a 600-line phantom diff.
    """
    name = draft.resolved_export_name
    entry = to_ts_entry(draft)

    span = _entry_span(text, name)
    if span:
        start, end = span
        if text[start:end] == entry:
            new_text = text  # byte-identical: true no-op
        else:
            new_text = text[:start] + entry + text[end:]
    else:
        decl_start, _, _ = _registry_span(text, registry)
        block = entry + '\n'
        if banner and banner not in text:
            block = banner + '\n' + block
        new_text = text[:decl_start] + block + text[decl_start:]

    # --- registry row, in the same transformation (C16) ---------------------
    _, body_start, body_end = _registry_span(new_text, registry)
    body = new_text[body_start:body_end]
    row = to_registry_row(draft)
    if not re.search(rf'(?m)^\s*{re.escape(name)},\s*$', body):
        addition = row
        if banner and banner not in body:
            addition = f'  {banner}\n' + row
        new_text = new_text[:body_end] + addition + new_text[body_end:]
    return new_text


def route_registration_finding(draft: PageDraft, project: Path) -> ValidationFinding | None:
    """C16/C17 — report route-array registration; never edit src/app by default.

    The two rules collide here and the collision is real, not a misreading:
      * C16 says the entry and its route-array row are one transaction, because a
        page missing from METRO_PAGES/SPOKE_PAGES/SUBSERVICE_PAGES does not build
        at all (dynamicParams=false -> 404).
      * C17 says assert nothing under src/app/ is touched.

    Resolved in favour of C17 by DEFAULT: this module writes data files only and
    reports the required registration as a blocking finding when it is missing, so
    the emitter can never silently produce a 404. `--register-routes` opts into
    splicing the route file, which is safe against pages_are_data_check because
    every route array lives in a DYNAMIC route (`[slug]/...`) and that gate only
    line-checks STATIC routes. Reported to Alex either way.
    """
    array = draft.route_array
    if not array:
        return None
    rel = _repo_layout.active().route_files.get(array)
    if not rel:
        return None
    path = project / rel
    if not path.exists():
        return ValidationFinding(
            code='route_file_missing', severity='block',
            message=f'{rel} not found; {draft.route} cannot be registered in {array}',
            field_path='slug')
    text = path.read_text(encoding='utf-8')
    name = draft.resolved_export_name
    # Parse the array for real. A line-anchored regex (`^\s*name,$`) silently
    # false-negatives on the single-line form the metro file actually uses:
    #   const METRO_PAGES: ServicePageType[] = [charlotteNC, ashevilleNC];
    # which reported every already-registered hub as unregistered and refused it.
    members = parse_identifier_array(text, array)
    if members is not None:
        if name in members:
            return None
    elif re.search(rf'(?m)^\s*{re.escape(name)},\s*$', text):
        return None   # array not found (renamed?) — fall back to the line probe
    return ValidationFinding(
        code='route_not_registered', severity='block',
        message=f'{name} is not in {array} ({rel}); with dynamicParams=false the page does '
                'not build and {route} 404s. Pass --register-routes to splice it, or add the '
                'import + array row by hand before building.'.replace('{route}', draft.route),
        field_path='slug', detail=f'{rel}: add `{name},` to {array} and to the import block')


def splice_route_file(text: str, draft: PageDraft, array: str, banner: str) -> str:
    """Add the import + the route-array row. Idempotent; dynamic route files only."""
    name = draft.resolved_export_name
    members = parse_identifier_array(text, array)
    if members is not None and name in members:
        return text          # already registered (handles the single-line form)
    if members is None and re.search(rf'(?m)^\s*{re.escape(name)},\s*$', text):
        return text

    # The named-import block that ends in '...location-pages'. `[^}]*` (not a
    # non-greedy `.*?` under DOTALL) is load-bearing: the lazy form starts at the
    # FIRST `^import {` in the file and stretches across every intervening import
    # until it reaches the location-pages one, so the insertion point lands inside
    # `import { notFound } from 'next/navigation'` and the file stops parsing.
    m = re.search(r"(?m)^import \{([^}]*)\} from '([^']*location-pages)';", text)
    if not m:
        raise ValueError('no location-pages import block found in the route file')
    if not re.search(rf'(?m)^\s*{re.escape(name)},\s*$', m.group(1)):
        insert_at = m.start(1) + len(m.group(1))   # exactly the closing '}' of THIS block
        if '\n' in m.group(1):
            text = text[:insert_at] + f'  {name},\n' + text[insert_at:]
        else:                                      # single-line `import { a, b } from ...`
            text = text[:insert_at].rstrip() + f', {name} ' + text[insert_at:]

    a = re.search(rf'(?m)^const {re.escape(array)}\s*:\s*ServicePageType\[\]\s*=\s*\[', text)
    if not a:
        raise ValueError(f'route array {array} not found in the route file')
    close = text.index('\n];', a.end())
    addition = ''
    if banner and banner not in text[a.end():close]:
        addition += f'\n  {banner}'
    addition += f'\n  {name},'
    return text[:close] + addition + text[close:]


# ---------------------------------------------------------------------------
# C16 — inbound link wiring: a new spoke/subservice must NOT be an orphan
# ---------------------------------------------------------------------------
#
# THE Acme orphan bug, closed BY CONSTRUCTION. The emitter registers the new
# page's route, its registry row and (through the registry) its sitemap entry, so
# Google can crawl it — but nothing LINKS to it. orphan_check.py (never
# baselineable, blocking) then fails on a page that is in the sitemap with zero
# inbound internal links.
#
# How existing subservice pages receive their inbound link today: the PARENT page
# (the city spoke for a 3-segment subservice, the metro hub for a 2-segment one)
# carries a `type: 'related-services'` section whose `services: [...]` array holds
# one card per child, each a `<Link href="/child/route/">`. e.g. matthewsNC's
# "Matthews Siding and Gutter Services" grid is what links
# /charlotte-nc/matthews/siding-installation/. ServicePageRenderer renders EVERY
# entry in that array (no slice), so the link always reaches the built HTML.
#
# So a newly emitted spoke/subservice is wired the SAME way: one card is spliced
# into the parent's FIRST related-services array, pointing at the new route. The
# page is non-orphan the instant it ships. Idempotent (the card is added once,
# keyed on its url) and a hard REFUSAL when the parent cannot be found or has no
# related-services section — a page that cannot be wired is never shipped orphan.

_RELATED_SERVICES_RE = re.compile(r"type:\s*'related-services'")
_SERVICES_ARRAY_RE = re.compile(r'\bservices\s*:\s*\[')


def _ts_str(s: str) -> str:
    """A single-quoted TS string literal. Values are slug/city-derived (clean of
    quotes, em dashes and the invisible codepoints the scrubbers ban)."""
    return "'" + s.replace('\\', '\\\\').replace("'", "\\'") + "'"


def _related_services_array_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    """(open_bracket_idx, close_bracket_idx) of the FIRST related-services
    `services: [ ... ]` inside text[start:end], or None. String-aware."""
    m = _RELATED_SERVICES_RE.search(text, start, end)
    if not m:
        return None
    sm = _SERVICES_ARRAY_RE.search(text, m.end(), end)
    if not sm:
        return None
    arr_open = sm.end() - 1                       # the '[' itself
    arr_close = _skip_balanced(text, arr_open, len(text)) - 1   # the matching ']'
    if arr_close <= arr_open or arr_close >= end:
        return None
    return arr_open, arr_close


def _inbound_card(draft: PageDraft) -> str:
    """The related-services card literal that links a page's parent to it.

    Title and description are derived from the slug leaf + city only — verbatim
    routing facts, never an authored claim. The icon is a neutral service glyph.
    """
    leaf = (draft.segments[-1] if draft.segments else '').replace('-', ' ').strip()
    svc = ' '.join(w.capitalize() for w in leaf.split()) if leaf else 'Service'
    city = (draft.city or '').strip()
    title = f'{svc} {city}'.strip()
    desc = f'{svc} for {city} homes.' if city else f'{svc}.'
    return (f'{{ title: {_ts_str(title)}, description: {_ts_str(desc)}, '
            f'url: {_ts_str(draft.route)}, icon: {_ts_str("fas fa-screwdriver-wrench")} }}')


def orphan_wire_finding(draft: PageDraft, project: Path, target_file: str,
                        staged: dict[Path, str] | None = None) -> ValidationFinding | None:
    """The C16 orphan-wireability check as a pre-write finding.

    Reads the target data file as it currently stands — the version staged earlier
    in this same batch if present, else the on-disk copy — and reports the BLOCK
    that wire_inbound_link would raise, without mutating anything. None means the
    page can be (or already is) wired non-orphan.
    """
    if draft.page_kind not in ('spoke', 'subservice') or len(draft.segments) < 2:
        return None
    data_path = project / target_file
    text = (staged or {}).get(data_path)
    if text is None:
        if not data_path.is_file():
            return None                          # data_file_missing handled elsewhere
        text = data_path.read_text(encoding='utf-8', errors='replace')
    _, finding = wire_inbound_link(text, draft)
    return finding


def wire_inbound_link(text: str, draft: PageDraft) -> tuple[str, ValidationFinding | None]:
    """Splice one inbound related-services card into the new page's PARENT entry.

    Returns (new_text, finding). finding is None on success (including the
    idempotent no-op when the link already exists); it is a BLOCK when the page
    cannot be wired non-orphan (no parent entry, or the parent has no
    related-services section to hang the link on).

    Only spoke/subservice pages have a parent inside the location data; a 1-segment
    hub is linked from the state/home chrome and is out of scope here (and flagged
    separately by new_metro_hub).
    """
    if draft.page_kind not in ('spoke', 'subservice') or len(draft.segments) < 2:
        return text, None

    parent_slug = '/'.join(draft.segments[:-1])
    parent = next((e for e in parse_service_pages(text, '') if e.slug == parent_slug), None)
    if parent is None:
        return text, ValidationFinding(
            code='orphan_no_parent', severity='block',
            message=f'{draft.route} would be an ORPHAN: its parent page /{parent_slug}/ has no '
                    'ServicePage entry to carry an inbound related-services link. Emit the '
                    'parent first, or the page ships crawlable with zero inbound links (the '
                    'Acme orphan bug orphan_check.py refuses).',
            field_path='slug')

    span = _entry_span(text, parent.export_name)
    if span is None:                              # parsed but unspannable — defensive
        return text, ValidationFinding(
            code='orphan_no_parent', severity='block',
            message=f'{draft.route}: parent entry {parent.export_name} could not be located '
                    'to wire an inbound link', field_path='slug')
    start, end = span

    arr = _related_services_array_span(text, start, end)
    if arr is None:
        return text, ValidationFinding(
            code='orphan_no_related_services', severity='block',
            message=f'{draft.route} would be an ORPHAN: parent /{parent_slug}/ '
                    f'({parent.export_name}) has no related-services section to carry the '
                    'inbound link. Add one to the parent before emitting this child.',
            field_path='slug')
    arr_open, arr_close = arr

    # Idempotent: the child is wired once, keyed on its route.
    if f'url: {_ts_str(draft.route)}' in text[arr_open:arr_close]:
        return text, None

    inner = text[arr_open + 1:arr_close]
    indent_m = re.search(r'\n([ \t]*)\{', inner)
    indent = indent_m.group(1) if indent_m else '        '
    close_m = re.search(r'\n([ \t]*)$', inner)
    close_indent = close_m.group(1) if close_m else '      '

    trimmed = inner.rstrip()
    if trimmed and not trimmed.endswith(','):
        trimmed += ','
    new_inner = f'{trimmed}\n{indent}{_inbound_card(draft)},\n{close_indent}'
    new_text = text[:arr_open + 1] + new_inner + text[arr_close:]
    return new_text, None


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

def atomic_write(path: Path, content: str) -> None:
    """Temp file in the SAME directory + os.replace: an atomic rename on POSIX.

    Writing in place would leave a half-written 21,844-line data file if the
    process died mid-write, and that file is the client's whole site.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def unified_diff(before: str, after: str, label: str) -> str:
    return ''.join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f'a/{label}', tofile=f'b/{label}', n=2))


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

class EmitResult:
    """The outcome of one emit run, per page.

    THREE page outcomes, not two:
      refused  a BLOCK finding — would ship harm. Not written, not fixable here.
      held     a CURATE finding — a quality decision. Not written either, but it
               lands in docs/briefs/_curation.md with a concrete proposed fix, and
               it does NOT stop any other page emitting.
      written/noop/flagged  the page emitted.
    """

    def __init__(self) -> None:
        self.refused: list[tuple[str, list[ValidationFinding]]] = []
        self.held: list[tuple[str, list[ValidationFinding]]] = []
        self.flagged: list[tuple[str, list[ValidationFinding]]] = []
        self.written: list[str] = []
        self.noop: list[str] = []
        self.autofixes: dict[str, list[str]] = {}
        self.diffs: dict[str, str] = {}
        self.notes: list[str] = []

    @property
    def exit_code(self) -> int:
        """The single number an orchestrator may branch on. Most severe wins.

        Each outcome owns a DISTINCT code. Overloading one code across two
        outcomes is the defect class that produced the old 3-vs-9 refusal bug
        (M1) and the old 1-for-both-flagged-and-held bug (M3): a workflow
        branching on status alone could not tell "shipped" from "did not ship".

            9   refused  — a BLOCK finding. Nothing was written for that page.
            15  held     — a CURATE finding. The page did NOT ship; its siblings
                           may have. Needs one human yes/no, not an upstream fix.
            1   flagged  — everything shipped; WARN flags ride along in the ledger.
            0   clean     — everything shipped, nothing to acknowledge.
        """
        # 9, not 3: __init__.py, SPEC-emitter §7 and brief.py all document 9 as
        # "refused to emit". The old 3 collided with forbidden-sweep's code and
        # made a refusal unreadable to any orchestrator branching on exit status.
        if self.refused:
            return 9
        # 15, not 1: a held page did NOT ship, and that is a materially different
        # cycle outcome from "shipped with warn flags". 15 is the first code free
        # of the gate registry (1-10) and pipeline/audit/preflight.py (11-14).
        if self.held:
            return HELD_FOR_CURATION_EXIT
        # Everything emitted. WARN flags are attached but nothing was withheld.
        return 1 if self.flagged else 0


def emit(drafts: list[tuple[PageDraft, str]],
         decisions: Decisions,
         project: Path,
         cfg: dict[str, Any] | None,
         dry_run: bool = True,
         register_routes: bool = False,
         banned_file_text: str = '') -> EmitResult:
    """Validate every draft; emit the ones that are emittable, per page.

    PER-PAGE INDEPENDENCE. One page's finding never suppresses another page's
    emission. The old all-or-nothing rule was justified by sibling-overlap
    coherence — but a refused page is never added to the sibling corpus, so the
    pages that DO land are measured against exactly the set that will exist. With
    B1's live corpus in place the coherence argument is satisfied directly, and
    "0 emitted, do it manually" stops being the only possible cycle output.

    Three outcomes per page: emitted (with or without warn flags), HELD for
    curation (a quality decision, page does not ship, proposed fix queued), or
    REFUSED (a block — would ship harm).
    """
    result = EmitResult()
    staged: dict[Path, str] = {}
    originals: dict[Path, str] = {}
    today = date.today().isoformat()
    banner = BANNER.format(date=today)

    # ---- B1: seed the sibling corpus from the client's LIVE pages -----------
    # Not `{}`. An empty seed made §21 duplicate detection batch-scoped, so two
    # sequential single-page runs wrote a 0.99-overlap duplicate unblocked.
    # EVERY registry data file, not only the ones this batch writes into: §21 is a
    # sitewide gate, and a location page that duplicates a service page is exactly
    # the finding it exists to raise.
    corpus_files = sorted(_repo_layout.active().data_file_registry)
    siblings: dict[str, str] = live_sibling_corpus(project, corpus_files)
    if siblings:
        result.notes.append(
            f'sibling corpus: {len(siblings)} live page(s) from '
            f'{", ".join(f for f in corpus_files if (project / f).is_file())} + this batch')
    else:
        # Loud, not silent: an empty corpus is exactly the B1 failure mode.
        result.notes.append(
            'WARNING: sibling corpus is EMPTY — no live ServicePage entries were '
            f'parsed from {", ".join(corpus_files)} under {project}. §21 duplicate '
            'detection is batch-scoped only for this run.')

    for draft, target_file in drafts:
        draft, applied = validators.apply_autofixes(draft)
        if applied:
            result.autofixes[draft.slug] = applied

        findings = validators.validate(draft, cfg, siblings, banned_file_text)
        findings += ledger_findings(draft, decisions)
        rf = route_registration_finding(draft, project)
        if rf and not register_routes:
            findings.append(rf)
        # C16 — a spoke/subservice that cannot be wired non-orphan is REFUSED, not
        # shipped into the sitemap with zero inbound links. Checked against the data
        # file as it stands (staged in this batch, else on disk) so a parent emitted
        # earlier in the same run counts.
        of = orphan_wire_finding(draft, project, target_file, staged)
        if of is not None:
            findings.append(of)
        findings = apply_severity_policy(findings)

        hard = [f for f in findings if f.is_block]
        curation = [f for f in findings if f.is_curate]
        soft = [f for f in findings if f.severity == 'warn'
                and not decisions.acknowledged(draft.slug, f.code)]

        if hard:
            # A block is never waivable and never proposed a fix — it is harm.
            result.refused.append((draft.slug, hard + curation))
            continue
        if curation:
            result.held.append((draft.slug, [
                replace(f, proposed_fix=validators.propose_fix(draft, f))
                for f in curation]))
            continue
        if soft:
            result.flagged.append((draft.slug, soft))

        data_path = project / target_file
        if data_path not in originals:
            if not data_path.exists():
                result.refused.append((draft.slug, [ValidationFinding(
                    code='data_file_missing', severity='block',
                    message=f'{target_file} not found under {project}')]))
                continue
            originals[data_path] = data_path.read_text(encoding='utf-8')
            staged[data_path] = originals[data_path]

        registry = DATA_FILE_REGISTRY[target_file]
        before = staged[data_path]
        after = splice_entry(before, draft, registry, banner)
        # Wire the inbound link into the parent, in the SAME transaction as the entry
        # + registry row (C16). Wireability was already validated above, so this
        # succeeds; the defensive refusal guards against a batch-ordering surprise
        # and never stages a half-wired page (after is local until assigned).
        after, orphan_finding = wire_inbound_link(after, draft)
        if orphan_finding is not None:
            result.flagged = [(s, f) for s, f in result.flagged if s != draft.slug]
            result.refused.append((draft.slug, [orphan_finding]))
            continue
        assert_balanced_ts(after)
        staged[data_path] = after
        if after == before:
            result.noop.append(draft.slug)
        else:
            result.written.append(draft.slug)

        if register_routes and draft.route_array:
            rel = ROUTE_FILES.get(draft.route_array)
            if rel:
                rpath = project / rel
                if '[' not in rel:
                    raise ValueError(f'refusing to edit non-dynamic route file {rel} (C17)')
                if rpath not in originals:
                    originals[rpath] = rpath.read_text(encoding='utf-8')
                    staged[rpath] = originals[rpath]
                staged[rpath] = splice_route_file(staged[rpath], draft,
                                                  draft.route_array, banner)

        bpath = project / brief_path(draft)
        staged[bpath] = to_brief_json(draft)
        if bpath not in originals:
            originals[bpath] = bpath.read_text(encoding='utf-8') if bpath.exists() else ''

        siblings[draft.route] = validators.projected_text(draft)

    # ---- the curation queue: "N emitted, M awaiting a yes/no" ---------------
    # Rendered on EVERY run, including a clean one. Writing it only when something
    # is held would leave the previous cycle's queue on disk claiming pages are
    # outstanding after they have been fixed — a stale queue is worse than none.
    qpath = project / CURATION_QUEUE
    if drafts:
        staged[qpath] = render_curation_queue(result, today)
        if qpath not in originals:
            originals[qpath] = qpath.read_text(encoding='utf-8') if qpath.exists() else ''

    for path, after in staged.items():
        rel = str(path.relative_to(project)) if path.is_relative_to(project) else str(path)
        if originals.get(path, '') != after:
            result.diffs[rel] = unified_diff(originals.get(path, ''), after, rel)

    if not dry_run:
        for path, content in staged.items():
            if originals.get(path, '') != content:
                atomic_write(path, content)
    return result


# ---------------------------------------------------------------------------
# The curation queue — the artifact that turns "0, do it manually" into a yes/no
# ---------------------------------------------------------------------------

#: Markdown, not JSON, and NOT `*.json` — brief_fanout_check globs
#: `docs/briefs/**/*.json`, so a queue file with a .json suffix would be read as
#: a malformed brief and fail the gate it exists to keep green.
CURATION_QUEUE = 'docs/briefs/_curation.md'


def render_curation_queue(result: EmitResult, today: str) -> str:
    """One row per HELD page: the finding, the offending text, a proposed fix.

    Refused (block-class) pages are listed too, but WITHOUT a proposed fix — a
    block means the emitter cannot produce correct output and "accept this
    suggestion" is not an available move.
    """
    lines = [
        f'# Curation queue — {today}',
        '',
        f'{len(result.written) + len(result.noop)} page(s) emitted · '
        f'{len(result.held)} awaiting a yes/no · {len(result.refused)} refused.',
        '',
        'Written by `pipeline/generate/emit_ts.py`. Every page below was NOT written.',
        'A HELD page needs one decision from you; a REFUSED page needs an upstream fix.',
        '',
    ]
    if not result.held and not result.refused:
        lines += ['Nothing is outstanding. Every draft in the last run emitted.', '']

    if result.held:
        lines += ['## Held for curation (page does not ship until resolved)', '']
        for slug, findings in result.held:
            lines += [f'### `/{slug}/`', '']
            for f in findings:
                lines.append(f'- **{f.code}** ({f.field_path or "—"}) — {f.message}')
                if f.detail:
                    lines.append(f'  - offending: {f.detail}')
                if f.proposed_fix:
                    lines.append(f'  - **proposed fix:** {f.proposed_fix}')
                lines.append('  - decision: [ ] accept  [ ] reject  [ ] rewrite upstream')
            lines.append('')

    if result.refused:
        lines += ['## Refused (blocking — would ship harm, not waivable)', '']
        for slug, findings in result.refused:
            lines += [f'### `/{slug}/`', '']
            for f in findings:
                lines.append(f'- **{f.severity.upper()} {f.code}** '
                             f'({f.field_path or "—"}) — {f.message}')
                if f.detail:
                    lines.append(f'  - offending: {f.detail}')
            lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(result: EmitResult, dry_run: bool, verbose: bool = False) -> None:
    mode = 'DRY RUN' if dry_run else 'WRITE'
    # "emitted" = every page that produced artifacts, whether or not warn flags
    # rode along. A held or refused page is NOT emitted — it did not ship.
    emitted = len(result.written) + len(result.noop)
    print(f'emit_ts ({mode}): {emitted} emitted '
          f'({len(result.written)} changed, {len(result.noop)} already current, '
          f'{len(result.flagged)} carrying warn flags), '
          f'{len(result.held)} held for curation (did NOT ship), '
          f'{len(result.refused)} blocked (refused, nothing written)')

    for note in result.notes:
        print(f'  [note] {note}')
    for slug, applied in result.autofixes.items():
        for line in applied:
            print(f'  [autofix] {slug}: {line}')
    for slug, findings in result.flagged:
        for f in findings:
            print(f'  [flag] {slug}: {f}')
    for slug, findings in result.held:
        for f in findings:
            print(f'  [HELD] {slug}: {f}')
            if f.proposed_fix:
                print(f'          proposed fix: {f.proposed_fix}')
    for slug, findings in result.refused:
        for f in findings:
            print(f'  [REFUSED] {slug}: {f}')

    if verbose or dry_run:
        for rel, diff in result.diffs.items():
            print(f'\n--- diff: {rel} ---')
            print(diff if len(diff) < 20000 else diff[:20000] + '\n... (truncated)')

    if result.held:
        print(f'\n{len(result.held)} page(s) were HELD and did NOT ship. Exit '
              f'{HELD_FOR_CURATION_EXIT} is "requires acknowledgement", never green — see '
              f'{CURATION_QUEUE} for the finding, the offending text and a concrete '
              'proposed fix per page.')
    if result.refused:
        print(f'\n{len(result.refused)} page(s) were REFUSED and nothing was written for '
              'them. Resolve every blocking finding upstream and re-run (a block is never '
              'waivable in decisions.json).')

    # Belt and braces for CI: a single stable, greppable line carrying the same
    # verdict as the exit status, so a workflow can cross-check the two and fail
    # loudly if they ever disagree. Keep this format STABLE — it is parsed.
    print(f'\nEMIT_SUMMARY emitted={emitted} held={len(result.held)} '
          f'blocked={len(result.refused)} flagged={len(result.flagged)} '
          f'exit={result.exit_code}')


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _fixture_spoke() -> PageDraft:
    """A capsule-complete Mode-A draft on a slug that does NOT exist in the repo.

    models.build_fixture() deliberately reuses the LIVE matthewsGutterReplacement
    slug so its output can be diffed against a real neighbour; that makes it
    unusable for a write test (it would replace a shipped page). This re-points it
    at an unused sibling slug and adds the TL;DR node the fixture lacks.
    """
    from pipeline.generate.models import build_fixture
    draft = build_fixture()
    draft = validators._with_tldr_node(draft)
    return replace(
        draft,
        url_path='charlotte-nc/matthews/gutter-guard-installation',
        export_name='',                       # re-derive from the new slug
        service='Gutter Guard Installation',
        meta_title='Gutter Guard Installation Matthews NC | Acme',
        title='Gutter Guard Installation in Matthews, NC',
    )


def self_test(project: Path, verbose: bool = False) -> list[str]:
    fails: list[str] = []
    cfg = None
    try:
        from pipeline.lib.common import load_config
        cfg = load_config(str(project))
        _repo_layout.activate(cfg)
    except SystemExit:
        fails.append(f'could not load client config from {project}')
        return fails

    data_rel = DEFAULT_DATA_FILE
    real_data = project / data_rel
    if not real_data.exists():
        return [f'{data_rel} not found under {project}']

    from pipeline.generate.models import build_fixture

    before_bytes = real_data.read_text(encoding='utf-8')

    # ---- (0) DRY RUN against the REAL Acme data, 2 entries -----------------
    # Deliberately one of each kind: an in-place REPLACE of a shipped entry, and
    # an INSERT of a new one. The two hardest diffs to get right are exactly these.
    live = validators._with_tldr_node(build_fixture())   # live matthewsGutterReplacement slug
    new = _fixture_spoke()                               # unused sibling slug

    res_replace = emit([(live, data_rel)], Decisions({}), project, cfg, dry_run=True)
    if res_replace.refused:
        fails.append('dry run (replace): unexpected refusal: '
                     + '; '.join(f.code for _, fs in res_replace.refused for f in fs))
    if data_rel not in res_replace.diffs:
        fails.append('dry run (replace): no diff produced for the shipped entry')
    else:
        d = res_replace.diffs[data_rel]
        # A replace must not add an entry or a registry row: the export line and
        # the `  matthewsGutterReplacement,` row are CONTEXT, never '+' lines.
        if re.search(r'(?m)^\+export const \w+: ServicePage', d):
            fails.append('dry run (replace): a duplicate entry was appended instead of '
                         'the existing one being replaced in place')
        if re.search(r'(?m)^\+\s*matthewsGutterReplacement,$', d):
            fails.append('dry run (replace): a duplicate registry row was added')
        if not re.search(r'(?m)^-\s+lastUpdated:', d):
            fails.append('dry run (replace): the shipped entry body was not rewritten')

    res_insert = emit([(new, data_rel)], Decisions({}), project, cfg,
                      dry_run=True, register_routes=True)
    if res_insert.refused:
        fails.append('dry run (insert): unexpected refusal: '
                     + '; '.join(f.code for _, fs in res_insert.refused for f in fs))
    if data_rel not in res_insert.diffs:
        fails.append('dry run (insert): no diff produced for the new entry')
    if verbose:
        for label, r in (('replace', res_replace), ('insert', res_insert)):
            print(f'\n===== dry-run diff [{label}] =====')
            print(r.diffs.get(data_rel, '(none)')[:6000])

    # ---- (0a) route registration is a BLOCK, not a silent 404 ---------------
    res_unreg = emit([(new, data_rel)], Decisions({}), project, cfg,
                     dry_run=True, register_routes=False)
    codes = {f.code for _, fs in res_unreg.refused for f in fs}
    if 'route_not_registered' not in codes:
        fails.append(f'dry run: an unregistered route was not blocked (got {sorted(codes)})')

    # ---- (0b) two pages built from ONE source refuse on sibling overlap -----
    # C6 with Acme's 'franchise' topology resolves to a 0.60 threshold, so two
    # pages sharing a dossier cannot both ship. Proving it here is the point.
    res_dupe = emit([(live, data_rel), (new, data_rel)], Decisions({}), project, cfg,
                    dry_run=True, register_routes=True)
    dupe_codes = {f.code for _, fs in res_dupe.refused for f in fs}
    if 'duplicate_of_sibling' not in dupe_codes:
        fails.append('C6: two near-identical siblings were not refused '
                     f'(got {sorted(dupe_codes)})')
    if res_dupe.exit_code != 9:
        fails.append(f'C6: exit code {res_dupe.exit_code}, expected 9')

    # ---- (1) REAL write of ONE spoke entry into a COPY -----------------------
    with tempfile.TemporaryDirectory(prefix='emit-ts-selftest-') as tmp:
        sandbox = Path(tmp) / 'acme-roofing-site'
        (sandbox / 'src' / 'data').mkdir(parents=True)
        (sandbox / 'docs').mkdir(parents=True)
        shutil.copy2(real_data, sandbox / data_rel)
        shutil.copy2(project / 'docs' / 'client-config.yml', sandbox / 'docs' / 'client-config.yml')
        for array, rel in ROUTE_FILES.items():
            src = project / rel
            if src.exists():
                dst = sandbox / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        one = [(_fixture_spoke(), data_rel)]
        wres = emit(one, Decisions({}), sandbox, cfg, dry_run=False, register_routes=True)
        if wres.refused:
            fails.append('write: refused unexpectedly: '
                         + '; '.join(str(f) for _, fs in wres.refused for f in fs))
        written = (sandbox / data_rel).read_text(encoding='utf-8')

        # (a) still balanced TS, and the untouched region is byte-identical
        try:
            assert_balanced_ts(written)
        except AssertionError as exc:
            fails.append(f'write: emitted file is not balanced TS: {exc}')
        if len(written) <= len(before_bytes):
            fails.append('write: file did not grow — the entry was not inserted')
        name = _fixture_spoke().resolved_export_name
        if f'export const {name}: ServicePage = {{' not in written:
            fails.append(f'write: entry {name} not found in the written file')
        if not re.search(rf'(?m)^  {re.escape(name)},$', written):
            fails.append(f'write: registry row for {name} not found (orphan)')
        # every pre-existing entry survived verbatim
        for existing in re.findall(r'(?m)^export const (\w+): ServicePage = \{', before_bytes):
            if f'export const {existing}: ServicePage = {{' not in written:
                fails.append(f'write: pre-existing entry {existing} was lost')
                break
        # (a2) the route file: additions ONLY, every original line intact.
        # Regression guard for the lazy-DOTALL import regex that spliced the row
        # into `import { notFound } from 'next/navigation'` and broke the parse.
        array = _fixture_spoke().route_array
        rel_route = ROUTE_FILES.get(array or '', '')
        if rel_route:
            orig_route = (project / rel_route).read_text(encoding='utf-8').splitlines()
            new_route = (sandbox / rel_route).read_text(encoding='utf-8').splitlines()
            if new_route[:1] != orig_route[:1]:
                fails.append(f'route file: line 1 was modified: {new_route[0]!r}')
            missing = [ln for ln in orig_route if ln not in new_route]
            if missing:
                fails.append(f'route file: original line(s) lost or rewritten: {missing[:2]}')
            added = [ln for ln in new_route if ln not in orig_route]
            if not any(ln.strip() == f'{name},' for ln in added):
                fails.append(f'route file: {name} was not added to {array}')
            for ln in added:
                if 'import' in ln or "from '" in ln:
                    fails.append(f'route file: an import line was rewritten: {ln!r}')

        brief = sandbox / brief_path(_fixture_spoke())
        if not brief.exists():
            fails.append(f'write: brief {brief_path(_fixture_spoke())} was not written')
        else:
            payload = json.loads(brief.read_text())
            for key in ('fanout', 'capsule', 'semantic_triples',
                        'proprietary_variable', 'intent'):
                if key not in payload:
                    fails.append(f'write: brief is missing required key {key!r}')

        # (b) re-running is a no-op
        snapshot = {p: p.read_text(encoding='utf-8')
                    for p in sandbox.rglob('*') if p.is_file()}
        rres = emit([(_fixture_spoke(), data_rel)], Decisions({}), sandbox, cfg,
                    dry_run=False, register_routes=True)
        if rres.refused:
            fails.append('re-run: refused on the second pass')
        for p, text in snapshot.items():
            if p.read_text(encoding='utf-8') != text:
                fails.append(f're-run was not a no-op: {p.relative_to(sandbox)} changed')
        if rres.written:
            fails.append(f're-run reported writes: {rres.written}')
        if _fixture_spoke().slug not in rres.noop:
            fails.append('re-run did not report the entry as already current')

        # (c) a draft with an unresolved blocking finding is refused, writes nothing
        snapshot = {p: p.read_text(encoding='utf-8')
                    for p in sandbox.rglob('*') if p.is_file()}
        bad = replace(_fixture_spoke(),
                      url_path='charlotte-nc/matthews/gutter-guard-cleaning',
                      export_name='',
                      meta_description='Gutter guards installed for $1,200 in Matthews, NC.')
        bres = emit([(bad, data_rel)], Decisions({}), sandbox, cfg,
                    dry_run=False, register_routes=True)
        if not bres.refused:
            fails.append('blocking: a draft with a forbidden dollar figure was NOT refused')
        elif 'forbidden_phrase' not in {f.code for _, fs in bres.refused for f in fs}:
            fails.append('blocking: refusal was for the wrong reason: '
                         + '; '.join(f.code for _, fs in bres.refused for f in fs))
        if bres.exit_code != 9:
            fails.append(f'blocking: exit code {bres.exit_code}, expected 9')
        # No PAGE artifact may be written for a refused draft. The curation queue is
        # deliberately exempt: it is the report OF the refusal, and suppressing it is
        # how a cycle ends as a silent "0 emitted" with no machine-readable reason.
        for p, text in snapshot.items():
            if p == sandbox / CURATION_QUEUE:
                continue
            if p.read_text(encoding='utf-8') != text:
                fails.append(f'blocking: {p.relative_to(sandbox)} was modified despite a refusal')
        if (sandbox / brief_path(bad)).exists():
            fails.append('blocking: a brief was written for a refused draft')
        queue = sandbox / CURATION_QUEUE
        if not queue.exists():
            fails.append(f'blocking: no {CURATION_QUEUE} was written for a refused draft')
        elif bad.slug not in queue.read_text(encoding='utf-8'):
            fails.append(f'blocking: {CURATION_QUEUE} does not name the refused page {bad.slug}')

        # ---- (d) TRIAGE: per-page independence + the held/refused/emitted split
        # One page's finding must never suppress another page's emission, and a
        # CURATE finding must hold its own page WITHOUT refusing the batch.
        fresh = Path(tmp) / 'independence'
        (fresh / 'src' / 'data').mkdir(parents=True)
        (fresh / 'docs').mkdir(parents=True)
        shutil.copy2(real_data, fresh / data_rel)
        shutil.copy2(project / 'docs' / 'client-config.yml', fresh / 'docs' / 'client-config.yml')
        for array, rel in ROUTE_FILES.items():
            src = project / rel
            if src.exists():
                dst = fresh / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        good = _fixture_spoke()
        harm = replace(good, url_path='charlotte-nc/matthews/gutter-guard-repair',
                       export_name='',
                       meta_description='Gutter guards installed for $1,200 in Matthews, NC.')
        hold = replace(good, url_path='charlotte-nc/matthews/gutter-guard-services',
                       export_name='',
                       meta_title='Gutter Guard Cleaning & Inspection & Repair Services in '
                                  'Matthews, North Carolina | Acme Roofing')
        # `hold` and `harm` are near-duplicates of `good` by construction, so the
        # ORDER matters: the two non-emitting pages go first, and neither may be
        # added to the sibling corpus. If either were, `good` would be refused.
        ires = emit([(hold, data_rel), (harm, data_rel), (good, data_rel)],
                    Decisions({}), fresh, cfg, dry_run=False, register_routes=True)
        if good.slug not in ires.written:
            fails.append('independence: the clean page did not emit alongside a refused '
                         f'and a held sibling (written={ires.written}, '
                         f'held={[s for s, _ in ires.held]}, '
                         f'refused={[s for s, _ in ires.refused]})')
        if harm.slug not in {s for s, _ in ires.refused}:
            fails.append('independence: the forbidden-phrase page was not REFUSED')
        if hold.slug not in {s for s, _ in ires.held}:
            fails.append('independence: the over-length metaTitle page was not HELD '
                         f'(held={[s for s, _ in ires.held]})')
        if (fresh / brief_path(hold)).exists() or (fresh / brief_path(harm)).exists():
            fails.append('independence: a brief was written for a page that did not ship')
        if not (fresh / brief_path(good)).exists():
            fails.append('independence: the clean page emitted without its brief')
        qtext = (fresh / CURATION_QUEUE).read_text(encoding='utf-8')
        if hold.slug not in qtext or 'proposed fix' not in qtext:
            fails.append('independence: the curation queue has no proposed fix for the held page')
        if ires.exit_code != 9:
            fails.append(f'independence: exit {ires.exit_code}, expected 9 (a BLOCK is present)')

        # ---- (e) B1: the sibling corpus is seeded from the LIVE repo -----------
        # A second, SEPARATE invocation must see the page the first one wrote.
        # Seeding this dict empty is what let two sequential runs ship a duplicate.
        corpus = live_sibling_corpus(fresh, {data_rel})
        if good.route not in corpus:
            fails.append('B1: the page just written is absent from the live sibling corpus')
        if len(corpus) < 50:
            fails.append(f'B1: live sibling corpus has only {len(corpus)} page(s); the real '
                         'Acme data file carries 71')
        dupe = replace(good, url_path='charlotte-nc/matthews/gutter-guard-claims',
                       export_name='', service='Gutter Guard Claims',
                       meta_title='Gutter Guard Claims Matthews NC | Acme',
                       title='Gutter Guard Claims in Matthews, NC')
        dres = emit([(dupe, data_rel)], Decisions({}), fresh, cfg,
                    dry_run=False, register_routes=True)
        if 'duplicate_of_sibling' not in {f.code for _, fs in dres.refused for f in fs}:
            fails.append('B1: a near-duplicate of a page written by a PREVIOUS run was not '
                         f'refused (refused={[f.code for _, fs in dres.refused for f in fs]})')
        if dres.written:
            fails.append(f'B1: the cross-run duplicate was written anyway: {dres.written}')

        # ---- (f) B2: the allow-list check agrees with brief.py -----------------
        from pipeline.generate.models import check_proprietary_variable, resolve_brief_allowlist
        allow = resolve_brief_allowlist({'brief': {'proprietary_variables': ['neighborhoods']}})
        _, bogus = check_proprietary_variable(['fabricated_nonsense_token'], allow)
        if not bogus or bogus[0].code != 'proprietary_variable_not_in_allowlist':
            fails.append('B2: an out-of-allow-list proprietary variable was not blocked')
        elif not bogus[0].is_block:
            fails.append('B2: the allow-list violation is not BLOCK severity')
        chosen, clean_f = check_proprietary_variable(['neighborhoods'], allow)
        if clean_f or chosen != 'neighborhoods':
            fails.append(f'B2: an allow-listed variable was rejected ({chosen!r}, {clean_f})')

    # ---- (2) the real client repo was never touched --------------------------
    if real_data.read_text(encoding='utf-8') != before_bytes:
        fails.append('SELF-TEST MUTATED THE REAL CLIENT FILE — this is a hard bug')
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Emit validated PageDrafts into the client repo as typed TS data.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
exit codes (each outcome owns a distinct code so CI can branch on status alone):
   0   every draft emitted clean
   1   emitted with curation flags - EVERYTHING SHIPPED, warn flags in the ledger
   2   usage / input / dependency error
   9   refused to emit - a BLOCK finding; nothing written for that page
  {HELD_FOR_CURATION_EXIT}   one or more pages HELD for curation - emitted what it could, the held
       pages did NOT ship. NOT green. See docs/briefs/_curation.md for the
       finding, the offending text and a concrete proposed fix per page.

Most severe wins: refused (9) outranks held ({HELD_FOR_CURATION_EXIT}) outranks flagged (1).
The stdout line `EMIT_SUMMARY emitted=.. held=.. blocked=.. exit=..` carries the
same verdict in parseable form.""")
    ap.add_argument('drafts', nargs='?', help='drafts.json — a list of PageDraft objects')
    ap.add_argument('decisions', nargs='?', help='decisions.json — Alex\'s curation record')
    ap.add_argument('--project', required=True, help='client dir (holds docs/client-config.yml)')
    ap.add_argument('--dry-run', action='store_true',
                    help='validate and print the exact diff; write nothing')
    ap.add_argument('--limit', type=int, default=None, help='emit at most N drafts')
    ap.add_argument('--register-routes', action='store_true',
                    help='also splice the DYNAMIC route file so the page builds '
                         '(default: report the missing registration and refuse)')
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f'[ERROR] project dir not found: {project}', file=sys.stderr)
        return 2

    if args.self_test:
        fails = self_test(project, verbose=args.verbose)
        if fails:
            print('FAIL: emit_ts.py self-test')
            for f in fails:
                print(f'  {f}')
            return 9
        print('PASS: emit_ts.py self-test — dry run diffed 2 entries against real Acme '
              'data; one spoke written to a COPY (balanced TS, registry row present, brief '
              'valid); re-run was a byte-for-byte no-op; a blocking draft was refused with '
              'no page artifact touched; per-page independence holds (1 emitted alongside 1 '
              'HELD + 1 REFUSED sibling, exit 9, proposed fix queued); B1 — a near-duplicate '
              'of a page written by a PREVIOUS invocation was refused from the live sibling '
              'corpus; B2 — the shared allow-list check blocks an off-list proprietary '
              'variable; the real client file is unchanged.')
        return 0

    if not args.drafts:
        ap.error('drafts.json is required (or pass --self-test)')

    try:
        from pipeline.lib.common import load_config
        cfg = load_config(str(project))
        _repo_layout.activate(cfg)
    except SystemExit:
        return 2

    try:
        drafts = load_drafts(Path(args.drafts))
        decisions = Decisions.load(Path(args.decisions) if args.decisions else None)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'[ERROR] {exc}', file=sys.stderr)
        return 2

    if args.limit is not None:
        drafts = drafts[:args.limit]
    if not drafts:
        if args.limit is not None:
            print('emit_ts: no drafts to emit (--limit produced an empty set).')
            return 0
        # An empty drafts.json with no --limit means upstream distill segmented no
        # pages (e.g. an unrecognized handoff format). Refuse loudly rather than
        # report a clean emit that shipped nothing. Distinct code, matching
        # distill/preflight (docs/gate-reference.md exit-code registry).
        from pipeline.generate.distill import UNSEGMENTABLE_EXIT
        print('[REFUSED] emit_ts: drafts.json contains 0 pages — nothing to emit. '
              'Upstream distill segmented no pages (unrecognized handoff format?). '
              'Refusing to report a clean emit on an empty input.', file=sys.stderr)
        return UNSEGMENTABLE_EXIT

    banned = project / 'docs' / 'banned-phrases.txt'
    banned_text = banned.read_text(encoding='utf-8') if banned.exists() else ''

    result = emit(drafts, decisions, project, cfg, dry_run=args.dry_run,
                  register_routes=args.register_routes, banned_file_text=banned_text)
    report(result, args.dry_run, args.verbose)

    if not args.dry_run and not result.refused:
        print(f'\nWrote the working tree only. NOTHING was staged, committed or pushed — '
              f'review with `git -C {project} diff` before Alex merges.')
    return result.exit_code


if __name__ == '__main__':
    sys.exit(main())
