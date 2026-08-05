"""Per-repo layout + renderer contract (P0-2, ENGINE-FIXES-2026-08 fix 2).

models.py and emit_ts.py have always encoded ONE repo's shape — Acme's:
`src/app/[slug]/...` route files, `location-pages.ts`/`services.ts` data files,
1/2/3-segment route arrays, `charlotte-nc`/`asheville-nc` metro hubs, and the
ServicePageRenderer contract (editorial section types, card-grid arities, the
transformLocationSections escape). The 2026-08 four-terminal cycle proved every
other client repo blocked on those assumptions: BLH North's 4-segment geo
spokes were inexpressible (`route_array_unknown`), BLH Florida's
`app/[city]/[service]/` had no `src/`, `masonry` (a real live slug) failed the
suffix rule, and `transform_would_rewrite` fired on renderers that never call
that transform.

This module makes the layout DATA, not assumption. Defaults reproduce the
historical Acme behavior exactly; a client repo overrides via
`docs/client-config.yml`:

    repo:
      layout:
        renderer_contract: generic          # or acme-service-page (default)
        route_arrays_by_segments: {2: SPOKE_PAGES, 4: GEO_SPOKE_PAGES}
        route_files:
          GEO_SPOKE_PAGES: app/[state]/[county]/[city]/[service]/page.tsx
        data_files:                          # data file -> registry array
          src/data/county-pages.ts: allCountyPages
        default_data_file: src/data/county-pages.ts
        metro_hubs: [trenton-nj]
        subservice_suffixes: [installation, repair, waterproofing]
        segments_by_kind: {hub: [1], spoke: [2, 4], subservice: [2, 3]}

`renderer_contract: generic` disables only the checks that mirror Acme's
ServicePageRenderer internals (section-type union, shared-builder arity,
card-grid counts, the transform escape). Content checks (capsule, brief,
core-body band, hero rule, meta bands) are renderer-independent and always run.

The active layout is process-level state set ONCE per CLI run from the loaded
client config (`activate(cfg)`), because PageDraft properties and the models
checklist have no config parameter and threading one through every dataclass
would touch half the package. Tests call `activate(None)` / `reset()`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: The renderer contract models.py's checklist was written against.
LEGACY_RENDERER = 'acme-service-page'
#: Any other renderer: structural routing checks still apply, renderer-internal
#: checks (sections union, builders, card grids, transform escape) do not.
GENERIC_RENDERER = 'generic'

KNOWN_RENDERER_CONTRACTS = frozenset({LEGACY_RENDERER, GENERIC_RENDERER})


@dataclass(frozen=True)
class RepoLayout:
    renderer_contract: str = LEGACY_RENDERER
    route_arrays_by_segments: dict[int, str] = field(default_factory=lambda: {
        1: 'METRO_PAGES',
        2: 'SPOKE_PAGES',
        3: 'SUBSERVICE_PAGES',
    })
    route_files: dict[str, str] = field(default_factory=lambda: {
        'METRO_PAGES': 'src/app/[slug]/page.tsx',
        'SPOKE_PAGES': 'src/app/[slug]/[city]/page.tsx',
        'SUBSERVICE_PAGES': 'src/app/[slug]/[city]/[subservice]/page.tsx',
    })
    data_file_registry: dict[str, str] = field(default_factory=lambda: {
        'src/data/location-pages.ts': 'allLocationPages',
        'src/data/services.ts': 'allServices',
    })
    default_data_file: str = 'src/data/location-pages.ts'
    segments_by_kind: dict[str, tuple[int, ...]] = field(default_factory=lambda: {
        'hub': (1,),
        'spoke': (2,),
        'subservice': (2, 3),
        'catalog': (1, 2),      # non-geo product/collection pages (Profile B)
    })
    metro_hubs: frozenset[str] = frozenset({'charlotte-nc', 'asheville-nc'})
    subservice_suffixes: tuple[str, ...] = (
        'installation', 'repair', 'replacement', 'services', 'claims')

    @property
    def is_acme_renderer(self) -> bool:
        return self.renderer_contract == LEGACY_RENDERER

    @property
    def subservice_suffix_re(self) -> re.Pattern[str]:
        return re.compile(r'-(' + '|'.join(re.escape(s) for s in self.subservice_suffixes) + r')$')


DEFAULT = RepoLayout()
_active: RepoLayout = DEFAULT


def active() -> RepoLayout:
    return _active


def reset() -> None:
    global _active
    _active = DEFAULT


def from_config(cfg: dict[str, Any] | None) -> RepoLayout:
    """Build a RepoLayout from a loaded client-config dict. Absent/partial
    `repo.layout:` degrades field-by-field to the Acme defaults. Bad shapes
    raise ValueError — a half-read layout must never silently classify."""
    raw = ((cfg or {}).get('repo') or {}).get('layout') or {}
    if not isinstance(raw, dict):
        raise ValueError(f'repo.layout must be a mapping, got {type(raw).__name__}')
    if not raw:
        return DEFAULT

    kw: dict[str, Any] = {}
    contract = raw.get('renderer_contract')
    if contract is not None:
        if contract not in KNOWN_RENDERER_CONTRACTS:
            raise ValueError(
                f'repo.layout.renderer_contract {contract!r} unknown '
                f'(known: {sorted(KNOWN_RENDERER_CONTRACTS)})')
        kw['renderer_contract'] = contract

    rabs = raw.get('route_arrays_by_segments')
    if rabs is not None:
        kw['route_arrays_by_segments'] = {int(k): str(v) for k, v in dict(rabs).items()}
    rf = raw.get('route_files')
    if rf is not None:
        kw['route_files'] = {str(k): str(v) for k, v in dict(rf).items()}
    dfr = raw.get('data_files')
    if dfr is not None:
        kw['data_file_registry'] = {str(k): str(v) for k, v in dict(dfr).items()}
    ddf = raw.get('default_data_file')
    if ddf is not None:
        kw['default_data_file'] = str(ddf)
    sbk = raw.get('segments_by_kind')
    if sbk is not None:
        kw['segments_by_kind'] = {
            str(k): tuple(int(x) for x in (v if isinstance(v, (list, tuple)) else [v]))
            for k, v in dict(sbk).items()}
    hubs = raw.get('metro_hubs')
    if hubs is not None:
        kw['metro_hubs'] = frozenset(str(h) for h in hubs)
    suf = raw.get('subservice_suffixes')
    if suf is not None:
        kw['subservice_suffixes'] = tuple(str(s) for s in suf)

    layout = RepoLayout(**kw)
    if layout.default_data_file not in layout.data_file_registry:
        raise ValueError(
            f'repo.layout.default_data_file {layout.default_data_file!r} is not a key of '
            f'data_files {sorted(layout.data_file_registry)}')
    return layout


def activate(cfg: dict[str, Any] | None) -> RepoLayout:
    """Set the process-active layout from a loaded client config (None resets
    to the Acme defaults). Call once per CLI run, right after load_config."""
    global _active
    _active = from_config(cfg)
    return _active
