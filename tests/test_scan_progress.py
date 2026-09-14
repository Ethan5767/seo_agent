"""Live scan progress: every line the activity panel shows is a real event.

The operator watched "Scanning..." for minutes while Site Health polled
DataForSEO silently every 12 s (the scanner log stopped at "Opened the page").
DataForSEO has no SSE; its on_page/summary poll is free and reports
pages_crawled / pages_in_queue. These tests pin that the scanner forwards what
it actually knows, and nothing it does not.
"""
from __future__ import annotations

import io
import json

import pytest

from pipeline.scanner import dataforseo, onpage_audit, progress, server


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "ops@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "0123456789abcdef")
    monkeypatch.delenv("DATAFORSEO_PAUSE_SPEND", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_emit_without_a_sink_is_a_no_op():
    progress.emit("nobody is listening", step="x")


def test_a_failing_sink_never_breaks_the_scan():
    def boom(text, detail):
        raise RuntimeError("ui went away")

    with progress.reporting(boom):
        progress.emit("still fine")


def test_a_dataforseo_request_reports_start_and_finish_with_cost(live, monkeypatch):
    monkeypatch.setattr(dataforseo.urllib.request, "urlopen",
                        lambda req, timeout=60: _Resp(json.dumps({"status_code": 20000, "cost": 0.024}).encode()))
    seen = []
    with progress.reporting(lambda text, d: seen.append((text, d))):
        dataforseo.call("/v3/backlinks/summary/live", [{"target": "x.com"}])
    phases = [d.get("phase") for _, d in seen]
    assert phases == ["start", "done"]
    assert "backlink summary" in seen[0][0].lower()
    assert seen[1][1]["cost"] == 0.024
    assert isinstance(seen[1][1]["ms"], int)


def test_a_failed_request_reports_the_error(live, monkeypatch):
    def refuse(req, timeout=60):
        import urllib.error
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(dataforseo.urllib.request, "urlopen", refuse)
    seen = []
    with progress.reporting(lambda text, d: seen.append((text, d))):
        dataforseo.call("/v3/backlinks/summary/live", [{}])
    assert seen[-1][1]["phase"] == "error"
    assert "401" in seen[-1][0]


def test_the_crawl_reports_real_page_counts_from_each_free_poll():
    polls = iter([
        {"status_code": 20000, "cost": 0, "tasks": [{"status_code": 20000, "result": [
            {"crawl_progress": "in_progress", "crawl_status": {"max_crawl_pages": 25, "pages_in_queue": 9, "pages_crawled": 6}}]}]},
        {"status_code": 20000, "cost": 0, "tasks": [{"status_code": 20000, "result": [
            {"crawl_progress": "finished", "crawl_status": {"max_crawl_pages": 25, "pages_in_queue": 0, "pages_crawled": 25}}]}]},
    ])

    def fake_call(path, payload=None, **k):
        if path.endswith("task_post"):
            return {"cost": 0.006, "tasks": [{"id": "T1", "status_code": 20100}]}, None
        if "/summary/" in path:
            return next(polls), None
        return {"cost": 0, "tasks": [{"status_code": 20000, "result": [{"items": []}]}]}, None

    seen = []
    with progress.reporting(lambda text, d: seen.append(d)):
        onpage_audit.crawl_onpage("x.com", 25, call=fake_call, sleep=lambda s: None)
    counts = [(d["pages_crawled"], d["pages_in_queue"], d["max_crawl_pages"]) for d in seen if d.get("step") == "crawl" and d.get("phase") == "progress"]
    assert counts == [(6, 9, 25), (25, 0, 25)]
    assert any(d.get("phase") == "posted" and d.get("cost") == 0.006 for d in seen)


def test_the_crawl_polls_faster_within_the_same_time_limit():
    import inspect
    sig = inspect.signature(onpage_audit.crawl_onpage)
    poll, n = sig.parameters["poll_seconds"].default, sig.parameters["max_polls"].default
    assert poll <= 5, "summary polls are free; 12 s between updates looked frozen"
    assert poll * n >= 240, "must not give up on a crawl sooner than before"


def test_build_report_streams_progress_under_the_running_tool(live, monkeypatch):
    monkeypatch.setattr(dataforseo.urllib.request, "urlopen",
                        lambda req, timeout=60: _Resp(json.dumps({"status_code": 20000, "cost": 0.02, "tasks": [
                            {"status_code": 20000, "result": [{"backlinks": 5, "referring_domains": 2, "rank": 1}]}]}).encode()))
    events = []

    def fetch(u):
        return ("<html><head><title>T</title></head><body><h1>H</h1></body></html>", 200, "", None)

    server.build_report("https://x.com/", fetch=fetch, crux=None, selected={"backlinks"},
                        on_progress=lambda name, text, detail: events.append((name, text, detail)))
    names = {n for n, _, _ in events}
    assert names == {"Backlinks (DataForSEO)"}
    assert [d["phase"] for _, _, d in events] == ["start", "done"]


def test_build_report_streams_each_page_of_the_free_crawl(monkeypatch):
    pages = {
        "https://x.com/": '<html><head><title>H</title></head><body><a href="/b">b</a></body></html>',
        "https://x.com/b": '<html><head><title>B</title></head><body></body></html>',
    }
    events = []
    server.build_report("https://x.com/", fetch=lambda u: (pages.get(u, ""), 200 if u in pages else 404, "", None),
                        crux=None, selected={"seo"}, crawl_pages=3,
                        on_progress=lambda name, text, detail: events.append((name, detail)))
    crawl = [d for n, d in events if n == "Multi-page crawl" and d.get("phase") == "progress"]
    assert crawl and crawl[0]["step"] == "page"
    assert {d["url"].rstrip("/") for d in crawl} >= {"https://x.com", "https://x.com/b"}


def test_on_tool_contract_is_unchanged():
    """Existing on_tool callbacks take five positional arguments; progress must
    not arrive through them."""
    calls = []
    server.build_report("https://x.com/", fetch=lambda u: ("<html><title>t</title></html>", 200, "", None),
                        crux=None, selected={"seo"}, on_tool=lambda a, b, c, d, e: calls.append(b))
    assert set(calls) <= {"phase", "running", "done"}


def test_the_free_crawl_reports_that_it_finished():
    pages = {"https://x.com/": "<html><head><title>H</title></head><body></body></html>"}
    events = []
    server.build_report("https://x.com/", fetch=lambda u: (pages.get(u, ""), 200 if u in pages else 404, "", None),
                        crux=None, selected={"seo"}, crawl_pages=2,
                        on_progress=lambda name, text, detail: events.append((name, detail)))
    assert events[-1][0] == "Multi-page crawl" and events[-1][1]["phase"] == "finished"


def test_request_labels_are_plain_words():
    assert dataforseo._label("/v3/on_page/task_post") == "start the site crawl"
    assert dataforseo._label("/v3/dataforseo_labs/google/ranked_keywords/live") == "the keywords this site ranks for"
    assert "/" not in dataforseo._label("/v3/some/unknown_endpoint/live")


def test_a_github_slug_is_never_treated_as_a_local_folder(tmp_path, monkeypatch):
    """Every scan of a project whose repo is `owner/name` created that folder in
    the scanner's working directory and ran `git init` in it."""
    monkeypatch.chdir(tmp_path)
    assert server.local_checkout("DonghuaOnly/student-attention-tracking") is None
    assert not (tmp_path / "DonghuaOnly").exists()
    assert server.local_checkout("") is None
    assert server.local_checkout(str(tmp_path / "missing")) is None
    real = tmp_path / "client"
    real.mkdir()
    assert server.local_checkout(str(real)) == real


def test_the_scan_handler_only_cycles_a_local_checkout():
    import inspect
    src = inspect.getsource(server)
    assert "= run_cycle(Path(repo)" not in src
    assert "checkout = local_checkout(repo)" in src
