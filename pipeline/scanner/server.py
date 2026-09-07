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
from pipeline.scanner.run import run_cycle

STATIC = Path(__file__).parent / "static"

# The one shared .env loader — same file every wf-* command reads.
from pipeline.lib.env import load_env as load_dotenv  # noqa: E402 (re-export)


def _default_fetch(url: str):
    """(html, status, robots_text) for a live URL. Reuses measure's curl."""
    status = measure.curl_status(url)
    html = measure.curl(url) if status else ""
    parts = urlsplit(url)
    robots = measure.curl(f"{parts.scheme}://{parts.netloc}/robots.txt", cache_bust=False)
    return html, status, robots


def build_report(url: str, fetch=_default_fetch, crux="auto", log=None) -> dict:
    """Compose the audit. `fetch(url)->(html,status,robots)`. `crux` = None
    (disabled), a (findings,status) tuple, or 'auto' (call CrUX if key set).
    `log` (a list) collects a human-readable trace of what the scan did."""
    log = log if log is not None else []
    html, status, robots = fetch(url)
    log.append(f"GET {url} -> HTTP {status}, {len(html)} bytes")
    log.append(f"robots.txt -> {str(len(robots)) + ' bytes' if robots else 'none served'}")
    if crux == "auto":
        if os.environ.get("CRUX_API_KEY"):
            crux = crux_metrics(urlsplit(url).netloc)
            log.append(f"CrUX -> {crux[1]}")
        else:
            crux = None
            log.append("CrUX -> disabled (no CRUX_API_KEY in the backend env)")
    seo = A.seo_rows(url, html, status, {})
    aeo = A.aeo_rows(robots, html)
    perf = A.perf_rows(crux)
    log.append(f"checks -> {len(seo)} SEO, {len(aeo)} AEO finding(s)")
    return A.assemble(seo, aeo, perf)


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
        url = (req.get("url") or "").strip()
        repo = (req.get("repo") or "").strip()
        model = (req.get("model") or "B").strip().upper()
        log: list[str] = []
        try:
            out = {"audit": build_report(url, log=log)}
            if repo:
                out["cycle"] = run_cycle(Path(repo), url, model, log=log)
        except Exception as exc:  # a failed scan is data, not a crash
            log.append(f"ERROR {type(exc).__name__}: {exc}")
            return self._send(200, json.dumps({"error": f"{type(exc).__name__}: {exc}", "log": log}))
        out["log"] = log
        self._send(200, json.dumps(out, default=str))


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
