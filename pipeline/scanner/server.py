"""wf-scan-web — a 127.0.0.1 web front end over the audit + Model A/B cycle.

Same rails as pipeline/dashboard: stdlib http.server, localhost only, no DB, no
accounts, no secrets on disk. build_report() is split out with injected fetchers
so it is unit-testable with no network.
"""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from datetime import date
from collections import namedtuple
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse, urlsplit

from pipeline.audit import measure
from pipeline.audit.providers import crux_metrics
from pipeline.scanner import audit as A
from pipeline.scanner import recommendations
from pipeline.scanner import dataforseo
from pipeline.scanner.extra_checks import tech_rows, internal_link_rows, local_rows
from pipeline.scanner import onpage
from pipeline.scanner import source_audit
from pipeline.scanner import onpage_audit
from pipeline.scanner import business_data
from pipeline.scanner import mentions
from pipeline.scanner import youtube
from pipeline.scanner.plan import build_plan
from pipeline.scanner.remediate import build_remediation
from pipeline.scanner.remediate_bridge import bridge_worklist
from pipeline.scanner.checks import checks_for
from pipeline.scanner.crawl import crawl_site, links_in, site_rows, crawl_trap_rows, crawl_depth_rows
from pipeline.lib.html import sitemap_locs
from pipeline.scanner.rows import unavailable_row
from pipeline.scanner import progress
from pipeline.scanner.multipage import merge_by_code
from pipeline.scanner import lighthouse
from pipeline.scanner.eeat import eeat_rows
from pipeline.scanner.schema_check import schema_rows
from pipeline.scanner.validate import validate_rows
from pipeline.scanner.content import content_rows
from pipeline.scanner.run import run_cycle

STATIC = Path(__file__).parent / "static"

# The one shared .env loader — same file every wf-* command reads.
from pipeline.lib.env import load_env as load_dotenv  # noqa: E402 (re-export)

load_dotenv()

from pipeline.lib.atomic import write_json_atomic
from pipeline.scanner.contracts import normalize_findings, tool_metadata
from pipeline.scanner.log_analysis import analyze_logs, parse_access_logs
from pipeline.scanner.index_reconcile import reconcile_index
from pipeline.scanner.rendering import rendering_rows, render_url
from pipeline.scanner.media import media_rows
from pipeline.scanner.security import security_rows
from pipeline.scanner.url_quality import url_quality_rows
from pipeline.scanner.migration import migration_rows
from pipeline.scanner.coverage_new import js_navigation_rows, parameter_inventory_rows, interstitial_rows


# robots.txt and sitemap.xml per origin, for the life of one scan. `_default_fetch`
# read both on EVERY call and the crawl calls it once per page, so a 100-page
# audit spent 200 requests re-reading two files that cannot change mid-scan.
_ORIGIN_FILES: dict = {}
_ORIGIN_FILES_TTL = 600.0


def _forget_origin_files() -> None:
    """Drop the cache. Called at the start of each scan, and by its tests."""
    _ORIGIN_FILES.clear()


def _origin_files(origin: str) -> tuple:
    hit = _ORIGIN_FILES.get(origin)
    if hit and (time.time() - hit[0]) < _ORIGIN_FILES_TTL:
        return hit[1], hit[2]
    robots = measure.curl(f"{origin}/robots.txt", cache_bust=False)
    sitemap = measure.curl(f"{origin}/sitemap.xml", cache_bust=False)
    _ORIGIN_FILES[origin] = (time.time(), robots, sitemap)
    return robots, sitemap


def _default_fetch(url: str):
    """(html, status, robots_text, sitemap_text, headers, chain) for a live URL.

    One `curl_full` gets the body, the status, the response headers and every
    redirect hop — what used to take a HEAD for the status and a GET for the
    body, and still threw the headers away. Callers that only want the first
    four values keep working: the tuple grew at the end.
    """
    from pipeline.lib.common import curl_full
    full = curl_full(url)
    status, html = full["status"], full["body"]
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    robots, sitemap = _origin_files(origin)
    return html, status, robots, sitemap, full["headers"], full["chain"]


def normalize_url(url: str) -> str:
    """A bare domain (no scheme) becomes https:// — otherwise urlsplit gets an
    empty netloc and robots/sitemap/CrUX/HTTPS all mis-read. Users paste bare
    domains; this makes that just work."""
    url = (url or "").strip()
    if url and "://" not in url:
        url = "https://" + url
    return url


def _status_line(rows: list) -> str:
    issues = sum(1 for r in rows if r["severity"] in ("error", "warn"))
    passed = sum(1 for r in rows if r["severity"] == "ok")
    return f"{issues} issue(s), {passed} passed"


def _perf_tool(c) -> tuple:
    """Resolve CrUX (auto = call it when a key is set) and build the perf rows.
    The one place the crux param's shape ('auto' | None | tuple) matters."""
    crux = c.crux
    if crux == "auto":
        crux = crux_metrics(c.domain) if os.environ.get("CRUX_API_KEY") else None
        # CrUX key missing or refused: PageSpeed Insights carries the same Chrome
        # field data, from the call Lighthouse makes anyway (cached on ctx).
        if crux is None or (not crux[0] and str(crux[1]).startswith(("error:", "skipped:"))):
            doc, err = lighthouse.get_psi(c)
            if not err:
                field = lighthouse.psi_field_metrics(doc)
                if field[0] or crux is None:
                    crux = field
    status = ("Core Web Vitals — " + _human_crux(crux[1])) if isinstance(crux, tuple) \
        else "Core Web Vitals — skipped: no Google speed key set up yet."
    return A.perf_rows(crux), status, 0.0


# One row per tool: (card name, report-group key, opts-flag gating it, run(ctx)).
# Adding a tool = append one row here — the orchestrator loop never changes.
# `run(ctx) -> (rows, status|None, cost)`. Free tools cost 0.0; DataForSEO tools
# return the exact cost from their response.
# One catalog row per Measure tool. `category` is the functional section the UI
# groups by (On-page, Technical, …); `group` is free/dataforseo/source (drives
# the paid badge + source precondition); `cost`/`cost_num` power the per-tool
# label + running total; `needs` is a precondition ("repo" = GitHub repo+token);
# `run(ctx) -> (rows, status, cost)` is the tool. Add a tool = one row; it shows
# up in /tools, the checklist and the results automatically.
Tool = namedtuple("Tool", "label key category group cost cost_num needs run")

# Display order of the functional sections.
CATEGORIES = ["On-page", "Technical", "Content", "Trust & E-E-A-T",
              "AEO (AI search)", "Performance", "Lighthouse (Google)", "Links",
              "Keywords & Rankings", "Local SEO", "Reputation", "Source code"]

TOOLS = [
    Tool("On-page SEO", "seo", "On-page", "free", "free", 0.0, None,
         lambda c: (A.seo_rows(c.url, c.html, c.status, {}), None, 0.0)),
    Tool("Site Health (DataForSEO)", "site", "On-page", "dataforseo", "~$0.006 (25 pages)", 0.006, None,
         lambda c: onpage_audit.site_audit_full(c.domain, c.max_pages)),
    Tool("On-page deep", "onpage", "On-page", "free", "free", 0.0, None,
         lambda c: (onpage.onpage_rows(c.url, c.html), None, 0.0)),
    Tool("Technical", "tech", "Technical", "free", "free", 0.0, None,
         lambda c: _tech_tool(c)),
    # What the RESPONSE says about itself: security headers, X-Robots-Tag,
    # cache/compression, the live redirect chain, the apex and HTTPS entry
    # points, whether a missing page really 404s, and the certificate's expiry.
    Tool("Headers & redirects", "headers", "Technical", "free", "free", 0.0, None,
         lambda c: _headers_tool(c)),
    # MONITOR — the live site after the merge, not the page being audited. Same
    # assertions as the client repo's daily seo-health workflow.
    Tool("Production monitor", "monitor", "Technical", "free", "free", 0.0, None,
         lambda c: _monitor_tool(c)),
    Tool("Schema validation", "schema", "Technical", "free", "free", 0.0, None,
         lambda c: (schema_rows(c.html), None, 0.0)),
    Tool("Sitemap & hreflang", "validate", "Technical", "free", "free", 0.0, None,
         lambda c: (validate_rows(c.html, c.sitemap), None, 0.0)),
    Tool("Content / info-gain", "content", "Content", "free", "free", 0.0, None,
         lambda c: (content_rows(c.html), None, 0.0)),
    Tool("Video", "video", "Content", "free", "free", 0.0, None,
         lambda c: youtube.video_rows_full(c.html, key=os.environ.get("YOUTUBE_API_KEY", ""))),
    Tool("Trust (E-E-A-T)", "eeat", "Trust & E-E-A-T", "free", "free", 0.0, None,
         lambda c: (eeat_rows(c.html, c.url), None, 0.0)),
    # Free local signals, read from the page we already fetched. Added when
    # B-096 removed four directory tiles that claimed "Synced" for Apple Maps,
    # Bing Places, Waze and YellowPages - none of which publishes a read API.
    # Removing a lie leaves a gap; these fill it with things that are true.
    Tool("Local signals", "local", "Local", "free", "free", 0.0, None,
         lambda c: (local_rows(c.html), None, 0.0)),
    Tool("AI visibility (AEO)", "aeo", "AEO (AI search)", "free", "free", 0.0, None,
         lambda c: (A.aeo_rows(c.robots, c.html), None, 0.0)),
    Tool("AI citations (DataForSEO)", "ai", "AEO (AI search)", "dataforseo", "~$0.11", 0.11, None,
         lambda c: dataforseo.llm_mentions(c.brand, c.domain)),
    Tool("Performance (speed)", "perf", "Performance", "free", "free", 0.0, None, _perf_tool),
    Tool("Lighthouse: Performance", "lh_perf", "Lighthouse (Google)", "free", "free", 0.0, None,
         lambda c: lighthouse.category_tool(c, "performance", "Performance")),
    Tool("Lighthouse: SEO", "lh_seo", "Lighthouse (Google)", "free", "free", 0.0, None,
         lambda c: lighthouse.category_tool(c, "seo", "SEO")),
    Tool("Lighthouse: Accessibility", "lh_a11y", "Lighthouse (Google)", "free", "free", 0.0, None,
         lambda c: lighthouse.category_tool(c, "accessibility", "Accessibility")),
    Tool("Lighthouse: Best practices", "lh_bp", "Lighthouse (Google)", "free", "free", 0.0, None,
         lambda c: lighthouse.category_tool(c, "best-practices", "Best practices")),
    # Site-wide, not this page: the four cards above judge the audited URL only.
    Tool("Lighthouse: Pages", "lh_pages", "Lighthouse (Google)", "free", "free", 0.0, None,
         lambda c: lighthouse.pages_tool(c)),
    Tool("Internal links", "internal", "Links", "free", "free", 0.0, None,
         lambda c: (internal_link_rows(c.url, c.html), None, 0.0)),
    Tool("Backlinks (DataForSEO)", "backlinks", "Links", "dataforseo", "~$0.025", 0.025, None,
         lambda c: dataforseo.backlinks(c.domain)),
    Tool("Backlink Overview (DataForSEO)", "backlink_overview", "Links", "dataforseo", "~$0.08", 0.08, None,
         lambda c: dataforseo.backlink_overview(c.domain)),
    Tool("Backlink Gap (DataForSEO)", "backlink_gap", "Links", "dataforseo", "~$0.025", 0.025, None,
         lambda c: dataforseo.backlink_gap(c.domain, c.competitors)),
    Tool("Keywords (DataForSEO)", "keywords", "Keywords & Rankings", "dataforseo", "~$0.18", 0.18, None,
         lambda c: dataforseo.keywords_card(c.domain, c.keywords, c.competitors)),
    Tool("Rankings (DataForSEO)", "rankings", "Keywords & Rankings", "dataforseo", "~$0.045", 0.045, None,
         # Your domain only. Passing competitors here mixed their overview and
         # keywords into Domain Overview and Organic Rankings, which show one domain.
         lambda c: dataforseo.rankings(c.domain, c.keywords)),
    Tool("Compare Domains (DataForSEO)", "compare", "Keywords & Rankings", "dataforseo", "~$0.05", 0.05, None,
         lambda c: dataforseo.compare_domains(c.domain, c.competitors)),
    Tool("Rankings trend (DataForSEO)", "rank_trend", "Keywords & Rankings", "dataforseo", "~$0.13", 0.13, None,
         lambda c: dataforseo.historical_rank(c.domain)),
    Tool("Local / GBP (DataForSEO)", "gbp", "Local SEO", "dataforseo", "~$0.006", 0.006, None,
         lambda c: business_data.gbp_local(c.brand)),
    Tool("Web mentions (DataForSEO)", "mentions", "Reputation", "dataforseo", "~$0.03", 0.03, None,
         lambda c: mentions.brand_mentions(c.brand)),
    Tool("Source code", "source", "Source code", "source", "free (needs repo)", 0.0, "repo",
         lambda c: (source_audit.analyze_source(
             source_audit.fetch_repo_files(c.repo, c.github_token),
             source_audit.fetch_repo_tree(c.repo, c.github_token)), None, 0.0)),
    # Access logs are user-uploaded evidence, not a network call. The tool is
    # opt-in and remains absent from a normal audit until a log file is supplied.
    Tool("Access log analysis", "logs", "Technical", "user_upload", "free (needs log upload)", 0.0, "logs",
         lambda c: (analyze_logs(parse_access_logs(c.access_logs), crawl_urls=set(c.crawl_urls)), None, 0.0)),
    Tool("Index reality reconciliation", "index_reality", "Technical", "third_party", "free (needs Search Console)", 0.0, "gsc",
         lambda c: (reconcile_index(set(c.crawl_urls), set(c.sitemap_urls), c.gsc_data), None, 0.0)),
    Tool("Headless rendering parity", "render", "Technical", "free", "free (Playwright)", 0.0, None,
         lambda c: (lambda rendered, error: (rendering_rows(c.url, c.html, rendered, error), None, 0.0))(*render_url(c.url))),
    Tool("Media SEO", "media", "Technical", "free", "free", 0.0, None,
         lambda c: (media_rows(c.html), None, 0.0)),
    Tool("Security and cloaking", "security", "Technical", "free", "free", 0.0, None,
         lambda c: (security_rows(c.url, c.html, c.headers), None, 0.0)),
    Tool("URL structure consistency", "url", "Technical", "free", "free", 0.0, None,
         lambda c: (url_quality_rows(c.crawl_urls), None, 0.0)),
    Tool("Crawl trap detection", "crawl_traps", "Links", "free", "free", 0.0, None,
         lambda c: (crawl_trap_rows(getattr(c, "crawl_snapshot", {})), None, 0.0)),
    Tool("Crawl depth & orphan analysis", "crawl_depth", "Links", "free", "free", 0.0, None,
         lambda c: (crawl_depth_rows(getattr(c, "crawl_snapshot", {})), None, 0.0)),
    Tool("JavaScript-only navigation", "js_navigation", "Technical", "free", "free", 0.0, None,
         lambda c: (js_navigation_rows(c.html), None, 0.0)),
    Tool("URL parameter inventory", "parameters", "Technical", "free", "free", 0.0, None,
         lambda c: (parameter_inventory_rows(getattr(c, "crawl_snapshot", {})), None, 0.0)),
    Tool("Mobile interstitial detection", "interstitial", "Technical", "free", "free", 0.0, None,
         lambda c: (interstitial_rows(c.html), None, 0.0)),
    Tool("Migration snapshot diff", "migration", "Technical", "own_crawler", "free (needs snapshots)", 0.0, "snapshot",
         lambda c: (migration_rows(c.migration_snapshot, c.migration_current), None, 0.0)),
]


# Execution phases, in order. Cheap/instant first, paid last, source last —
# so money (phase 3) is only spent after the free signal is in. This is the
# EXECUTION order; `category` is the separate VISUAL grouping of results.
PHASES = [(1, "Page & technical"), (2, "Google Lighthouse"),
          (3, "Search data (paid)"), (4, "Source code")]
_PHASE_LABEL = dict(PHASES)


def phase_of(t: Tool) -> int:
    """Which phase a tool runs in — derived from what it already is."""
    if t.group == "source":
        return 4
    if t.group == "dataforseo":
        return 3
    if t.key.startswith("lh_"):
        return 2
    return 1


# Pure per-page HTML tools — when a multi-page crawl is on, these run on every
# crawled page and merge by code. They must read ONLY per-page data (url/html/
# status). `tech` (reads site-level sitemap) and `aeo` (reads site-level robots)
# are deliberately excluded: those origin files aren't swapped per page, so
# running them per-page would repeat the homepage's robots/sitemap on every page.
# Everything else (CrUX, Lighthouse, DataForSEO, source, validate) runs once.
PER_PAGE = {"seo", "onpage", "schema", "content", "video", "eeat", "internal"}

# Tools whose data never came from our fetch of the page: DataForSEO queries by
# domain or brand, the source lane reads the repository. When the page cannot be
# fetched their results still stand; they were bought, and they are true.
PAGE_INDEPENDENT = {t.key for t in TOOLS if t.group in ("dataforseo", "source")}

# The on-page audit: every technical/on-page check that reads the site's pages
# or crawl, including DataForSEO Site Health. It deliberately excludes keyword,
# ranking, competitor, backlink, content, trust, video and local tools. The
# Dashboard and Site Audit run exactly this. DataForSEO availability and the
# spend pause are still enforced before the paid tool can run.
# What the pipeline's on-page audit runs.
#
# `headers` (response headers, redirect chain, soft-404, certificate), `aeo`
# (robots.txt and AI-crawler access) and `perf` (real-user Core Web Vitals from
# CrUX) were all built, tested, and reachable from nowhere in this flow — the
# audit judged the HTML and never the response, the robots file, or the speed
# real visitors get. The four Lighthouse category cards share ONE PageSpeed call
# per scan, so they cost one round trip between them.
#
# Lighthouse page checks run at the chosen audit depth, rather than hiding
# behind a separate Speed toggle. This makes Run Audit a complete technical SEO
# audit with a single, predictable scope.
ONPAGE_AUDIT_TOOLS = ("seo", "site", "onpage", "tech", "headers", "monitor", "schema", "validate",
                      "internal", "aeo", "perf", "lh_perf", "lh_seo", "lh_a11y", "lh_bp", "lh_pages", "render", "media", "security", "url", "crawl_traps", "crawl_depth", "js_navigation", "parameters", "interstitial")

# How deep the free multi-page crawl may go in one scan.
#
# It was 25 because the scan fetched every page twice — once to map the site,
# once again for the per-page tools — and the walk is sequential, so 25 pages
# already meant 50 round trips. The crawl now carries each page's body, so a
# page costs one request, and a real site (operator, 2026-09-16: "one website is
# at least 100 pages") fits in a single audit. Still bounded: the crawl is
# serial and every page runs the per-page tools, so depth is time.
MAX_CRAWL_PAGES = 100


def handle_plan(req: dict) -> dict:
    """Plan-stage ratchet over two findings lists — pure, so it's unit-testable
    without the HTTP layer. Bad/absent lists default to empty."""
    cur = req.get("current")
    prev = req.get("previous")
    return build_plan(cur if isinstance(cur, list) else [],
                      prev if isinstance(prev, list) else [])


def handle_monitor(req: dict, fetch=None, files=None) -> dict:
    """One production-watch run, for the live Monitor screen to poll.

    Deliberately NOT a scan: it saves nothing. The screen refreshes on a timer,
    and a scan row per refresh would bury the audit history in the same table.
    `fetch` and `files` are injected by the tests; live, both read the site.
    """
    from pipeline.scanner import monitor as M

    url = normalize_url(str(req.get("url") or "").strip())
    if not url:
        return {"rows": [], "counts": {}, "domain": "", "checked_at": "",
                "error": "no url given — the monitor needs the site to watch"}

    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if files is None:
        def files(o):
            return (measure.curl(f"{o}/robots.txt", cache_bust=False),
                    measure.curl(f"{o}/sitemap.xml", cache_bust=False))
    robots, sitemap = files(origin)

    routes = req.get("routes")
    rows = M.monitor_rows(url, sitemap=sitemap, robots=robots,
                          fetch=fetch or _live_fetch_full,
                          routes=routes if isinstance(routes, list) and routes else None,
                          min_sitemap=int(req.get("min_sitemap") or 0),
                          limit=max(1, min(int(req.get("limit") or M.DEFAULT_ROUTE_LIMIT), MAX_CRAWL_PAGES)))
    counts = {"error": 0, "warn": 0, "info": 0, "ok": 0}
    for r in rows:
        counts[r["severity"]] = counts.get(r["severity"], 0) + 1
    return {"rows": rows, "counts": counts, "domain": parts.netloc,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def handle_remediate(req: dict) -> dict:
    """Remediate stage — classify a Plan worklist into fix lanes (auto vs manual).
    Pure, unit-testable without HTTP. A bad/absent worklist defaults to empty."""
    wl = req.get("worklist")
    return build_remediation(wl if isinstance(wl, list) else [])


# Engine repo root (this file is pipeline/scanner/server.py → parents[2]).
_ENGINE_ROOT = Path(__file__).resolve().parents[2]


def parse_dryrun_output(stdout: str) -> list[dict]:
    """Split wf-site-remediate --dry-run stdout into per-item {header, prompt}.
    The tool prints `\\n===== <id> — <code> on <url> =====` before each item's
    prompt, so the marker is a clean, stable split point."""
    blocks = ("\n" + stdout).split("\n===== ")
    items = []
    for b in blocks[1:]:
        head, _, body = b.partition("\n")
        items.append({"header": head.replace(" =====", "").strip(), "prompt": body.strip()})
    return items


def _remediate_prep(req: dict):
    """Shared setup for dry-run and apply: validate, bridge, write the worklist
    into the client repo. Returns (err_dict, ctx). `err_dict` is None on success;
    `ctx` = {repo_path, cycle, bridged, out_dir}. Every failure is named."""
    repo = (req.get("repo") or "").strip()
    url = (req.get("url") or "").strip()
    worklist = req.get("worklist")
    tier = req.get("tier") or 1
    cycle = (req.get("cycle") or date.today().strftime("%Y-%m")).strip()
    # cycle names a folder we create + write into — pin it to YYYY-MM so a crafted
    # value ("../../etc") can't escape docs/audit/ (path traversal).
    if not re.fullmatch(r"\d{4}-\d{2}", cycle):
        return {"ok": False, "error": f"bad cycle {cycle!r} — must be YYYY-MM."}, None
    if not isinstance(worklist, list):
        worklist = []
    if not repo:
        return {"ok": False, "error": "no repo on this client — add the repo path in Onboard."}, None
    repo_path = Path(repo).expanduser()
    if not repo_path.is_dir():
        return {"ok": False, "error": f"'{repo}' is not a local checkout. Remote owner/repo isn't "
                f"supported yet — clone it and point the client at the local path."}, None
    if not (repo_path / "docs" / "client-config.yml").is_file():
        return {"ok": False, "error": f"{repo} isn't onboarded for Model B — it has no "
                f"docs/client-config.yml (which declares the tier). Run wf-onboard --tier on it first."}, None

    bridged = bridge_worklist(worklist, url, tier, cycle)
    out_dir = repo_path / "docs" / "audit" / cycle
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_dir / "worklist.json", bridged["worklist"])
    return None, {"repo_path": repo_path, "cycle": cycle, "bridged": bridged, "out_dir": out_dir}


def handle_remediate_dryrun(req: dict) -> dict:
    """Bridge the web worklist into the pipeline shape, write it into the client
    repo, and run `wf-site-remediate --dry-run` — which streams the exact fix
    prompts and EDITS NOTHING. Real edit-runs are the separate, confirmed apply.

    Returns {ok, items, unbridged, prompts, exit_code, error?}. Every failure is
    named (remote repo, not onboarded, tool error), never a silent empty."""
    err, ctx = _remediate_prep(req)
    if err:
        return err
    bridged, repo_path, cycle = ctx["bridged"], ctx["repo_path"], ctx["cycle"]
    if not bridged["worklist"]["items"]:
        return {"ok": True, "items": [], "unbridged": bridged["unbridged"], "prompts": [],
                "exit_code": 0, "note": "nothing bridged to the code-fix rail this cycle."}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pipeline.audit.remediate",
             "--project", str(repo_path), "--cycle", cycle, "--dry-run", "--max-items", "1000"],
            cwd=str(_ENGINE_ROOT), capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "dry-run timed out after 120s", "unbridged": bridged["unbridged"]}

    prompts = parse_dryrun_output(proc.stdout)
    ok = proc.returncode == 0
    res = {"ok": ok, "items": bridged["worklist"]["items"], "unbridged": bridged["unbridged"],
           "prompts": prompts, "exit_code": proc.returncode}
    if not ok:
        # Surface the tool's own message (stderr first) so a config/tier refusal is visible.
        res["error"] = (proc.stderr.strip() or proc.stdout.strip() or "dry-run failed")[:2000]
    return res


def summarize_changelog(changelog: dict) -> dict:
    """Trim the pipeline changelog to what the UI shows after a real run: per-item
    status + note + files, plus the run totals. Defensive on a partial/absent doc."""
    items = []
    for it in (changelog.get("items") or []):
        items.append({"id": it.get("id"), "code": it.get("code"), "url": it.get("url"),
                      "status": it.get("status"), "note": (it.get("note") or "")[:500],
                      "files": it.get("files") or []})
    return {
        "attempted": changelog.get("attempted"),
        "queued": changelog.get("queued"),
        "stopped": changelog.get("stopped"),
        "cost_usd": changelog.get("cost_usd"),
        "files": changelog.get("files") or {},
        "items": items,
    }


def stream_remediate_apply(req: dict):
    """The REAL edit-run, as a stream of events.

    Hands the bridged worklist to Claude Code (the Claude subscription) so it
    edits the client repo, then reads back changelog.json and the git diff.
    Irreversible, so it demands `confirm: true` and refuses without `claude` on
    PATH. Bounded by `max_items` (default 3, cap 25) so a first run cannot run
    away. The operator commits and opens the PR downstream, where the gates are.

    Yields `{"log": line}` per line as Claude produces it, then exactly one
    terminal `{"result": {...}}`. This used to be a single blocking
    subprocess.run(capture_output=True, timeout=1800): remediate.py already
    streamed Claude's output line by line and this handler threw it away, so an
    operator clicking Apply watched nothing happen for up to thirty minutes.
    /scan solved the same problem the same way.
    """
    def done(result):
        return {"result": result}

    if req.get("confirm") is not True:
        yield done({"ok": False,
                    "error": "apply needs confirm:true — it edits the repo via Claude Code."})
        return
    if shutil.which("claude") is None:
        yield done({"ok": False,
                    "error": "Claude Code ('claude') isn't on PATH. Install it and log into "
                             "your Claude subscription, then retry — apply runs on the "
                             "subscription (no API key)."})
        return

    err, ctx = _remediate_prep(req)
    if err:
        yield done(err)
        return
    bridged, repo_path, cycle, out_dir = (
        ctx["bridged"], ctx["repo_path"], ctx["cycle"], ctx["out_dir"])
    if not bridged["worklist"]["items"]:
        yield done({"ok": True, "applied": 0, "unbridged": bridged["unbridged"],
                    "note": "nothing bridged to the code-fix rail — nothing to apply."})
        return

    try:
        max_items = int(req.get("max_items") or 3)
    except (TypeError, ValueError):
        max_items = 3
    max_items = max(1, min(max_items, 25))

    # Line-buffered so a long-running agent's output reaches the operator as it
    # is written rather than when the pipe fills.
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pipeline.audit.remediate",
             "--project", str(repo_path), "--cycle", cycle, "--max-items", str(max_items)],
            cwd=str(_ENGINE_ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except OSError as exc:
        yield done({"ok": False, "error": f"could not start the remediation run: {exc}"})
        return

    # Keep only the tail: a 30-minute run can emit a great deal, and the error
    # message needs the end of it, not all of it.
    tail: list[str] = []
    try:
        for line in proc.stdout:
            line = line.rstrip("\n")
            tail.append(line)
            if len(tail) > 200:
                del tail[0]
            yield {"log": line}
    except (BrokenPipeError, ConnectionResetError):
        # The operator closed the tab. Stop the agent rather than leaving it
        # editing a repo nobody is watching.
        proc.kill()
        return

    try:
        returncode = proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        returncode = -1

    changelog = {}
    cl_path = out_dir / "changelog.json"
    if cl_path.is_file():
        try:
            changelog = json.loads(cl_path.read_text())
        except json.JSONDecodeError:
            changelog = {}
    summary = summarize_changelog(changelog)
    diffstat = ""
    try:
        diffstat = subprocess.run(["git", "-C", str(repo_path), "diff", "--stat"],
                                  capture_output=True, text=True, timeout=30).stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass

    applied = sum(1 for it in summary["items"] if it["status"] == "fixed")
    ok = returncode in (0, 1)  # 1 = tool's "nothing fixed", not a crash
    res = {"ok": ok, "applied": applied, "exit_code": returncode, "cycle": cycle,
           "summary": summary, "diffstat": diffstat, "unbridged": bridged["unbridged"]}
    if not ok:
        res["error"] = ("\n".join(tail).strip() or "apply failed")[-2000:]
    yield done(res)


def handle_remediate_apply(req: dict) -> dict:
    """The non-streaming form, kept so the plain JSON endpoint still works.

    Drains the stream and returns its terminal result. Callers that want live
    progress should consume `stream_remediate_apply` directly.
    """
    result = {"ok": False, "error": "apply produced no result"}
    for ev in stream_remediate_apply(req):
        if "result" in ev:
            result = ev["result"]
    return result


def all_playbooks() -> dict:
    """Every code that has a written playbook, keyed by code.

    Only the written ones: an empty playbook is indistinguishable from a missing
    screen, and shipping 24 empty shells would let the UI offer "How to fix" on
    findings with nothing behind it.
    """
    return {code: recommendations.playbook(code)
            for code in recommendations.RECOMMENDATIONS
            if recommendations.has_playbook(code)}


def tool_catalog() -> list[dict]:
    """The tool list the frontend renders — single source of truth for the UI.
    `checks` is the tool's named checks (from checks.checks_for) so the UI can show
    every individual check as its own row, pending → checking → result."""
    paid_ok, paid_reason = dataforseo.availability()

    def _avail(t):
        # Environment-level only: a repo/token is per request, so the source lane
        # is reported available here and refuses by name inside the scan.
        return (paid_ok, paid_reason) if t.group == "dataforseo" else (True, "")

    return [{"key": t.key, "label": t.label, "category": t.category,
             "group": t.group, "cost": t.cost, "cost_num": t.cost_num,
             **tool_metadata(t),
             "phase": phase_of(t), "phase_label": _PHASE_LABEL[phase_of(t)],
             "checks": checks_for(t.key),
             "available": _avail(t)[0], "unavailable_reason": _avail(t)[1]} for t in TOOLS]


def _live_fetch_full(url: str, **kw):
    from pipeline.lib.common import curl_full
    return curl_full(url, **kw)


def _monitor_tool(c) -> tuple:
    """(rows, status, cost) — one production-watch run over the live routes."""
    from pipeline.scanner import monitor as M

    live = getattr(c, "fetch_full", None)
    if not live:
        return ([], "not run: the monitor reads the live site, and no live fetcher was supplied", 0.0)
    rows = M.monitor_rows(c.url, sitemap=c.sitemap, robots=c.robots, fetch=live,
                          limit=int(getattr(c, "monitor_routes", 0) or M.DEFAULT_ROUTE_LIMIT))
    return rows, f"ok (live site, {len(rows)} check(s))", 0.0


def _tech_tool(c) -> tuple:
    """(rows, status, cost) — Technical on-page checks, comparing raw HTML with
    PageSpeed Insights rendered DOM when available."""
    psi_doc = getattr(c, "_psi", None)
    if psi_doc is None:
        try:
            from pipeline.scanner import lighthouse
            psi_doc, _ = lighthouse.get_psi(c)
        except Exception:
            psi_doc = None
    return tech_rows(c.url, c.html, c.status, c.sitemap, psi_doc=psi_doc), None, 0.0


def _headers_tool(c) -> tuple:
    """(rows, status, cost) — every response-level check for this page."""
    from pipeline.scanner import headers_check as H

    rows = H.header_rows(c.headers) + H.redirect_rows(c.url, c.chain)
    live = getattr(c, "fetch_full", None)
    if live:
        rows += H.entry_point_rows(c.url, fetch=live)
        rows += H.soft_404_rows(c.url, fetch=live)
        rows += H.ssl_rows(c.url)
    read = "ok (response headers)" if c.headers is not None else "no response headers were read"
    return rows, read, 0.0


def build_report(url: str, fetch=_default_fetch, crux="auto", log=None,
                 max_pages=25, keywords=None, selected=None,
                 competitors=None, business="", on_tool=None, on_progress=None,
                 repo="", github_token="", crawl_pages=1, lighthouse_pages=0, monitor_routes=0,
                 fetch_full=None, access_logs="", gsc_data=None, migration_snapshot=None,
                 migration_current=None) -> dict:
    """Compose the audit by running each selected tool in TOOLS.
    `selected`: a set of tool keys to run, or None = run all. A tool with
    `needs="repo"` is skipped when no repo/token is supplied.
    `fetch(url)->(html,status,robots[,sitemap])`. `crux`: None | (metrics,status)
    | 'auto'. `log` collects a human trace; `on_tool(name,state,rows,status,cost)`
    fires per tool (running → done) so the UI shows a card per tool.

    Tests inject DataForSEO tools by monkeypatching `dataforseo.<fn>` (the same
    module-level seam the parser tests use) — no per-tool injection params."""
    log = log if log is not None else []
    # One scan, one read of robots.txt and sitemap.xml per origin. Cleared here
    # so a later scan of the same site sees whatever those files say then.
    _forget_origin_files()
    url = normalize_url(url)
    fetched = fetch(url)
    html, status = fetched[0], fetched[1]
    # B-074. "Reachable" means a response we can actually judge: a 200 carrying
    # a body. A connection failure (status 0), an error page, or a 200 with an
    # empty body all mean the same thing to every downstream row builder — they
    # see `html == ""` and cannot distinguish it from a page that simply lacks
    # the feature they check. `assemble` drops the verdicts rather than letting
    # them read as passes.
    reachable = status == 200 and bool((html or "").strip())
    if status == 200 and not (html or "").strip():
        log.append("Opened the page — the server answered 200 with an empty body, "
                   "so there was nothing to measure.")
    else:
        log.append(f"Opened the page — {_human_size(len(html))}, loaded OK." if status == 200
                   else f"Opened the page — the server responded {status} (couldn't read it normally).")

    ctx = SimpleNamespace(
        url=url, domain=urlsplit(url).netloc or url, html=html, status=status,
        robots=fetched[2], sitemap=fetched[3] if len(fetched) > 3 else None,
        crux=crux, max_pages=max_pages, keywords=keywords or [], competitors=competitors or [],
        brand=business or (urlsplit(url).netloc or url),
        repo=repo, github_token=github_token, access_logs=access_logs,
        gsc_data=gsc_data, migration_snapshot=migration_snapshot, migration_current=migration_current,
        sitemap_urls=set(sitemap_locs(fetched[3] if len(fetched) > 3 else None)),
        # Filled in after the crawl, for the tools that judge the site rather
        # than this page (Lighthouse: Pages).
        crawled_urls=[url], crawl_urls=[url], lighthouse_pages=lighthouse_pages, monitor_routes=monitor_routes,
        # The response's own headers and redirect hops, when the fetcher carries
        # them (`_default_fetch` does; a test's 4-tuple fetch does not).
        headers=fetched[4] if len(fetched) > 4 else None,
        chain=fetched[5] if len(fetched) > 5 else [],
        # The live entry-point, soft-404 and certificate checks each ask the
        # origin something the page fetch cannot answer. Absent, they say they
        # were not measured rather than passing the site.
        fetch_full=fetch_full)
    # The source lane runs only for an owner/name GitHub repo + read token —
    # same guard as fetch_repo_files, so a local path skips instead of running
    # the tool to an empty result.
    source_ok = bool(repo and github_token and "/" in repo and not repo.startswith((".", "/", "~")))

    def _wanted(t):
        # An explicit selection is honoured as asked, paid tools included; a tool
        # that then cannot run says why (`_blocker`) rather than vanishing. With
        # no selection the scanner runs what costs nothing and needs nothing: a
        # paid call is only ever made because someone picked it.
        if selected is not None:
            return t.key in selected
        return t.group not in ("dataforseo", "user_upload", "third_party") and not (t.needs == "repo" and not source_ok)

    def _blocker(t) -> str:
        """Why a wanted tool cannot run right now, or "" when it can."""
        if t.group == "dataforseo":
            ok, reason = dataforseo.availability()
            return "" if ok else reason
        if t.needs == "snapshot" and not (ctx.migration_snapshot and ctx.migration_current):
            return "Migration mode needs both a pre-launch snapshot and a post-launch crawl."
        if t.needs == "logs" and not getattr(ctx, "access_logs", ""):
            return "upload an Apache/Nginx/Cloudflare/Fastly/CloudFront access log first"
        if t.needs == "gsc" and not getattr(ctx, "gsc_data", None):
            return "connect Google Search Console before reconciling index reality"
        if t.needs == "repo" and not source_ok:
            return ("needs a GitHub repo (owner/name) on the project and a GitHub "
                    "token: sign in with GitHub, then scan again")
        return ""

    # Free multi-page crawl: homepage + same-origin sitemap/nav URLs. Per-page
    # tools run on each; everything else runs once on the homepage.
    extra_pages: list = []
    # Site-wide rows from the same walk: broken internal links, orphan pages,
    # duplicate titles and descriptions. `crawl.crawl_site`/`site_rows` have
    # existed, tested, since the free-crawl work, and were called by NOTHING -
    # the scan used `discover_pages` instead, which fetches a flat list and so
    # can only ever run per-page tools. Every site-level finding the crawler
    # already knew how to produce was unreachable. B-007's shape.
    site_findings: list = []
    if crawl_pages > 1:
        # The scan's fetch returns (html, status, robots, sitemap); crawl_site
        # wants the (html, status) contract its own tests use. Adapt here rather
        # than widening the crawler, which is also used standalone.
        # The crawl reads each page once and does not need a cold render: a
        # cache-busted fetch of this site measured 12.5s against 3.3s cached,
        # and the crawl is serial. The audited URL above is still fetched fresh.
        crawl_fetch = ((lambda u: (lambda r: (r["body"], r["status"]))(fetch_full(u, cache_bust=False)))
                       if fetch_full else (lambda u: fetch(u)[:2]))
        walk = crawl_site(url, crawl_fetch, ctx.sitemap,
                          max_pages=crawl_pages, seed=(html, status),
                          on_page=(lambda n, total, u: on_progress(
                              "Multi-page crawl", f"Fetching page {n} of up to {total}: {u}",
                              {"step": "page", "phase": "progress", "n": n, "total": total, "url": u}))
                          if on_progress else None)
        for page in walk["pages"]:
            if page["url"] == url:
                continue
            # The crawl carries each page's body, so the per-page tools read what
            # it already fetched. This used to re-fetch every page: a 100-page
            # audit made 200 sequential requests, which is what held the depth
            # at 25.
            extra_pages.append((page["url"], page.get("html") or "", page["status"]))
        site_findings = site_rows(walk)
        ctx.sitemap_urls = set(walk["sitemap_urls"])
        ctx.crawl_snapshot = walk
        if on_progress:
            on_progress("Multi-page crawl", f"Crawled {len(walk['pages'])} page(s)",
                        {"step": "page", "phase": "finished", "n": len(walk["pages"]), "total": crawl_pages})
        if extra_pages:
            log.append(f"Crawled {len(extra_pages) + 1} pages for the free checks.")
        # Only pages that answered 200: PSI on a 404 measures the error page,
        # and a redirect would score a URL the crawl never judged.
        ctx.crawled_urls = [url] + [u for u, _, st in extra_pages if st == 200]
        ctx.crawl_urls = list(ctx.crawled_urls)

    if crawl_pages <= 1:
        ctx.crawl_snapshot = {}

    # url -> {code: worst failing severity} for the per-page summary. Filled
    # from the scored per-page tools only, so a page's counts add up to the
    # same findings the health score graded.
    page_issues: dict[str, dict] = {}

    def _note_issues(page_url, rows):
        mine = page_issues.setdefault(page_url, {})
        for r in rows or []:
            sev, code = r.get("severity"), r.get("code")
            if code and sev in ("error", "warn") and (mine.get(code) != "error"):
                mine[code] = sev

    def _run_tool(t):
        """Run one tool — across all crawled pages (merged) if it's per-page and
        a crawl is on, else once on the homepage."""
        noted = t.key in PER_PAGE and t.key in A.SCORED_GROUPS
        if t.key in PER_PAGE and extra_pages:
            per = [(url, t.run(ctx)[0])]
            for pu, phtml, pstatus in extra_pages:
                pctx = copy.copy(ctx)
                pctx.url, pctx.html, pctx.status = pu, phtml, pstatus
                per.append((pu, t.run(pctx)[0]))
            if noted:
                for pu, prows in per:
                    _note_issues(pu, prows)
            merged = merge_by_code(per)
            return merged, f"{len(per)} pages checked", 0.0
        result = t.run(ctx)
        if noted:
            _note_issues(url, result[0])
        return result

    groups: dict[str, list] = {}
    if site_findings:
        site_tool = next(t for t in TOOLS if t.key == "site")
        groups["site"] = normalize_findings(site_findings, site_tool)
    cost = 0.0
    # Walk phases in order (cheap → paid → source); a phase with no selected
    # tool is skipped silently, with no marker.
    for pn, plabel in PHASES:
        phase_tools = [t for t in TOOLS if phase_of(t) == pn and _wanted(t)]
        if not phase_tools:
            continue
        marker = f"Phase {pn}/{len(PHASES)}: {plabel}"
        log.append(f"— {marker} —")
        if on_tool:
            on_tool(marker, "phase", [], "", 0.0)
        for t in phase_tools:
            if on_tool:
                on_tool(t.label, "running", [], "", 0.0)
            blocker = _blocker(t)
            if blocker:
                rows, tool_status, tool_cost = [unavailable_row(t.key, blocker, t.label)], f"not run: {blocker}", 0.0
            else:
                sink = (lambda text, detail, _label=t.label: on_progress(_label, text, detail)) if on_progress else None
                with progress.reporting(sink):
                    rows, tool_status, tool_cost = _run_tool(t)
                # Ran, produced nothing, and its status is an error (HTTP 401,
                # a timeout, a crawl that never finished): say so on the page.
                # Only refusals checked before the run used to get a row, so a
                # failed Backlinks call read as "Run a scan with Backlinks enabled".
                if not rows and tool_status and not str(tool_status).startswith("ok"):
                    rows = [unavailable_row(t.key, str(tool_status), t.label)]
            cost += tool_cost
            # Extend, never assign: the free crawl's site-wide rows are already
            # filed under "site", which is also the Site Health tool's key. An
            # assignment here threw the crawl's findings away whenever both ran.
            groups.setdefault(t.key, []).extend(normalize_findings(rows, t))
            line = tool_status or _status_line(rows)
            log.append(f"{t.label} — {line}")
            if on_tool:
                on_tool(t.label, "done", rows, line, tool_cost)

    all_rows = [r for rows in groups.values() for r in rows]
    log.append(f"Checked {len(all_rows)} things — {_status_line(all_rows)}. "
               f"Cost this run: ${cost:.4f}.")
    report = A.assemble(groups, reachable=reachable, page_independent=PAGE_INDEPENDENT)
    report["cost"] = round(cost, 4)

    # The page AS FETCHED. Every row builder has had the HTML all along and the
    # report carried only verdicts about it, never the text itself - so two
    # features downstream were fabricating what they could have read:
    #
    #   * the SERP preview simulated a title and description, and shipped one
    #     pilot client's hospital copy to every account because it had nothing
    #     real to show;
    #   * `ContentContext.page` was declared, read by five content tools, and
    #     populated by nobody - so "rewrite the scanned page" rewrote nothing.
    #
    # Pass/fail is a judgement. This is the evidence the judgement was made on,
    # and both of those features need the evidence, not the verdict.
    report["page"] = page_facts(url, html, status) if reachable else None

    # One entry per page the audit read, for the Crawled Pages tables. An object
    # rather than a list: every list at the top of a report is read as a row
    # group (here by `assemble`, on the web by `rowsOf`), and a page is not a
    # finding.
    if reachable:
        for r in groups.get("site", []):
            if r.get("severity") in ("error", "warn"):
                for pu in r.get("pages") or []:
                    _note_issues(pu, [r])
        report["crawl"] = {"requested": crawl_pages,
                           "pages": page_summaries([(url, html, status)] + extra_pages, page_issues)}
    else:
        report["crawl"] = None
    return report


def page_summaries(pages: list, issues: dict) -> list[dict]:
    """`[(url, html, status)]` -> what the Crawled Pages table shows for each.
    Read from HTML already fetched; costs nothing."""
    from pipeline.lib.html import page_title, inner_text

    links = {pu: links_in(pu, ph) for pu, ph, _ in pages}
    out = []
    for pu, ph, pstatus in pages:
        h = ph or ""
        text = inner_text(re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", h))
        desc = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)', h, re.I)
        mine = issues.get(pu, {})
        sevs = list(mine.values())
        out.append({
            "url": pu,
            "status": pstatus,
            "title": page_title(h),
            "has_description": bool(desc and desc.group(1).strip()),
            "h1_count": len(re.findall(r"<h1\b", h, re.I)),
            "words": len(text.split()),
            "links_out": len(links[pu]),
            "links_in": sum(1 for other, ls in links.items()
                            if other != pu and pu.rstrip("/") in {l.rstrip("/") for l in ls}),
            "errors": sevs.count("error"),
            "warnings": sevs.count("warn"),
            "issues": mine,
        })
    return out



def local_checkout(repo: str) -> Path | None:
    """The repo as an existing local directory, or None.

    The scan used to call `run_cycle(Path(repo))` for any non-empty repo. A
    project's repo is usually a GitHub `owner/name`, which Path() reads as a
    relative folder: every scan created `owner/name/` in the scanner's working
    directory, ran `git init`, committed a baseline and wrote a client config
    into it (found 2026-09-14 when one was nearly committed into this repo).
    """
    if not repo or not isinstance(repo, str):
        return None
    p = Path(repo).expanduser()
    if not p.is_absolute() and not repo.startswith((".", "~")):
        return None
    return p if p.is_dir() else None


def page_facts(url: str, html: str, status: int) -> dict:
    """What the page actually says, for features that need the text and not a
    verdict about it. Read-only over HTML already in hand; costs nothing."""
    from pipeline.lib.html import page_title, inner_text

    h = html or ""
    desc = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)', h, re.I)
    canonical = re.search(r'<link[^>]*rel=["\']canonical["\'][^>]*href=["\']([^"\']+)', h, re.I)
    headings = [f"H{m.group(1)} {inner_text(m.group(2))[:120]}"
                for m in re.finditer(r"<h([1-3])\b[^>]*>(.*?)</h\1>", h, re.I | re.S)][:40]
    text = inner_text(re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", h))
    return {
        "url": url,
        "status": status,
        "title": page_title(h),
        "description": desc.group(1).strip() if desc else None,
        "canonical": canonical.group(1).strip() if canonical else None,
        "headings": headings,
        "wordCount": len(text.split()),
        # Capped: this rides in every scan response and the whole page is not
        # needed to rewrite it. The content tools slice to 6000 anyway.
        "text": text[:12000],
    }


def _human_size(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1000:
        return f"{n // 1000} KB"
    return f"{n} bytes"


def _human_crux(status: str) -> str:
    s = (status or "").lower()
    if s.startswith("ok"):
        return "real Google speed data found for this site."
    if "no field data" in s or "no record" in s:
        return "no Google speed data yet — the site needs more visitor traffic to be measured."
    if "skipped" in s:
        return "skipped: no Google speed key set up yet."
    return status


class Progress(list):
    """A log list that also streams each line to a callback the moment it's
    appended — so build_report/crawl progress reaches the browser live instead
    of all at once when the request finishes."""

    def __init__(self, cb=None):
        super().__init__()
        self._cb = cb

    def append(self, item):
        super().append(item)
        if self._cb:
            self._cb(item)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # keep the console quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/playbooks":
            # Served separately rather than inlined on every row: a report holds
            # 50+ rows and the steps and markup would dwarf the findings. The UI
            # fetches this once and looks up by code.
            return self._send(200, json.dumps({"playbooks": all_playbooks()}), "application/json")
        if self.path == "/tools":
            return self._send(200, json.dumps({"tools": tool_catalog()}))
        path = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        if path.startswith("static/"):
            path = path[len("static/"):]
        f = STATIC / path
        if f.is_file() and STATIC in f.resolve().parents and f.suffix == ".html":
            # The token rides in the HTML. CORS stops a cross-origin page from
            # reading it, which is what stops that page forging the header.
            body = f.read_text(encoding="utf-8").replace(
                "</head>",
                f'<script>window.SCAN_TOKEN="{getattr(self.server, "token", "")}";</script></head>',
                1)
            return self._send(200, body, "text/html")
        if f.is_file() and STATIC in f.resolve().parents:
            ctype = "text/html" if f.suffix == ".html" else "application/javascript"
            self._send(200, f.read_bytes(), ctype)
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        # B-079. Every POST here either spends money, writes to a repository, or
        # starts an AI agent inside one. None of them may be reachable by a page
        # the operator merely happens to be visiting.
        if not authorized(self.headers, getattr(self.server, "token", "")):
            return self._send(403, json.dumps({
                "error": "not authorized — this endpoint is not reachable from "
                         "another page. Open the console the server printed."
            }), "application/json")
        if self.path == "/monitor":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            return self._send(200, json.dumps(handle_monitor(req)))
        if self.path == "/plan":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            return self._send(200, json.dumps(handle_plan(req)))
        if self.path == "/remediate":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            return self._send(200, json.dumps(handle_remediate(req)))
        if self.path == "/remediate/dryrun":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            return self._send(200, json.dumps(handle_remediate_dryrun(req)))
        if self.path == "/remediate/apply":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            # Newline-delimited JSON, same shape as /scan: {"log": "..."} per
            # line as Claude writes it, then one {"result": {...}}. An apply can
            # run for half an hour; buffering it meant the operator watched a
            # dead screen and could not tell a working run from a hung one.
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for ev in stream_remediate_apply(req):
                try:
                    self.wfile.write((json.dumps(ev, default=str) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    break
            return
        if self.path != "/scan":
            return self._send(404, "not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        url = normalize_url(req.get("url") or "")
        repo = (req.get("repo") or "").strip()
        model = (req.get("model") or "B").strip().upper()

        def _list(v):
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
            return [s.strip() for s in str(v or "").split(",") if s.strip()]

        profile = {
            "business": (req.get("business") or "").strip(),
            "keywords": _list(req.get("keywords")),
            "competitors": _list(req.get("competitors")),
            "goal": (req.get("goal") or "").strip(),
        }
        # Selected tool keys — a list from the checklist, or absent → run all.
        # An explicit empty list means "nothing selected" (a client error): a
        # scan that runs zero tools must never report a clean score, so reject it.
        _tools = req.get("tools")
        selected = set(_tools) if isinstance(_tools, list) else None
        if selected is not None and not selected:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write((json.dumps({"error": "select at least one tool to run"}) + "\n").encode())
            return
        try:
            max_pages = max(1, min(int(req.get("max_pages") or 25), 100))
        except (TypeError, ValueError):
            max_pages = 25
        try:
            crawl_pages = max(1, min(int(req.get("crawl_pages") or 1), MAX_CRAWL_PAGES))
            lighthouse_pages = max(0, min(int(req.get("lighthouse_pages") or 0), MAX_CRAWL_PAGES))
            monitor_routes = max(0, min(int(req.get("monitor_routes") or 0), MAX_CRAWL_PAGES))
        except (TypeError, ValueError):
            crawl_pages = 1
            lighthouse_pages = 0
            monitor_routes = 0
        # The project's market (web/lib/market.ts derives it from the domain).
        # Validated here: a location code is a positive integer, a language a
        # short code. Anything else falls back to the env default.
        try:
            location = int(req.get("location_code") or 0)
            location = location if 1000 <= location <= 99_999_999 else None
        except (TypeError, ValueError):
            location = None
        language = str(req.get("language_code") or "").strip().lower()
        language = language if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", language) else None

        # Stream newline-delimited JSON: {"log": "..."} events live, then one
        # {"result": {...}} (or {"error": "..."}). The browser renders each event
        # as it arrives instead of waiting for the whole scan.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(obj):
            try:
                self.wfile.write((json.dumps(obj, default=str) + "\n").encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        print(f"\n[scan] url={url!r} model={model} tools={len(selected) if selected is not None else 'all'} repo={repo or '-'}", flush=True)
        log = Progress(cb=lambda ln: (emit({"log": ln}), print(f"   {ln}", flush=True)))

        def on_tool(name, state, rows, status, cost):
            emit({"tool": name, "state": state, "rows": rows, "status": status, "cost": cost})

        def on_progress(name, text, detail):
            emit({"tool": name, "state": "progress", "status": text, "detail": detail, "rows": [], "cost": 0})

        try:
            with dataforseo.market(location, language):
                log.append(f"Search data market: location {dataforseo.location_code()}, "
                           f"language {dataforseo.language_code()}.")
                out = {"audit": build_report(url, log=log, selected=selected,
                                             max_pages=max_pages,
                                             on_tool=on_tool, on_progress=on_progress, keywords=profile["keywords"],
                                             competitors=profile["competitors"], business=profile["business"],
                                             repo=repo, github_token=(req.get("github_token") or ""),
                                             crawl_pages=crawl_pages,
                                             lighthouse_pages=lighthouse_pages,
                                             monitor_routes=monitor_routes,
                                             fetch_full=_live_fetch_full)}
            checkout = local_checkout(repo)
            if checkout:
                out["cycle"] = run_cycle(checkout, url, model, log=log, profile=profile)
            elif repo:
                log.append(f"Plan cycle skipped: '{repo}' is not a local checkout on this machine "
                           "(a GitHub owner/name is read by the Source code tool, not cloned here).")
            out["log"] = list(log)
            emit({"result": out})
            print(f"[scan] done — score {out['audit']['score']}/100", flush=True)
        except Exception as exc:  # a failed scan is data, not a crash
            emit({"error": f"{type(exc).__name__}: {exc}", "log": list(log)})
            print(f"[scan] FAILED: {exc}", flush=True)


def authorized(headers, token: str) -> bool:
    """Is this request allowed to drive the scanner? (B-079)

    127.0.0.1 is not a trust boundary: any page in the operator's browser can
    POST to localhost, and a `text/plain` body triggers no CORS preflight to
    stop it. This server hands a request-supplied repo path to
    `claude -p --permission-mode acceptEdits`, so an unauthenticated POST is a
    remote page choosing which of the operator's repositories an AI agent edits.
    The response is unreadable cross-origin; the edit is not.

    Two layers, the same pair `pipeline/dashboard/server.py` already uses:

    1. A token minted per run and injected into the served HTML. CORS stops a
       cross-origin page from reading that HTML, so it cannot forge the header.
    2. Origin compared against THIS request's own Host — which is the
       same-origin test and needs no allow-list. A hardcoded list is what made
       the dashboard 403 every browser POST under `--host 0.0.0.0`. A forged
       Origin still fails: the browser sets Host to whatever it connected to,
       and an attacker page cannot make the two agree.

    Fails closed. No configured token means refuse, never allow.
    """
    if not token:
        return False
    origin = headers.get("Origin")
    if origin and urlparse(origin).netloc != headers.get("Host"):
        return False
    return headers.get("X-Scan-Token") == token


def main() -> int:
    loaded = load_dotenv()  # pipeline.lib.env.load_env — the one shared .env
    if loaded:
        print(f"loaded from .env: {', '.join(loaded)}")
    port = int(os.environ.get("SCAN_PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # Minted per run, never persisted. The console reads it from its own HTML.
    srv.token = os.environ.get("SCAN_TOKEN") or secrets.token_urlsafe(16)
    print(f"wf-scan-web on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
