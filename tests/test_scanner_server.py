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


def test_build_report_site_audit_uses_dataforseo_not_free_crawler(monkeypatch):
    # Site-wide comes from DataForSEO's on-page audit. Tests inject by
    # monkeypatching the module seam (onpage_audit.site_audit_full).
    from pipeline.scanner import onpage_audit
    monkeypatch.setattr(onpage_audit, "site_audit_full", lambda domain, mp: (
        [{"code": "dfs.op.is_orphan_page", "what": "Orphan page", "why": "w", "fix": "f",
          "severity": "warn", "detail": "1 page(s)"}], "crawled 20 · $0.0075", 0.0075))
    report = build_report("https://s.com/", fetch=lambda u: (BAD, 200, "", ""),
                          crux=None, selected={"site"})
    assert report["site"] and report["site"][0]["code"] == "dfs.op.is_orphan_page"
    assert report["cost"] == 0.0075  # the DataForSEO crawl cost flowed into the total


# ── streaming apply ──────────────────────────────────────────────────────────
# /remediate/apply used subprocess.run(capture_output=True, timeout=1800): it
# buffered everything and returned one JSON at the end, so an operator clicking
# Apply saw nothing for up to thirty minutes. remediate.py already streams
# Claude's output line by line; only this handler threw it away. /scan solved
# the same problem with Popen + flush per event.

class _GitStub:
    """Stands in for the `git diff --stat` call, which subprocess.run makes.

    Needed because patching subprocess.Popen also intercepts subprocess.run:
    run is implemented on top of Popen.
    """
    stdout = ""
    returncode = 0


def test_apply_stream_yields_log_events_then_a_result(monkeypatch, tmp_path):
    """The handler must emit progress as it arrives, not one blob at the end."""
    from pipeline.scanner import server as S

    lines = ["item 1/2 health.title_missing\n", "  fixed\n", "item 2/2 done\n"]

    class _FakeProc:
        returncode = 0
        stdout = iter(lines)

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(S.subprocess, "Popen", lambda *a, **k: _FakeProc())
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: _GitStub())
    monkeypatch.setattr(S, "_remediate_prep", lambda req: (None, {
        "bridged": {"worklist": {"items": [{"id": "x"}]}, "unbridged": []},
        "repo_path": tmp_path, "cycle": "2026-09", "out_dir": tmp_path,
    }))
    monkeypatch.setattr(S.shutil, "which", lambda name: "/usr/bin/claude")

    events = list(S.stream_remediate_apply({"confirm": True}))

    logs = [e for e in events if "log" in e]
    results = [e for e in events if "result" in e]
    assert logs, "no log events were emitted; the run was buffered again"
    assert [e["log"] for e in logs] == [ln.rstrip("\n") for ln in lines]
    assert len(results) == 1, "exactly one terminal result event is expected"
    assert results[-1] is events[-1], "the result must be the last event"


def test_apply_stream_refuses_without_confirm():
    from pipeline.scanner import server as S
    events = list(S.stream_remediate_apply({}))
    assert len(events) == 1
    assert events[0]["result"]["ok"] is False
    assert "confirm" in events[0]["result"]["error"]


def test_apply_stream_refuses_when_claude_is_missing(monkeypatch):
    from pipeline.scanner import server as S
    monkeypatch.setattr(S.shutil, "which", lambda name: None)
    events = list(S.stream_remediate_apply({"confirm": True}))
    assert len(events) == 1
    assert events[0]["result"]["ok"] is False
    assert "PATH" in events[0]["result"]["error"]


def test_apply_stream_reports_a_crash_as_a_result_not_an_exception(monkeypatch, tmp_path):
    """A failing subprocess must still terminate the stream with one result, so
    the browser is never left waiting on a socket that will not close."""
    from pipeline.scanner import server as S

    class _Boom:
        returncode = 2
        stdout = iter(["starting\n"])

        def wait(self, timeout=None):
            return 2

        def kill(self):
            pass

    monkeypatch.setattr(S.subprocess, "Popen", lambda *a, **k: _Boom())
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: _GitStub())
    monkeypatch.setattr(S, "_remediate_prep", lambda req: (None, {
        "bridged": {"worklist": {"items": [{"id": "x"}]}, "unbridged": []},
        "repo_path": tmp_path, "cycle": "2026-09", "out_dir": tmp_path,
    }))
    monkeypatch.setattr(S.shutil, "which", lambda name: "/usr/bin/claude")

    events = list(S.stream_remediate_apply({"confirm": True}))
    assert "result" in events[-1]
    assert events[-1]["result"]["ok"] is False
