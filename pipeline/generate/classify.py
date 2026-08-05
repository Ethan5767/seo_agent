#!/usr/bin/env python3
"""
classify.py — NEW / UPDATE / SKIP / INVALID, decided against what already ships.

The emitter's job is to turn a messy DOCX into typed page data. This module is
the gate in front of that write: it answers "does this page already exist, and
if so has anything actually changed?" so a cycle can never silently DUPLICATE a
live page (two exports, same slug, one route wins, the other is dead weight) or
CLOBBER one (a re-run of last month's DOCX overwriting a hand-tuned entry with a
regenerated near-copy).

    NEW      no live entry claims this url_path        -> emit
    UPDATE   a live entry claims it AND content moved  -> emit over it (review the diff)
    SKIP     a live entry claims it and nothing moved  -> do not touch the repo
    INVALID  the url does not fit the client topology  -> never emit; report

Everything is read-only. This module parses TypeScript; it never executes it,
never writes TS, and never touches the client repo.

WHAT "ALREADY EXISTS" MEANS HERE
--------------------------------
Four independent sources of truth are indexed, because in this codebase they can
and do disagree — and the disagreements are exactly the bugs worth surfacing:

  1. src/data/location-pages.ts   `export const <name>: ServicePage = {...}`
  2. src/data/services.ts         same shape, the non-location service pages
  3. src/app/**/page.tsx          METRO_PAGES / SPOKE_PAGES / SUBSERVICE_PAGES
                                  route arrays (absent => dynamicParams=false => 404)
  4. out/sitemap.xml              what the last build actually shipped (optional)

An entry present in (1) but missing from (3) does not build. Present in (3) but
missing from `allLocationPages` builds, is crawlable, and has zero inbound links
— the orphan bug orphan_check.py exists to catch. Both are material: a draft
matching such an entry classifies UPDATE (reason `registration_repair`), never
SKIP, so the cycle repairs the registration instead of walking past it.

WHAT "MATERIAL DELTA" MEANS
---------------------------
A match is compared on three axes, cheapest first:

  a. the 5 SEO strings the renderer actually surfaces — title, metaTitle,
     metaDescription, hero.title, hero.description. ANY difference is material;
     these are the fields the whole pipeline exists to control.
  b. the structural shape — the ordered sequence of section `type` discriminants
     plus shared-builder calls. A reordered or re-typed page is a different page.
  c. the prose — Jaccard similarity over the set of normalized CONTENT strings
     (>= MIN_CONTENT_WORDS words; icon/url/enum strings filtered out). Below
     --similarity-threshold is material.

Whitespace, curly-vs-straight quotes, and en/em dashes are normalized away
before comparison, so a prettier reflow or an em-dash scrub is NOT a delta.
`lastUpdated` is deliberately NOT compared: it changes on every emit by
construction and would make every page look dirty forever.

THE TOPOLOGY GAP (read this before trusting an INVALID)
-------------------------------------------------------
`common.url_fits_topology` only models hub (1 segment) and spoke (2 segments).
Acme's topology is `franchise`, and the repo ships 24 THREE-segment sub-service
pages (`charlotte-nc/matthews/siding-installation`) that the helper therefore
calls invalid. That is a gap in the topology table, not 24 bad pages.

So a draft whose url fails `url_fits_topology` is INVALID *unless the live repo
already ships a page of the same shape class* (same segment count, and — at 3
segments — the same SUBSERVICE_SUFFIX_RE requirement). With that live precedent
the draft is classified normally and carries a `topology_gap` warning naming the
precedent. Pass --strict-topology to disable the precedent escape and take
url_fits_topology literally; that is the honest way to see how wide the gap is.

Exit codes:
    0  every draft classified, nothing needs a human
    1  at least one INVALID draft or at least one warning — review before emitting
    2  usage / dependency / unreadable-input error

Usage:
    classify.py drafts.json --project ../acme-roofing-site --out decisions.json
    classify.py --self-test --project ../acme-roofing-site
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

if __name__ == '__main__':  # pragma: no cover - direct-invocation bootstrap
    # Run as `python3 pipeline/generate/classify.py`, NOT `-m pipeline.generate.classify`:
    # the package __init__ re-exports models, so -m executes models' body twice under two
    # names and the two copies of Section fail isinstance against each other. Repo root has
    # to be importable before the `pipeline.*` imports below, hence the bootstrap here.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.lib.common import client_profile, load_config, resolve_repo_path, url_fits_topology

from pipeline.generate import repo_layout
from pipeline.generate.models import (
    ROUTE_ARRAY_BY_SEGMENTS,
    SUBSERVICE_SUFFIX_RE,
    BuilderCall,
    Capsule,
    FaqItem,
    Hero,
    HeroButton,
    PageDraft,
    Section,
    SemanticTriple,
    count_words,
    derive_export_name,
)

# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

NEW = 'NEW'
UPDATE = 'UPDATE'
SKIP = 'SKIP'
INVALID = 'INVALID'

DECISIONS = (NEW, UPDATE, SKIP, INVALID)

#: Prose similarity at or above this counts as "nothing moved". Not 1.0: a
#: regenerated page that differs only by a normalized quote or a re-wrapped
#: paragraph is the same page. Tunable per run via --similarity-threshold.
DEFAULT_SIMILARITY_THRESHOLD = 0.98

#: A string shorter than this many words is chrome (an icon name, a button
#: label, a state code), not prose, and is excluded from the fingerprint.
MIN_CONTENT_WORDS = 3

#: The renderer-visible SEO strings. Any difference here is material by
#: definition — these are the fields the pipeline exists to control.
SEO_FIELDS = ('title', 'metaTitle', 'metaDescription', 'hero.title', 'hero.description')

#: Deliberately NOT compared. `lastUpdated` moves on every emit by construction.
IGNORED_FIELDS = ('lastUpdated',)

#: Data files scanned for live `ServicePage` entries, in index order.
DATA_FILES = ('src/data/location-pages.ts', 'src/data/services.ts')

#: Route-array file -> the arrays declared in it. Missing from ALL of a depth's
#: arrays => generateStaticParams never emits the param => dynamicParams=false
#: => the route 404s.
ROUTE_ARRAY_FILES = {
    'src/app/[slug]/page.tsx': ('METRO_PAGES', 'SERVICE_PAGES'),
    'src/app/[slug]/[city]/page.tsx': ('SPOKE_PAGES',),
    'src/app/[slug]/[city]/[subservice]/page.tsx': ('SUBSERVICE_PAGES',),
}

#: Segment count -> the arrays that can satisfy registration at that depth.
#: One segment has TWO: Next 16 disallows sibling dynamic segments at the same
#: depth, so a single `[slug]` route serves BOTH global service pages and metro
#: hubs and unions SERVICE_PAGES with METRO_PAGES. Registration in EITHER is
#: sufficient; `ROUTE_ARRAY_BY_SEGMENTS` in models.py names only the canonical
#: one a NEW location page should be appended to.
ROUTE_ARRAYS_BY_SEGMENTS: dict[int, tuple[str, ...]] = {
    1: ('METRO_PAGES', 'SERVICE_PAGES'),
    2: ('SPOKE_PAGES',),
    3: ('SUBSERVICE_PAGES',),
}

#: The registry that feeds sitemap + hub grids + footers. Absent => orphan.
REGISTRY_ARRAYS = ('allLocationPages', 'allServices')

# Strings that are plumbing, never prose: icon tokens, urls, tel: links, image
# paths, css class names. Excluded from the content fingerprint on both sides.
#: The alphabet every TOPOLOGY_PATTERNS regex is built from. A segment outside
#: it can never fit any topology, and — critically — must never be waved through
#: by the shape-precedent escape below: `not a slug` and `charlotte-nc` are both
#: "1-segment", and precedent on segment COUNT alone would accept the former.
_SLUG_SEGMENT_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

_PLUMBING_RE = re.compile(
    r'^(?:'
    r'fas fa-[a-z0-9-]+'          # icon tokens
    r'|https?://\S*'              # absolute urls
    r'|tel:\S*'                   # phone links
    r'|mailto:\S*'
    r'|/\S*'                      # site-relative paths + image paths
    r'|btn-[a-z-]+'               # button class names
    r'|#[0-9a-fA-F]{3,8}'         # colors
    r')$'
)


# ---------------------------------------------------------------------------
# Text normalization — shared by both sides of every comparison
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')

# Curly quotes / dashes fold to ASCII so a typographic pass is not a "delta",
# and NBSP folds to a space so a copy-paste artifact is not a "delta" either.
_FOLD = {
    '‘': "'", '’': "'", '‚': "'", '‛': "'",
    '“': '"', '”': '"', '„': '"', '‟': '"',
    '–': '-', '—': '-', '―': '-', '−': '-',
    '…': '...', ' ': ' ', ' ': ' ', ' ': ' ',
}


def normalize_text(text: str) -> str:
    """Fold a rendered string to its comparable core.

    NFKC, strip markup, fold typographic punctuation to ASCII, drop zero-width
    and bidi codepoints (fingerprint_check's set — an invisible-codepoint scrub
    must not read as a content change), collapse whitespace, casefold.
    """
    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize('NFKC', text)
    text = _TAG_RE.sub(' ', text)
    text = ''.join(_FOLD.get(ch, ch) for ch in text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Cf')
    return _WS_RE.sub(' ', text).strip().casefold()


def normalize_url_path(url: str) -> str:
    """Any spelling of a route -> a bare slug with no leading or trailing slash.

    Absorbs the shapes a draft or a sitemap can hand us: absolute urls, missing
    or doubled slashes, an `index.html` tail, query strings, fragments, and
    stray case. `''` is the homepage and is returned as `''`.
    """
    if not url:
        return ''
    u = str(url).strip()
    u = u.split('#', 1)[0].split('?', 1)[0]
    u = re.sub(r'^[a-zA-Z][a-zA-Z0-9+.-]*://[^/]+', '', u)
    u = re.sub(r'/index\.html?$', '/', u, flags=re.I)
    u = re.sub(r'/{2,}', '/', u)
    return u.strip('/').casefold()


def route_of(slug: str) -> str:
    """Canonical path. Trailing slash is mandatory — the canonical is derived."""
    return f'/{slug}/' if slug else '/'


def shape_class(slug: str) -> str:
    """The url's structural class: how many segments, and (at 3) whether the
    tail carries the sub-service suffix `locationLabel()` needs."""
    segs = [s for s in slug.split('/') if s]
    n = len(segs)
    if n == 3:
        ok = bool(SUBSERVICE_SUFFIX_RE.search(segs[-1]))
        return f'3-segment{"" if ok else "-nosuffix"}'
    return f'{n}-segment'


# ---------------------------------------------------------------------------
# A tolerant TypeScript scanner
#
# Deliberately NOT a TS parser and NOT an evaluator: it walks the source with a
# string/template/comment-aware brace matcher and pulls out the handful of facts
# a classification needs. Anything it cannot read degrades to "unknown", never to
# a wrong answer — an unreadable entry is reported, not silently treated as
# absent (absent would mean NEW, which is how a duplicate gets written).
# ---------------------------------------------------------------------------

_OPENERS = {'{': '}', '[': ']', '(': ')'}
_CLOSERS = {'}', ']', ')'}


def _skip_trivia(src: str, i: int, end: int) -> int:
    """Advance past whitespace and both comment forms."""
    while i < end:
        ch = src[i]
        if ch.isspace():
            i += 1
        elif src.startswith('//', i):
            nl = src.find('\n', i)
            i = end if nl == -1 else nl + 1
        elif src.startswith('/*', i):
            close = src.find('*/', i + 2)
            i = end if close == -1 else close + 2
        else:
            return i
    return end


def _skip_string(src: str, i: int, end: int) -> int:
    """Advance past a ' " or ` literal, honouring escapes and `${}` nesting."""
    quote = src[i]
    i += 1
    while i < end:
        ch = src[i]
        if ch == '\\':
            i += 2
            continue
        if quote == '`' and src.startswith('${', i):
            i = _skip_balanced(src, i + 1, end)  # the interpolation's own braces
            continue
        if ch == quote:
            return i + 1
        i += 1
    return end


def _skip_balanced(src: str, i: int, end: int) -> int:
    """`i` points at an opener; return the index just past its match."""
    stack = [_OPENERS[src[i]]]
    i += 1
    while i < end and stack:
        ch = src[i]
        if ch in '\'"`':
            i = _skip_string(src, i, end)
            continue
        if src.startswith('//', i) or src.startswith('/*', i):
            i = _skip_trivia(src, i, end)
            continue
        if ch in _OPENERS:
            stack.append(_OPENERS[ch])
            i += 1
            continue
        if ch in _CLOSERS:
            if stack and ch == stack[-1]:
                stack.pop()
            i += 1
            continue
        i += 1
    return i


_KEY_RE = re.compile(r'''(?:(['"])(?P<q>(?:\\.|(?!\1).)*)\1|(?P<b>[A-Za-z_$][\w$]*))\s*:''')


def _object_keys(src: str, open_idx: int) -> dict[str, tuple[int, int]]:
    """Map each DEPTH-1 key of the object literal at `open_idx` to its value span.

    Nested objects are skipped wholesale, so `sections[].title` never shadows the
    entry's own `title`. Later duplicate keys win, matching JS semantics.
    """
    end = _skip_balanced(src, open_idx, len(src)) - 1  # index of the closing '}'
    out: dict[str, tuple[int, int]] = {}
    i = open_idx + 1
    while i < end:
        i = _skip_trivia(src, i, end)
        if i >= end:
            break
        if src[i] == ',':
            i += 1
            continue
        m = _KEY_RE.match(src, i)
        if not m:
            # Not a `key:` — a spread, a shorthand, or something we do not model.
            if src[i] in _OPENERS:
                i = _skip_balanced(src, i, end)
            elif src[i] in '\'"`':
                i = _skip_string(src, i, end)
            else:
                i += 1
            continue
        key = m.group('q') if m.group('q') is not None else m.group('b')
        vstart = _skip_trivia(src, m.end(), end)
        vend = _value_end(src, vstart, end)
        out[key] = (vstart, vend)
        i = vend
    return out


def _value_end(src: str, i: int, end: int) -> int:
    """End of the value starting at `i`: the next depth-0 ',' or the object end."""
    while i < end:
        ch = src[i]
        if ch in '\'"`':
            i = _skip_string(src, i, end)
            continue
        if src.startswith('//', i) or src.startswith('/*', i):
            i = _skip_trivia(src, i, end)
            continue
        if ch in _OPENERS:
            i = _skip_balanced(src, i, end)
            continue
        if ch == ',':
            return i
        i += 1
    return end


def _read_string_value(src: str, span: tuple[int, int]) -> str | None:
    """Read a value span as a string.

    Handles the prettier-wrapped adjacent-literal form the repo uses for long
    metaDescriptions. A template literal with `${}` is returned with each
    interpolation collapsed to a stable `${}` marker: the substituted city name
    is not knowable statically, and pretending otherwise would fake a delta.
    """
    start, end = span
    parts: list[str] = []
    i = _skip_trivia(src, start, end)
    while i < end:
        ch = src[i]
        if ch in '\'"`':
            close = _skip_string(src, i, end)
            parts.append(_unquote(src[i:close]))
            i = _skip_trivia(src, close, end)
            continue
        if ch == '+':
            i = _skip_trivia(src, i + 1, end)
            continue
        return None if not parts else ''.join(parts)
    return ''.join(parts) if parts else None


_ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', 'b': '\b', 'f': '\f', '0': '\0',
            '\\': '\\', "'": "'", '"': '"', '`': '`', '\n': ''}


def _unquote(lit: str) -> str:
    """Decode one string literal, collapsing `${...}` to a `${}` marker."""
    if len(lit) < 2:
        return lit
    quote, body = lit[0], lit[1:-1]
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == '\\' and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt == 'u':
                if i + 2 < len(body) and body[i + 2] == '{':
                    close = body.find('}', i + 3)
                    if close != -1:
                        try:
                            out.append(chr(int(body[i + 3:close], 16)))
                            i = close + 1
                            continue
                        except ValueError:
                            pass
                else:
                    try:
                        out.append(chr(int(body[i + 2:i + 6], 16)))
                        i += 6
                        continue
                    except ValueError:
                        pass
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if quote == '`' and body.startswith('${', i):
            depth, j = 1, i + 2
            while j < len(body) and depth:
                if body[j] == '{':
                    depth += 1
                elif body[j] == '}':
                    depth -= 1
                j += 1
            out.append('${}')
            i = j
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def _iter_strings(src: str, start: int, end: int) -> Iterable[str]:
    """Every string literal in a span, in source order."""
    i = start
    while i < end:
        ch = src[i]
        if ch in '\'"`':
            close = _skip_string(src, i, end)
            yield _unquote(src[i:close])
            i = close
            continue
        if src.startswith('//', i) or src.startswith('/*', i):
            i = _skip_trivia(src, i, end)
            continue
        i += 1


_ENTRY_RE = re.compile(
    r'^export\s+const\s+(?P<name>[A-Za-z_$][\w$]*)\s*:\s*ServicePage\s*=\s*(?P<brace>\{)',
    re.M,
)
_ARRAY_RE_TMPL = r'(?:export\s+)?const\s+{name}\s*(?::[^=]*)?=\s*\['
_BUILDER_CALL_RE = re.compile(r'^([A-Za-z_$][\w$]*)\s*\(')


@dataclass
class TsEntry:
    """One live `export const <name>: ServicePage = {...}` as classification sees it."""

    export_name: str
    slug: str                                  # normalized, no slashes
    source_file: str                           # repo-relative
    line: int
    seo: dict[str, str] = field(default_factory=dict)     # SEO_FIELDS -> raw value
    section_shape: list[str] = field(default_factory=list)
    content_strings: set[str] = field(default_factory=set)   # normalized; the fingerprint
    raw_content_strings: list[str] = field(default_factory=list)  # pre-normalization, for round-trip
    parse_warnings: list[str] = field(default_factory=list)

    @property
    def route(self) -> str:
        return route_of(self.slug)


def parse_service_pages(src: str, source_file: str) -> list[TsEntry]:
    """Scan one TS module for every `ServicePage` export. Never executes TS."""
    entries: list[TsEntry] = []
    for m in _ENTRY_RE.finditer(src):
        name = m.group('name')
        open_idx = m.start('brace')
        line = src.count('\n', 0, m.start()) + 1
        end = _skip_balanced(src, open_idx, len(src))
        keys = _object_keys(src, open_idx)
        warnings: list[str] = []

        raw_slug = _read_string_value(src, keys['slug']) if 'slug' in keys else None
        if raw_slug is None:
            warnings.append('slug is missing or not a static string literal')
            raw_slug = ''

        seo: dict[str, str] = {}
        for f in ('title', 'metaTitle', 'metaDescription'):
            if f in keys:
                v = _read_string_value(src, keys[f])
                if v is None:
                    warnings.append(f'{f} is not a static string literal')
                else:
                    seo[f] = v
        if 'hero' in keys:
            hstart = _skip_trivia(src, *keys['hero'])
            if hstart < len(src) and src[hstart] == '{':
                hkeys = _object_keys(src, hstart)
                for f in ('title', 'description'):
                    if f in hkeys:
                        v = _read_string_value(src, hkeys[f])
                        if v is None:
                            warnings.append(f'hero.{f} is not a static string literal')
                        else:
                            seo[f'hero.{f}'] = v
            else:
                warnings.append('hero is not an inline object literal')
        else:
            warnings.append('hero is absent — the renderer dereferences it unconditionally')

        shape = _section_shape(src, keys.get('sections'))

        strings = [s for s in _iter_strings(src, open_idx, end) if is_content_string(s)]

        entries.append(TsEntry(
            export_name=name,
            slug=normalize_url_path(raw_slug),
            source_file=source_file,
            line=line,
            seo=seo,
            section_shape=shape,
            content_strings={normalize_text(s) for s in strings},
            raw_content_strings=strings,
            parse_warnings=warnings,
        ))
    return entries


def _section_shape(src: str, span: tuple[int, int] | None) -> list[str]:
    """The ordered discriminant sequence of a `sections: [...]` array.

    Object elements contribute their `type` literal; identifier calls contribute
    `<builder:name>`, matching `BuilderCall.type` so a draft and a live entry
    compare on the same vocabulary.
    """
    if span is None:
        return []
    start = _skip_trivia(src, *span)
    if start >= len(src) or src[start] != '[':
        return []
    end = _skip_balanced(src, start, len(src)) - 1
    shape: list[str] = []
    i = start + 1
    while i < end:
        i = _skip_trivia(src, i, end)
        if i >= end:
            break
        if src[i] == ',':
            i += 1
            continue
        if src[i] == '{':
            close = _skip_balanced(src, i, end)
            keys = _object_keys(src, i)
            t = _read_string_value(src, keys['type']) if 'type' in keys else None
            shape.append(t or '<untyped>')
            i = close
            continue
        call = _BUILDER_CALL_RE.match(src, i)
        if call:
            shape.append(f'<builder:{call.group(1)}>')
            i = _skip_balanced(src, call.end() - 1, end)
            continue
        i = _value_end(src, i, end)
    return shape


def parse_identifier_array(src: str, array_name: str) -> list[str] | None:
    """The identifier members of `const <array_name> = [...]`, or None if absent.

    Spreads and inline literals are ignored; only bare identifiers are membership
    evidence, which is exactly what registration means here.
    """
    m = re.search(_ARRAY_RE_TMPL.format(name=re.escape(array_name)), src)
    if not m:
        return None
    start = m.end() - 1
    end = _skip_balanced(src, start, len(src)) - 1
    names: list[str] = []
    i = start + 1
    while i < end:
        i = _skip_trivia(src, i, end)
        if i >= end:
            break
        if src[i] == ',':
            i += 1
            continue
        ident = re.match(r'[A-Za-z_$][\w$]*', src[i:end])
        vend = _value_end(src, i, end)
        if ident and _skip_trivia(src, i + ident.end(), vend) >= vend:
            names.append(ident.group(0))
        i = vend
    return names


def is_content_string(s: str) -> bool:
    """True for prose worth fingerprinting; False for plumbing.

    The same filter runs on both sides of every comparison, so an asymmetry here
    would be a bug on both sides equally rather than a false delta on one.
    """
    if not isinstance(s, str):
        return False
    t = s.strip()
    if not t or _PLUMBING_RE.match(t):
        return False
    return count_words(_TAG_RE.sub(' ', t)) >= MIN_CONTENT_WORDS


# ---------------------------------------------------------------------------
# Repo index
# ---------------------------------------------------------------------------

@dataclass
class RepoIndex:
    """Everything the client repo already claims, indexed by normalized slug."""

    project: Path
    entries: list[TsEntry] = field(default_factory=list)
    by_slug: dict[str, list[TsEntry]] = field(default_factory=dict)
    route_arrays: dict[str, set[str]] = field(default_factory=dict)   # array -> export names
    registries: dict[str, set[str]] = field(default_factory=dict)     # array -> export names
    sitemap_slugs: set[str] = field(default_factory=set)
    sitemap_source: str | None = None                                 # which sitemap file was read
    shape_precedent: dict[str, str] = field(default_factory=dict)     # shape class -> example slug
    #: shape classes whose precedent came from the sitemap, not a typed entry —
    #: weaker evidence (a sitemap can be stale), surfaced as an extra warning.
    sitemap_precedent_shapes: set[str] = field(default_factory=set)
    problems: list[str] = field(default_factory=list)

    def match(self, slug: str) -> TsEntry | None:
        got = self.by_slug.get(slug)
        return got[0] if got else None


def build_repo_index(project: Path, profile: dict | None = None) -> RepoIndex:
    """Read the four sources of truth. Missing optional files degrade to empty.

    `profile` (from client_profile) makes the index CONFIG-DRIVEN: the client's
    declared repo layout (`repo.sitemap`, `repo.spoke_data_dir`) is read instead
    of assuming the default Next.js App Router shape. Without it, behavior is
    exactly the legacy hardcoded scan. Paths resolve through resolve_repo_path,
    so a wrapper-stale prefix (the Northstar `<repo>-main/` class) falls away.
    """
    idx = RepoIndex(project=project)
    repo_paths = (profile or {}).get('repo_paths') or {}

    data_files: list[str] = list(DATA_FILES)
    spoke_dir = resolve_repo_path(repo_paths.get('spoke_data_dir'), project)
    if spoke_dir:
        extra = sorted(
            p.relative_to(project).as_posix()
            for p in (project / spoke_dir).glob('*.ts')
            if p.is_file()
        )
        data_files.extend(f for f in extra if f not in data_files)
    elif repo_paths.get('spoke_data_dir'):
        idx.problems.append(
            f"repo.spoke_data_dir '{repo_paths['spoke_data_dir']}' does not resolve on disk")

    for rel in data_files:
        path = project / rel
        if not path.is_file():
            idx.problems.append(f'{rel}: not found — live entries from it cannot be seen')
            continue
        src = path.read_text(encoding='utf-8', errors='replace')
        found = parse_service_pages(src, rel)
        idx.entries.extend(found)
        for name in REGISTRY_ARRAYS:
            members = parse_identifier_array(src, name)
            if members is not None:
                idx.registries.setdefault(name, set()).update(members)

    for e in idx.entries:
        if not e.slug:
            idx.problems.append(f'{e.source_file}:{e.line} {e.export_name}: unreadable slug')
            continue
        idx.by_slug.setdefault(e.slug, []).append(e)
        idx.shape_precedent.setdefault(shape_class(e.slug), e.slug)

    for slug, dupes in idx.by_slug.items():
        if len(dupes) > 1:
            where = ', '.join(f'{d.export_name} ({d.source_file}:{d.line})' for d in dupes)
            idx.problems.append(f'slug collision already in the repo: /{slug}/ claimed by {where}')

    for rel, arrays in ROUTE_ARRAY_FILES.items():
        path = project / rel
        if not path.is_file():
            idx.problems.append(
                f'{rel}: not found — {"/".join(arrays)} membership cannot be checked')
            continue
        src = path.read_text(encoding='utf-8', errors='replace')
        for array in arrays:
            members = parse_identifier_array(src, array)
            if members is None:
                idx.problems.append(
                    f'{rel}: {array} not found — route registration cannot be checked')
                continue
            idx.route_arrays[array] = set(members)

    # Sitemap resolution order: the client's declared repo.sitemap first, then
    # the resolved build dir, then the legacy hardcoded locations. First file
    # that exists wins; which one is recorded so a verdict can be audited.
    sitemap_candidates: list[str] = []
    configured_sitemap = resolve_repo_path(repo_paths.get('sitemap'), project)
    if configured_sitemap:
        sitemap_candidates.append(configured_sitemap)
    elif repo_paths.get('sitemap'):
        idx.problems.append(
            f"repo.sitemap '{repo_paths['sitemap']}' does not resolve on disk")
    build_dir = ((profile or {}).get('resolved_build_dir') or '').lstrip('./')
    if build_dir:
        sitemap_candidates.append(f'{build_dir}/sitemap.xml')
    sitemap_candidates += ['out/sitemap.xml', 'dist/sitemap.xml', 'public/sitemap.xml']

    seen: set[str] = set()
    for rel in sitemap_candidates:
        if rel in seen:
            continue
        seen.add(rel)
        sitemap = project / rel
        if not sitemap.is_file():
            continue
        text = sitemap.read_text(encoding='utf-8', errors='replace')
        slugs = {
            normalize_url_path(loc)
            for loc in re.findall(r'<loc>\s*(.*?)\s*</loc>', text, re.S)
        }
        if not slugs:
            # Exists but yields nothing — a sitemap SOURCE (src/app/sitemap.ts)
            # or an empty file. Keep walking the chain rather than letting a
            # zero-URL "sitemap" mask a real XML further down.
            idx.problems.append(
                f'{rel}: exists but contains no <loc> entries — not a usable '
                'sitemap XML; trying the next candidate')
            continue
        idx.sitemap_slugs = slugs
        idx.sitemap_source = rel
        break

    # Sitemap-seeded shape precedent (fallback only): a live URL proves a shape
    # ships even when no typed entry supplies it (the topology-gap escape at
    # classify_draft exists precisely for this). Weaker evidence than a typed
    # entry — sitemaps go stale — so these shapes are tracked and warned on.
    # The _SLUG_SEGMENT_RE guard stays: a malformed segment never seeds precedent.
    for s in sorted(idx.sitemap_slugs):
        segs = [x for x in s.split('/') if x]
        if not segs or any(not _SLUG_SEGMENT_RE.match(x) for x in segs):
            continue
        shape = shape_class(s)
        if shape not in idx.shape_precedent:
            idx.shape_precedent[shape] = s
            idx.sitemap_precedent_shapes.add(shape)
    return idx


# ---------------------------------------------------------------------------
# Draft loading
#
# Tolerant on purpose. This is NOT a schema — models.py owns the schema. It is
# the smallest reader that can turn whatever pass 2 hands over into a PageDraft
# faithful enough to CLASSIFY. Fields classification does not read are carried
# through untouched; fields it does read are required to be readable or the
# draft is rejected outright rather than mis-classified.
# ---------------------------------------------------------------------------

class DraftLoadError(ValueError):
    """A drafts.json entry that cannot be read as a PageDraft."""


_ALIASES = {
    'urlpath': 'url_path', 'url': 'url_path', 'route': 'url_path', 'path': 'url_path',
    'pagekind': 'page_kind', 'kind': 'page_kind',
    'metatitle': 'meta_title', 'metadescription': 'meta_description',
    'lastupdated': 'last_updated', 'exportname': 'export_name',
    'corebodywords': 'core_body_words', 'sourceref': 'source_ref',
    'coveragemethod': 'coverage_method', 'relatedlinks': 'related_links',
    'fanoutqueries': 'fanout_queries', 'semantictriples': 'semantic_triples',
    'proprietaryvariables': 'proprietary_variables',
}


def _canon_keys(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in raw.items():
        key = str(k)
        out[_ALIASES.get(key.replace('_', '').replace('-', '').lower(), key)] = v
    return out


def draft_from_dict(raw: dict[str, Any]) -> PageDraft:
    """Build a PageDraft from a drafts.json object.

    Only `url_path` is truly required — a draft with no route cannot be
    classified at all. Everything else defaults, so a partial pass-2 draft is
    still classifiable (and its emptiness shows up honestly as a delta).
    """
    if not isinstance(raw, dict):
        raise DraftLoadError(f'expected an object, got {type(raw).__name__}')
    d = _canon_keys(raw)

    url_path = str(d.get('url_path') or d.get('slug') or '').strip()
    if not url_path:
        raise DraftLoadError('no url_path (or slug) — a draft without a route cannot be classified')

    hero_raw = d.get('hero') or {}
    if not isinstance(hero_raw, dict):
        raise DraftLoadError('hero must be an object')
    h = _canon_keys(hero_raw)
    hero = Hero(
        badge_icon=str(h.get('badge_icon') or h.get('badgeIcon') or ''),
        badge_text=str(h.get('badge_text') or h.get('badgeText') or ''),
        title=str(h.get('title') or d.get('h1') or ''),
        description=str(h.get('description') or ''),
        bg_image=h.get('bg_image') or h.get('bgImage'),
        buttons=[
            HeroButton(
                text=str(_canon_keys(b).get('text', '')),
                url=str(_canon_keys(b).get('url', '')),
                class_name=str(_canon_keys(b).get('class_name') or _canon_keys(b).get('className') or 'btn-primary'),
                icon_before=_canon_keys(b).get('icon_before') or _canon_keys(b).get('iconBefore'),
                icon_after=_canon_keys(b).get('icon_after') or _canon_keys(b).get('iconAfter'),
            )
            for b in (h.get('buttons') or []) if isinstance(b, dict)
        ],
        features=[str(x) for x in (h.get('features') or [])],
    )

    sections: list[Section | BuilderCall] = []
    for s in (d.get('sections') or []):
        if not isinstance(s, dict):
            raise DraftLoadError(f'section must be an object, got {type(s).__name__}')
        sd = _canon_keys(s)
        if 'builder' in sd or sd.get('type', '').startswith('<builder:'):
            name = sd.get('builder') or sd['type'][len('<builder:'):-1]
            sections.append(BuilderCall(name=str(name), args=list(sd.get('args') or [])))
            continue
        stype = str(sd.get('type') or '')
        props = sd.get('props')
        if not isinstance(props, dict):
            # Flat form: everything that is not draft metadata is a prop.
            props = {k: v for k, v in s.items()
                     if k not in ('type', 'core_body', 'source_ref', 'verdict', 'props')}
        sections.append(Section(
            type=stype,
            props=dict(props),
            core_body=bool(sd.get('core_body', False)),
            source_ref=sd.get('source_ref'),
            verdict=sd.get('verdict'),
        ))

    cap_raw = _canon_keys(d.get('capsule') or {}) if isinstance(d.get('capsule'), dict) else {}
    triples = [
        SemanticTriple(str(_canon_keys(t).get('subject', '')),
                       str(_canon_keys(t).get('predicate', '')),
                       str(_canon_keys(t).get('object', '')))
        for t in (d.get('semantic_triples') or []) if isinstance(t, dict)
    ]

    return PageDraft(
        url_path=url_path,
        page_kind=str(d.get('page_kind') or ''),
        city=str(d.get('city') or ''),
        state=str(d.get('state') or ''),
        service=str(d.get('service') or ''),
        h1=str(d.get('h1') or hero.title),
        meta_title=str(d.get('meta_title') or ''),
        meta_description=str(d.get('meta_description') or ''),
        hero=hero,
        title=str(d.get('title') or ''),
        export_name=str(d.get('export_name') or ''),
        last_updated=str(d.get('last_updated') or ''),
        sections=sections,
        faqs=[
            FaqItem(str(_canon_keys(f).get('question', '')), str(_canon_keys(f).get('answer', '')))
            for f in (d.get('faqs') or []) if isinstance(f, dict)
        ],
        capsule=Capsule(
            interrogative_h2=str(cap_raw.get('interrogative_h2') or ''),
            answer_first=str(cap_raw.get('answer_first') or ''),
            tldr=str(cap_raw.get('tldr') or ''),
        ),
        proprietary_variables=[str(x) for x in (d.get('proprietary_variables') or [])],
        fanout_queries=[str(x) for x in (d.get('fanout_queries') or [])],
        semantic_triples=triples,
        intent=str(d.get('intent') or ''),
        core_body_words=int(d.get('core_body_words') or 0),
        source_ref=str(d.get('source_ref') or ''),
        coverage_method=str(d.get('coverage_method') or ''),
        related_links=[x for x in (d.get('related_links') or []) if isinstance(x, dict)],
        ledger=list(d.get('ledger') or []),
    )


def load_drafts(path: Path) -> tuple[list[PageDraft], list[str]]:
    """Read drafts.json. Accepts a bare list, `{"drafts": [...]}`, or one object.

    A malformed member is a reported failure, not a crash and not a skip — a
    draft silently dropped here is a page silently not written.
    """
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise DraftLoadError(f'{path}: {exc}') from exc

    if isinstance(payload, dict):
        payload = payload.get('drafts', payload.get('pages', [payload]))
    if not isinstance(payload, list):
        raise DraftLoadError(f'{path}: expected a list of drafts or {{"drafts": [...]}}')

    drafts: list[PageDraft] = []
    failures: list[str] = []
    for i, raw in enumerate(payload):
        try:
            drafts.append(draft_from_dict(raw))
        except DraftLoadError as exc:
            failures.append(f'drafts[{i}]: {exc}')
    return drafts, failures


# ---------------------------------------------------------------------------
# Draft projection — the draft's side of every comparison
# ---------------------------------------------------------------------------

def draft_seo(draft: PageDraft) -> dict[str, str]:
    """The 5 renderer-visible SEO strings, keyed identically to TsEntry.seo."""
    return {
        'title': draft.resolved_title,
        'metaTitle': draft.meta_title,
        'metaDescription': draft.meta_description,
        'hero.title': draft.hero.title or draft.h1,
        'hero.description': draft.hero.description,
    }


def draft_section_shape(draft: PageDraft) -> list[str]:
    return [s.type for s in draft.sections]


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from _walk_strings(v)


def draft_content_strings(draft: PageDraft) -> set[str]:
    """Every prose string the draft would emit, normalized.

    Walks exactly what `to_ts_entry` would serialize — hero props, section props,
    builder args, faqs — so the fingerprint compares like with like against a
    live entry's own string literals.
    """
    pool: list[Any] = [draft.hero.to_props()]
    for s in draft.sections:
        pool.append(s.to_props() if isinstance(s, Section) else list(s.args))
    pool.extend(f.to_props() for f in draft.faqs)
    return {
        normalize_text(s)
        for chunk in pool
        for s in _walk_strings(chunk)
        if is_content_string(s)
    }


def jaccard(a: set[str], b: set[str]) -> float:
    """|A n B| / |A u B|. Two empty sets are identical (1.0), not undefined."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 1.0


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    """One draft's verdict, with every input that produced it kept visible."""

    url_path: str
    slug: str
    route: str
    decision: str
    reason_code: str
    reason: str
    export_name: str = ''
    matched_export: str | None = None
    matched_source: str | None = None
    matched_line: int | None = None
    page_kind: str = ''
    shape: str = ''
    topology_kind: str = ''
    body_similarity: float | None = None
    seo_deltas: list[dict[str, str]] = field(default_factory=list)
    shape_delta: dict[str, list[str]] | None = None
    registration: dict[str, Any] = field(default_factory=dict)
    in_sitemap: bool = False
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        d = {
            'url_path': self.url_path,
            'slug': self.slug,
            'route': self.route,
            'decision': self.decision,
            'reason_code': self.reason_code,
            'reason': self.reason,
            'export_name': self.export_name,
            'matched_export': self.matched_export,
            'matched_source': self.matched_source,
            'matched_line': self.matched_line,
            'page_kind': self.page_kind,
            'shape': self.shape,
            'topology_kind': self.topology_kind,
            'body_similarity': self.body_similarity,
            'seo_deltas': self.seo_deltas,
            'shape_delta': self.shape_delta,
            'registration': self.registration,
            'in_sitemap': self.in_sitemap,
            'warnings': self.warnings,
        }
        return d


def _registration_state(idx: RepoIndex, entry: TsEntry | None, slug: str) -> dict[str, Any]:
    """Where a matched entry is (and is not) registered.

    Route array absent  -> dynamicParams=false -> the page 404s.
    Registry absent     -> builds, crawlable, zero inbound links -> orphan.
    Both are material: they make a matching draft an UPDATE, never a SKIP.
    """
    segs = len([s for s in slug.split('/') if s])
    accepted = ROUTE_ARRAYS_BY_SEGMENTS.get(segs, ())
    state: dict[str, Any] = {
        'expected_route_array': ROUTE_ARRAY_BY_SEGMENTS.get(segs),   # where a NEW page goes
        'accepted_route_arrays': list(accepted),                      # what satisfies an existing one
        'in_route_array': None,
        'found_in_route_arrays': [],
        'in_registry': None,
        'registry_array': None,
    }
    if entry is None:
        return state
    known = [a for a in accepted if a in idx.route_arrays]
    if known:
        found = [a for a in known if entry.export_name in idx.route_arrays[a]]
        state['found_in_route_arrays'] = found
        state['in_route_array'] = bool(found)
    registry = 'allServices' if entry.source_file.endswith('services.ts') else 'allLocationPages'
    state['registry_array'] = registry
    if registry in idx.registries:
        state['in_registry'] = entry.export_name in idx.registries[registry]
    return state


def classify_draft(
    draft: PageDraft,
    idx: RepoIndex,
    topology: str | None,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    strict_topology: bool = False,
) -> Decision:
    """Decide NEW / UPDATE / SKIP / INVALID for one draft. Reads only."""
    slug = normalize_url_path(draft.url_path)
    shape = shape_class(slug)
    dec = Decision(
        url_path=draft.url_path,
        slug=slug,
        route=route_of(slug),
        decision=INVALID,
        reason_code='unclassified',
        reason='',
        # From the NORMALIZED slug, not draft.resolved_export_name.
        # PageDraft.slug is `url_path.strip('/')`, which does not strip a scheme,
        # host, query or fragment — so a draft whose url_path is an absolute URL
        # derives an export name like `acmeroofing.example.comCharlotteNcMatthews?utm=x`.
        # Recorded here as the name a write SHOULD use; the mismatch is warned on
        # below so the emitter module can normalize at the source.
        export_name=draft.export_name or derive_export_name(normalize_url_path(draft.url_path)),
        page_kind=draft.page_kind,
        shape=shape,
        in_sitemap=slug in idx.sitemap_slugs,
    )

    if draft.resolved_export_name != dec.export_name:
        dec.warnings.append(
            f'export_name_drift: PageDraft.resolved_export_name is '
            f'{draft.resolved_export_name!r} but the normalized route yields '
            f'{dec.export_name!r} — PageDraft.slug is url_path.strip("/") and does not '
            f'strip a scheme, host, query or fragment. Normalize url_path before emitting.'
        )

    # --- slug well-formedness ------------------------------------------------
    # Checked BEFORE topology and before any precedent escape. A segment outside
    # the slug alphabet is invalid at every topology, and letting one reach the
    # precedent escape would accept anything that merely had the right number of
    # slashes.
    segments = [s for s in slug.split('/') if s]
    bad = [s for s in segments if not _SLUG_SEGMENT_RE.match(s)]
    if not segments or bad:
        dec.decision = INVALID
        dec.reason_code = 'malformed_slug'
        dec.reason = (
            f'url_path {draft.url_path!r} is not a usable route: '
            + ('empty after normalization' if not segments
               else f'segment(s) outside [a-z0-9-]: {bad}')
        )
        return dec

    # --- topology -----------------------------------------------------------
    if not topology:
        dec.warnings.append(
            'client-config.yml has no `topology:` — url shape cannot be validated; '
            'every draft is accepted on shape precedent alone'
        )
        fits, kind = True, 'unknown'
    else:
        fits, kind = url_fits_topology(route_of(slug), topology)
    dec.topology_kind = kind

    if not fits:
        precedent = idx.shape_precedent.get(shape)
        if precedent and not strict_topology:
            dec.warnings.append(
                f'topology_gap: /{slug}/ does not match TOPOLOGY_PATTERNS["{topology}"] '
                f'(which models hub + spoke only), but the repo already ships /{precedent}/ '
                f'with the same {shape} shape. Classified on that precedent; the topology '
                f'table needs a {shape} pattern.'
            )
            if shape in idx.sitemap_precedent_shapes:
                dec.warnings.append(
                    f'sitemap_precedent: the /{precedent}/ precedent comes from '
                    f'{idx.sitemap_source or "the sitemap"} only (no typed entry ships that '
                    'shape) — a sitemap can be stale; verify the live route before writing'
                )
        else:
            dec.decision = INVALID
            dec.reason_code = 'topology_mismatch'
            dec.reason = (
                f'/{slug}/ does not fit topology "{topology}" (resolved kind: {kind})'
                + ('' if strict_topology else ' and no live page shares its shape')
            )
            return dec

    if shape == '3-segment-nosuffix':
        dec.warnings.append(
            'sub-service slug does not end in -(installation|repair|replacement|services|claims); '
            'locationLabel() will resolve the city from the wrong segment'
        )

    # --- match --------------------------------------------------------------
    entry = idx.match(slug)
    if entry is None:
        # A slug in the shipped sitemap IS an existing page, typed entry or not
        # (hand-built route, Vite data shape, hub page.tsx). Calling it NEW is
        # the duplicate-route defect this classifier exists to refuse — the
        # 2026-08 runs produced 15/16 wrong verdicts on Northstar and misread all
        # four BLH /services/ hubs this way. UPDATE, with the evidence named.
        if dec.in_sitemap:
            dec.decision = UPDATE
            dec.reason_code = 'live_in_sitemap_untyped'
            dec.reason = (
                f'/{slug}/ is live in {idx.sitemap_source or "the build sitemap"} but no '
                'typed ServicePage entry claims it — the page exists; this draft updates '
                'it. The emitter must locate the page source by route, not by entry.'
            )
            dec.registration = _registration_state(idx, None, slug)
            dec.warnings.append(
                'sitemap_match_untyped: matched on sitemap evidence only — no typed '
                'entry to diff against, so no seo/shape deltas are computed; verify '
                'the live route before writing'
            )
            return dec
        dec.decision = NEW
        dec.reason_code = 'no_existing_entry'
        dec.reason = f'no live ServicePage claims /{slug}/'
        dec.registration = _registration_state(idx, None, slug)
        collisions = [
            e for e in idx.entries
            if e.export_name == dec.export_name and e.slug != slug
        ]
        if collisions:
            c = collisions[0]
            dec.warnings.append(
                f'export name collision: `{dec.export_name}` is already taken by '
                f'/{c.slug}/ at {c.source_file}:{c.line} — set export_name explicitly'
            )
        return dec

    dec.matched_export = entry.export_name
    dec.matched_source = entry.source_file
    dec.matched_line = entry.line
    dec.registration = _registration_state(idx, entry, slug)
    for w in entry.parse_warnings:
        dec.warnings.append(f'{entry.export_name}: {w}')

    # --- delta axis 1: the renderer-visible SEO strings ----------------------
    d_seo = draft_seo(draft)
    for f in SEO_FIELDS:
        live = entry.seo.get(f)
        new = d_seo.get(f, '')
        if live is None:
            if new:
                dec.seo_deltas.append({'field': f, 'existing': None, 'draft': new,
                                       'note': 'field absent from the live entry'})
            continue
        if normalize_text(live) != normalize_text(new):
            dec.seo_deltas.append({'field': f, 'existing': live, 'draft': new})

    # --- delta axis 2: structural shape --------------------------------------
    d_shape = draft_section_shape(draft)
    if d_shape and d_shape != entry.section_shape:
        dec.shape_delta = {'existing': entry.section_shape, 'draft': d_shape}
    elif not d_shape:
        dec.warnings.append('draft carries no sections — shape comparison skipped')

    # --- delta axis 3: prose --------------------------------------------------
    d_strings = draft_content_strings(draft)
    dec.body_similarity = round(jaccard(entry.content_strings, d_strings), 4)

    # --- verdict --------------------------------------------------------------
    reasons: list[str] = []
    if dec.seo_deltas:
        reasons.append(f"{len(dec.seo_deltas)} SEO field(s) changed: "
                       f"{', '.join(d['field'] for d in dec.seo_deltas)}")
    if dec.shape_delta:
        reasons.append(f'section shape changed ({len(entry.section_shape)} -> {len(d_shape)})')
    if d_strings and dec.body_similarity < similarity_threshold:
        reasons.append(f'prose similarity {dec.body_similarity:.4f} < {similarity_threshold}')

    reg = dec.registration
    if reg.get('in_route_array') is False:
        reasons.append("not registered in "
                       + ' or '.join(reg.get('accepted_route_arrays') or ['any route array'])
                       + ' — the route 404s')
    if reg.get('in_registry') is False:
        reasons.append(f"not registered in {reg['registry_array']} — orphan page")

    if reasons:
        dec.decision = UPDATE
        dec.reason_code = 'registration_repair' if (
            not dec.seo_deltas and not dec.shape_delta
            and (d_strings and dec.body_similarity >= similarity_threshold or not d_strings)
        ) else 'material_delta'
        dec.reason = '; '.join(reasons)
    else:
        dec.decision = SKIP
        dec.reason_code = 'no_material_delta'
        dec.reason = (
            f'matches {entry.export_name} ({entry.source_file}:{entry.line}); '
            f'SEO identical, shape identical, prose similarity {dec.body_similarity:.4f}'
        )
    return dec


def classify_all(
    drafts: list[PageDraft],
    idx: RepoIndex,
    topology: str | None,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    strict_topology: bool = False,
) -> list[Decision]:
    """Classify a batch, additionally catching collisions WITHIN the batch.

    Two drafts claiming one route is a duplicate the repo cannot see yet — the
    second write silently wins. Caught here, before either is emitted.
    """
    decisions = [
        classify_draft(d, idx, topology,
                       similarity_threshold=similarity_threshold,
                       strict_topology=strict_topology)
        for d in drafts
    ]
    seen: dict[str, int] = {}
    for i, dec in enumerate(decisions):
        first = seen.setdefault(dec.slug, i)
        if first != i:
            # Positions are within the LOADED batch, which is not the source
            # array index when an earlier member failed to load.
            dec.warnings.append(
                f'duplicate route within this batch: batch position {first} already claims /{dec.slug}/'
            )
            decisions[first].warnings.append(
                f'duplicate route within this batch: batch position {i} also claims /{dec.slug}/'
            )
    return decisions


def summarize(decisions: list[Decision]) -> dict[str, int]:
    counts = {d: 0 for d in DECISIONS}
    for dec in decisions:
        counts[dec.decision] = counts.get(dec.decision, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Self-test — against the REAL client repo, never a mock
# ---------------------------------------------------------------------------

def _draft_from_entry(entry: TsEntry, idx: RepoIndex) -> PageDraft:
    """Reconstruct a draft that SHOULD classify SKIP against its own live entry.

    Round-tripping the repo through the comparator is the only honest way to
    prove SKIP works: if a page cannot match itself, every real UPDATE verdict
    downstream is noise.

    Fidelity matters here. The reconstruction carries the entry's own section
    discriminants AND its own prose, so the draft side of the comparison is fed
    exactly what the live side holds. A fixture that reconstructed only the SEO
    strings would score ~0.03 similarity against its own source and "prove"
    nothing except that the fixture was empty.
    """
    sections: list[Section | BuilderCall] = []
    for t in entry.section_shape:
        if t.startswith('<builder:'):
            sections.append(BuilderCall(name=t[len('<builder:'):-1]))
        else:
            sections.append(Section(type=t))
    # Park the entry's prose on the LAST section rather than a new one: adding a
    # section would change the shape under test and turn every round-trip into a
    # false shape delta.
    prose = list(entry.raw_content_strings)
    carrier = next((s for s in reversed(sections) if isinstance(s, Section)), None)
    if carrier is not None:
        carrier.props['content'] = prose
        prose = []

    return PageDraft(
        url_path=entry.slug,
        page_kind='hub',
        city='', state='', service='',
        h1=entry.seo.get('hero.title', ''),
        meta_title=entry.seo.get('metaTitle', ''),
        meta_description=entry.seo.get('metaDescription', ''),
        hero=Hero(
            badge_icon='', badge_text='',
            title=entry.seo.get('hero.title', ''),
            description=entry.seo.get('hero.description', ''),
            features=prose,   # only when there was no section to carry it
        ),
        title=entry.seo.get('title', ''),
        export_name=entry.export_name,
        sections=sections,
    )


def self_test(project: Path, *, strict_topology: bool = False, verbose: bool = False) -> int:
    """Round-trip every live Acme page, then probe the three other verdicts."""
    print(f'classify self-test against {project}')
    cfg = load_config(str(project))
    profile = client_profile(cfg, str(project))
    topology = profile.get('url_topology')
    repo_layout.activate(cfg)
    print(f"  client={profile['client_slug']} topology={topology} "
          f"topology_class={profile['topology_class']} framework={profile['framework_family']}")

    idx = build_repo_index(project, profile=profile)
    print(f'  indexed {len(idx.entries)} ServicePage entries across {len(DATA_FILES)} data files, '
          f'{len(idx.by_slug)} distinct slugs, {len(idx.sitemap_slugs)} sitemap urls'
          + (f' (sitemap: {idx.sitemap_source})' if idx.sitemap_source else ''))
    for name, members in sorted(idx.route_arrays.items()):
        print(f'    route array {name}: {len(members)} members')
    for name, members in sorted(idx.registries.items()):
        print(f'    registry    {name}: {len(members)} members')
    for p in idx.problems:
        print(f'    REPO PROBLEM: {p}')

    if not idx.entries:
        print('FAIL: no live entries parsed — the TS scanner is broken or the paths moved',
              file=sys.stderr)
        return 1

    # --- part 1: every live page must recognize itself ----------------------
    round_trip = [_draft_from_entry(e, idx) for e in idx.entries if e.slug]
    decisions = classify_all(round_trip, idx, topology, strict_topology=strict_topology)
    counts = summarize(decisions)
    print(f'\n  [1] round-trip of {len(round_trip)} live pages: '
          + ', '.join(f'{k}={counts[k]}' for k in DECISIONS))

    failures: list[str] = []
    not_skipped = [d for d in decisions if d.decision != SKIP]
    for d in not_skipped:
        if d.decision == INVALID:
            continue  # reported separately as the topology gap
        failures.append(f'live page /{d.slug}/ did not SKIP against itself: '
                        f'{d.decision} — {d.reason}')

    # --- part 2: the three other verdicts ------------------------------------
    sample = next((e for e in idx.entries if e.slug and e.seo.get('metaTitle')), None)
    probes: list[tuple[str, PageDraft, str]] = []

    if sample is not None:
        mutated = _draft_from_entry(sample, idx)
        mutated.meta_title = (sample.seo.get('metaTitle', '') + ' Updated').strip()
        probes.append(('UPDATE on a changed metaTitle', mutated, UPDATE))

    unused_metro = next(
        (s for s in ('greensboro-nc', 'raleigh-nc', 'durham-nc') if s not in idx.by_slug), None)
    if unused_metro:
        probes.append((
            'NEW on an unclaimed hub route',
            PageDraft(url_path=f'/{unused_metro}/', page_kind='hub', city='Greensboro', state='NC',
                      service='', h1='x', meta_title='x', meta_description='x',
                      hero=Hero('', '', 'x', 'x')),
            NEW,
        ))

    probes.append((
        'INVALID on a 4-segment route no live page shares',
        PageDraft(url_path='/charlotte-nc/matthews/siding-installation/deep/',
                  page_kind='subservice', city='Matthews', state='NC', service='Siding',
                  h1='x', meta_title='x', meta_description='x', hero=Hero('', '', 'x', 'x')),
        INVALID,
    ))
    probes.append((
        'INVALID on a route with no topology fit and no precedent',
        PageDraft(url_path='/NOT a slug/', page_kind='hub', city='', state='', service='',
                  h1='x', meta_title='x', meta_description='x', hero=Hero('', '', 'x', 'x')),
        INVALID,
    ))

    print(f'\n  [2] {len(probes)} verdict probes:')
    for label, draft, expected in probes:
        got = classify_draft(draft, idx, topology, strict_topology=strict_topology)
        ok = got.decision == expected
        print(f'      {"ok  " if ok else "FAIL"}  {label}: {got.decision} ({got.reason_code})')
        if not ok:
            failures.append(f'probe "{label}": expected {expected}, got {got.decision} — {got.reason}')

    # --- part 3: batch-level duplicate detection -----------------------------
    if sample is not None:
        dupes = classify_all(
            [_draft_from_entry(sample, idx), _draft_from_entry(sample, idx)],
            idx, topology, strict_topology=strict_topology)
        dup_caught = all(any('duplicate route within this batch' in w for w in d.warnings)
                         for d in dupes)
        print(f'\n  [3] in-batch duplicate route: {"ok  caught" if dup_caught else "FAIL missed"}')
        if not dup_caught:
            failures.append('two drafts claiming one route were not flagged as a batch duplicate')

    # --- report --------------------------------------------------------------
    invalid = [d for d in decisions if d.decision == INVALID]
    print(f'\n  INVALID live urls: {len(invalid)}')
    for d in sorted(invalid, key=lambda x: x.slug)[:40]:
        print(f'      {d.route}  {d.reason}')
    if len(invalid) > 40:
        print(f'      ... and {len(invalid) - 40} more')

    warned = [d for d in decisions if d.warnings]
    print(f'  live urls carrying a warning: {len(warned)}')
    buckets: dict[str, list[tuple[str, str]]] = {}
    for d in warned:
        for w in d.warnings:
            buckets.setdefault(w.split(':', 1)[0], []).append((d.route, w))
    for head, items in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        print(f'      [{head}] x{len(items)}  e.g. {items[0][0]}')
        print(f'          {items[0][1]}')

    if verbose:
        for d in not_skipped:
            print(f'      {d.decision:8} {d.route} — {d.reason}')

    if failures:
        print(f'\nFAIL: {len(failures)} self-test failure(s):', file=sys.stderr)
        for f in failures:
            print(f'  - {f}', file=sys.stderr)
        return 1
    print('\nPASS: every live page recognizes itself; all verdict probes correct.')
    if invalid:
        # The comparator is correct, but it just called N pages that are LIVE
        # today unroutable. That is a finding, not a clean run.
        print(f'REVIEW: {len(invalid)} live page(s) classify INVALID under this topology.',
              file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description='Classify PageDrafts NEW / UPDATE / SKIP / INVALID against the live client repo.')
    ap.add_argument('drafts', nargs='?',
                    help='drafts.json — a list of PageDraft objects, or {"drafts": [...]}')
    ap.add_argument('--project', required=True, help='client repo root (e.g. ../acme-roofing-site)')
    ap.add_argument('--out', help='write decisions.json here (default: stdout)')
    ap.add_argument('--similarity-threshold', type=float, default=DEFAULT_SIMILARITY_THRESHOLD,
                    help=f'prose Jaccard at or above this counts as unchanged '
                         f'(default {DEFAULT_SIMILARITY_THRESHOLD})')
    ap.add_argument('--allow-empty-repo', action='store_true',
                    help='permit classification against a repo with 0 typed entries AND '
                         '0 sitemap urls (a genuine greenfield site with no live pages); '
                         'without it, an empty index refuses with exit 17')
    ap.add_argument('--strict-topology', action='store_true',
                    help='take url_fits_topology literally; do not accept a live page of the '
                         'same shape as precedent')
    ap.add_argument('--self-test', action='store_true',
                    help='round-trip the real client repo through the comparator and report counts')
    ap.add_argument('--verbose', action='store_true')
    args = ap.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        print(f'ERROR: --project not a directory: {project}', file=sys.stderr)
        return 2

    if args.self_test:
        return self_test(project, strict_topology=args.strict_topology, verbose=args.verbose)

    if not args.drafts:
        print('ERROR: drafts.json is required (or pass --self-test)', file=sys.stderr)
        return 2
    if not 0.0 <= args.similarity_threshold <= 1.0:
        print('ERROR: --similarity-threshold must be between 0.0 and 1.0', file=sys.stderr)
        return 2

    try:
        drafts, load_failures = load_drafts(Path(args.drafts).expanduser())
    except DraftLoadError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    cfg = load_config(str(project))
    profile = client_profile(cfg, str(project))
    topology = profile.get('url_topology')
    repo_layout.activate(cfg)

    idx = build_repo_index(project, profile=profile)

    # A blind index cannot refuse duplicates — which is this tool's one job.
    # 0 typed entries + 0 sitemap urls means every verdict would be a confident
    # NEW with zero duplicate protection (the silent-failure class of the July
    # assert_segmentable bug). Refuse loudly; a genuine greenfield repo opts in.
    if not idx.entries and not idx.sitemap_slugs and not args.allow_empty_repo:
        print(
            'ERROR: repo index is EMPTY — 0 typed entries and 0 sitemap urls.\n'
            '  The repo layout is not visible to this index (wrong/missing '
            'repo.sitemap / repo.spoke_data_dir in docs/client-config.yml?).\n'
            '  Classifying blind would return NEW for every draft with no duplicate '
            'protection. Refusing.\n'
            '  For a genuine greenfield repo with no live pages, pass --allow-empty-repo.',
            file=sys.stderr)
        for p in idx.problems:
            print(f'  REPO PROBLEM: {p}', file=sys.stderr)
        return 17

    decisions = classify_all(drafts, idx, topology,
                             similarity_threshold=args.similarity_threshold,
                             strict_topology=args.strict_topology)
    counts = summarize(decisions)

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'project': str(project),
        'client_slug': profile.get('client_slug'),
        'topology': topology,
        'strict_topology': bool(args.strict_topology),
        'similarity_threshold': args.similarity_threshold,
        'indexed': {
            'entries': len(idx.entries),
            'distinct_slugs': len(idx.by_slug),
            'sitemap_urls': len(idx.sitemap_slugs),
            'sitemap_source': idx.sitemap_source,
            'route_arrays': {k: len(v) for k, v in sorted(idx.route_arrays.items())},
            'registries': {k: len(v) for k, v in sorted(idx.registries.items())},
        },
        'repo_problems': idx.problems,
        'draft_load_failures': load_failures,
        'counts': counts,
        'decisions': [d.as_dict() for d in decisions],
    }

    text = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    if args.out:
        out_path = Path(args.out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding='utf-8')
        print(f'classify: wrote {out_path}')
    else:
        sys.stdout.write(text)

    print('classify: ' + ', '.join(f'{k}={counts[k]}' for k in DECISIONS)
          + f' (of {len(drafts)} draft(s))')
    for f in load_failures:
        print(f'  LOAD FAILURE: {f}', file=sys.stderr)
    for d in decisions:
        if d.decision == INVALID:
            print(f'  INVALID  {d.route}  {d.reason}', file=sys.stderr)
        for w in d.warnings:
            print(f'  WARN     {d.route}  {w}', file=sys.stderr)

    flagged = counts.get(INVALID, 0) or load_failures or any(d.warnings for d in decisions)
    return 1 if flagged else 0


if __name__ == '__main__':
    sys.exit(main())
