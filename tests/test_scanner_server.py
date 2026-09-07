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
    assert any("Opened the page" in ln for ln in log)
    assert any("Checked" in ln and "passed" in ln for ln in log)
    # plain language, no raw byte counts or "HTTP 200" jargon
    assert not any("HTTP 200" in ln for ln in log)


def test_root_serves_index():
    idx = Path("pipeline/scanner/static/index.html")
    assert idx.is_file()
    combined = idx.read_text() + Path("pipeline/scanner/static/app.js").read_text()
    assert "/scan" in combined


def test_load_dotenv_sets_env_without_overwriting(tmp_path, monkeypatch):
    from pipeline.scanner.server import load_dotenv
    env = tmp_path / ".env"
    env.write_text("# comment\nCRUX_API_KEY=abc123\nALREADY_SET=fromfile\n\n")
    monkeypatch.setenv("ALREADY_SET", "preexisting")
    monkeypatch.delenv("CRUX_API_KEY", raising=False)
    loaded = load_dotenv(env)
    import os
    assert "CRUX_API_KEY" in loaded
    assert os.environ["CRUX_API_KEY"] == "abc123"
    assert os.environ["ALREADY_SET"] == "preexisting"  # never overwrites


def test_bare_domain_is_normalized_to_https():
    seen = {}
    def fetch(u):
        seen["u"] = u
        return BAD, 200, "", ""
    report = build_report("example.com/page/", fetch=fetch, crux=None)
    assert seen["u"].startswith("https://example.com/")
    https = next(r for r in report["tech"] if r["what"] == "HTTPS")
    assert https["severity"] == "ok"  # no longer a false error


def test_build_report_crawl_adds_site_group():
    # entry links to /a/ and /b/ (dup titles); injected page fetcher, no network.
    site_pages = {
        "https://s.com/": '<title>Home</title><a href="/a/">a</a><a href="/b/">b</a>',
        "https://s.com/a/": "<title>Dup</title>",
        "https://s.com/b/": "<title>Dup</title>",
    }
    def fetch(u):  # single-page fetch (entry): html,status,robots,sitemap
        return site_pages["https://s.com/"], 200, "", ""
    def page_fetch(u):
        return site_pages.get(u, ""), (200 if u in site_pages else 404)
    report = build_report("https://s.com/", fetch=fetch, crux=None,
                          crawl=True, page_fetch=page_fetch, max_pages=25)
    assert "site" in report and report["site"]
    assert any(r["code"] == "site.duplicate_page_titles" for r in report["site"])
