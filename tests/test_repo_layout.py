"""P0-2 (ENGINE-FIXES-2026-08 fixes 2, 9, 10): per-repo layout + renderer contract.

The emitter/models checklist encoded exactly one repo shape (Acme's). The
2026-08 cycle blockers this pins: `route_array_unknown` on BLH North's
4-segment geo spokes, `subservice_suffix_missing` on real live slugs
(`basement-waterproofing`), `new_metro_hub` warns against another client's
hardcoded metros, and `transform_would_rewrite` firing on renderers that never
call that transform (Northstar x16, BLH).
"""

import pytest

from pipeline.generate import repo_layout
from pipeline.generate.models import Hero, PageDraft, Section, structural_findings


def _draft(url_path: str, page_kind: str, sections=None) -> PageDraft:
    return PageDraft(
        url_path=url_path,
        city='Hamilton', state='NJ', service='Masonry',
        h1='Test Page Heading',
        meta_title='Masonry Contractor in Hamilton NJ | Blueline Mechanical',
        meta_description='Test meta description for layout fixtures.',
        hero=Hero(badge_icon='', badge_text='',
                  title='Test Page Heading', description='Short hero copy.'),
        page_kind=page_kind,
        sections=sections or [],
    )


def _codes(draft):
    return {f.code for f in structural_findings(draft)}


# --- from_config -----------------------------------------------------------

def test_absent_layout_is_acme_default():
    layout = repo_layout.from_config({'repo': {}})
    assert layout is repo_layout.DEFAULT
    assert layout.is_acme_renderer


def test_unknown_renderer_contract_raises():
    with pytest.raises(ValueError):
        repo_layout.from_config({'repo': {'layout': {'renderer_contract': 'sveltekit'}}})


def test_default_data_file_must_be_registered():
    with pytest.raises(ValueError):
        repo_layout.from_config({'repo': {'layout': {
            'default_data_file': 'src/data/nope.ts'}}})


def test_partial_override_keeps_other_defaults():
    layout = repo_layout.from_config({'repo': {'layout': {
        'route_arrays_by_segments': {2: 'SPOKE_PAGES', 4: 'GEO_SPOKE_PAGES'},
    }}})
    assert layout.route_arrays_by_segments[4] == 'GEO_SPOKE_PAGES'
    assert layout.data_file_registry == repo_layout.DEFAULT.data_file_registry


# --- the 2026-08 blockers, reproduced then released ------------------------

def test_four_segment_route_refused_by_default_expressible_by_layout():
    d = _draft('/nj/mercer-county/hamilton/masonry/', 'spoke')
    assert 'route_array_unknown' in _codes(d)          # the BLH North blocker

    repo_layout.activate({'repo': {'layout': {
        'renderer_contract': 'generic',
        'route_arrays_by_segments': {4: 'GEO_SPOKE_PAGES'},
        'route_files': {'GEO_SPOKE_PAGES': 'app/[state]/[county]/[city]/[service]/page.tsx'},
        'segments_by_kind': {'hub': [1], 'spoke': [2, 4], 'subservice': [2, 3]},
    }}})
    codes = _codes(d)
    assert 'route_array_unknown' not in codes
    assert 'segment_count_mismatch' not in codes
    assert d.route_array == 'GEO_SPOKE_PAGES'


def test_subservice_suffix_vocabulary_is_layout_driven():
    d = _draft('/pennington-nj/basement-waterproofing/', 'subservice')
    assert 'subservice_suffix_missing' in _codes(d)     # real live slug, refused

    repo_layout.activate({'repo': {'layout': {
        'subservice_suffixes': ['installation', 'repair', 'waterproofing'],
    }}})
    assert 'subservice_suffix_missing' not in _codes(d)


def test_metro_hubs_are_layout_driven():
    d = _draft('/trenton-nj/', 'hub')
    assert any(f.code == 'new_metro_hub' for f in structural_findings(d))

    repo_layout.activate({'repo': {'layout': {'metro_hubs': ['trenton-nj']}}})
    assert not any(f.code == 'new_metro_hub' for f in structural_findings(d))


def test_generic_renderer_skips_acme_renderer_checks():
    sections = [Section(type='not-a-acme-type', props={})]
    d = _draft('/hamilton-nj/masonry-repair/', 'spoke', sections=sections)

    default_codes = _codes(d)                           # Acme contract: both fire
    assert 'transform_would_rewrite' in default_codes
    assert 'unknown_section_type' in default_codes

    repo_layout.activate({'repo': {'layout': {'renderer_contract': 'generic'}}})
    generic_codes = _codes(d)
    assert 'transform_would_rewrite' not in generic_codes
    assert 'unknown_section_type' not in generic_codes


def test_content_checks_always_run_regardless_of_renderer():
    repo_layout.activate({'repo': {'layout': {'renderer_contract': 'generic'}}})
    d = _draft('/hamilton-nj/masonry-repair/', 'spoke')
    d = type(d)(**{**d.__dict__, 'hero': Hero(
        badge_icon='', badge_text='', title='Test Page Heading',
        description=('word ' * 40).strip())})           # 40w > 25w hero rule
    assert any(f.code == 'hero_rule' for f in structural_findings(d))
