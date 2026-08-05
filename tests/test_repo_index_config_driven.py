"""P0-1 (ENGINE-FIXES-2026-08 fix 1): the repo index is config-driven.

The 2026-08 cycle proved the hardcoded Next.js App Router scan blind on three
of five client repos: Northstar (Vite, 0 entries against a 162-URL site → 15/16
verdicts wrong), Crestline (locations.ts layout, entries: 0 vs a 118-URL
sitemap), BLH North (/services/ hubs read as NEW while sitemap-live). These
tests pin the fix: declared repo paths are honored, wrapper-stale prefixes
fall away, sitemap-live slugs classify UPDATE instead of NEW, and a fully
blind index refuses instead of returning confident NEWs.
"""

from pathlib import Path

import pytest

from pipeline.lib.common import client_profile, resolve_repo_path
from pipeline.generate.classify import (
    NEW,
    UPDATE,
    build_repo_index,
    classify_draft,
)
from pipeline.generate.models import Hero, PageDraft


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/landscape-material/topsoil/</loc></url>
  <url><loc>https://example.com/demolition/trenton-nj/</loc></url>
  <url><loc>https://example.com/services/</loc></url>
</urlset>
"""


def _draft(url_path: str) -> PageDraft:
    return PageDraft(
        url_path=url_path,
        city='Trenton', state='NJ', service='Topsoil',
        h1='Test Page Heading',
        meta_title='Test Meta Title',
        meta_description='Test meta description for classification fixtures.',
        hero=Hero(badge_icon='', badge_text='',
                  title='Test Page Heading', description='Test hero description.'),
        page_kind='location',
    )


@pytest.fixture()
def vite_repo(tmp_path: Path) -> Path:
    """A Northstar-shaped repo: no src/data/location-pages.ts, no out/, sitemap in
    public/, declared through a wrapper-stale repo: block."""
    (tmp_path / 'public').mkdir()
    (tmp_path / 'public' / 'sitemap.xml').write_text(SITEMAP, encoding='utf-8')
    (tmp_path / 'src' / 'data' / 'locations').mkdir(parents=True)
    (tmp_path / 'src' / 'data' / 'locations' / 'trenton.ts').write_text(
        '// no ServicePage exports here — custom Vite data shape\n', encoding='utf-8')
    return tmp_path


VITE_CFG = {
    'client_slug': 'vite-client',
    'states_served': ['NJ'],
    'topology': 'hub-spoke',
    'repo': {
        'framework': 'vite-react-ssg-custom',
        # deliberately wrapper-stale: the leading segment does not exist on disk
        'sitemap': 'The-Repo-main/public/sitemap.xml',
        'spoke_data_dir': 'The-Repo-main/src/data/locations',
    },
}


def test_resolve_repo_path_drops_stale_wrapper_prefix(vite_repo: Path):
    assert resolve_repo_path('The-Repo-main/public/sitemap.xml', vite_repo) == 'public/sitemap.xml'
    assert resolve_repo_path('public/sitemap.xml', vite_repo) == 'public/sitemap.xml'
    assert resolve_repo_path('Nope/never/was.xml', vite_repo) is None
    assert resolve_repo_path(None, vite_repo) is None
    assert resolve_repo_path('', vite_repo) is None


def test_configured_sitemap_is_read_and_source_recorded(vite_repo: Path):
    profile = client_profile(VITE_CFG, str(vite_repo))
    idx = build_repo_index(vite_repo, profile=profile)
    assert idx.sitemap_source == 'public/sitemap.xml'
    assert 'landscape-material/topsoil' in idx.sitemap_slugs
    assert 'demolition/trenton-nj' in idx.sitemap_slugs


def test_legacy_behavior_unchanged_without_profile(tmp_path: Path):
    """No profile → exactly the old scan: out/sitemap.xml or nothing."""
    (tmp_path / 'out').mkdir()
    (tmp_path / 'out' / 'sitemap.xml').write_text(SITEMAP, encoding='utf-8')
    idx = build_repo_index(tmp_path)
    assert idx.sitemap_source == 'out/sitemap.xml'
    assert len(idx.sitemap_slugs) >= 3


def test_sitemap_live_untyped_slug_classifies_update_not_new(vite_repo: Path):
    """The acceptance flip: a live page with no typed entry is an UPDATE."""
    profile = client_profile(VITE_CFG, str(vite_repo))
    idx = build_repo_index(vite_repo, profile=profile)

    live = classify_draft(_draft('/landscape-material/topsoil/'), idx, None)
    assert live.decision == UPDATE
    assert live.reason_code == 'live_in_sitemap_untyped'
    assert live.in_sitemap is True
    assert any('sitemap_match_untyped' in w for w in live.warnings)

    genuinely_new = classify_draft(_draft('/landscape-material/mulch/'), idx, None)
    assert genuinely_new.decision == NEW
    assert genuinely_new.reason_code == 'no_existing_entry'


def test_sitemap_seeds_shape_precedent_with_warning(vite_repo: Path):
    """A live 2-segment URL lets a same-shape draft through a topology the
    pattern table cannot express — with the weaker-evidence warning attached."""
    profile = client_profile(VITE_CFG, str(vite_repo))
    idx = build_repo_index(vite_repo, profile=profile)
    assert idx.sitemap_precedent_shapes  # seeded from sitemap, no typed entries

    # 'franchise' has patterns, but /landscape-material/mulch/ is a catalog
    # shape its table does not model — precedent must carry it through.
    d = classify_draft(_draft('/landscape-material/mulch/'), idx, 'franchise')
    assert d.decision == NEW
    assert any('topology_gap' in w for w in d.warnings)
    assert any('sitemap_precedent' in w for w in d.warnings)


def test_empty_index_has_no_entries_and_no_sitemap(tmp_path: Path):
    """The guard condition main() refuses on: nothing typed, nothing shipped."""
    idx = build_repo_index(tmp_path)
    assert not idx.entries
    assert not idx.sitemap_slugs
    assert idx.sitemap_source is None
