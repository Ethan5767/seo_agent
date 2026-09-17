"""Compare Domains reads the competitors the operator names (and only then
discovers), and Domain Overview no longer carries competitor rows."""
from pathlib import Path

from pipeline.scanner import dataforseo, server


def _overview(count, etv):
    return {"status_code": 20000, "cost": 0.0101, "tasks": [{"status_code": 20000, "result": [{"items": [
        {"metrics": {"organic": {"count": count, "etv": etv, "pos_1": 1}, "paid": {}}}]}]}]}


def _fake(overviews, discovered=()):
    calls = []

    def call(path, payload):
        calls.append((path, payload[0].get("target")))
        if "competitors_domain" in path:
            items = [{"domain": d} for d in discovered]
            return {"status_code": 20000, "cost": 0.0107, "tasks": [{"status_code": 20000, "result": [{"items": items}]}]}, None
        return _overview(*overviews[payload[0]["target"]]), None
    return call, calls


def test_named_competitors_are_the_ones_compared_and_nothing_is_discovered():
    call, calls = _fake({"you.com": (120, 900), "rival.com": (300, 4000)})
    rows, status, cost = dataforseo.compare_domains("https://www.you.com/", ["https://www.Rival.com/x", "you.com", ""], call=call)
    assert [p for p, _ in calls if "competitors_domain" in p] == []
    assert [r["domain"] for r in rows] == ["you.com", "rival.com"]
    assert all(r["code"] == "dfs.compare_domain" for r in rows)
    assert "competitor" not in rows[0] and rows[1]["competitor"] == "rival.com"
    assert rows[0]["what"].startswith("you.com (you): ")
    assert cost == round(0.0101 * 2, 4)


def test_with_none_named_the_top_discovered_competitors_are_used_capped_at_three():
    call, _ = _fake({d: (10, 10) for d in ["you.com", "a.com", "b.com", "c.com"]},
                    discovered=["you.com", "a.com", "b.com", "c.com", "d.com"])
    rows, status, cost = dataforseo.compare_domains("you.com", [], call=call)
    assert [r["domain"] for r in rows] == ["you.com", "a.com", "b.com", "c.com"]


def test_no_competitors_at_all_is_said_not_hidden():
    call, _ = _fake({"you.com": (10, 10)}, discovered=[])
    rows, status, cost = dataforseo.compare_domains("you.com", None, call=call)
    assert any(r["code"] == "unavailable.compare" for r in rows)
    assert "found none" in status


def test_rankings_is_wired_without_competitors_and_compare_is_a_priced_tool():
    src = Path(server.__file__).read_text()
    assert "dataforseo.rankings(c.domain, c.keywords))" in src
    assert "competitors=c.competitors" not in src
    tool = next(t for t in server.TOOLS if t.key == "compare")
    assert tool.group == "dataforseo" and tool.cost_num == 0.05
    budget = (Path(server.__file__).parents[2] / "web" / "lib" / "budget.ts").read_text()
    assert "compare: 0.05" in budget
