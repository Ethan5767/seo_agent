"""Backlink Gap: sites that link to a competitor but not to you.

Built 2026-09-14 on DataForSEO `backlinks/domain_intersection/live` with the
project's competitors as `targets` and the project's own domain in
`exclude_targets`. The fixture is the real response for the hospital against
royalphnompenhhospital.com (limit 5, $0.02418, total_count 338).
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.scanner import dataforseo, server

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "dfs_backlinks_domain_intersection.json").read_text())


def test_bare_domain_strips_scheme_www_path_and_case():
    assert dataforseo.bare_domain("https://www.RoyalPhnomPenhHospital.com/en?x=1") == "royalphnompenhhospital.com"
    assert dataforseo.bare_domain("royalphnompenhhospital.com") == "royalphnompenhhospital.com"
    assert dataforseo.bare_domain("") == ""


def test_parse_real_response_into_opportunities():
    rows = dataforseo.parse_backlink_gap(FIXTURE, ["royalphnompenhhospital.com"])
    summary = [r for r in rows if r["code"] == "dfs.backlink_gap_summary"]
    gaps = [r for r in rows if r["code"] == "dfs.backlink_gap"]
    assert summary and "338" in summary[0]["what"]
    assert [r["what"] for r in gaps][:2] == ["bdms.co.th", "edi-cambodia.org"]   # highest rank first
    bdms = gaps[0]
    assert "rank 311" in bdms["detail"] and "11 links" in bdms["detail"]
    assert "royalphnompenhhospital.com" in bdms["why"]


def test_high_spam_domains_are_flagged_not_recommended():
    rows = dataforseo.parse_backlink_gap(FIXTURE, ["royalphnompenhhospital.com"])
    flgg = next(r for r in rows if r["what"] == "flgg.cc")
    assert "spam 30" in flgg["detail"]


def test_request_sends_competitors_as_targets_and_you_as_excluded():
    sent = {}

    def spy(path, payload=None, **k):
        sent["path"], sent["body"] = path, payload[0]
        return FIXTURE, None

    rows, status, cost = dataforseo.backlink_gap(
        "www.oriendainternationalhospital.com.kh", ["https://royalphnompenhhospital.com/"], call=spy)
    assert sent["path"] == "/v3/backlinks/domain_intersection/live"
    assert sent["body"]["targets"] == {"1": "royalphnompenhhospital.com"}
    assert sent["body"]["exclude_targets"] == ["oriendainternationalhospital.com.kh"]
    assert cost == 0.0242
    assert "338" in status


def test_no_competitor_is_named_not_silent():
    def boom(*a, **k):
        raise AssertionError("must not call without a competitor")

    rows, status, cost = dataforseo.backlink_gap("x.com", [], call=boom, discover=False)
    assert [r["code"] for r in rows] == ["unavailable.backlink_gap"]
    assert "competitor" in rows[0]["why"]
    assert cost == 0


def test_competitors_are_discovered_when_the_project_has_none():
    calls = []

    def fake(path, payload=None, **k):
        calls.append(path)
        if "competitors_domain" in path:
            return {"cost": 0.01, "status_code": 20000, "tasks": [{"status_code": 20000, "result": [{"items": [
                {"domain": "x.com"}, {"domain": "rival.com"}, {"domain": "other.com"}]}]}]}, None
        return FIXTURE, None

    rows, status, cost = dataforseo.backlink_gap("x.com", [], call=fake)
    assert calls[0].endswith("competitors_domain/live") and calls[1].endswith("domain_intersection/live")
    assert cost == round(0.01 + 0.02418, 4)
    assert "rival.com" in status


def test_the_tool_is_registered_as_paid_and_mirrored_in_the_web_budget():
    tool = next(t for t in server.TOOLS if t.key == "backlink_gap")
    assert tool.group == "dataforseo" and tool.category == "Links"
    budget = (Path(__file__).parents[1] / "web" / "lib" / "budget.ts").read_text()
    assert "backlink_gap: 0.025" in budget
