"""common.py — framework-family mapping, build-dir resolution (the Northstar stale
wrapper footgun), and client-profile topology derivation.

resolve_build_dir is the silent-failure guard: a stale config path that resolves
to a missing dir makes every built-mode gate scan zero pages and report green.
"""
from __future__ import annotations

import pytest

from pipeline.lib.common import (
    framework_family,
    resolve_build_dir,
    client_profile,
    FRAMEWORK_FAMILY_DEFAULT_DIR,
)


# ── framework_family ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("nextjs-app-router", "next"),
    ("next.js-15-app-router", "next"),
    ("vite-react-ssg-custom", "vite"),
    ("wordpress", "wordpress"),
    ("wp-headless", "wordpress"),
    ("", None),
    ("gatsby", None),
])
def test_framework_family_mapping(raw, expected):
    assert framework_family(raw) == expected


# ── resolve_build_dir ────────────────────────────────────────────────────────

def test_resolve_build_dir_prefers_existing_configured(tmp_path):
    (tmp_path / "out").mkdir()
    prof = {"framework_family": "next", "build_output_dir": "out"}
    assert resolve_build_dir(prof, tmp_path) == "./out"


def test_resolve_build_dir_strips_stale_wrapper_segment(tmp_path):
    """The Northstar footgun: config still carries a `<repo>-main/` wrapper prefix that
    never existed on disk. resolve must drop the leading segment and find `dist`."""
    (tmp_path / "dist").mkdir()
    prof = {"framework_family": "vite",
            "build_output_dir": "northstar-landscaping-site-main/dist"}
    assert resolve_build_dir(prof, tmp_path) == "./dist"


def test_resolve_build_dir_falls_back_to_family_default(tmp_path):
    """Nothing on disk yet (pre-build): fall back to the family default, not the
    stale configured path."""
    prof = {"framework_family": "next", "build_output_dir": "some-wrapper/out"}
    assert resolve_build_dir(prof, tmp_path) == "./out"
    prof_vite = {"framework_family": "vite", "build_output_dir": ""}
    assert resolve_build_dir(prof_vite, tmp_path) == "./dist"


def test_resolve_build_dir_tolerates_missing_keys(tmp_path):
    """Never raises on an empty profile — defaults to next's `out`."""
    assert resolve_build_dir({}, tmp_path) == "./out"


# ── client_profile topology derivation ───────────────────────────────────────

def test_topology_derived_single_state():
    cfg = {"client": "acme", "states_served": ["NC"], "repo": {"framework": "nextjs"}}
    prof = client_profile(cfg)
    assert prof["topology_class"] == "single-site-single-state"
    assert prof["topology_class_derived"] is True
    assert prof["is_multi_state"] is False


def test_topology_derived_multi_state():
    cfg = {"client": "Lee", "states_served": ["MD", "FL"], "repo": {"framework": "nextjs"}}
    prof = client_profile(cfg)
    assert prof["topology_class"] == "single-site-multi-state"
    assert prof["is_multi_state"] is True
    assert prof["state_count"] == 2


def test_topology_derived_multi_site_from_sisters():
    cfg = {"client": "Pat", "states_served": ["FL"],
           "sister_sites": [{"slug": "blh-north", "repo": "x/y"}],
           "repo": {"framework": "nextjs"}}
    prof = client_profile(cfg)
    assert prof["topology_class"] == "multi-site-division"
    assert prof["is_multi_site"] is True
    assert prof["site_count"] == 2


def test_explicit_topology_class_not_overridden():
    cfg = {"client": "x", "topology_class": "single-site-multi-state",
           "states_served": ["NC"], "repo": {"framework": "nextjs"}}
    prof = client_profile(cfg)
    assert prof["topology_class"] == "single-site-multi-state"
    assert prof["topology_class_derived"] is False


def test_states_served_string_is_split():
    cfg = {"client": "x", "states_served": "NC, SC, VA", "repo": {"framework": "nextjs"}}
    prof = client_profile(cfg)
    assert prof["states_served"] == ["NC", "SC", "VA"]
    assert prof["state_count"] == 3


def test_family_default_dir_table():
    assert FRAMEWORK_FAMILY_DEFAULT_DIR["next"] == "out"
    assert FRAMEWORK_FAMILY_DEFAULT_DIR["vite"] == "dist"
    assert FRAMEWORK_FAMILY_DEFAULT_DIR["wordpress"] is None
