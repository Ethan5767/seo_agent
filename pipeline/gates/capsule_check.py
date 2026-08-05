#!/usr/bin/env python3
"""
capsule-check.py — content-capsule gate (doctrine §20 / GN-§20-capsule). Exit 6.

The content capsule is the literal unit AI engines lift into an answer: an
INTERROGATIVE H2 ("How much does a roof replacement cost in Charlotte?"), a
DIRECT ANSWER-FIRST block immediately under it (2-3 sentences, 40-80 words), and
a TL;DR / Key-Takeaways node on long pages. Every service + blog page must carry
one. This gate parses the BUILT HTML and asserts all three on each selected page.

Per selected page:
  1. interrogative_h2 — >=1 <h2> text ends with '?' OR starts with an
     interrogative lead (how|what|why|when|where|which|who|do|does|is|are|can|
     should|will). Fail `capsule.interrogative_h2` otherwise.
  2. answer_first — the first block-level run after that H2 is prose of 2-3
     sentences AND 40-80 words. Fail `capsule.answer_first` on empty / <40w
     fragment / >80w or >3-sentence wall.
  3. tldr_on_long — if the stripped body word count > long_page_threshold
     (config content.long_page_threshold, default 1500 per the Content Team
     Operating Standard §01 Gate 1), a TL;DR node must exist
     (tl;dr | key takeaways | in short | the short answer | bottom line). Short
     pages skip this sub-check.

Page selection mirrors parity-check.built_routes(): a route is selected when it
fits the config `topology` hub/spoke shape (common.url_fits_topology) OR starts
with /blog/. Utility pages (/, /contact/, /about/, /privacy*, /terms*,
/thank-you/, 404/500, /blog/ index) are never selected. --include-glob /
--exclude-glob tune the set. Utility pages that legitimately carry no capsule
therefore never fail.

Exit codes:
    0  every selected page has an interrogative H2 + answer-first block (+ TL;DR if long)
    6  one or more capsule failures (lists file + failing sub-checks)

Usage:
    capsule-check.py PROJECT_DIR [--out DIR] [--long-threshold 1200]
                     [--include-glob '/services/*'] [--exclude-glob '/about/']
                     [--log-dir DIR]
    # --out defaults to PROJECT_DIR/<resolved build dir> (out for next, dist for vite)
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import html as _html
import os
import re
import sys
from datetime import date
from pathlib import Path

from pipeline.lib import baseline as bl
from pipeline.lib.common import load_config, url_fits_topology, client_profile

GATE = "capsule_check"


# strip_to_text — verbatim copy of audit-built.py L24-28 so this gate and
# audit-built never disagree on what "body text" is.
def strip_to_text(html: str) -> str:
    text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
H2_RE = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
NEXT_HEADING_RE = re.compile(r"<h[1-6]\b", re.IGNORECASE)
FIRST_BLOCK_RE = re.compile(r"<(p|li)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
INTERROGATIVE_LEAD = re.compile(
    r"^(how|what|why|when|where|which|who|do|does|is|are|can|should|will)\b", re.IGNORECASE)
TLDR_RE = re.compile(r"tl;?dr|key takeaways|in short|the short answer|bottom line", re.IGNORECASE)

# Utility/listing routes that legitimately carry no capsule.
DEFAULT_EXCLUDE = {
    "/", "/contact/", "/about/", "/privacy/", "/privacy-policy/",
    "/terms/", "/terms-of-service/", "/thank-you/", "/404/", "/500/",
    "/_not-found/", "/blog/",
}


def heading_text(inner: str) -> str:
    """Strip nested tags + collapse whitespace + unescape entities (mirrors the
    audit-built H1 extraction at L38-39)."""
    t = re.sub(r"<[^>]+>", "", inner)
    t = re.sub(r"\s+", " ", t).strip()
    return _html.unescape(t)


def built_routes(out_dir: str) -> dict:
    """route -> absolute index.html path (parity-check.built_routes shape)."""
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


def find_interrogative_h2(stripped_html: str):
    """Return (match, text) of the first interrogative <h2>, or (None, None)."""
    for m in H2_RE.finditer(stripped_html):
        t = heading_text(m.group(1))
        if t.rstrip().endswith("?") or INTERROGATIVE_LEAD.match(t):
            return m, t
    return None, None


def answer_block_after(stripped_html: str, h2_match) -> str:
    """Text of the first block-level run (<p>/<li>, else the raw region) that
    follows the interrogative H2, up to the next heading."""
    start = h2_match.end()
    nxt = NEXT_HEADING_RE.search(stripped_html, start)
    region = stripped_html[start: nxt.start() if nxt else len(stripped_html)]
    fb = FIRST_BLOCK_RE.search(region)
    block_html = fb.group(2) if fb else region
    text = strip_to_text(block_html).strip()
    return text or strip_to_text(region).strip()


def audit_capsule(html: str, long_threshold: int) -> dict:
    stripped = SCRIPT_STYLE_RE.sub(lambda mm: "\n" * mm.group(0).count("\n"), html)
    checks: dict = {}
    detail: dict = {}

    h2_match, h2_text = find_interrogative_h2(stripped)
    checks["interrogative_h2"] = h2_match is not None
    detail["interrogative_h2"] = h2_text or "(no interrogative H2 found)"

    if h2_match is None:
        # answer_first cannot be evaluated without an interrogative H2; not a
        # separate failure (the interrogative_h2 failure already blocks the page).
        checks["answer_first"] = True
        detail["answer_first"] = "(skipped — no interrogative H2)"
    else:
        ans = answer_block_after(stripped, h2_match)
        words = len(ans.split())
        sentences = len(re.findall(r"[.!?]+", ans))
        ok = bool(ans) and 40 <= words <= 80 and sentences <= 3
        checks["answer_first"] = ok
        detail["answer_first"] = f"words={words} sentences={sentences}"

    body_words = len(strip_to_text(html).split())
    if body_words > long_threshold:
        has_tldr = bool(TLDR_RE.search(strip_to_text(html)))
        checks["tldr_on_long"] = has_tldr
        detail["tldr_on_long"] = f"body_words={body_words} (>{long_threshold}) tldr={'yes' if has_tldr else 'MISSING'}"
    else:
        checks["tldr_on_long"] = True
        detail["tldr_on_long"] = f"body_words={body_words} (<= {long_threshold}, skipped)"

    return {"checks": checks, "detail": detail, "body_words": body_words}


def main() -> int:
    ap = argparse.ArgumentParser(description="Content-capsule gate (§20): interrogative H2 + answer-first + TL;DR.")
    ap.add_argument("project", help="PROJECT_DIR (holds docs/client-config.yml)")
    ap.add_argument("--out", default=None, help="built dir (default: resolved build dir under PROJECT_DIR)")
    ap.add_argument("--long-threshold", type=int, default=None,
                    help="TL;DR word trigger (default: config content.long_page_threshold or 1500)")
    ap.add_argument("--include-glob", default="", help="only pages whose route matches this fnmatch glob")
    ap.add_argument("--exclude-glob", default="", help="drop pages whose route matches this fnmatch glob")
    ap.add_argument("--log-dir", default=None, help="where to write the markdown report (default: PROJECT_DIR/docs/audit-logs/<date>)")
    bl.add_baseline_args(ap)
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cfg = load_config(str(project))
    prof = client_profile(cfg, str(project))

    out_dir = args.out or os.path.join(str(project), prof.get("resolved_build_dir", "out").lstrip("./"))
    out_dir = os.path.abspath(out_dir)
    if not os.path.isdir(out_dir):
        print(f"[ERROR] build dir not found: {out_dir} (run the build first).", file=sys.stderr)
        return 6

    topology = cfg.get("topology", "") or ""
    if args.long_threshold is not None:
        long_threshold = args.long_threshold
    else:
        # Default is the Content Team Operating Standard (2026-07-29) §01 Gate 1:
        # "On pages over 1,500 words, add a TL;DR". Was 1200, which demanded a
        # TL;DR on pages the published standard says do not need one.
        long_threshold = (cfg.get("content") or {}).get("long_page_threshold", 1500)

    pages = select_pages(out_dir, topology, args.include_glob, args.exclude_glob)
    print(f"capsule-check: topology={topology or '(none)'} selected {len(pages)} page(s) under {out_dir}")
    if not pages:
        print("capsule-check: no service/blog pages selected — nothing to check (PASS).")
        return 0

    lines = [f"# Capsule Check (§20) — {date.today().isoformat()}", "",
             f"Build dir: {out_dir}", f"Topology: {topology or '(none)'} | long_threshold: {long_threshold}",
             f"Selected pages: {len(pages)}", ""]
    failures = []
    findings = []          # baseline-comparable view of `failures`
    for route, path in pages:
        try:
            html = Path(path).read_text(errors="replace")
        except Exception as e:
            failures.append((route, [f"read_error:{e}"]))
            findings.append(bl.Finding(GATE, "capsule.read_error", route, detail=str(e)))
            continue
        r = audit_capsule(html, long_threshold)
        fails = [k for k, v in r["checks"].items() if not v]
        status = "PASS" if not fails else "FAIL"
        lines.append(f"## {route}  {status}  words={r['body_words']}")
        for k in ("interrogative_h2", "answer_first", "tldr_on_long"):
            lines.append(f"  {'PASS' if r['checks'][k] else 'FAIL'}  capsule.{k}  — {r['detail'][k]}")
        lines.append("")
        if fails:
            failures.append((route, [f"capsule.{k}" for k in fails]))
            # Fingerprint on (gate, sub-check, route) only. r['detail'] carries word
            # and sentence counts, which churn on every copy edit — they ride along
            # as `detail` (never fingerprinted) so a page getting slightly worse does
            # not silently turn a pre-existing finding into a "new" one.
            for k in fails:
                findings.append(bl.Finding(GATE, f"capsule.{k}", route, detail=r["detail"][k]))

    verdict, early = bl.resolve(GATE, findings, args)
    if early is not None:
        return early

    # Write the markdown report (best-effort; never blocks on a read-only tree).
    log_dir = Path(args.log_dir) if args.log_dir else (project / "docs" / "audit-logs" / date.today().isoformat())
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "capsule-check.md").write_text("\n".join(lines))
        print(f"capsule-check: report -> {log_dir / 'capsule-check.md'}")
    except Exception as e:  # pragma: no cover
        print(f"[WARN] could not write report ({e}).", file=sys.stderr)

    if args.baseline:
        verdict.report()
    if verdict.blocking:
        label = "NEW " if args.baseline else ""
        print(f"[FAIL] {len(verdict.blocking)} {label}capsule finding(s) across {len(pages)} page(s) (§20):")
        for f in verdict.blocking:
            print(f"  {f.location}: {f.code}  — {f.detail}")
        return 6
    if args.baseline:
        print(f"[OK] no new capsule findings ({len(verdict.preexisting)} pre-existing accepted as legacy debt).")
        return 0
    print(f"[OK] all {len(pages)} selected page(s) carry a valid content capsule.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
