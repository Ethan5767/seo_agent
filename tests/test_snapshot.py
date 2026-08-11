"""snapshot.py — crawl a rendered deployment into the tree the nine OUT gates read.

Hermetic: `curl` and `curl_status` are stubbed, so no network. What is worth
testing is the SHAPE of the tree (three gates derive routes from
`<dir>/index.html`, so the flat form would starve them) and the refusal on an
empty crawl (an empty build dir makes every gate glob zero files and pass).
"""
from __future__ import annotations

import json

import pytest
import yaml

from pipeline.audit import snapshot as sn

PAGE = "<html><head><title>T</title></head><body><h1>H</h1></body></html>"
SITEMAP = ('<?xml version="1.0"?><urlset>'
           '<url><loc>https://acme.com/</loc></url>'
           '<url><loc>https://acme.com/about/</loc></url></urlset>')


@pytest.fixture
def project(tmp_path):
    p = tmp_path / "client"
    (p / "docs").mkdir(parents=True)
    (p / "docs" / "client-config.yml").write_text(yaml.safe_dump({
        "client": "acme", "domain": "acme.com",
        "repo": {"framework": "nextjs-16-app-router"}}))
    return p


@pytest.fixture
def served(monkeypatch):
    """A fake deployment: {url-suffix: body}. Anything not listed 404s."""
    pages = {}

    def _path(url):
        # Exact path match. An `endswith` stub would make every key ending in "/"
        # match every trailing-slash URL, so a 404 case could never be expressed.
        return "/" + url.split("://", 1)[-1].split("/", 1)[1] if "/" in \
            url.split("://", 1)[-1] else "/"

    def fake_status(url, **kw):
        return 200 if _path(url) in pages else 404

    def fake_curl(url, **kw):
        return pages.get(_path(url), "")

    monkeypatch.setattr(sn, "curl_status", fake_status)
    monkeypatch.setattr(sn, "curl", fake_curl)
    # The auth-wall probe (B-037). Stubbed to "the host you asked for answered",
    # which is the ordinary case; the wall tests below override it. Without this
    # stub every test here would make a real 30-second network call.
    monkeypatch.setattr(sn, "curl_final_host",
                        lambda url: url.split("://", 1)[-1].split("/", 1)[0].lower())
    # discover_urls fetches the LIVE sitemap through measure's own curl.
    monkeypatch.setattr("pipeline.audit.measure.curl", lambda u, **kw: SITEMAP)
    return pages


# ── the tree shape ───────────────────────────────────────────────────────────

def test_a_route_becomes_a_directory_with_an_index_html(project, served, tmp_path):
    """`<route>/index.html`, never `<route>.html`. parity_check and orphan_check
    derive a route from `<dir>/index.html` and noncommodity_check globs for
    `index.html` specifically — the flat form is a tree those three cannot read."""
    served.update({"/": PAGE, "/about/": PAGE})
    out = tmp_path / "out"
    out.mkdir()
    manifest = sn.snapshot(project, "https://pr-34.pages.dev", out, [])
    assert (out / "index.html").read_text() == PAGE
    assert (out / "about" / "index.html").read_text() == PAGE
    assert manifest["routes"] == ["/", "/about/"]


def test_the_manifest_says_the_html_came_from_a_crawl(project, served, tmp_path):
    # A crawl of a deployment and a local build are not the same evidence, and a
    # gate verdict over one must not be filed as the other.
    served.update({"/": PAGE})
    out = tmp_path / "out"
    out.mkdir()
    m = sn.snapshot(project, "https://pr-34.pages.dev", out, ["/"])
    assert m["source"] == "crawl"
    assert m["base_url"] == "https://pr-34.pages.dev"


def test_root_assets_are_captured_because_two_gates_read_them(project, served, tmp_path):
    # parity_check reads <out>/sitemap.xml, robots_aicrawler_check reads robots.txt.
    # A static export emits them; a crawl has to ask by name.
    served.update({"/": PAGE, "/sitemap.xml": SITEMAP, "/robots.txt": "User-agent: *\n"})
    out = tmp_path / "out"
    out.mkdir()
    m = sn.snapshot(project, "https://x.pages.dev", out, ["/"])
    assert (out / "sitemap.xml").read_text() == SITEMAP
    assert "robots.txt" in m["root_assets"]


def test_a_missing_root_asset_is_not_fatal(project, served, tmp_path):
    # Each of those gates has its own verdict for an absent file, and that verdict
    # is theirs to give — not ours to pre-empt by refusing the snapshot.
    served.update({"/": PAGE})
    out = tmp_path / "out"
    out.mkdir()
    m = sn.snapshot(project, "https://x.pages.dev", out, ["/"])
    assert m["root_assets"] == []
    assert m["routes"] == ["/"]


# ── a snapshot of nothing is not a clean site ────────────────────────────────

def test_an_empty_crawl_refuses_and_writes_no_tree(project, served, tmp_path):
    """THE property. An empty --out lets every OUT gate glob zero files and report
    PASS, which is worse than not running them — it is the exact failure this module
    exists to remove."""
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(sn.SnapshotError, match="report green"):
        sn.snapshot(project, "https://dead.pages.dev", out, ["/", "/about/"])
    assert list(out.iterdir()) == []


def test_an_auth_wall_refuses_instead_of_crawling_the_login_page(project, served,
                                                                 tmp_path, monkeypatch):
    """B-037 — the failure mode that is WORSE than an empty tree.

    Found live: lee's Vercel previews had Deployment Protection on, so every route
    302'd to `vercel.com/sso-api` and answered 200 with `<title>Login – Vercel</title>`.
    `curl -L` follows that, so the crawl would have written 26 identical login pages
    and reported success — and the nine OUT gates would have judged a login screen as
    the client's site. An empty --out at least leaves an empty directory to notice.
    """
    served.update({"/": PAGE, "/about/": PAGE})   # the wall answers 200 for everything
    monkeypatch.setattr(sn, "curl_final_host", lambda url: "vercel.com")
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(sn.SnapshotError, match="auth wall"):
        sn.snapshot(project, "https://lee-series-rn75is60j-lee-serie.vercel.app",
                    out, ["/", "/about/"])
    assert list(out.iterdir()) == [], "a walled crawl wrote a tree"


def test_a_same_host_redirect_is_still_followed(project, served, tmp_path, monkeypatch):
    """Narrowed, not disarmed. Trailing-slash policies and locale prefixes redirect
    within the same host and MUST keep working — that is why `curl -L` is there."""
    served.update({"/": PAGE, "/about/": PAGE})
    monkeypatch.setattr(sn, "curl_final_host", lambda url: "x.pages.dev")
    out = tmp_path / "out"
    out.mkdir()
    m = sn.snapshot(project, "https://x.pages.dev", out, ["/", "/about/"])
    assert m["routes"] == ["/", "/about/"]


def test_an_unreachable_probe_does_not_masquerade_as_a_wall(project, served, tmp_path,
                                                            monkeypatch):
    """`curl_final_host` returns "" when it cannot reach the host at all. That is
    already the empty-crawl case, which has its own refusal and its own message —
    reporting it as an auth wall would send the operator to the wrong setting."""
    monkeypatch.setattr(sn, "curl_final_host", lambda url: "")
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(sn.SnapshotError, match="report green"):
        sn.snapshot(project, "https://dead.pages.dev", out, ["/", "/about/"])


def test_a_route_that_404s_is_skipped_and_recorded(project, served, tmp_path):
    served.update({"/": PAGE})
    out = tmp_path / "out"
    out.mkdir()
    m = sn.snapshot(project, "https://x.pages.dev", out, ["/", "/gone/"])
    assert m["routes"] == ["/"]
    assert m["failed"] == [{"route": "/gone/", "status": 404}]
    assert not (out / "gone").exists()


def test_a_200_with_an_empty_body_is_a_failure_not_a_page(project, served, tmp_path):
    # An SSR shell that returns 200 and no HTML is the blank-shell disaster
    # audit_ssr exists for. Writing it would make every content gate scan nothing.
    served.update({"/": PAGE, "/empty/": "   "})
    out = tmp_path / "out"
    out.mkdir()
    m = sn.snapshot(project, "https://x.pages.dev", out, ["/", "/empty/"])
    assert m["routes"] == ["/"]
    assert m["failed"][0]["route"] == "/empty/"


# ── routes ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url, route", [
    ("https://acme.com/", "/"),
    ("https://acme.com/about", "/about/"),
    ("https://acme.com/a/b/", "/a/b/"),
    ("https://acme.com/x?utm=1", "/x/"),
])
def test_a_url_normalises_to_the_route_the_gates_use(url, route):
    assert sn.route_for(url) == route


def test_the_sitemap_comes_from_the_live_domain_not_the_candidate(project, served, tmp_path):
    """Reading the CANDIDATE's own sitemap would let a PR that dropped a route also
    drop it from the set of routes being judged."""
    served.update({"/": PAGE, "/about/": PAGE})
    out = tmp_path / "out"
    out.mkdir()
    m = sn.snapshot(project, "https://pr-34.pages.dev", out, [])
    # Both routes from the live sitemap were fetched from the preview base.
    assert m["routes"] == ["/", "/about/"]


def test_duplicate_routes_are_fetched_once(project, served, tmp_path):
    served.update({"/": PAGE, "/about/": PAGE})
    out = tmp_path / "out"
    out.mkdir()
    # `/about` and `/about/` are the same route; `/index` is NOT `/`.
    m = sn.snapshot(project, "https://x.pages.dev", out, ["/", "/", "/about", "/about/"])
    assert m["routes"] == ["/", "/about/"]
