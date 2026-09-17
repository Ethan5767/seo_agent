"""common.py — framework-family mapping, build-dir resolution (the Northstar stale
wrapper footgun), and client-profile topology derivation.

resolve_build_dir is the silent-failure guard: a stale config path that resolves
to a missing dir makes every built-mode gate scan zero pages and report green.
"""
from __future__ import annotations

import subprocess

import pytest

from pipeline.lib.common import (
    curl,
    curl_status,
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


# ── curl / curl_status timeout handling ──────────────────────────────────────
# A hung host must be reported as unreachable, not crash the run. Found by a
# real wf-site-health smoke run against an unresolvable domain, where curl hung
# for the full 30s and TimeoutExpired propagated as an uncaught traceback,
# bypassing the exit-19 refusal path entirely.

def test_curl_returns_empty_on_timeout(monkeypatch):
    def hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="curl", timeout=30)
    monkeypatch.setattr(subprocess, "run", hang)
    assert curl("https://hung.example.com/") == ""


def test_curl_status_returns_zero_on_timeout(monkeypatch):
    def hang(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="curl", timeout=30)
    monkeypatch.setattr(subprocess, "run", hang)
    assert curl_status("https://hung.example.com/") == 0


# ── curl_full: body AND response headers from one fetch ──────────────────────
#
# `curl -sL` returned the body alone, so nothing downstream could see a response
# header. That one gap blocked the security headers, X-Robots-Tag, cache and
# compression checks and soft-404 detection, and hid every redirect hop behind
# -L's silent follow.

CURL_DUMP = (
    "HTTP/2 301 \r\n"
    "location: https://www.x.com/\r\n"
    "server: cloudflare\r\n"
    "\r\n"
    "HTTP/2 200 \r\n"
    "content-type: text/html; charset=utf-8\r\n"
    "X-Frame-Options: DENY\r\n"
    "cache-control: public, max-age=0\r\n"
    "\r\n"
    "<html><body>hi</body></html>"
)


def _stub(monkeypatch, stdout, code=0):
    import types
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=stdout, stderr="", returncode=code))


def test_curl_full_splits_headers_from_body(monkeypatch):
    from pipeline.lib.common import curl_full
    _stub(monkeypatch, CURL_DUMP)
    r = curl_full("https://x.com/")
    assert r["body"] == "<html><body>hi</body></html>"
    assert r["status"] == 200
    # Header names are matched by callers, so the dict is lower-cased for them.
    assert r["headers"]["x-frame-options"] == "DENY"
    assert r["headers"]["cache-control"] == "public, max-age=0"


def test_curl_full_records_every_redirect_hop(monkeypatch):
    """-L's auto-follow hid the chain: a 302 chain and a clean 301 looked the
    same. Each hop's status and Location is what makes them different."""
    from pipeline.lib.common import curl_full
    _stub(monkeypatch, CURL_DUMP)
    r = curl_full("https://x.com/")
    assert [h["status"] for h in r["chain"]] == [301, 200]
    assert r["chain"][0]["location"] == "https://www.x.com/"
    assert r["chain"][1]["location"] == ""


def test_curl_full_is_unreachable_not_a_crash_on_timeout(monkeypatch):
    from pipeline.lib.common import curl_full

    def hang(*a, **k):
        raise subprocess.TimeoutExpired(cmd="curl", timeout=30)

    monkeypatch.setattr(subprocess, "run", hang)
    r = curl_full("https://hung.example.com/")
    assert r == {"body": "", "status": 0, "headers": {}, "chain": []}


def test_curl_full_handles_a_response_with_no_body(monkeypatch):
    from pipeline.lib.common import curl_full
    _stub(monkeypatch, "HTTP/1.1 404 Not Found\r\ncontent-type: text/html\r\n\r\n")
    r = curl_full("https://x.com/nope")
    assert r["status"] == 404 and r["body"] == ""


def test_curl_keeps_returning_just_the_body(monkeypatch):
    """Every existing caller takes a string. curl_full is additive."""
    _stub(monkeypatch, CURL_DUMP)
    assert curl("https://x.com/") == "<html><body>hi</body></html>"
