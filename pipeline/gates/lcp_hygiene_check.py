#!/usr/bin/env python3
"""
lcp-hygiene-check.py — deterministic LCP / layout-shift pre-conditions (exit 1).

Core Web Vitals are 28-day CrUX FIELD data and cannot be blocked at merge (that
is T14 monitoring). But three static, deterministic pre-conditions predict a bad
LCP / CLS with certainty and CAN be blocked before deploy:

  BLOCK 1 — hero lazy-loaded.
      An image the page itself declares as the LCP candidate — via
      <link rel=preload as=image> OR <img fetchpriority=high> — that ALSO carries
      loading="lazy". Preloading (or high-priority) an image while lazy-loading
      its tag is self-contradictory: the browser defers the very element you told
      it was critical. This is the classic LCP-killer, and it is deterministic.
      (Filename-only "hero-*.webp" images are NOT blocked for lazy: on real sites
      those are frequently below-the-fold cards that are CORRECTLY lazy. Only the
      strong, page-declared LCP signals gate the lazy block, so this stays
      false-positive-free.)

  BLOCK 2 — dimensionless <img>.
      An <img> with no width/height (raster only) can't reserve layout box before
      it loads -> cumulative layout shift. SVGs are allow-listed (intrinsic ratio
      / CSS-sized, and inline/data SVGs commonly ship without pixel dims).

  WARN  — un-prioritized hero (warn, not block).
      A page that ships a large content image but declares NO LCP candidate at all
      (no preload-as-image, no fetchpriority=high) is probably leaving its LCP
      un-hinted. Surfaced as a WARN so it informs without red-gating; promote to a
      block per-client via performance.block_unprioritized_hero: true.

<script>/<style> are stripped line-preserving (same masking em-dash-check uses)
so RSC flight payloads and inline CSS never produce phantom <img>/<link> hits.

Config (docs/client-config.yml, all optional — absent -> defaults, never KeyError):
    performance:
      hero_patterns:  [hero, banner, masthead, jumbotron]   # (unused by blocks; reserved)
      hero_min_px:    600     # long-edge at/over this = "large" content image (warn heuristic)
      svg_dim_exempt: true    # allow <img> without width/height when src is .svg / data:svg
      block_unprioritized_hero: false   # promote the WARN to a hard block

Exit codes:
    0  every page clean (warns do not affect exit unless promoted)
    1  one or more blocking violations (lazy hero / dimensionless img), or dir missing

Usage:
    lcp-hygiene-check.py --out ./out
    lcp-hygiene-check.py --project . --config docs/client-config.yml
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

from pipeline.lib import baseline as bl
from pipeline.lib.common import load_config, client_profile, resolve_build_dir

GATE = "lcp_hygiene_check"

DEFAULT_HERO_MIN_PX = 600

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
LINK_TAG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)


def blank_keep_lines(m: "re.Match") -> str:
    return "\n" * m.group(0).count("\n")


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf'{name}\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
    return m.group(1) if m else None


def _num_attr(tag: str, name: str) -> int | None:
    m = re.search(rf'\b{name}\s*=\s*"?(\d+)', tag, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _norm(url: str | None) -> str | None:
    if not url:
        return None
    return url.strip().split("?", 1)[0].split("#", 1)[0]


def _is_svg(src: str | None) -> bool:
    if not src:
        return False
    low = src.strip().lower()
    return low.endswith(".svg") or low.startswith("data:image/svg")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_page(html: str, hero_min_px: int, svg_exempt: bool):
    """Return (block_findings, warn_findings) for one page.
    Each finding: (line, kind, detail, ref) — `ref` is the stable identity of the
    offending element (its src), carried alongside the volatile line number so the
    baseline can fingerprint on src and ignore line churn."""
    stripped = SCRIPT_STYLE_RE.sub(blank_keep_lines, html)

    # page-declared LCP candidates
    preload_img: set[str] = set()
    for link in LINK_TAG_RE.findall(stripped):
        low = link.lower()
        if 'rel="preload"' in low and 'as="image"' in low:
            h = _norm(_attr(link, "href"))
            if h:
                preload_img.add(h)

    block, warn = [], []
    has_priority_signal = bool(preload_img)
    has_large_content_img = False

    for m in IMG_TAG_RE.finditer(stripped):
        tag = m.group(0)
        line = _line_of(stripped, m.start())
        src = _norm(_attr(tag, "src"))
        loading = (_attr(tag, "loading") or "").lower()
        fp = (_attr(tag, "fetchpriority") or "").lower()
        w, h = _num_attr(tag, "width"), _num_attr(tag, "height")
        is_svg = _is_svg(src)

        if fp == "high":
            has_priority_signal = True

        strong_hero = (src in preload_img) or (fp == "high")

        # BLOCK 1 — declared LCP candidate that is lazy-loaded
        if strong_hero and loading == "lazy":
            why = "preload=image" if src in preload_img else "fetchpriority=high"
            block.append((line, "lazy-hero",
                          f'{src or "<no src>"} is declared LCP ({why}) but loading="lazy"',
                          src or "<no src>"))

        # BLOCK 2 — dimensionless raster <img>
        if not (w and h):
            if is_svg and svg_exempt:
                pass
            else:
                block.append((line, "no-dimensions",
                              f'{src or "<no src>"} missing width/height',
                              src or "<no src>"))

        # large content image bookkeeping for the un-prioritized-hero warn
        if not is_svg and ((w or 0) >= hero_min_px or (h or 0) >= hero_min_px):
            has_large_content_img = True

    if has_large_content_img and not has_priority_signal:
        warn.append((0, "unprioritized-hero",
                     "page ships a large image but declares no LCP candidate "
                     "(no preload=image, no fetchpriority=high)",
                     "(page)"))
    return block, warn


def resolve_dirs(args) -> tuple[Path, dict]:
    cfg: dict = {}
    cfg_path: Path | None = None
    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.is_absolute() and args.project:
            alt = Path(args.project) / args.config
            cfg_path = cfg_path if cfg_path.exists() else alt
    elif args.project:
        cand = Path(args.project) / "docs" / "client-config.yml"
        cfg_path = cand if cand.exists() else None
    if cfg_path and cfg_path.exists():
        if args.project:
            cfg = load_config(args.project)
        else:
            import yaml
            cfg = yaml.safe_load(cfg_path.read_text()) or {}

    if args.out:
        build_dir = Path(args.out)
    elif args.project:
        profile = client_profile(cfg, args.project)
        build_dir = Path(args.project) / resolve_build_dir(profile, args.project).lstrip("./")
    else:
        build_dir = Path("./out")
    return build_dir, cfg


def main() -> int:
    ap = argparse.ArgumentParser(description="Block deterministic LCP/CLS anti-patterns in built HTML.")
    ap.add_argument("--out", default=None, help="built output dir (default ./out)")
    ap.add_argument("--project", default=None, help="project dir (config + build-dir resolution)")
    ap.add_argument("--config", default=None, help="path to client-config.yml")
    bl.add_baseline_args(ap)
    args = ap.parse_args()
    if not args.out and not args.project:
        args.out = "./out"

    build_dir, cfg = resolve_dirs(args)
    build_dir = build_dir.resolve()
    if not build_dir.is_dir():
        print(f"[FAIL] build dir not found: {build_dir} — run the build first.", file=sys.stderr)
        return 1

    perf = (cfg.get("performance") or {}) if isinstance(cfg, dict) else {}
    hero_min_px = int(perf.get("hero_min_px") or DEFAULT_HERO_MIN_PX)
    svg_exempt = perf.get("svg_dim_exempt", True)
    promote_warn = bool(perf.get("block_unprioritized_hero", False))

    files = sorted(glob.glob(str(build_dir / "**" / "*.html"), recursive=True))
    findings = []
    warnings = []
    for f in files:
        try:
            html = Path(f).read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        block, warn = scan_page(html, hero_min_px, svg_exempt)
        if promote_warn:
            block = block + warn
            warn = []
        rel = Path(os.path.relpath(f, build_dir)).as_posix()
        # Fingerprint on (gate, kind, build-relative file, src). The LINE NUMBER is
        # deliberately excluded: every content edit reflows the HTML and moves every
        # line, which would make the whole baseline go "new" on the next build.
        # Repeated identical (file, kind, src) findings are disambiguated by the
        # document-order ordinal that bl.assign_ordinals() applies.
        for line, kind, detail, ref in block:
            findings.append(bl.Finding(GATE, kind, rel, context=ref,
                                       detail=f"line {line}: {detail}"))
        for line, kind, detail, ref in warn:
            warnings.append((rel, kind, detail))

    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    for f in (verdict.blocking if args.baseline else findings):
        print(f"  [BLOCK] {f.location}: {f.code}: {f.detail}")
    for rel, kind, detail in warnings:
        print(f"  [warn]  {rel}: {kind}: {detail}")

    print(f"lcp-hygiene-check: scanned {len(files)} HTML file(s) under {build_dir}")
    if warnings:
        print(f"  {len(warnings)} warning(s) (non-blocking).")
    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        print(f"FAIL: {len(verdict.blocking)} {label}blocking LCP/CLS violation(s).")
        return 1
    if args.baseline:
        print(f"PASS: no new LCP/CLS violations ({len(verdict.preexisting)} pre-existing accepted as legacy debt).")
        return 0
    print("PASS: no blocking LCP/CLS violations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
