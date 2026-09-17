"""MONITOR — the production watch, as the product can run it.

The pipeline ends at a human merge; after that, the only thing looking at the
live site is the daily `seo-health` workflow inside the client's repo
(.github/workflows/seo-health.reusable.yml). It asserts exactly what is below —
every watched route answers 200 with a real body and carries a title, an h1, a
canonical and JSON-LD; the sitemap still lists what it should; the AI citation
crawlers still reach the edge.

Nothing in the product could run those checks or show what they found, so a
client without that workflow was gated but unwatched, and an operator had to read
Actions logs to learn anything. The checks live here, phrased the same way, so
the two cannot drift.

Pure by construction: routes, robots, sitemap and the fetcher are arguments.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from pipeline.gates.robots_aicrawler_check import (DEFAULT_CITATION_UAS, parse_groups,
                                                   root_blocked, rules_for_ua)
from pipeline.lib.html import sitemap_locs
from pipeline.scanner.rows import make_row

_mk = make_row("monitor")


def _row(code: str, what: str, severity: str, why: str, fix: str, detail: str = "", pages=None) -> dict:
    r = _mk(what, severity, why, fix, detail)
    r["code"] = f"monitor.{code}"
    if pages:
        r["pages"] = pages
    return r


#: A 200 carrying less than this is a shell, not a page. The workflow's floor.
MIN_BODY_BYTES = 5000
#: Watched routes per run. The walk is serial, so this is a time budget.
DEFAULT_ROUTE_LIMIT = 10


def routes_to_watch(url: str, sitemap: str | None, limit: int = DEFAULT_ROUTE_LIMIT) -> list[str]:
    """The home page first, then the sitemap's own URLs, capped.

    Home is never dropped: it is the one route whose failure is unambiguous.
    """
    parts = urlsplit(url)
    home = urlunsplit((parts.scheme or "https", parts.netloc, "/", "", ""))
    routes = [home]
    for loc in sitemap_locs(sitemap or ""):
        if loc not in routes and urlsplit(loc).netloc == parts.netloc:
            routes.append(loc)
        if len(routes) >= limit:
            break
    return routes[:limit]


def _furniture(body: str) -> list[str]:
    """Which of the four page essentials this HTML is missing."""
    low = (body or "").lower()
    missing = []
    if "<title" not in low:
        missing.append("title")
    if "<h1" not in low:
        missing.append("h1")
    if 'rel="canonical"' not in low and "rel='canonical'" not in low:
        missing.append("canonical")
    if "application/ld+json" not in low:
        missing.append("JSON-LD")
    return missing


def monitor_rows(url: str, sitemap: str | None = None, robots: str | None = None,
                 fetch=None, routes: list | None = None, min_sitemap: int = 0,
                 limit: int = DEFAULT_ROUTE_LIMIT) -> list[dict]:
    """Rows for one monitor run over the live site."""
    from pipeline.lib.common import curl_full
    fetch = fetch or curl_full
    watched = routes or routes_to_watch(url, sitemap, limit)

    down: list[str] = []
    codes: list[str] = []
    shells: list[str] = []
    bare: dict = {}

    for route in watched:
        r = fetch(route, cache_bust=False) or {}
        status, body = r.get("status") or 0, r.get("body") or ""
        if status != 200:
            down.append(route)
            codes.append(f"{route.rsplit('/', 1)[-1] or '/'} → {status or 'unreachable'}")
            continue
        if len(body) < MIN_BODY_BYTES:
            shells.append(route)
            continue
        missing = _furniture(body)
        if missing:
            bare[route] = missing

    rows: list[dict] = []

    if down:
        rows.append(_row("routes_live", "Watched routes answer", "error",
                         f"{len(down)} of {len(watched)} watched route(s) did not return 200. A route that stops "
                         "answering is invisible to search engines and to visitors.",
                         "check the deployment and the routes listed here",
                         detail="; ".join(codes[:4]), pages=down))
    else:
        rows.append(_row("routes_live", "Watched routes answer", "ok",
                         f"All {len(watched)} watched route(s) returned 200.",
                         "passing", detail=f"{len(watched)} route(s)"))

    if shells:
        rows.append(_row("blank_shell", "Pages have a body", "error",
                         "These routes answered 200 with almost no HTML, which is what a broken build or a "
                         "client-side render failure looks like to a crawler. An uptime check would call this fine.",
                         "check the build output for these routes",
                         detail=f"under {MIN_BODY_BYTES} bytes", pages=shells))
    elif not down:
        rows.append(_row("blank_shell", "Pages have a body", "ok",
                         "Every watched route returned real HTML, not an empty shell.",
                         "passing", detail=f"at least {MIN_BODY_BYTES} bytes each"))

    if bare:
        every = sorted({m for miss in bare.values() for m in miss})
        rows.append(_row("page_furniture", "Title, h1, canonical and schema", "error",
                         "Routes are missing page essentials that were present when the work was merged: "
                         + ", ".join(every) + ". A regression here is silent — the page still loads.",
                         "restore the missing tags on the routes listed here",
                         detail="missing: " + ", ".join(every), pages=sorted(bare)))
    elif not down and not shells:
        rows.append(_row("page_furniture", "Title, h1, canonical and schema", "ok",
                         "Every watched route carries a title, an h1, a canonical and JSON-LD.",
                         "passing", detail=f"{len(watched)} route(s) checked"))

    locs = sitemap_locs(sitemap or "")
    if not sitemap:
        rows.append(_row("sitemap_size", "Sitemap", "warn",
                         "No sitemap was read, so a sitemap that shrank or disappeared would not be noticed.",
                         "serve a sitemap.xml and list it in robots.txt", detail="not served"))
    elif min_sitemap and len(locs) < min_sitemap:
        rows.append(_row("sitemap_size", "Sitemap", "error",
                         f"The sitemap lists {len(locs)} URLs, below the {min_sitemap} expected. Pages usually "
                         "disappear from a sitemap because a build dropped them.",
                         "check what stopped being generated",
                         detail=f"{len(locs)} URLs, expected at least {min_sitemap}"))
    else:
        rows.append(_row("sitemap_size", "Sitemap", "ok",
                         f"The sitemap lists {len(locs)} URL(s).",
                         "passing", detail=f"{len(locs)} URLs"))

    if not (robots or "").strip():
        rows.append(_row("ai_crawlers", "AI citation crawlers", "warn",
                         "No robots.txt was served, so whether AI answer engines may read this site is decided by "
                         "each crawler's default rather than by the site.",
                         "serve a robots.txt that allows the citation crawlers", detail="no robots.txt"))
    else:
        groups = parse_groups(robots)
        # Same call shape as `audit.aeo_rows`: the rules that address this agent,
        # then whether they block the whole site. B-080 lives in that matcher.
        blocked = [ua for ua in DEFAULT_CITATION_UAS if root_blocked(rules_for_ua(groups, ua)[0])]
        if blocked:
            rows.append(_row("ai_crawlers", "AI citation crawlers", "error",
                             "robots.txt blocks crawlers that build the index AI answer engines cite from, so this "
                             "site cannot be quoted in their answers.",
                             "allow these crawlers in robots.txt",
                             detail=", ".join(blocked)))
        else:
            rows.append(_row("ai_crawlers", "AI citation crawlers", "ok",
                             "Every AI citation crawler we check reaches the live site.",
                             "passing", detail=f"{len(DEFAULT_CITATION_UAS)} crawlers allowed"))
    return rows
