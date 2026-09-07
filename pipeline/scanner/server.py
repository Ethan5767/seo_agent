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


def build_report(url: str, fetch=_default_fetch, crux="auto", log=None,
                 crawl=False, page_fetch=None, max_pages=25) -> dict:
    """Compose the audit. `fetch(url)->(html,status,robots[,sitemap])`. `crux` =
    None (disabled), a (metrics,status) tuple, or 'auto' (call CrUX if key set).
    `log` (a list) collects a human-readable trace of what the scan did."""
    log = log if log is not None else []
    url = normalize_url(url)
    fetched = fetch(url)
    html, status, robots = fetched[0], fetched[1], fetched[2]
    sitemap = fetched[3] if len(fetched) > 3 else None
    if status == 200:
        log.append(f"Opened the page — {_human_size(len(html))}, loaded OK.")
    else:
        log.append(f"Opened the page — the server responded {status} (couldn't read it normally).")
    log.append(
        f"Found robots.txt — the file that tells Google and AI crawlers what they may read."
        if robots else
        "No robots.txt found — crawlers have no explicit instructions."
    )
    log.append("Running on-page SEO checks…")
    seo = A.seo_rows(url, html, status, {})
    log.append("Running AI-visibility (AEO) checks…")
    aeo = A.aeo_rows(robots, html)
    log.append("Measuring speed (Core Web Vitals)…")
    if crux == "auto":
        if os.environ.get("CRUX_API_KEY"):
            crux = crux_metrics(urlsplit(url).netloc)
            log.append("Speed (Core Web Vitals) — " + _human_crux(crux[1]))
        else:
            crux = None
            log.append("Speed (Core Web Vitals) — skipped: no Google speed key set up yet.")
    perf = A.perf_rows(crux)
    log.append("Running technical checks…")
    tech = tech_rows(url, html, status, sitemap)
    log.append(
        f"Sitemap.xml -> {'found' if sitemap and sitemap.strip() else 'none found'}."
    )
    site: list[dict] = []
    if crawl:
        log.append(f"Crawling the whole site (up to {max_pages} pages)…")
        c = crawl_site(url, page_fetch or _default_page_fetch,
                       sitemap_text=sitemap, max_pages=max_pages,
                       on_page=lambda n, total, u: log.append(f"  crawling {n}/{total}: {u}"))
        site = site_rows(c)
        n_ok = sum(1 for p in c["pages"] if p["status"] == 200)
        log.append(f"Crawled the whole site — {n_ok} page(s) walked"
                   + (" (page cap reached)." if c["capped"] else "."))
    all_rows = seo + aeo + perf + tech + site
    issues = sum(1 for r in all_rows if r["severity"] in ("error", "warn"))
    passed = sum(1 for r in all_rows if r["severity"] == "ok")
    log.append(
        f"Checked {len(all_rows)} things — {issues} need attention, {passed} passed. "
        "Everything is listed below (green = good)."
    )
    return A.assemble(seo, aeo, perf, tech, site)


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
        try:
            out = {"audit": build_report(url, log=log, crawl=crawl, max_pages=max_pages)}
            if repo:
                out["cycle"] = run_cycle(Path(repo), url, model, log=log)
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
