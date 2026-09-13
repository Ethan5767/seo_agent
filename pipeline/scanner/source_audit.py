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
import re
import urllib.request

# Strip // line and /* */ block comments so a commented-out `// metadataBase`
# or `// images` can't produce a false "pass". Not a full JS parse — good enough
# to keep the string-match checks honest against disabled config.
# Strip block comments, and line comments only when the `//` isn't glued to a
# URL/string/word: the lookbehind rejects `:` (https://), `/` (already //),
# a quote (a "//cdn" string) and a word char (a//b), so protocol-relative URLs
# and CDN hosts survive while real `x = 1 // note` comments are removed.
_COMMENT = re.compile(r"""/\*.*?\*/|(?<![:/\w'"])//[^\n]*""", re.DOTALL)


def _strip_comments(text: str) -> str:
    return _COMMENT.sub("", text or "")


def _has_file(paths, files: dict, name: str) -> bool:
    """A file ending in `name` exists in the tree, or was fetched with content."""
    return any(p.endswith(name) for p in paths) or any(p.endswith(name) and files.get(p) for p in files)

_LAYOUTS = ["app/layout.tsx", "app/layout.jsx", "app/layout.js",
            "src/app/layout.tsx", "src/app/layout.jsx", "src/app/layout.js"]

_FILES = ["package.json", "next.config.js", "next.config.mjs", "next.config.ts",
          "public/robots.txt", "public/sitemap.xml", "robots.txt"] + _LAYOUTS

_ANALYTICS = ("@vercel/analytics", "react-ga", "react-ga4", "@next/third-parties",
              "gtag", "google-analytics", "posthog-js", "@segment/analytics-next")


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
    has_robots = _has_file(paths, files, "robots.txt") or robots_route
    rows.append(_row("Source: robots.txt", "ok" if has_robots else "warn",
                     "robots.txt is provided (static file or a route handler)." if has_robots
                     else "No robots.txt anywhere in the repo — crawlers get no explicit instructions.",
                     "keep it" if has_robots else "add public/robots.txt (or app/robots.ts) allowing the AI citation crawlers",
                     detail="route" if robots_route and not any(p.endswith("robots.txt") for p in paths) else ""))

    # sitemap.xml — static file, app/sitemap route, or next-sitemap generation.
    sitemap_route = any(p.split("/")[-1].startswith("sitemap.") and p.startswith(("app/", "src/app/")) for p in paths)
    next_sitemap = "next-sitemap" in deps or any("next-sitemap.config" in p for p in paths)
    has_sitemap = _has_file(paths, files, "sitemap.xml") or sitemap_route or next_sitemap
    rows.append(_row("Source: sitemap.xml", "ok" if has_sitemap else "warn",
                     "A sitemap is provided (static, a route handler, or next-sitemap)." if has_sitemap
                     else "No sitemap in the repo and no generator configured.",
                     "keep it" if has_sitemap else "add a sitemap.xml, an app/sitemap.ts, or the next-sitemap package",
                     detail="next-sitemap" if next_sitemap and not sitemap_route else ("route" if sitemap_route else "")))

    # llms.txt — reported, not recommended. No search or answer engine documents
    # reading one, and Google's AI-features documentation says the opposite in
    # as many words: "You don't need to create new machine readable files, AI
    # text files, or markup to appear in these features." Publishing it costs
    # nothing and proves nothing, so the row states presence and stops. Selling
    # it as a visibility lever would be the invention the provenance gate exists
    # to refuse.
    has_llms = _has_file(paths, files, "llms.txt")
    rows.append(_row("Source: llms.txt", "info",
                     "llms.txt is present. No engine documents reading one, so treat it as optional housekeeping."
                     if has_llms
                     else "No llms.txt. No engine documents reading one, and Google states no AI text file is needed, so this is not a gap.",
                     "no action needed"))

    # middleware — edge control over headers / redirects / i18n (a bonus signal).
    if any(p in paths for p in ("middleware.ts", "middleware.js", "src/middleware.ts", "src/middleware.js")):
        rows.append(_row("Source: middleware", "ok",
                         "middleware present — can set security/caching headers, redirects and i18n at the edge.",
                         "keep it"))

    # next.config — parse the one that was fetched (string checks, not a JS parse).
    cfg = next((files[p] for p in ("next.config.js", "next.config.mjs", "next.config.ts") if files.get(p)), None)
    if cfg:
        rows.extend(_next_config_rows(cfg))

    # Root-layout metadata (App Router) — the code-level SEO/OG setup.
    layout = next((files[p] for p in _LAYOUTS if files.get(p)), None)
    if layout:
        rows.extend(_metadata_rows(layout))

    # Analytics — measurement is wired in (from deps).
    if any(a in deps for a in _ANALYTICS):
        rows.append(_row("Source: analytics", "ok",
                         "Analytics is wired in — you can measure what the SEO work moves.",
                         "keep it"))
    return rows


def _metadata_rows(layout: str) -> list[dict]:
    """SEO/OG signals from the App Router root layout (string match)."""
    layout = _strip_comments(layout)
    rows: list[dict] = []
    has_base = "metadataBase" in layout
    rows.append(_row("Source: metadataBase", "ok" if has_base else "warn",
                     "metadataBase is set — canonical and Open Graph URLs resolve to absolute." if has_base
                     else "No metadataBase in the root layout — OG/canonical URLs can end up relative and ignored.",
                     "keep it" if has_base else "set metadataBase: new URL(siteUrl) in the root layout"))
    has_meta = "export const metadata" in layout or "generateMetadata" in layout
    rows.append(_row("Source: default metadata", "ok" if has_meta else "warn",
                     "A default metadata export sets title/description site-wide." if has_meta
                     else "No metadata export in the root layout — pages inherit no default title/description.",
                     "keep it" if has_meta else "export const metadata with a default title + description template"))
    if "openGraph" in layout or "twitter" in layout:
        rows.append(_row("Source: social tags", "ok",
                         "Open Graph / Twitter card metadata is defined — rich link previews.",
                         "keep it"))
    if "next/font" in layout:
        rows.append(_row("Source: fonts", "ok",
                         "next/font — self-hosted, layout-shift-free fonts (helps CLS + speed).",
                         "keep it"))
    return rows


def _next_config_rows(cfg: str) -> list[dict]:
    """SEO-relevant signals from next.config (string match, tolerant of format)."""
    cfg = _strip_comments(cfg)
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
