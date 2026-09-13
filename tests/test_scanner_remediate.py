"""Remediate stage (web MVP) — turn the prioritised worklist into an actionable
remediation guide: each item classified into a fix lane, marked auto-fixable by
the Model-B code agent or manual, grouped and ordered. Pure, offline, no cost."""
from pipeline.scanner.remediate import build_remediation, classify_fix


def w(code, sev="warn", pri=1, status="NEW", fix="do it", what="thing", pages=None):
    r = {"code": code, "severity": sev, "priority": pri, "status": status,
         "fix": fix, "what": what}
    if pages is not None:
        r["pages"] = pages
    return r


def test_classify_fix_lanes_and_auto():
    # source code + on-page tags live in the repo → the agent can fix them
    assert classify_fix("src.metadata_missing")[0] == "code"
    assert classify_fix("src.metadata_missing")[2] is True
    assert classify_fix("health.title_missing")[2] is True         # page <title>/metadata
    # thin content is authoring, not a code edit → manual even though health.*
    assert classify_fix("health.thin_content")[0] == "content"
    assert classify_fix("health.thin_content")[2] is False
    # performance → code/config, agent-fixable
    assert classify_fix("crux.lcp")[0] == "perf"
    assert classify_fix("lh.perf.uses_webp")[0] == "perf"
    assert classify_fix("crux.lcp")[2] is True
    # robots / crawler access → a config edit the agent can make
    assert classify_fix("aeo.crawler_blocked")[0] == "config"
    assert classify_fix("aeo.crawler_blocked")[2] is True
    # GEO/answer content → human authoring
    assert classify_fix("aeo.statistics")[0] == "content"
    assert classify_fix("aeo.statistics")[2] is False
    assert classify_fix("content.depth")[2] is False
    # off-page / search data → strategy, never a code fix
    assert classify_fix("dfs.rank.dropped")[0] == "strategy"
    assert classify_fix("dfs.rank.dropped")[2] is False
    # unknown code → manual by default (never claim we can auto-fix the unknown)
    assert classify_fix("weird.thing")[2] is False


def test_build_remediation_groups_and_counts():
    worklist = [
        w("health.title_missing", "error", 1),
        w("src.next_config", "error", 2),
        w("aeo.statistics", "warn", 3),
        w("content.depth", "warn", 4),
        w("dfs.rank.dropped", "warn", 5),
    ]
    out = build_remediation(worklist)
    # steps preserve the incoming priority order and gain lane/auto/effort
    assert [s["priority"] for s in out["steps"]] == [1, 2, 3, 4, 5]
    assert all("lane" in s and "auto" in s and "effort" in s for s in out["steps"])
    # counts: 2 auto (title, src) vs 3 manual
    assert out["counts"]["total"] == 5
    assert out["counts"]["auto"] == 2
    assert out["counts"]["manual"] == 3
    assert out["counts"]["error"] == 2 and out["counts"]["warn"] == 3
    # lanes grouped, each with its auto flag and items
    lanes = {l["key"]: l for l in out["lanes"]}
    assert set(lanes) == {"code", "content", "strategy"}
    assert lanes["code"]["auto"] is True
    assert lanes["content"]["auto"] is False
    assert {i["code"] for i in lanes["code"]["items"]} == {"health.title_missing", "src.next_config"}


def test_lanes_ordered_by_best_priority():
    # a lane whose best (lowest-priority-number) item is more urgent comes first
    worklist = [
        w("content.depth", "warn", 1),          # content lane best = 1
        w("src.a", "error", 2),                 # code lane best = 2
    ]
    out = build_remediation(worklist)
    assert [l["key"] for l in out["lanes"]] == ["content", "code"]


def test_effort_assigned_per_lane():
    out = build_remediation([w("aeo.crawler_blocked", "warn", 1),
                             w("content.depth", "warn", 2)])
    by = {s["code"]: s for s in out["steps"]}
    # config edits are quick; authoring is deep
    assert by["aeo.crawler_blocked"]["effort"] == "quick"
    assert by["content.depth"]["effort"] == "deep"


def test_empty_worklist():
    out = build_remediation([])
    assert out["steps"] == [] and out["lanes"] == []
    assert out["counts"] == {"total": 0, "auto": 0, "manual": 0, "error": 0, "warn": 0}
