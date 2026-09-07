from pathlib import Path

from pipeline.scanner.server import build_report

BAD = ("<html><head><title>t</title></head><body><main><h1>H</h1><p>x</p>"
       "</main></body></html>")


def test_build_report_composes_three_groups_without_network():
    def fetch(url):
        return BAD, 200, "User-agent: PerplexityBot\nDisallow: /\n"
    report = build_report("https://x.com/p/", fetch=fetch, crux=None)
    assert set(report) >= {"seo", "aeo", "perf", "score", "counts"}
    assert any(r["code"] == "aeo.crawler_blocked" for r in report["aeo"])
    assert report["perf"][0]["code"] == "crux.disabled"


def test_build_report_populates_log():
    def fetch(url):
        return BAD, 200, ""
    log: list[str] = []
    build_report("https://x.com/p/", fetch=fetch, crux=None, log=log)
    assert any("HTTP 200" in ln for ln in log)
    assert any("checks ->" in ln for ln in log)


def test_root_serves_index():
    idx = Path("pipeline/scanner/static/index.html")
    assert idx.is_file()
    combined = idx.read_text() + Path("pipeline/scanner/static/app.js").read_text()
    assert "/scan" in combined
