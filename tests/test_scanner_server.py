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
