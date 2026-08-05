"""P0-3 (ENGINE-FIXES-2026-08 fix 3): `url_topology:` is honored.

The multistate gate has always REQUIRED `url_topology:` (city-state-direct /
locations-state-city / single-state) while client_profile read `topology:`
unconditionally — so Crestline could pass the gate (topology: multi-state-chain)
or classify correctly (its /baltimore-md/ shape), never both. Proven both ways
on the 2026-08 run: multi-state-chain → gate PASS + 24 INVALID;
satellite-offices → correct verdicts + gate FAIL exit 1.
"""

from pipeline.lib.common import (
    TOPOLOGY_PATTERNS,
    client_profile,
    url_fits_topology,
    validate_profile,
)


def test_city_state_direct_patterns_match_crestlines_real_urls():
    assert url_fits_topology('/baltimore-md/', 'city-state-direct') == (True, 'hub')
    assert url_fits_topology('/baltimore-md/roof-replacement/', 'city-state-direct') == (True, 'spoke')
    assert url_fits_topology('/md/baltimore/', 'city-state-direct')[0] is False


def test_locations_state_city_patterns():
    assert url_fits_topology('/locations/md/baltimore/', 'locations-state-city') == (True, 'hub')
    assert url_fits_topology('/locations/md/baltimore/roofing/', 'locations-state-city') == (True, 'spoke')
    assert url_fits_topology('/baltimore-md/', 'locations-state-city')[0] is False


def _cfg(**kw):
    base = {'client_slug': 't', 'states_served': ['MD', 'FL']}
    base.update(kw)
    return base


def test_url_topology_key_wins_when_known():
    p = client_profile(_cfg(topology='multi-state-chain', url_topology='city-state-direct'))
    assert p['url_topology'] == 'city-state-direct'
    assert p['url_topology_declared'] == 'city-state-direct'


def test_single_state_value_falls_back_to_topology():
    p = client_profile(_cfg(topology='franchise', url_topology='single-state'))
    assert p['url_topology'] == 'franchise'
    # documented gate vocabulary — no warning
    assert not [i for i in validate_profile(p) if 'url_topology' in i[1]]


def test_unknown_url_topology_falls_back_and_warns():
    p = client_profile(_cfg(topology='franchise', url_topology='zigzag-shape'))
    assert p['url_topology'] == 'franchise'
    warns = [i for i in validate_profile(p) if 'url_topology' in i[1]]
    assert warns and warns[0][0] == 'WARN'


def test_absent_url_topology_is_legacy_behavior():
    p = client_profile(_cfg(topology='franchise'))
    assert p['url_topology'] == 'franchise'
    assert p['url_topology_declared'] is None


def test_every_gate_vocabulary_value_resolves():
    """The multistate gate's required values must all be usable: pattern-table
    members directly, 'single-state' via fallback."""
    for v in ('city-state-direct', 'locations-state-city'):
        assert v in TOPOLOGY_PATTERNS
