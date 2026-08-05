#!/usr/bin/env python3
"""
pages-are-data-check.py — enforce the "pages are DATA, not bespoke code" rule
(Lesson-1), pre-BUILD, on `src/app`.

Lesson-1 / the architecture doctrine: SEO pages are produced by a SMALL fixed set
of route templates (`[slug]`, `[slug]/[city]`, `[slug]/[city]/[subservice]`, a blog
`[slug]`) fed from `src/data/*`. Content lives in DATA; the `page.tsx` is a thin
template. The failure mode this gate makes impossible is *bespoke-per-route drift*:
someone hand-authors `roofing-in-charlotte/page.tsx` as a 400-line literal instead
of adding a row to the data + letting the template render it. Every other content
gate (capsule, non-commodity, forbidden-sweep) silently assumes that drift away;
this gate catches it at the source, before build.

Model:
  - A route is DYNAMIC if any path segment is a Next dynamic segment (`[x]`,
    `[...x]`, `[[...x]]`) or a route group `(group)`. Dynamic routes ARE the
    templated/data-driven architecture → they always PASS (never line-checked).
  - A route is STATIC otherwise. A static route's `page.tsx` over
    `--max-static-lines` (default 120) is a bespoke-heavy literal → FAIL, UNLESS
    the route is whitelisted. Thin static stubs (a 15-line `/careers`) pass.
  - Whitelist = the union of `static_route_whitelist[]` and `templated_routes[]`
    from docs/client-config.yml (both optional), plus any `--whitelist` CLI
    entries. This is where legitimately hand-authored long static pages live
    (home, /our-process, legal pages).

Only `page.*` route files are scanned (page.tsx/jsx/ts/js). Framework specials
(`layout`, `not-found`, `template`, `error`, `loading`) and colocated components
(e.g. a `PageClient.tsx`) are not route entry points and are not line-checked.

Config (read GRACEFULLY; absent keys default to empty so no KeyError on an
un-provisioned repo):
  static_route_whitelist: ["/", "/our-process", "/privacy-policy", ...]
  templated_routes: ["/[slug]", "/[slug]/[city]", ...]

Exit codes:
    0  every static route is a thin stub or whitelisted; dynamic routes pass
    1  one or more over-threshold non-whitelisted static routes (bespoke drift)
    2  usage error (no src/app found)

Usage:
    pages-are-data-check.py PROJECT_DIR
    pages-are-data-check.py --app-dir src/app --max-static-lines 120 --whitelist /our-process
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

from pipeline.lib import baseline as bl

GATE = "pages_are_data_check"


def _load_common():
    """Return the shared pipeline lib module, or None if it cannot be imported."""
    try:
        from pipeline.lib import common  # type: ignore
        return common
    except Exception:
        return None


PAGE_FILE_RE = re.compile(r"^page\.(tsx|jsx|ts|js)$")
DYNAMIC_SEG_RE = re.compile(r"^\[.*\]$")          # [x] [...x] [[...x]]
ROUTE_GROUP_RE = re.compile(r"^\(.*\)$")           # (marketing) — grouping, no URL segment
PRIVATE_SEG_RE = re.compile(r"^_")                 # _components etc. (not routable)


def load_cfg(project_dir: str | None, config_path: str | None) -> dict:
    if config_path:
        p = Path(config_path)
        if p.is_file():
            try:
                import yaml
                return yaml.safe_load(p.read_text()) or {}
            except Exception:
                return {}
        return {}
    if not project_dir:
        return {}
    cfg_path = Path(project_dir) / "docs" / "client-config.yml"
    if not cfg_path.is_file():
        return {}
    common = _load_common()
    if common is not None:
        try:
            return common.load_config(project_dir) or {}
        except SystemExit:
            return {}
        except Exception:
            return {}
    try:
        import yaml
        return yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:
        return {}


def route_from_page(page_path: str, app_dir: str) -> tuple[str, bool]:
    """Map an app-dir-relative page file to (route, is_dynamic).

    Route groups `(group)` contribute no URL segment. A route is dynamic if ANY
    remaining segment is a Next dynamic segment."""
    rel_dir = os.path.relpath(os.path.dirname(page_path), app_dir)
    segs = [] if rel_dir in (".", "") else rel_dir.split(os.sep)
    url_segs = []
    is_dynamic = False
    for s in segs:
        if ROUTE_GROUP_RE.match(s) or PRIVATE_SEG_RE.match(s):
            continue  # non-routable / grouping segment
        if DYNAMIC_SEG_RE.match(s):
            is_dynamic = True
        url_segs.append(s)
    route = "/" + "/".join(url_segs) if url_segs else "/"
    return route, is_dynamic


def norm_route(r: str) -> str:
    """Normalize for whitelist comparison: leading slash, no trailing slash
    (except root)."""
    r = (r or "").strip()
    if not r.startswith("/"):
        r = "/" + r
    if len(r) > 1 and r.endswith("/"):
        r = r.rstrip("/")
    return r or "/"


def count_lines(path: str) -> int:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Enforce data-driven route templates (Lesson-1).")
    ap.add_argument("project", nargs="?", default=".", help="Project dir (app at PROJECT/src/app)")
    ap.add_argument("--app-dir", default=None, help="Explicit app dir (default PROJECT/src/app)")
    ap.add_argument("--config", default=None, help="Explicit client-config.yml path")
    ap.add_argument("--max-static-lines", type=int, default=120,
                    help="Max lines a NON-whitelisted static route page.tsx may have (default 120)")
    ap.add_argument("--whitelist", action="append", default=[],
                    help="Route to whitelist (repeatable), e.g. --whitelist /our-process")
    bl.add_baseline_args(ap)
    args = ap.parse_args()

    project = os.path.abspath(args.project)
    app_dir = os.path.abspath(args.app_dir) if args.app_dir else os.path.join(project, "src", "app")
    if not os.path.isdir(app_dir):
        print(f"ERROR: app dir not found: {app_dir}", file=sys.stderr)
        return 2

    cfg = load_cfg(project, args.config)
    whitelist = set()
    for key in ("static_route_whitelist", "templated_routes"):
        for r in (cfg.get(key) or []):
            whitelist.add(norm_route(str(r)))
    for r in args.whitelist:
        whitelist.add(norm_route(str(r)))

    # collect page.* route files
    page_files = []
    for path in glob.glob(os.path.join(app_dir, "**", "*"), recursive=True):
        if os.path.isfile(path) and PAGE_FILE_RE.match(os.path.basename(path)):
            page_files.append(path)
    page_files.sort()

    n_dynamic = 0
    n_static_ok = 0
    n_whitelisted = 0
    violations = []  # (route, lines, file)
    for pf in page_files:
        route, is_dynamic = route_from_page(pf, app_dir)
        nroute = norm_route(route)
        if is_dynamic:
            n_dynamic += 1
            continue
        if nroute in whitelist:
            n_whitelisted += 1
            continue
        lines = count_lines(pf)
        if lines > args.max_static_lines:
            violations.append((nroute, lines, os.path.relpath(pf, app_dir)))
        else:
            n_static_ok += 1

    # Fingerprint on (gate, rule, ROUTE, app-relative page file). The LINE COUNT is
    # excluded on purpose: a known-bespoke 175-line page edited to 190 lines is the
    # same outstanding piece of architecture debt, not a new violation. Only the route
    # dropping back under the threshold (or being whitelisted) clears the entry.
    findings = [
        bl.Finding(GATE, "pages_are_data.bespoke_static_route", route,
                   context=Path(rel).as_posix(),
                   detail=f"{lines} lines > {args.max_static_lines}")
        for route, lines, rel in violations
    ]
    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    print(f"pages-are-data-check: {len(page_files)} route file(s) — "
          f"{n_dynamic} dynamic (template), {n_static_ok} thin static, "
          f"{n_whitelisted} whitelisted, threshold {args.max_static_lines} lines")
    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        print(f"FAIL: {len(verdict.blocking)} {label}bespoke-heavy static route(s) — "
              f"move content to DATA + a route template, or whitelist if genuinely hand-authored:")
        for f in verdict.blocking:
            print(f"  BESPOKE  {f.location}  ({f.detail})  [{f.context}]")
        return 1
    if args.baseline:
        print(f"PASS: no new bespoke static routes ({len(verdict.preexisting)} pre-existing accepted as legacy debt).")
        return 0
    print("PASS: every static route is a thin stub or whitelisted; dynamic routes are data-driven.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
