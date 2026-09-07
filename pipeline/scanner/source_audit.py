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


def analyze_source(files: dict) -> list[dict]:
    """Report rows from the fetched repo files."""
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

    # robots.txt / sitemap.xml committed in the repo.
    has_robots = any("robots.txt" in p and files.get(p) for p in files)
    rows.append(_row("Source: robots.txt", "ok" if has_robots else "warn",
                     "robots.txt is committed in the repo." if has_robots
                     else "No robots.txt in the repo — crawlers get no explicit instructions.",
                     "keep it" if has_robots else "add public/robots.txt allowing the citation crawlers"))
    has_sitemap = any("sitemap" in p and files.get(p) for p in files)
    rows.append(_row("Source: sitemap.xml", "ok" if has_sitemap else "warn",
                     "sitemap.xml is committed in the repo." if has_sitemap
                     else "No sitemap.xml in the repo (may be generated at build — verify on the live site).",
                     "keep it" if has_sitemap else "add or generate a sitemap.xml"))
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


def _gh_get(url: str, token: str):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            doc = json.loads(r.read().decode())
        content = doc.get("content")
        return base64.b64decode(content).decode("utf-8", "replace") if content else None
    except Exception:
        return None
