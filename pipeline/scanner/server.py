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
from urllib.parse import urlsplit

from pipeline.audit import measure
from pipeline.audit.providers import crux_metrics
from pipeline.scanner import audit as A
from pipeline.scanner import dataforseo
from pipeline.scanner.crawl import crawl_site, site_rows
from pipeline.scanner.extra_checks import tech_rows
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


def _default_page_fetch(url: str):
    """(html, status) for one page — the crawler's per-page fetcher."""
    status = measure.curl_status(url)
    return (measure.curl(url) if status else ""), status


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


def build_report(url: str, fetch=_default_fetch, crux="auto", log=None,
                 crawl=False, page_fetch=None, max_pages=25, deep=False,
                 on_tool=None) -> dict:
    """Compose the audit. `fetch(url)->(html,status,robots[,sitemap])`. `crux` =
    None (disabled), a (metrics,status) tuple, or 'auto' (call CrUX if key set).
    `log` collects a human trace; `on_tool(name, state, rows, status)` fires
    per tool (state 'running' then 'done') so the UI shows a card per tool."""
    log = log if log is not None else []

    totals = {"cost": 0.0}

    def running(name):
        if on_tool:
            on_tool(name, "running", [], "", 0.0)

    def done(name, rows, status=None, cost=0.0):
        totals["cost"] += cost
        if on_tool:
            on_tool(name, "done", rows, status or _status_line(rows), cost)

    url = normalize_url(url)
    fetched = fetch(url)
    html, status, robots = fetched[0], fetched[1], fetched[2]
    sitemap = fetched[3] if len(fetched) > 3 else None
    if status == 200:
        log.append(f"Opened the page — {_human_size(len(html))}, loaded OK.")
    else:
        log.append(f"Opened the page — the server responded {status} (couldn't read it normally).")

    running("On-page SEO")
    seo = A.seo_rows(url, html, status, {})
    done("On-page SEO", seo)

    running("AI visibility (AEO)")
    aeo = A.aeo_rows(robots, html)
    done("AI visibility (AEO)", aeo)

    running("Performance (speed)")
    if crux == "auto":
        crux = crux_metrics(urlsplit(url).netloc) if os.environ.get("CRUX_API_KEY") else None
    perf = A.perf_rows(crux)
    done("Performance (speed)", perf,
         "real Google field data" if isinstance(crux, tuple) else "no speed key / no field data")

    running("Technical")
    tech = tech_rows(url, html, status, sitemap)
    done("Technical", tech)

    site: list[dict] = []
    if crawl:
        running("Whole-site crawl (our crawler)")
        c = crawl_site(url, page_fetch or _default_page_fetch,
                       sitemap_text=sitemap, max_pages=max_pages,
                       on_page=lambda n, total, u: log.append(f"  crawling {n}/{total}: {u}"))
        site = site_rows(c)
        n_ok = sum(1 for p in c["pages"] if p["status"] == 200)
        done("Whole-site crawl (our crawler)", site, f"{n_ok} page(s) walked, {_status_line(site)}")

    rankings: list[dict] = []
    if deep:
        running("Rankings (DataForSEO)")
        rankings, dfs_status, dfs_cost = dataforseo.ranked_keywords(urlsplit(url).netloc or url)
        done("Rankings (DataForSEO)", rankings, dfs_status, dfs_cost)

    all_rows = seo + aeo + perf + tech + site + rankings
    log.append(f"Checked {len(all_rows)} things — {_status_line(all_rows)}. "
               f"Cost this run: ${totals['cost']:.4f}.")
    report = A.assemble(seo, aeo, perf, tech, site, rankings)
    report["cost"] = round(totals["cost"], 4)
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
                                         on_tool=on_tool)}
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
