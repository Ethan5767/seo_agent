#!/usr/bin/env python3
"""
parity-check.py — sitemap <-> built routes <-> llms.txt 3-way parity gate.

Lesson 5, the "32-vs-62 scar": on the Vite build the sitemap listed 32 URLs
while the site actually shipped 62 routes (and vice-versa drift the other way).
Either direction is an SEO bug: a built page missing from the sitemap is hidden
from crawlers; a sitemap URL with no built page is a soft-404 that burns crawl
budget and tanks trust.

This gate enforces, against a built `./out`:
    A. SITEMAP  == BUILT ROUTES   (set equality, excluding known utility pages)
    B. LLMS.TXT  consistency       (every llms.txt site URL is a real route /
                                    in the sitemap; reported, see --strict-llms)

Built routes are derived from the export output itself (every `<dir>/index.html`
=> "/<dir>/", plus root index.html => "/"), so it measures what ACTUALLY
shipped, not what a data file claims.

Utility pages excluded from the sitemap-equality check by default:
    /404/  /500/  /thank-you/  /_not-found/  and anything under /_next/.
These are intentionally noindex / not in the sitemap.

Exit codes:
    0  sitemap == built routes (and llms.txt clean, or only warned)
    1  any sitemap<->routes mismatch  (or llms mismatch when --strict-llms)

Usage:
    parity-check.py --out /tmp/acme/out
    parity-check.py --out ./out --llms ./public/llms.txt --strict-llms
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from urllib.parse import urlsplit, unquote

LOC_RE = re.compile(r"<loc>\s*([^<]+?)\s*</loc>", re.IGNORECASE)
HAS_EXT_RE = re.compile(r"/[^/]*\.[^/]+$")

DEFAULT_UTILITY = {"/404/", "/500/", "/thank-you/", "/_not-found/"}


def to_path(url: str) -> str:
    parts = urlsplit(url.strip())
    path = unquote(parts.path) or "/"
    if path != "/" and not path.endswith("/") and not HAS_EXT_RE.search(path):
        path += "/"
    if not path.startswith("/"):
        path = "/" + path
    return path


def sitemap_paths(out_dir: str) -> set[str]:
    paths: set[str] = set()
    files: list[str] = []
    for pat in ("sitemap.xml", os.path.join("sitemap", "*.xml"), "sitemap-*.xml"):
        files.extend(sorted(glob.glob(os.path.join(out_dir, pat))))
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for m in LOC_RE.finditer(fh.read()):
                paths.add(to_path(m.group(1)))
    return paths


def built_routes(out_dir: str) -> set[str]:
    routes: set[str] = set()
    for idx in glob.glob(os.path.join(out_dir, "**", "index.html"), recursive=True):
        rel = os.path.relpath(os.path.dirname(idx), out_dir)
        if rel == ".":
            routes.add("/")
            continue
        # skip _next internals
        if rel.split(os.sep)[0].startswith("_next"):
            continue
        route = "/" + rel.replace(os.sep, "/") + "/"
        routes.add(route)
    # top-level 404.html style pages (no index.html dir)
    for html in glob.glob(os.path.join(out_dir, "*.html")):
        name = os.path.basename(html)
        if name == "index.html":
            continue
        routes.add("/" + name[:-5] + "/")  # 404.html -> /404/
    return routes


def llms_paths(llms_file: str) -> set[str]:
    paths: set[str] = set()
    if not os.path.exists(llms_file):
        return paths
    with open(llms_file, encoding="utf-8") as fh:
        text = fh.read()
    for m in re.finditer(r"https?://[^\s)\]>\"']+", text):
        u = m.group(0).rstrip(".,)")
        # only same-site page URLs; skip social/external by host check handled by caller
        paths.add((urlsplit(u).netloc.lower(), to_path(u)))
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="3-way sitemap/routes/llms.txt parity check.")
    ap.add_argument("--out", default="./out")
    ap.add_argument("--llms", default=None, help="Path to llms.txt (default <out>/llms.txt then ./public/llms.txt)")
    ap.add_argument("--strict-llms", action="store_true", help="Fail (exit 1) on llms.txt mismatches too")
    ap.add_argument("--extra-utility", default="", help="Comma-separated extra routes to exclude from equality, e.g. /preview/")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        print(f"ERROR: out dir not found: {out_dir}", file=sys.stderr)
        return 1

    utility = set(DEFAULT_UTILITY)
    utility.update(p.strip() for p in args.extra_utility.split(",") if p.strip())

    sm = sitemap_paths(out_dir)
    if not sm:
        print(f"ERROR: no sitemap URLs found under {out_dir}", file=sys.stderr)
        return 1
    routes = {r for r in built_routes(out_dir) if r not in utility}
    sm_eff = {r for r in sm if r not in utility}

    missing_pages = sorted(sm_eff - routes)   # in sitemap, not built  -> soft-404 risk
    missing_sitemap = sorted(routes - sm_eff)  # built, not in sitemap -> hidden from crawlers

    failed = False
    print(f"parity-check: sitemap={len(sm_eff)} built-routes={len(routes)} (utility excluded: {sorted(utility)})")

    if missing_pages:
        failed = True
        print(f"FAIL: {len(missing_pages)} sitemap URL(s) with NO built page (soft-404 risk):")
        for p in missing_pages:
            print(f"  SITEMAP-ONLY  {p}")
    if missing_sitemap:
        failed = True
        print(f"FAIL: {len(missing_sitemap)} built page(s) MISSING from sitemap (hidden from crawlers):")
        for p in missing_sitemap:
            print(f"  ROUTE-ONLY    {p}")
    if not failed:
        print("PASS: sitemap == built routes (set equality).")

    # ---- llms.txt third pillar ----
    llms_file = args.llms or next(
        (c for c in (os.path.join(out_dir, "llms.txt"),
                     os.path.join(os.path.dirname(out_dir), "public", "llms.txt"))
         if os.path.exists(c)), os.path.join(out_dir, "llms.txt"))
    site_hosts = {urlsplit(next(iter(sm))).netloc.lower()} if sm else set()
    # derive host set from sitemap
    site_hosts = set()
    for f in glob.glob(os.path.join(out_dir, "sitemap*.xml")):
        with open(f, encoding="utf-8") as fh:
            for m in LOC_RE.finditer(fh.read()):
                h = urlsplit(m.group(1)).netloc.lower()
                if h:
                    site_hosts.add(h)
                    if h.startswith("www."):
                        site_hosts.add(h[4:])
                    else:
                        site_hosts.add("www." + h)

    llms_all = llms_paths(llms_file)
    llms_site = {p for (h, p) in llms_all if h in site_hosts}
    if not os.path.exists(llms_file):
        print(f"llms.txt: not found at {llms_file} (skipping llms parity)")
    else:
        # Only compare page-style paths (ignore asset/file paths).
        llms_pages = {p for p in llms_site if not HAS_EXT_RE.search(p)}
        llms_not_in_sitemap = sorted(llms_pages - sm)
        sitemap_not_in_llms = sorted(sm_eff - llms_pages)
        print(f"llms.txt: {len(llms_pages)} same-site page URLs at {llms_file}")
        if llms_not_in_sitemap:
            print(f"  {'FAIL' if args.strict_llms else 'WARN'}: {len(llms_not_in_sitemap)} llms.txt URL(s) not in sitemap:")
            for p in llms_not_in_sitemap:
                print(f"    LLMS-ONLY     {p}")
            if args.strict_llms:
                failed = True
        if sitemap_not_in_llms:
            print(f"  WARN: {len(sitemap_not_in_llms)} sitemap URL(s) not listed in llms.txt (informational):")
            for p in sitemap_not_in_llms[:50]:
                print(f"    NOT-IN-LLMS   {p}")
        if not llms_not_in_sitemap and not sitemap_not_in_llms:
            print("  PASS: llms.txt page URLs are consistent with the sitemap.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
