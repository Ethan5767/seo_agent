"""wf-scan-web — a 127.0.0.1 web front end over the audit + Model A/B cycle.

Same rails as pipeline/dashboard: stdlib http.server, localhost only, no DB, no
accounts, no secrets on disk. build_report() is split out with injected fetchers
so it is unit-testable with no network.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from pipeline.audit import measure
from pipeline.audit.providers import crux_metrics
from pipeline.scanner import audit as A
from pipeline.scanner import dataforseo
from pipeline.scanner.extra_checks import tech_rows, video_rows, internal_link_rows
from pipeline.scanner import source_audit
from pipeline.scanner.onpage import onpage_deep_rows
from pipeline.scanner.run import run_cycle

STATIC = Path(__file__).parent / "static"

# The one shared .env loader — same file every wf-* command reads.
from pipeline.lib.env import load_env as load_dotenv  # noqa: E402 (re-export)


def _default_fetch(url: str):
    """(html, status, robots_text, sitemap_text) for a live URL. Reuses curl."""
    status = measure.curl_status(url)
    html = measure.curl(url) if status else ""
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    robots = measure.curl(f"{origin}/robots.txt", cache_bust=False)
    sitemap = measure.curl(f"{origin}/sitemap.xml", cache_bust=False)
    return html, status, robots, sitemap


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
    status = ("Core Web Vitals — " + _human_crux(crux[1])) if isinstance(crux, tuple) \
        else "Core Web Vitals — skipped: no Google speed key set up yet."
    return A.perf_rows(crux), status, 0.0


# One row per tool: (card name, report-group key, opts-flag gating it, run(ctx)).
# Adding a tool = append one row here — the orchestrator loop never changes.
# `run(ctx) -> (rows, status|None, cost)`. Free tools cost 0.0; DataForSEO tools
# return the exact cost from their response.
TOOLS = [
    ("On-page SEO", "seo", None, lambda c: (A.seo_rows(c.url, c.html, c.status, {}), None, 0.0)),
    ("AI visibility (AEO)", "aeo", None, lambda c: (A.aeo_rows(c.robots, c.html), None, 0.0)),
    ("Performance (speed)", "perf", None, _perf_tool),
    ("Technical", "tech", None, lambda c: (tech_rows(c.url, c.html, c.status, c.sitemap), None, 0.0)),
    ("On-page (deep)", "onpage", None, lambda c: (onpage_deep_rows(c.url, c.html, c.status), None, 0.0)),
    ("Video", "video", None, lambda c: (video_rows(c.html), None, 0.0)),
    ("Internal links", "internal", None, lambda c: (internal_link_rows(c.url, c.html), None, 0.0)),
    ("Source code", "source", "source",
     lambda c: (source_audit.analyze_source(source_audit.fetch_repo_files(c.repo, c.github_token)), None, 0.0)),
    ("Site Health (DataForSEO)", "site", "crawl", lambda c: dataforseo.site_audit(c.domain, c.max_pages)),
    ("Rankings (DataForSEO)", "rankings", "deep", lambda c: dataforseo.rankings(c.domain, c.keywords)),
    ("Keywords (DataForSEO)", "keywords", "deep", lambda c: dataforseo.keywords_card(c.domain, c.keywords, c.competitors)),
    ("AI citations (DataForSEO)", "ai", "deep", lambda c: dataforseo.llm_mentions(c.brand, c.domain)),
    ("Backlinks (DataForSEO)", "backlinks", "deep", lambda c: dataforseo.backlinks(c.domain)),
    ("Rankings trend (DataForSEO)", "rank_trend", "deep", lambda c: dataforseo.historical_rank(c.domain)),
]


def build_report(url: str, fetch=_default_fetch, crux="auto", log=None,
                 crawl=False, max_pages=25, deep=False, keywords=None,
                 competitors=None, business="", on_tool=None,
                 repo="", github_token="") -> dict:
    """Compose the audit by running each tool in TOOLS whose gate is on.
    `fetch(url)->(html,status,robots[,sitemap])`. `crux`: None | (metrics,status)
    | 'auto'. `log` collects a human trace; `on_tool(name,state,rows,status,cost)`
    fires per tool (running → done) so the UI shows a card per tool.

    Tests inject DataForSEO tools by monkeypatching `dataforseo.<fn>` (the same
    module-level seam the parser tests use) — no per-tool injection params."""
    log = log if log is not None else []
    url = normalize_url(url)
    fetched = fetch(url)
    html, status = fetched[0], fetched[1]
    log.append(f"Opened the page — {_human_size(len(html))}, loaded OK." if status == 200
               else f"Opened the page — the server responded {status} (couldn't read it normally).")

    ctx = SimpleNamespace(
        url=url, domain=urlsplit(url).netloc or url, html=html, status=status,
        robots=fetched[2], sitemap=fetched[3] if len(fetched) > 3 else None,
        crux=crux, max_pages=max_pages, keywords=keywords or [], competitors=competitors or [],
        brand=business or (urlsplit(url).netloc or url),
        repo=repo, github_token=github_token)
    # Two input lanes: the URL lane (always, when the page loaded) + the source
    # lane (when a GitHub repo + read token are supplied). Both run when both given.
    opts = {"crawl": crawl, "deep": deep,
            "source": bool(repo and github_token and "/" in repo)}

    groups: dict[str, list] = {}
    cost = 0.0
    for name, key, gate, run in TOOLS:
        if gate and not opts.get(gate):
            continue
        if on_tool:
            on_tool(name, "running", [], "", 0.0)
        rows, tool_status, tool_cost = run(ctx)
        cost += tool_cost
        groups[key] = rows
        line = tool_status or _status_line(rows)
        log.append(f"{name} — {line}")
        if on_tool:
            on_tool(name, "done", rows, line, tool_cost)

    all_rows = [r for rows in groups.values() for r in rows]
    log.append(f"Checked {len(all_rows)} things — {_status_line(all_rows)}. "
               f"Cost this run: ${cost:.4f}.")
    report = A.assemble(groups)
    report["cost"] = round(cost, 4)
    return report


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
        path = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        if path.startswith("static/"):
            path = path[len("static/"):]
        f = STATIC / path
        if f.is_file() and STATIC in f.resolve().parents:
            ctype = "text/html" if f.suffix == ".html" else "application/javascript"
            self._send(200, f.read_bytes(), ctype)
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
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
        crawl = bool(req.get("crawl"))
        try:
            max_pages = max(1, min(int(req.get("max_pages") or 25), 100))
        except (TypeError, ValueError):
            max_pages = 25

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

        print(f"\n[scan] url={url!r} model={model} crawl={crawl} repo={repo or '-'}", flush=True)
        log = Progress(cb=lambda ln: (emit({"log": ln}), print(f"   {ln}", flush=True)))

        def on_tool(name, state, rows, status, cost):
            emit({"tool": name, "state": state, "rows": rows, "status": status, "cost": cost})

        try:
            out = {"audit": build_report(url, log=log, crawl=crawl,
                                         max_pages=max_pages, deep=bool(req.get("deep")),
                                         on_tool=on_tool, keywords=profile["keywords"],
                                         competitors=profile["competitors"], business=profile["business"],
                                         repo=repo, github_token=(req.get("github_token") or ""))}
            if repo:
                out["cycle"] = run_cycle(Path(repo), url, model, log=log, profile=profile)
            out["log"] = list(log)
            emit({"result": out})
            print(f"[scan] done — score {out['audit']['score']}/100", flush=True)
        except Exception as exc:  # a failed scan is data, not a crash
            emit({"error": f"{type(exc).__name__}: {exc}", "log": list(log)})
            print(f"[scan] FAILED: {exc}", flush=True)


def main() -> int:
    loaded = load_dotenv()  # pipeline.lib.env.load_env — the one shared .env
    if loaded:
        print(f"loaded from .env: {', '.join(loaded)}")
    port = int(os.environ.get("SCAN_PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"wf-scan-web on http://127.0.0.1:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
