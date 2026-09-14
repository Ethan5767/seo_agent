"""The DataForSEO spend gate, and what a tool that cannot run says about it.

Until 2026-09-14 two hardcoded latches kept every paid tool dark in a live scan:
`server._wanted` admitted a `dataforseo` tool only under pytest, and
`dataforseo.call` refused any credentials except the literal fixture pair
`x`/`y`. Both were meant as a zero-spend safety and both were silent: a scan
that asked for Backlinks returned no Backlinks group and no reason, so 13
screens read as "nothing found" for a week.

The replacement rule is the one decision 1 of the tools-revamp design states: a
paid tool runs when credentials are set, `DATAFORSEO_PAUSE_SPEND` is not "1",
and it was selected. Anything short of that is a NAMED skip, one ungraded row,
never an absent group.
"""
from __future__ import annotations

import io
import json

import pytest

from pipeline.scanner import dataforseo, server


def fake_fetch(url):
    return ("<html><head><title>T</title></head><body><h1>H</h1>"
            "<main>hi</main></body></html>", 200, "", None)


@pytest.fixture
def no_creds(monkeypatch):
    monkeypatch.delenv("DATAFORSEO_LOGIN", raising=False)
    monkeypatch.delenv("DATAFORSEO_PASSWORD", raising=False)
    monkeypatch.delenv("DATAFORSEO_PAUSE_SPEND", raising=False)


@pytest.fixture
def real_creds(monkeypatch):
    # Deliberately NOT the x/y fixture pair the old latch demanded.
    monkeypatch.setenv("DATAFORSEO_LOGIN", "ops@example.com")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "0123456789abcdef")
    monkeypatch.delenv("DATAFORSEO_PAUSE_SPEND", raising=False)


# ── availability: one source of truth, no network ────────────────────────────

def test_unavailable_without_credentials(no_creds):
    ok, reason = dataforseo.availability()
    assert ok is False
    assert "DATAFORSEO_LOGIN" in reason and "DATAFORSEO_PASSWORD" in reason


def test_unavailable_when_paused(real_creds, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_PAUSE_SPEND", "1")
    ok, reason = dataforseo.availability()
    assert ok is False
    assert "DATAFORSEO_PAUSE_SPEND=1" in reason


def test_available_with_real_credentials(real_creds):
    assert dataforseo.availability() == (True, "")


def test_pause_zero_is_not_a_pause(real_creds, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_PAUSE_SPEND", "0")
    assert dataforseo.availability() == (True, "")


# ── call(): refuses by name, and calls when it should ────────────────────────

def test_call_refuses_without_credentials(no_creds):
    doc, err = dataforseo.call("/v3/anything", [{}])
    assert doc is None
    assert err.startswith("skipped:") and "DATAFORSEO_LOGIN" in err


def test_call_refuses_when_paused(real_creds, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_PAUSE_SPEND", "1")
    doc, err = dataforseo.call("/v3/anything", [{}])
    assert doc is None
    assert err.startswith("skipped:") and "DATAFORSEO_PAUSE_SPEND=1" in err


def test_call_makes_the_request_with_real_credentials(real_creds, monkeypatch):
    """The old latch refused every login but `x`. Real credentials must reach
    the network layer (stubbed here; the suite is hermetic)."""
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=60):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return Resp(json.dumps({"status_code": 20000, "cost": 0.01}).encode())

    monkeypatch.setattr(dataforseo.urllib.request, "urlopen", fake_urlopen)
    doc, err = dataforseo.call("/v3/backlinks/summary/live", [{"target": "x.com"}])
    assert err is None
    assert doc["status_code"] == 20000
    assert seen["url"].endswith("/v3/backlinks/summary/live")
    assert seen["auth"].startswith("Basic ")


# ── build_report: a selected paid tool runs outside pytest ───────────────────

def _scan(selected, monkeypatch, fetch=fake_fetch, **kw):
    # Prove the pytest-only branch is gone: behave like a live process.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    events = []

    def cap(name, state, rows, status, cost):
        events.append((name, state, rows, status))

    rep = server.build_report("https://x.com/", fetch=fetch, crux=None,
                              selected=selected, on_tool=cap, **kw)
    return rep, events


def test_selected_paid_tool_runs_in_a_live_process(real_creds, monkeypatch):
    called = []

    def fake_backlinks(domain, call=None):
        called.append(domain)
        return ([{"code": "dfs.backlinks", "what": "12 backlinks", "why": "", "fix": "",
                  "severity": "info"}], "ok", 0.02)

    monkeypatch.setattr(dataforseo, "backlinks", fake_backlinks)
    rep, _ = _scan({"backlinks"}, monkeypatch)
    assert called == ["x.com"]
    assert rep["backlinks"][0]["code"] == "dfs.backlinks"
    assert rep["cost"] == 0.02


def test_unselected_paid_tool_does_not_run(real_creds, monkeypatch):
    monkeypatch.setattr(dataforseo, "backlinks",
                        lambda *a, **k: pytest.fail("unselected paid tool ran"))
    rep, _ = _scan({"seo"}, monkeypatch)
    assert "backlinks" not in rep


def test_unavailable_paid_tool_is_a_named_ungraded_row(no_creds, monkeypatch):
    monkeypatch.setattr(dataforseo, "backlinks",
                        lambda *a, **k: pytest.fail("ran without credentials"))
    rep, events = _scan({"seo", "backlinks"}, monkeypatch)
    rows = rep["backlinks"]
    assert len(rows) == 1
    row = rows[0]
    assert row["code"] == "unavailable.backlinks"
    assert row["severity"] == "info"          # ungraded: must not move the score
    assert "DATAFORSEO_LOGIN" in row["why"]
    assert rep["cost"] == 0
    done = [e for e in events if e[0] == "Backlinks (DataForSEO)" and e[1] == "done"]
    assert done and "DATAFORSEO_LOGIN" in done[0][3]


def test_paused_tool_names_the_pause(real_creds, monkeypatch):
    monkeypatch.setenv("DATAFORSEO_PAUSE_SPEND", "1")
    monkeypatch.setattr(dataforseo, "backlinks",
                        lambda *a, **k: pytest.fail("ran while paused"))
    rep, _ = _scan({"backlinks"}, monkeypatch)
    assert "DATAFORSEO_PAUSE_SPEND=1" in rep["backlinks"][0]["why"]


def test_source_without_token_says_so(monkeypatch):
    """D12: the source lane used to vanish from the run with no row."""
    rep, _ = _scan({"source"}, monkeypatch, repo="owner/name", github_token="")
    row = rep["source"][0]
    assert row["code"] == "unavailable.source"
    assert row["severity"] == "info"
    assert "GitHub" in row["why"]


def test_catalog_states_availability(no_creds):
    cat = {t["key"]: t for t in server.tool_catalog()}
    assert cat["seo"]["available"] is True and cat["seo"]["unavailable_reason"] == ""
    assert cat["backlinks"]["available"] is False
    assert "DATAFORSEO_LOGIN" in cat["backlinks"]["unavailable_reason"]


def test_catalog_paid_available_with_credentials(real_creds):
    cat = {t["key"]: t for t in server.tool_catalog()}
    assert cat["backlinks"]["available"] is True


# ── composite cards surface the sub-call that did not run ────────────────────

def test_rankings_surfaces_a_skipped_sub_call(monkeypatch):
    def refusing_call(path, payload=None, **k):
        return None, "skipped: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD unset"

    rows, status, cost = dataforseo.rankings("x.com", ["roofing"], call=refusing_call)
    assert cost == 0
    assert any(r["code"] == "unavailable.rankings" for r in rows)
    assert "DATAFORSEO_LOGIN" in status


def test_keywords_card_without_project_keywords_says_so(monkeypatch):
    def ok_call(path, payload=None, **k):
        return {"cost": 0.0, "tasks": [{"result": [{"items": []}]}]}, None

    rows, status, _ = dataforseo.keywords_card("x.com", [], [], call=ok_call)
    reasons = [r["why"] for r in rows if r["code"] == "unavailable.keywords"]
    assert any("target keywords" in w for w in reasons)


# ── the free crawl and Site Health share the "site" group ────────────────────

def test_site_health_does_not_overwrite_the_free_crawl(real_creds, monkeypatch):
    """Both file under report["site"]. The run loop assigned `groups[t.key] =
    rows`, so selecting Site Health with a multi-page crawl on discarded every
    crawl finding. Found while wiring the unavailable row, 2026-09-14."""
    from pipeline.scanner import onpage_audit
    monkeypatch.setattr(onpage_audit, "site_audit_full", lambda d, mp: (
        [{"code": "dfs.op.is_orphan_page", "what": "Orphan page", "why": "w", "fix": "f",
          "severity": "warn"}], "ok", 0.006))
    pages = {
        "https://x.com/": '<html><head><title>H</title></head><body><a href="/b">b</a></body></html>',
        "https://x.com/b": '<html><head><title>B</title></head><body><a href="/gone">x</a></body></html>',
    }
    sitemap = "<urlset><url><loc>https://x.com/b</loc></url></urlset>"

    def fetch(u):
        return (pages.get(u, ""), 200 if u in pages else 404, "", sitemap)

    rep, _ = _scan({"seo", "site"}, monkeypatch, fetch=fetch, crawl_pages=3)
    codes = [r["code"] for r in rep["site"]]
    assert "dfs.op.is_orphan_page" in codes
    assert any(c.startswith("site.") for c in codes), codes


# ── review findings, 2026-09-14 ──────────────────────────────────────────────

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen_returning(body: dict):
    def fake(req, timeout=60):
        return _Resp(json.dumps(body).encode())
    return fake


def test_task_level_refusal_inside_http_200_is_an_error(real_creds, monkeypatch):
    """DataForSEO answers HTTP 200 and puts the refusal in the body. It was read
    as an empty result: rankings invented '"kw" — not in top 20' warns, AI
    citations invented 'not cited'. The account hit exactly this (40104) in
    August (docs/ADMIN-CHECKLIST.md)."""
    monkeypatch.setattr(dataforseo.urllib.request, "urlopen", _urlopen_returning(
        {"status_code": 20000, "cost": 0, "tasks": [
            {"status_code": 40104, "status_message": "Please verify your account before using the API.", "result": None}]}))
    doc, err = dataforseo.call("/v3/serp/google/organic/live/advanced", [{}])
    assert doc is None
    assert "40104" in err and "verify your account" in err


def test_top_level_refusal_is_an_error(real_creds, monkeypatch):
    monkeypatch.setattr(dataforseo.urllib.request, "urlopen", _urlopen_returning(
        {"status_code": 40200, "status_message": "Payment Required.", "tasks": None}))
    doc, err = dataforseo.call("/v3/backlinks/summary/live", [{}])
    assert doc is None and "40200" in err


def test_a_refused_card_invents_no_finding(real_creds, monkeypatch):
    monkeypatch.setattr(dataforseo.urllib.request, "urlopen", _urlopen_returning(
        {"status_code": 20000, "tasks": [{"status_code": 40501, "status_message": "Invalid Field", "result": None}]}))
    rows, status, _ = dataforseo.rankings("x.com", ["roofing"])
    assert [r["code"] for r in rows] == ["unavailable.rankings"]
    assert "40501" in status


def test_a_truncated_body_is_an_error_not_a_crash(real_creds, monkeypatch):
    import http.client

    def cut(req, timeout=60):
        class R(_Resp):
            def read(self, *a):
                raise http.client.IncompleteRead(b"{\"sta", 900)
        return R(b"")

    monkeypatch.setattr(dataforseo.urllib.request, "urlopen", cut)
    doc, err = dataforseo.call("/v3/x", [{}], sleep=lambda s: None)
    assert doc is None and "IncompleteRead" in err


def test_a_runtime_failure_names_itself_on_the_page(real_creds, monkeypatch):
    """Credentials pass availability(), then DataForSEO answers 401. The group
    came back [] and the page said 'Run a scan with the Backlinks tool enabled'."""
    monkeypatch.setattr(dataforseo, "backlinks", lambda d, call=None: ([], "HTTP 401 from DataForSEO", 0.0))
    rep, _ = _scan({"backlinks"}, monkeypatch)
    assert [r["code"] for r in rep["backlinks"]] == ["unavailable.backlinks"]
    assert "HTTP 401" in rep["backlinks"][0]["why"]


@pytest.mark.parametrize("value", ["1", " 1 ", "1  # keep paused", "true", "TRUE", "yes", "on"])
def test_the_kill_switch_does_not_fail_open(real_creds, monkeypatch, value):
    monkeypatch.setenv("DATAFORSEO_PAUSE_SPEND", value)
    assert dataforseo.availability()[0] is False


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_the_kill_switch_off_values_are_live(real_creds, monkeypatch, value):
    monkeypatch.setenv("DATAFORSEO_PAUSE_SPEND", value)
    assert dataforseo.availability() == (True, "")


def test_the_market_is_read_when_the_call_is_made(real_creds, monkeypatch):
    """wf-scan-web imports this module before main() loads .env, so a market set
    in .env was ignored and every lookup went out as 2840/en (B-076 again)."""
    sent = {}

    def spy(path, payload=None, **k):
        sent.update(payload[0])
        return {"cost": 0, "status_code": 20000, "tasks": [{"status_code": 20000, "result": [{"items": []}]}]}, None

    monkeypatch.setenv("DFS_LOCATION_CODE", "2116")
    monkeypatch.setenv("DFS_LANGUAGE_CODE", "km")
    dataforseo.domain_overview("x.com", call=spy)
    assert (sent["location_code"], sent["language_code"]) == (2116, "km")
    from pipeline.scanner import business_data, mentions
    business_data.gbp_local("Acme", call=spy)
    assert (sent["location_code"], sent["language_code"]) == (2116, "km")
    mentions.brand_mentions("Acme", call=spy)
    assert (sent["location_code"], sent["language_code"]) == (2116, "km")


def test_an_unreachable_page_keeps_paid_results_that_never_read_it(real_creds, monkeypatch):
    """A WAF 403 on our fetch rewrote every group to '<group>.not_measured',
    including backlinks already bought from DataForSEO, which never reads the
    page. The cost stayed; the result went."""
    monkeypatch.setattr(dataforseo, "backlinks", lambda d, call=None: (
        [{"code": "dfs.backlinks", "what": "12 backlinks", "why": "", "fix": "", "severity": "info"}], "ok", 0.02))
    rep, _ = _scan({"seo", "backlinks"}, monkeypatch, fetch=lambda u: ("", 403, "", None))
    assert rep["backlinks"][0]["code"] == "dfs.backlinks"
    assert rep["seo"][0]["code"].endswith(".not_measured")
