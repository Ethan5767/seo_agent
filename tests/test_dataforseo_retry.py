"""call() retries transient network/TLS failures but not HTTP/JSON errors."""
import urllib.error

from pipeline.scanner import dataforseo as d


def _creds(monkeypatch):
    monkeypatch.setenv("DATAFORSEO_LOGIN", "x")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "y")
    # Opt in to the live-call path so retry behaviour is exercised. The suite's
    # autouse `_no_network` guard still blocks any real socket, so urlopen must
    # be stubbed (as each test does) — this only lifts the spend gate.
    monkeypatch.setenv("DATAFORSEO_PAUSE_SPEND", "0")


class _Resp:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return b'{"ok": 1}'


def test_call_retries_then_succeeds(monkeypatch):
    _creds(monkeypatch)
    n = {"c": 0}

    def flaky(req, timeout=0):
        n["c"] += 1
        if n["c"] < 3:
            raise urllib.error.URLError("_ssl.c:1064: handshake timed out")
        return _Resp()

    monkeypatch.setattr(d.urllib.request, "urlopen", flaky)
    doc, err = d.call("/x", sleep=lambda _s: None)
    assert err is None and doc == {"ok": 1}
    assert n["c"] == 3  # failed twice, succeeded on the third


def test_call_gives_up_after_retries(monkeypatch):
    _creds(monkeypatch)
    n = {"c": 0}

    def always_fail(req, timeout=0):
        n["c"] += 1
        raise urllib.error.URLError("network down")

    monkeypatch.setattr(d.urllib.request, "urlopen", always_fail)
    doc, err = d.call("/x", retries=3, sleep=lambda _s: None)
    assert doc is None and "URLError" in err
    assert n["c"] == 3


def test_call_retries_5xx(monkeypatch):
    _creds(monkeypatch)
    n = {"c": 0}

    def flaky(req, timeout=0):
        n["c"] += 1
        if n["c"] < 2:
            raise urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)
        return _Resp()

    monkeypatch.setattr(d.urllib.request, "urlopen", flaky)
    doc, err = d.call("/x", sleep=lambda _s: None)
    assert err is None and doc == {"ok": 1}
    assert n["c"] == 2  # 503 retried, then succeeded


def test_call_does_not_retry_http_error(monkeypatch):
    _creds(monkeypatch)
    n = {"c": 0}

    def http_err(req, timeout=0):
        n["c"] += 1
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(d.urllib.request, "urlopen", http_err)
    doc, err = d.call("/x", sleep=lambda _s: None)
    assert doc is None and "HTTP 401" in err
    assert n["c"] == 1  # not retried
