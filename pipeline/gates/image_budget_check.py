#!/usr/bin/env python3
"""
image-budget-check.py — per-image weight ceiling on the BUILT output (exit 1).

Why this gate exists:
    next.config.mjs sets `images.unoptimized: true` (forced by CF Pages static
    export), so Next does ZERO resize / format conversion / srcset. A 3 MB hero
    PNG ships to every visitor unblocked. Images are ~48% of page weight and the
    LCP element on ~85% of pages, so an unbounded image is the single biggest
    silent CWV regression an emitter can introduce. This turns "someone dropped a
    full-res photo in public/images/" into a hard, deterministic build-time fail.

    Core Web Vitals themselves are 28-day CrUX FIELD data — non-blockable at
    merge. This gate blocks only the deterministic STATIC pre-condition (file
    bytes on disk), never a lab/field number. CWV monitoring is T14.

What it does:
    1. Walk BUILD_DIR/**/*.{jpg,jpeg,png,webp,avif,gif}.
    2. Classify each file hero / content / thumb by its REFERENCE CONTEXT across
       every built HTML page (not filename alone):
         hero    — declared LCP candidate: <link rel=preload as=image>, an
                   <img fetchpriority=high>, or a hero/banner/masthead filename.
         thumb   — logo/icon/thumb/avatar/favicon/sprite filename, OR every <img>
                   that references it renders at <= thumb_max_px on its long edge.
         content — everything else (the default).
       thumb-by-filename wins over a hero signal (a preloaded logo is still a
       thumb), so a small preloaded icon is never held to the hero ceiling.
    3. Fail any file whose size exceeds its tier ceiling. Report `path:SIZE:tier`.

Config (docs/client-config.yml, all optional — absent -> defaults, never KeyError):
    performance:
      image_budget:            # KB ceilings
        hero:    200
        content: 100
        thumb:   30
      hero_patterns:  [hero, banner, masthead, jumbotron, hero-]   # filename substrings
      thumb_patterns: [logo, icon, thumb, avatar, favicon, sprite, badge]
      thumb_max_px:   128      # <img> long-edge at/under this -> thumb tier

Exit codes:
    0  every image within its tier ceiling
    1  one or more over-budget images (lists path:size:tier), or build dir missing

Usage:
    image-budget-check.py --out ./out
    image-budget-check.py --project . --config docs/client-config.yml
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

GATE = "image_budget_check"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")

DEFAULT_BUDGET_KB = {"hero": 200, "content": 100, "thumb": 30}
DEFAULT_HERO_PATTERNS = ["hero", "banner", "masthead", "jumbotron"]
DEFAULT_THUMB_PATTERNS = ["logo", "icon", "thumb", "avatar", "favicon", "sprite", "badge"]
DEFAULT_THUMB_MAX_PX = 128

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
PRELOAD_IMG_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
BG_URL_RE = re.compile(r"background-image\s*:\s*url\(\s*['\"]?([^)'\"]+)['\"]?\s*\)", re.IGNORECASE)


def _attr(tag: str, name: str) -> str | None:
    m = re.search(rf'{name}\s*=\s*"([^"]*)"', tag, re.IGNORECASE)
    return m.group(1) if m else None


def _num_attr(tag: str, name: str) -> int | None:
    m = re.search(rf'\b{name}\s*=\s*"?(\d+)', tag, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _norm_ref(url: str) -> str | None:
    """Reduce a referenced image URL to a site-absolute path (leading /), or None
    for externals / data URIs / non-image refs."""
    if not url:
        return None
    u = url.strip().split("?", 1)[0].split("#", 1)[0]
    low = u.lower()
    if low.startswith(("data:", "http://", "https://", "//", "mailto:", "tel:")):
        return None
    if not low.endswith(IMAGE_EXTS):
        return None
    if not u.startswith("/"):
        u = "/" + u.lstrip("./")
    return u


class RefIndex:
    """Site-wide image reference context, built in one pass over the HTML."""

    def __init__(self) -> None:
        self.preload: set[str] = set()          # <link rel=preload as=image href=...>
        self.fp_high: set[str] = set()          # <img fetchpriority=high src=...>
        self.dims: dict[str, list[int]] = {}    # path -> [long-edge px per <img>]
        self.referenced: set[str] = set()

    def add_dim(self, path: str, long_edge: int | None) -> None:
        self.dims.setdefault(path, [])
        if long_edge is not None:
            self.dims[path].append(long_edge)

    def scan_html(self, html: str) -> None:
        stripped = SCRIPT_STYLE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), html)
        for link in PRELOAD_IMG_RE.findall(stripped):
            low = link.lower()
            if 'rel="preload"' in low and 'as="image"' in low:
                p = _norm_ref(_attr(link, "href") or "")
                if p:
                    self.preload.add(p)
                    self.referenced.add(p)
        for tag in IMG_TAG_RE.findall(stripped):
            p = _norm_ref(_attr(tag, "src") or "")
            if not p:
                continue
            self.referenced.add(p)
            w, h = _num_attr(tag, "width"), _num_attr(tag, "height")
            long_edge = max(w or 0, h or 0) or None
            self.add_dim(p, long_edge)
            if (_attr(tag, "fetchpriority") or "").lower() == "high":
                self.fp_high.add(p)
        for bg in BG_URL_RE.findall(stripped):
            p = _norm_ref(bg)
            if p:
                self.referenced.add(p)


def build_index(build_dir: Path) -> RefIndex:
    idx = RefIndex()
    for f in glob.glob(str(build_dir / "**" / "*.html"), recursive=True):
        try:
            idx.scan_html(Path(f).read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
    return idx


def classify(url: str, idx: RefIndex, hero_pat: list[str], thumb_pat: list[str],
             thumb_max_px: int) -> str:
    low = url.lower()
    base = os.path.basename(low)
    if any(p in base for p in thumb_pat):
        return "thumb"
    hero_signal = (
        url in idx.preload
        or url in idx.fp_high
        or any(p in low for p in hero_pat)
    )
    dims = idx.dims.get(url, [])
    thumb_by_dims = bool(dims) and max(dims) <= thumb_max_px
    if hero_signal and not thumb_by_dims:
        return "hero"
    if thumb_by_dims:
        return "thumb"
    return "content"


def resolve_dirs(args) -> tuple[Path, dict]:
    """Return (build_dir, cfg). cfg is {} when no config file is found (defaults)."""
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
            cfg = load_config(args.project)          # reuse common helper
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
    ap = argparse.ArgumentParser(description="Fail if any built image exceeds its tier byte budget.")
    ap.add_argument("--out", default=None, help="built output dir to scan (default ./out)")
    ap.add_argument("--project", default=None, help="project dir (to load config + resolve build dir)")
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
    budget = dict(DEFAULT_BUDGET_KB)
    for k, v in (perf.get("image_budget") or {}).items():
        if k in budget and isinstance(v, (int, float)):
            budget[k] = float(v)
    hero_pat = [p.lower() for p in (perf.get("hero_patterns") or DEFAULT_HERO_PATTERNS)]
    thumb_pat = [p.lower() for p in (perf.get("thumb_patterns") or DEFAULT_THUMB_PATTERNS)]
    thumb_max_px = int(perf.get("thumb_max_px") or DEFAULT_THUMB_MAX_PX)

    idx = build_index(build_dir)

    files = []
    for ext in IMAGE_EXTS:
        files += glob.glob(str(build_dir / "**" / f"*{ext}"), recursive=True)
        files += glob.glob(str(build_dir / "**" / f"*{ext.upper()}"), recursive=True)
    files = sorted(set(files))

    tier_counts = {"hero": 0, "content": 0, "thumb": 0}
    over = []
    for f in files:
        rel = os.path.relpath(f, build_dir)
        url = "/" + Path(rel).as_posix()
        tier = classify(url, idx, hero_pat, thumb_pat, thumb_max_px)
        tier_counts[tier] += 1
        size_kb = os.path.getsize(f) / 1024.0
        ceiling = budget[tier]
        if size_kb > ceiling:
            over.append((rel, size_kb, tier, ceiling))

    # Fingerprint on (gate, rule, build-relative image path, tier). The measured
    # SIZE is deliberately excluded — an image that grows from 300KB to 400KB is
    # the same known-oversized asset, not a new finding. Replacing it with a
    # DIFFERENT oversized file at the same path is likewise the same debt entry;
    # what the baseline records is "this path is over budget", and the ratchet
    # clears it when the path comes back under its ceiling.
    findings = [
        bl.Finding(GATE, "image_budget.over_budget", Path(rel).as_posix(), context=tier,
                   detail=f"{size_kb:.0f}KB > {ceiling:.0f}KB ceiling ({tier})")
        for rel, size_kb, tier, ceiling in over
    ]
    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    print(f"image-budget-check: scanned {len(files)} image(s) under {build_dir}")
    print(f"  tiers: hero={tier_counts['hero']} content={tier_counts['content']} thumb={tier_counts['thumb']}")
    print(f"  ceilings (KB): hero={budget['hero']:.0f} content={budget['content']:.0f} thumb={budget['thumb']:.0f}")
    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        for f in verdict.blocking:
            print(f"  [OVER] {f.location}: {f.detail}")
        print(f"FAIL: {len(verdict.blocking)} {label}image(s) over budget.")
        return 1
    if args.baseline:
        print(f"PASS: no new over-budget images ({len(verdict.preexisting)} pre-existing accepted as legacy debt).")
        return 0
    print("PASS: all images within tier budgets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
