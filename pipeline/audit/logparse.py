#!/usr/bin/env python3
"""logparse.py — a server access log becomes crawl-budget findings.

The SOP's "Log File & Indexability Analysis": the one data source that shows how
crawlers ACTUALLY treat the site, not how it renders. A live crawl or a CrUX
pull cannot tell you Googlebot spent its budget on 404s, or that every bot visit
ships a megabyte of un-minified HTML. The access log can.

Input is a log FILE the client exports (no live tail, no server access from the
engine). Two formats are understood:

  * Apache / Nginx "combined"  — the default access log, the one that carries the
    User-Agent so a request can be attributed to a crawler.
  * Cloudflare Logpush JSON    — one JSON object per line.

Everything crawler-attributed is aggregated per path; findings are emitted as
lib.baseline.Finding objects using the SAME gate as measure.py, so they ride the
cycle's findings.json and the ratchet partitions them like any other finding.

Honest degradation (CLAUDE.md sharp-edge #4/#6): a missing file, or a file with
no recognizable lines, returns a NAMED SKIP and zero findings — never a silent
green. The "common" log format carries no User-Agent, so it cannot support
crawler attribution; such lines count as unrecognized and are reported.

Codes emitted (all left unclassified in plan.ACTIONS on purpose — a log-derived
crawl error is as often a server/ops fix as a repo edit, so it goes to the
report's NEEDS A HUMAN section rather than the agent's queue):
  log.crawl_error     a crawler received a 4xx/5xx on this path
  log.byte_overhead   this path's average crawler payload exceeds the ceiling
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from pipeline.lib.baseline import Finding, assign_ordinals, sort_findings

from pipeline.lib.atomic import write_json_atomic

GATE = "site_health"
SCHEMA = "site-logs/1"

# Average bytes per crawler visit above which a path is flagged as bloated. A
# content page's rendered HTML rarely exceeds a couple hundred KB; half a MB is a
# generous ceiling that only un-minified / un-compressed payloads cross.
BYTE_OVERHEAD = 500_000

# User-Agent substrings that identify a crawler we care about. Lowercased match.
CRAWLER_UAS = (
    "googlebot", "bingbot", "gptbot", "claudebot", "claude-searchbot",
    "oai-searchbot", "chatgpt-user", "perplexitybot", "google-extended",
    "ccbot", "applebot", "duckduckbot", "yandexbot", "baiduspider",
)

# Apache/Nginx "combined". The UA is the last quoted field; the optional group
# lets a "common" line (no referer/UA) still parse for status, though without a
# UA it cannot be crawler-attributed.
_COMBINED_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[[^\]]*\] '
    r'"(?P<method>\S+) (?P<path>\S+)[^"]*" '
    r'(?P<status>\d{3}) (?P<bytes>\S+)'
    r'(?: "[^"]*" "(?P<ua>[^"]*)")?'
)


def _classify_ua(ua: str) -> str | None:
    """The crawler name if this UA is one we track, else None."""
    low = (ua or "").lower()
    for name in CRAWLER_UAS:
        if name in low:
            return name
    return None


def _int(value) -> int:
    """A byte count, tolerating '-' (no body) and non-numeric junk."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _norm_path(raw: str) -> str:
    """Reduce a request target to a bare path — drop scheme/host and query."""
    if not raw:
        return ""
    raw = raw.split("?", 1)[0].split("#", 1)[0]
    if raw.startswith("http://") or raw.startswith("https://"):
        raw = "/" + raw.split("/", 3)[-1] if raw.count("/") >= 3 else "/"
    return raw or "/"


def parse_line(line: str) -> dict | None:
    """One log line -> {path, status, bytes, ua} or None if unrecognizable."""
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return None
        req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
        headers = req.get("headers") if isinstance(req.get("headers"), dict) else {}
        path = (rec.get("ClientRequestURI") or rec.get("ClientRequestPath")
                or rec.get("EdgePathingSrc") or req.get("uri"))
        status = rec.get("EdgeResponseStatus") or rec.get("OriginResponseStatus")
        nbytes = rec.get("EdgeResponseBytes") or rec.get("ResponseBytes")
        ua = (rec.get("ClientRequestUserAgent") or rec.get("UserAgent")
              or headers.get("user-agent"))
        if path is None or status is None:
            return None
        return {"path": _norm_path(str(path)), "status": int(_int(status)),
                "bytes": _int(nbytes), "ua": ua or ""}
    m = _COMBINED_RE.match(line)
    if not m:
        return None
    return {"path": _norm_path(m.group("path")), "status": int(m.group("status")),
            "bytes": _int(m.group("bytes")), "ua": m.group("ua") or ""}


def parse_logs(path: str) -> tuple:
    """(findings, status_string). Never raises. A missing/empty/unparseable log
    is a named skip with zero findings, so a log that measured nothing can never
    read as a clean site."""
    p = Path(path) if path else None
    if not p or not p.is_file():
        return [], f"skipped: log file not found: {path}"
    try:
        text = p.read_text(errors="replace")
    except OSError as exc:
        return [], f"skipped: cannot read {path}: {exc}"

    # per path: crawler status counts, crawler byte samples, crawler hit total
    status_by_path: dict = defaultdict(Counter)
    bytes_by_path: dict = defaultdict(list)
    crawler_reqs = 0
    total = parsed = unknown = 0

    for line in text.splitlines():
        total += 1
        rec = parse_line(line)
        if rec is None:
            unknown += 1
            continue
        parsed += 1
        crawler = _classify_ua(rec["ua"])
        if not crawler:
            continue
        crawler_reqs += 1
        status_by_path[rec["path"]][rec["status"]] += 1
        bytes_by_path[rec["path"]].append(rec["bytes"])

    if parsed == 0:
        return [], (f"skipped: no recognizable log lines in {path} "
                    f"({total} lines, need Apache/Nginx combined or Cloudflare JSON)")
    if crawler_reqs == 0:
        return [], (f"parsed {parsed}/{total} lines but none were from a known "
                    f"crawler — nothing to attribute (common-format logs carry no "
                    f"User-Agent)")

    findings: list = []
    errors = 0
    for path_, counts in status_by_path.items():
        for status, n in sorted(counts.items()):
            if status >= 400:
                errors += 1
                findings.append(Finding(GATE, "log.crawl_error", path_,
                                        context=str(status),
                                        detail=f"crawler got {status} x{n}"))
    for path_, samples in bytes_by_path.items():
        if samples:
            avg = sum(samples) // len(samples)
            if avg > BYTE_OVERHEAD:
                findings.append(Finding(GATE, "log.byte_overhead", path_,
                                        detail=f"avg {avg} bytes over {len(samples)} "
                                               f"crawler visits"))

    status = (f"parsed {parsed}/{total} lines ({unknown} unrecognized), "
              f"{crawler_reqs} crawler requests across {len(status_by_path)} paths, "
              f"{errors} crawl errors")
    return sort_findings(assign_ordinals(findings)), status


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="wf-logparse",
        description="Parse a server access log into crawl-budget findings.")
    ap.add_argument("--logs", required=True, help="path to the access log file")
    ap.add_argument("--out", help="write a findings doc here (default: stdout summary only)")
    args = ap.parse_args()

    findings, status = parse_logs(args.logs)
    print(f"[logs] {status}", file=sys.stderr)

    if args.out:
        doc = {
            "schema": SCHEMA,
            "generated": date.today().isoformat(),
            "source": args.logs,
            "findings": [dict(f.to_json(), fingerprint=f.fingerprint) for f in findings],
        }
        write_json_atomic(args.out, doc)
        print(f"[OK] {len(findings)} findings -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
