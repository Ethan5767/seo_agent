#!/usr/bin/env python3
"""
noncommodity-check.py — non-commodity / proprietary-variable gate
(doctrine §21 / GN-§21-noncommodity, pairs with §16 scale-caution). Exit 7.

Every service + blog page must carry at least one PROPRIETARY VARIABLE — a fact
or entity unique to this client (real crew name, neighborhood/street/zip, project
figure, testimonial proper noun) — and must NOT be a near-duplicate of its
siblings. This is the survival moat against scaled-content penalties: a page that
is pure generic-trade boilerplate, or a template clone of another page, is a
liability, not an asset.

Per selected page (same service/blog selection as capsule-check §20):
  1. no_proprietary_token — assert >=1 allow-list token appears in the page text
     (case-insensitive, word-boundary for word tokens; literal substring for
     punctuated tokens like a phone number). Fail if the page contains ZERO
     client-unique tokens.
  2. duplicate_of_sibling — reuse audit-built.py's 5-gram overlap engine verbatim
     (L217-235): compute each page's 5-gram set and its MAX overlap vs every
     sibling. Threshold: 0.90 when `topology` contains 'hub-spoke' (programmatic
     templates legitimately share chrome), else 0.60 — identical to audit-built
     check 14b, so the two gates never disagree. Fail if overlap > threshold.

Allow-list = config `required_phrases` (repurposed as the §21 proprietary-variable
allow-list) UNION nap.city / nap.street / service_areas[] / service_area.cities[]
/ business.crew_names[] / owner_name / primary_metro. If the RESOLVED allow-list
is EMPTY the gate FAILS LOUD (exit 4) — an empty differentiation gate is a silent
pass exactly like an empty legal gate.

Exit codes:
    0  every page has >=1 proprietary token AND <= threshold sibling overlap
    4  allow-list empty (refuse to run an empty differentiation gate)
    7  one or more non-commodity failures (lists page + failing sub-checks)

Usage:
    noncommodity-check.py PROJECT_DIR [--out DIR] [--overlap-threshold auto|0.6]
                          [--include-glob '/services/*'] [--exclude-glob '/about/']
                          [--log-dir DIR]
    # --out defaults to PROJECT_DIR/<resolved build dir> (out for next, dist for vite)
    # --overlap-threshold auto -> 0.90 for hub-spoke topology, else 0.60
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import os
import re
import sys
from datetime import date
from pathlib import Path

from pipeline.lib import baseline as bl
from pipeline.lib.common import load_config, url_fits_topology, client_profile

GATE = "noncommodity_check"


# strip_to_text — verbatim copy of audit-built.py L24-28 so this gate and
# audit-built never disagree on what "body text" is.
def strip_to_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


DEFAULT_EXCLUDE = {
    "/", "/contact/", "/about/", "/privacy/", "/privacy-policy/",
    "/terms/", "/terms-of-service/", "/thank-you/", "/404/", "/500/",
    "/_not-found/", "/blog/",
}


def built_routes(out_dir: str) -> dict:
    routes: dict = {}
    for idx in glob.glob(os.path.join(out_dir, "**", "index.html"), recursive=True):
        rel = os.path.relpath(os.path.dirname(idx), out_dir)
        if rel == ".":
            routes["/"] = idx
            continue
        if rel.split(os.sep)[0].startswith("_next"):
            continue
        routes["/" + rel.replace(os.sep, "/") + "/"] = idx
    return routes


def select_pages(out_dir: str, topology: str, include_glob: str, exclude_glob: str) -> list:
    routes = built_routes(out_dir)
    selected = []
    for route, path in sorted(routes.items()):
        if include_glob:
            if not fnmatch.fnmatch(route, include_glob):
                continue
        else:
            fits, _ = url_fits_topology(route, topology)
            if not (fits or route.startswith("/blog/")):
                continue
        if route in DEFAULT_EXCLUDE:
            continue
        if exclude_glob and fnmatch.fnmatch(route, exclude_glob):
            continue
        selected.append((route, path))
    return selected


def _flatten_tokens(value) -> list:
    """Pull string tokens out of str / list / dict config values. For a comma
    string like 'Charlotte, NC' also yield the leading segment ('Charlotte')."""
    out = []
    if value is None:
        return out
    if isinstance(value, str):
        s = value.strip()
        if s:
            out.append(s)
            head = s.split(",")[0].strip()
            if head and head != s:
                out.append(head)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out.extend(_flatten_tokens(v))
    elif isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_tokens(v))
    return out


def build_allow_list(cfg: dict) -> list:
    """required_phrases UNION client-unique entity fields (§21 allow-list)."""
    tokens: list = []
    tokens += _flatten_tokens(cfg.get("required_phrases"))
    nap = cfg.get("nap") or {}
    tokens += _flatten_tokens(nap.get("city"))
    tokens += _flatten_tokens(nap.get("street"))
    tokens += _flatten_tokens(cfg.get("service_areas"))
    sa = cfg.get("service_area") or {}
    tokens += _flatten_tokens(sa.get("primary_city"))
    tokens += _flatten_tokens(sa.get("cities"))
    tokens += _flatten_tokens(cfg.get("primary_metro"))
    business = cfg.get("business") or {}
    tokens += _flatten_tokens(business.get("crew_names"))
    tokens += _flatten_tokens(cfg.get("owner_name"))
    # dedupe case-insensitively, drop empties and 1-char noise
    seen, ordered = set(), []
    for t in tokens:
        t = t.strip()
        if len(t) < 2:
            continue
        key = t.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(t)
    return ordered


def compile_token_matchers(tokens: list) -> list:
    """(token, compiled_regex). Word tokens get \\b anchors; punctuated tokens
    (phone numbers, '% off') match as an escaped literal substring."""
    matchers = []
    for t in tokens:
        esc = re.escape(t)
        if re.fullmatch(r"[\w ]+", t):
            rx = re.compile(r"\b" + re.escape(t).replace(r"\ ", r"\s+") + r"\b", re.IGNORECASE)
        else:
            rx = re.compile(esc, re.IGNORECASE)
        matchers.append((t, rx))
    return matchers


def five_grams(text_lower: str) -> set:
    """audit-built.py L222-223 verbatim: set of space-joined 5-word shingles."""
    w = text_lower.split()
    return set(' '.join(w[i:i + 5]) for i in range(len(w) - 4))


def main() -> int:
    ap = argparse.ArgumentParser(description="Non-commodity gate (§21): proprietary variable + cross-page uniqueness.")
    ap.add_argument("project", help="PROJECT_DIR (holds docs/client-config.yml)")
    ap.add_argument("--out", default=None, help="built dir (default: resolved build dir under PROJECT_DIR)")
    ap.add_argument("--min-tokens", type=int, default=1, help="min distinct proprietary tokens per page (default 1)")
    ap.add_argument("--overlap-threshold", default="auto",
                    help="'auto' (0.90 hub-spoke / 0.60 else) or an explicit float")
    ap.add_argument("--include-glob", default="", help="only pages whose route matches this fnmatch glob")
    ap.add_argument("--exclude-glob", default="", help="drop pages whose route matches this fnmatch glob")
    ap.add_argument("--log-dir", default=None, help="markdown report dir (default: PROJECT_DIR/docs/audit-logs/<date>)")
    bl.add_baseline_args(ap)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg = load_config(str(project))
    prof = client_profile(cfg, str(project))

    out_dir = args.out or os.path.join(str(project), prof.get("resolved_build_dir", "out").lstrip("./"))
    out_dir = os.path.abspath(out_dir)
    if not os.path.isdir(out_dir):
        print(f"[ERROR] build dir not found: {out_dir} (run the build first).", file=sys.stderr)
        return 7

    # ── allow-list: empty -> exit 4 (refuse a silent-pass differentiation gate) ──
    tokens = build_allow_list(cfg)
    if not tokens:
        print("[FAIL] proprietary allow-list empty (checked required_phrases + nap.city/street + "
              "service_areas + service_area.cities + crew_names + owner_name). "
              "Refusing to run an empty differentiation gate. Seed required_phrases at onboarding.",
              file=sys.stderr)
        return 4
    matchers = compile_token_matchers(tokens)

    topology = cfg.get("topology", "") or ""
    if str(args.overlap_threshold).lower() == "auto":
        threshold = 0.90 if "hub-spoke" in topology else 0.60
    else:
        try:
            threshold = float(args.overlap_threshold)
        except ValueError:
            print(f"[ERROR] --overlap-threshold must be 'auto' or a float, got {args.overlap_threshold!r}", file=sys.stderr)
            return 7

    pages = select_pages(out_dir, topology, args.include_glob, args.exclude_glob)
    print(f"noncommodity-check: topology={topology or '(none)'} allow-list={len(tokens)} tokens "
          f"overlap-threshold={threshold} selected {len(pages)} page(s) under {out_dir}")
    if not pages:
        print("noncommodity-check: no service/blog pages selected — nothing to check (PASS).")
        return 0

    # gather stripped, lowercased text + 5-gram sets (audit-built.py first pass)
    texts, grams = {}, {}
    for route, path in pages:
        try:
            html = Path(path).read_text(errors="replace")
        except Exception:
            texts[route] = ""
            grams[route] = set()
            continue
        low = strip_to_text(html).lower()
        texts[route] = low
        grams[route] = five_grams(low)

    lines = [f"# Non-commodity Check (§21) — {date.today().isoformat()}", "",
             f"Build dir: {out_dir}", f"Topology: {topology or '(none)'} | overlap threshold: {threshold}",
             f"Allow-list ({len(tokens)}): {', '.join(tokens[:40])}{' ...' if len(tokens) > 40 else ''}",
             f"Selected pages: {len(pages)}", ""]

    failures = []
    findings = []          # baseline-comparable view of `failures`
    for route, path in pages:
        low = texts[route]
        matched = [t for t, rx in matchers if rx.search(low)]
        checks = {}
        detail = {}
        checks["no_proprietary_token"] = len(matched) >= args.min_tokens
        detail["no_proprietary_token"] = (f"{len(matched)} token(s): {', '.join(matched[:6])}"
                                          if matched else "ZERO client-unique tokens (generic boilerplate)")

        page_g = grams[route]
        overlap_max, worst = 0.0, None
        if page_g:
            for other, og in grams.items():
                if other == route or not og:
                    continue
                ov = len(page_g & og) / len(page_g)
                if ov > overlap_max:
                    overlap_max, worst = ov, other
        checks["duplicate_of_sibling"] = overlap_max <= threshold
        detail["duplicate_of_sibling"] = f"max overlap={overlap_max:.3f} (<= {threshold}?) vs {worst or '(none)'}"

        fails = [k for k, v in checks.items() if not v]
        lines.append(f"## {route}  {'PASS' if not fails else 'FAIL'}")
        for k in ("no_proprietary_token", "duplicate_of_sibling"):
            lines.append(f"  {'PASS' if checks[k] else 'FAIL'}  noncommodity.{k}  — {detail[k]}")
        lines.append("")
        if fails:
            failures.append((route, [f"noncommodity.{k}" for k in fails]))
            # Fingerprint on (gate, sub-check, route). The detail strings carry the
            # matched-token list and the overlap RATIO — both churn as copy changes,
            # so they ride along as `detail` and are never fingerprinted.
            for k in fails:
                findings.append(bl.Finding(GATE, f"noncommodity.{k}", route, detail=detail[k]))

    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    log_dir = Path(args.log_dir) if args.log_dir else (project / "docs" / "audit-logs" / date.today().isoformat())
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "noncommodity-check.md").write_text("\n".join(lines))
        print(f"noncommodity-check: report -> {log_dir / 'noncommodity-check.md'}")
    except Exception as e:  # pragma: no cover
        print(f"[WARN] could not write report ({e}).", file=sys.stderr)

    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        print(f"[FAIL] {len(verdict.blocking)} {label}non-commodity finding(s) across {len(pages)} page(s) (§21):")
        for f in verdict.blocking:
            print(f"  {f.location}: {f.code}  — {f.detail}")
        return 7
    if args.baseline:
        print(f"[OK] no new non-commodity findings ({len(verdict.preexisting)} pre-existing accepted as legacy debt).")
        return 0
    print(f"[OK] all {len(pages)} selected page(s) carry a proprietary variable and are non-duplicate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
