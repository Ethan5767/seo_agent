"""Source-code audit — reads a GitHub repo (read-only) to judge things the live
HTML can only guess at: the framework and its rendering model (SSR vs CSR), and
whether robots.txt / sitemap.xml are committed.

`analyze_source(files)` is pure (files = {path: text}) so it's unit-tested
offline. `fetch_repo_files(repo, token, fetch)` pulls the handful of files we
need via the GitHub contents API (read-only token). Only for `owner/name`
GitHub repos; a local path is skipped.
"""
from __future__ import annotations

import base64
import json
import urllib.request

_FILES = ["package.json", "next.config.js", "next.config.mjs", "next.config.ts",
          "public/robots.txt", "public/sitemap.xml", "robots.txt"]


def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": f"src.{what.lower().replace(' ', '_').replace(':', '')}", "what": what,
            "why": why, "fix": fix, "detail": detail, "severity": severity}


def analyze_source(files: dict, tree: list | None = None) -> list[dict]:
    """Report rows from the fetched repo files. `tree` is the repo's full path
    list (from fetch_repo_tree) — it powers cheap existence checks (route files,
    llms.txt, middleware) without fetching each file. Defaults to the fetched
    file paths so older callers still work."""
    paths = set(tree if tree is not None else files)
    rows: list[dict] = []
    pkg_raw = files.get("package.json")
    deps: dict = {}
    if pkg_raw:
        try:
            pkg = json.loads(pkg_raw)
            deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        except (ValueError, TypeError):
            pass

    # Framework + rendering model — the definitive SSR/CSR read.
    if not pkg_raw:
        rows.append(_row("Source: framework", "info",
                         "No package.json at the repo root — can't detect the framework from source.",
                         "point at the repo/branch that holds the site code"))
    elif "next" in deps:
        rows.append(_row("Source: rendering", "ok",
                         "Next.js — supports server-side rendering / static generation, so crawlers and AI bots get real HTML.",
                         "keep SSR/SSG on for content pages", detail="Next.js"))
    elif "react-scripts" in deps:
        rows.append(_row("Source: rendering", "error",
                         "Create React App — a client-side SPA. Search and AI crawlers get an empty shell on first load.",
                         "move to Next.js/SSG or add prerendering", detail="CRA (CSR)"))
    elif "nuxt" in deps:
        rows.append(_row("Source: rendering", "ok",
                         "Nuxt — Vue with SSR/SSG, crawler-friendly.", "keep SSR on", detail="Nuxt"))
    elif "vite" in deps:
        rows.append(_row("Source: rendering", "warn",
                         "Vite SPA — client-side rendered unless SSR is configured; risky for SEO/AEO.",
                         "add SSR/prerender (e.g. vite-ssg) or move to Next.js", detail="Vite SPA"))
    elif "@angular/core" in deps:
        rows.append(_row("Source: rendering", "warn",
                         "Angular SPA — needs Angular Universal for crawler-visible HTML.",
                         "enable Angular Universal (SSR)", detail="Angular SPA"))
    else:
        rows.append(_row("Source: framework", "info",
                         "Framework not recognised from package.json.",
                         "verify the site is server-rendered or statically generated",
                         detail=", ".join(sorted(deps)[:5])))

    # Router — App Router (Next 13+) gives built-in metadata + route handlers.
    if any(p.startswith("app/") or p.startswith("src/app/") for p in paths):
        rows.append(_row("Source: router", "ok",
                         "App Router (Next 13+) — built-in metadata API and robots/sitemap route handlers.",
                         "keep it", detail="app router"))
    elif any(p.startswith("pages/") or p.startswith("src/pages/") for p in paths):
        rows.append(_row("Source: router", "info",
                         "Pages Router — fine; metadata comes via next/head or _document.",
                         "metadata is manual here — keep title/description per page", detail="pages router"))

    # robots.txt — a static file, an app/robots route, or a pages route all count.
    robots_route = any(p.split("/")[-1].startswith("robots.") and (p.startswith(("app/", "src/app/"))) for p in paths)
    has_robots = any("robots.txt" in p and files.get(p) for p in files) \
        or any(p.endswith("robots.txt") for p in paths) or robots_route
    rows.append(_row("Source: robots.txt", "ok" if has_robots else "warn",
                     "robots.txt is provided (static file or a route handler)." if has_robots
                     else "No robots.txt anywhere in the repo — crawlers get no explicit instructions.",
                     "keep it" if has_robots else "add public/robots.txt (or app/robots.ts) allowing the AI citation crawlers",
                     detail="route" if robots_route and not any(p.endswith("robots.txt") for p in paths) else ""))

    # sitemap.xml — static file, app/sitemap route, or next-sitemap generation.
    sitemap_route = any(p.split("/")[-1].startswith("sitemap.") and p.startswith(("app/", "src/app/")) for p in paths)
    next_sitemap = "next-sitemap" in deps or any("next-sitemap.config" in p for p in paths)
    has_sitemap = any("sitemap" in p and files.get(p) for p in files) \
        or any(p.endswith("sitemap.xml") for p in paths) or sitemap_route or next_sitemap
    rows.append(_row("Source: sitemap.xml", "ok" if has_sitemap else "warn",
                     "A sitemap is provided (static, a route handler, or next-sitemap)." if has_sitemap
                     else "No sitemap in the repo and no generator configured.",
                     "keep it" if has_sitemap else "add a sitemap.xml, an app/sitemap.ts, or the next-sitemap package",
                     detail="next-sitemap" if next_sitemap and not sitemap_route else ("route" if sitemap_route else "")))

    # llms.txt — the AEO signpost for AI answer engines (optional but a plus).
    has_llms = any(p.endswith("llms.txt") for p in paths) or any("llms.txt" in p and files.get(p) for p in files)
    rows.append(_row("Source: llms.txt", "ok" if has_llms else "info",
                     "llms.txt is present — a curated signpost for AI answer engines." if has_llms
                     else "No llms.txt — an emerging (optional) way to guide AI engines to your key pages.",
                     "keep it" if has_llms else "consider adding public/llms.txt for AEO"))

    # middleware — edge control over headers / redirects / i18n (a bonus signal).
    if any(p in paths for p in ("middleware.ts", "middleware.js", "src/middleware.ts", "src/middleware.js")):
        rows.append(_row("Source: middleware", "ok",
                         "middleware present — can set security/caching headers, redirects and i18n at the edge.",
                         "keep it"))

    # next.config — parse the one that was fetched (string checks, not a JS parse).
    cfg = next((files[p] for p in ("next.config.js", "next.config.mjs", "next.config.ts") if files.get(p)), None)
    if cfg:
        rows.extend(_next_config_rows(cfg))
    return rows


def _next_config_rows(cfg: str) -> list[dict]:
    """SEO-relevant signals from next.config (string match, tolerant of format)."""
    rows: list[dict] = []
    if "i18n" in cfg:
        rows.append(_row("Source: i18n", "ok",
                         "i18n is configured — multi-language routing and hreflang readiness.",
                         "keep locales in sync with your hreflang tags"))
    has_headers = "headers(" in cfg or "headers :" in cfg or "headers:" in cfg
    rows.append(_row("Source: HTTP headers", "ok" if has_headers else "warn",
                     "Custom headers are configured — the place for security + cache-control headers." if has_headers
                     else "No headers() in next.config — security and cache-control headers aren't set here.",
                     "keep it" if has_headers else "add a headers() returning HSTS, X-Content-Type-Options and Cache-Control"))
    if "redirects(" in cfg:
        rows.append(_row("Source: redirects", "ok",
                         "redirects() is configured — old URLs can 301 to their new home (preserves link equity).",
                         "keep redirects current as URLs change"))
    if "trailingSlash" in cfg:
        rows.append(_row("Source: trailingSlash", "info",
                         "trailingSlash is set — make sure canonical URLs and the sitemap match it.",
                         "keep canonical + sitemap consistent with trailingSlash"))
    if "images" in cfg:
        rows.append(_row("Source: images", "ok",
                         "next/image is configured — responsive, optimised images out of the box.",
                         "keep using next/image for content images"))
    return rows


def fetch_repo_files(repo: str, token: str, fetch=None) -> dict:
    """{path: text} for the files we audit, via the GitHub contents API. `repo`
    is `owner/name`; a local path (no slash / a filesystem path) returns {}.
    `fetch(url, token) -> text|None` is injectable for tests."""
    if not repo or "/" not in repo or repo.startswith((".", "/", "~")):
        return {}
    fetch = fetch or _gh_get
    out: dict = {}
    for path in _FILES:
        text = fetch(f"https://api.github.com/repos/{repo}/contents/{path}", token)
        if text is not None:
            out[path] = text
    return out


def fetch_repo_tree(repo: str, token: str, fetch=None) -> list:
    """Every blob (file) path in the repo, via one git/trees?recursive=1 call.
    `repo` is `owner/name`; a local path returns []. `fetch(url, token) -> dict`
    is injectable for tests. Tries `main` then `master`."""
    if not repo or "/" not in repo or repo.startswith((".", "/", "~")):
        return []
    fetch = fetch or _gh_get_json
    for branch in ("main", "master"):
        doc = fetch(f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1", token)
        if doc and doc.get("tree"):
            return [it["path"] for it in doc["tree"] if it.get("type") == "blob" and it.get("path")]
    return []


def _gh_get(url: str, token: str):
    doc = _gh_get_json(url, token)
    if not doc:
        return None
    content = doc.get("content")
    return base64.b64decode(content).decode("utf-8", "replace") if content else None


def _gh_get_json(url: str, token: str):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None
