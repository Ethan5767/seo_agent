"""Backlink Overview: parsers against DataForSEO sandbox responses (free sample
data in the live shape, fetched 2026-09-15), and the tool's wiring and cost."""
import datetime
import json
from pathlib import Path

from pipeline.scanner import dataforseo, server

FIX = Path(__file__).parent / "fixtures"
load = lambda name: json.loads((FIX / f"dfs_backlinks_{name}.json").read_text())


def test_summary_row_carries_the_link_profile():
    rows = dataforseo.parse_backlinks(load("summary"))
    main = next(r for r in rows if r["code"] == "dfs.backlinks")
    m = main["metrics"]
    raw = load("summary")["tasks"][0]["result"][0]
    assert m["backlinks"] == raw["backlinks"] and m["referring_domains"] == raw["referring_domains"]
    assert m["referring_domains_nofollow"] == raw["referring_domains_nofollow"]
    assert m["types"][0] == {"label": "image", "value": raw["referring_links_types"]["image"]}
    assert all(c["label"] for c in m["countries"]), "the blank country key is dropped"
    assert len(m["tld"]) <= 8 and m["tld"] == sorted(m["tld"], key=lambda x: -x["value"])


def test_referring_domains_anchors_and_history_parse():
    rd = dataforseo.parse_referring_domains(load("referring_domains"))
    item = load("referring_domains")["tasks"][0]["result"][0]["items"][0]
    assert rd[0]["code"] == "dfs.referring_domain" and rd[0]["what"] == item["domain"]
    assert rd[0]["metrics"]["backlinks"] == item["backlinks"]
    assert f"spam {item['backlinks_spam_score']}" in rd[0]["detail"]

    an = dataforseo.parse_anchors(load("anchors"))
    a0 = load("anchors")["tasks"][0]["result"][0]["items"][0]
    assert an[0]["what"] == f'"{a0["anchor"]}"' and an[0]["metrics"]["referring_domains"] == a0["referring_domains"]

    hist = dataforseo.parse_backlink_history(load("history"))
    assert len(hist) == 1 and hist[0]["code"] == "dfs.backlink_history"
    pts = hist[0]["metrics"]["points"]
    assert len(pts) == 14 and pts == sorted(pts, key=lambda p: p["date"])
    assert set(pts[0]) >= {"date", "backlinks", "referring_domains", "new_referring_domains", "lost_referring_domains"}


def test_the_tool_makes_four_calls_sums_their_cost_and_names_failures():
    docs = {"summary": load("summary"), "referring_domains": load("referring_domains"),
            "anchors": load("anchors"), "history": load("history")}
    calls = []

    def fake(path, payload):
        calls.append((path, payload[0]))
        key = path.split("/")[3]
        if key == "history":
            return None, "error: HTTP 500"
        doc = dict(docs[key]); doc["cost"] = 0.02
        return doc, None

    rows, status, cost = dataforseo.backlink_overview("https://www.Example.com/", call=fake, today=datetime.date(2026, 9, 15))
    assert [c[0].split("/")[3] for c in calls] == ["summary", "referring_domains", "anchors", "history"]
    assert all(p["target"] == "example.com" for _, p in calls)
    assert calls[3][1]["date_from"].startswith("2025-09")
    assert cost == 0.06
    assert any(r["code"] == "unavailable.backlink_overview" for r in rows)
    assert "not run" in status


def test_wired_and_priced():
    tool = next(t for t in server.TOOLS if t.key == "backlink_overview")
    assert tool.group == "dataforseo" and tool.cost_num == 0.08
    budget = (Path(server.__file__).parents[2] / "web" / "lib" / "budget.ts").read_text()
    assert "backlink_overview: 0.08" in budget
