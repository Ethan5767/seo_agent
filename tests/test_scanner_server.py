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


def test_build_report_site_audit_uses_dataforseo_not_free_crawler():
    # Site-wide now comes from DataForSEO (injected), not the retired free crawler.
    def fetch(u):
        return BAD, 200, "", ""
    fake_site_audit = lambda domain, mp: (
        [{"code": "dfs.orphan_page", "what": "orphan page", "why": "w", "fix": "f",
          "severity": "warn", "detail": "/x/"}], "ok: crawled 20 · ~$0.0075 est", 0.0075)
    report = build_report("https://s.com/", fetch=fetch, crux=None,
                          crawl=True, site_audit_run=fake_site_audit)
    assert report["site"] and report["site"][0]["code"] == "dfs.orphan_page"
    assert report["cost"] == 0.0075  # the DataForSEO crawl cost flowed into the total
