"""Plan stage — classify findings vs the previous scan into a priority worklist."""
from pipeline.scanner.plan import build_plan, classify


def f(code, sev, what="w", fix="do it", tool="t"):
    return {"code": code, "severity": sev, "what": what, "fix": fix, "tool": tool}


def test_classify_statuses():
    assert classify(f("a", "error"), None) == "NEW"
    assert classify(f("a", "error"), f("a", "error")) == "PERSISTING"
    assert classify(f("a", "error"), f("a", "warn")) == "REGRESSION"   # got worse
    # improvement (error -> warn) is still an open item, not a regression
    assert classify(f("a", "warn"), f("a", "error")) == "PERSISTING"


def test_build_plan_orders_and_buckets():
    current = [f("e_new", "error"), f("e_keep", "error"), f("w_new", "warn"),
               f("reg", "error"), f("passing", "ok"), f("noteworthy", "info")]
    previous = [f("e_keep", "error"), f("reg", "warn"), f("gone", "error")]
    out = build_plan(current, previous)
    codes = [w["code"] for w in out["worklist"]]
    # ok/info excluded from the worklist
    assert "passing" not in codes and "noteworthy" not in codes
    # NEW-error and REGRESSION come before PERSISTING-error, before NEW-warn
    assert codes.index("e_new") < codes.index("e_keep")
    assert codes.index("reg") < codes.index("e_keep")
    assert codes.index("e_keep") < codes.index("w_new")
    # statuses attached
    by = {w["code"]: w for w in out["worklist"]}
    assert by["e_new"]["status"] == "NEW"
    assert by["e_keep"]["status"] == "PERSISTING"
    assert by["reg"]["status"] == "REGRESSION"
    # RESOLVED = in previous, gone from current → a win, not a worklist item
    assert [r["code"] for r in out["resolved"]] == ["gone"]
    assert out["counts"]["NEW"] == 2 and out["counts"]["REGRESSION"] == 1
    assert out["counts"]["RESOLVED"] == 1


def test_empty_previous_all_new():
    out = build_plan([f("a", "error"), f("b", "warn"), f("c", "ok")], [])
    assert {w["status"] for w in out["worklist"]} == {"NEW"}
    assert len(out["worklist"]) == 2  # ok excluded
    assert out["resolved"] == []


def test_priority_is_stable_int():
    out = build_plan([f("a", "error"), f("b", "warn")], [])
    prios = [w["priority"] for w in out["worklist"]]
    assert prios == sorted(prios) and all(isinstance(p, int) for p in prios)


def test_duplicate_code_deduped_to_worst():
    out = build_plan([f("a", "warn"), f("a", "error")], [])
    codes = [w["code"] for w in out["worklist"]]
    assert codes.count("a") == 1               # not double-counted
    assert out["worklist"][0]["severity"] == "error"  # worst severity kept


def test_codeless_findings_excluded():
    out = build_plan([f("", "error"), f("a", "error")], [])
    assert [w["code"] for w in out["worklist"]] == ["a"]  # codeless can't ratchet


def test_plan_endpoint_helper_shape():
    from pipeline.scanner.server import handle_plan
    out = handle_plan({"current": [f("a", "error")], "previous": []})
    assert set(out) == {"worklist", "resolved", "counts"}
    assert out["worklist"][0]["status"] == "NEW"


def test_plan_endpoint_helper_defaults_bad_input():
    from pipeline.scanner.server import handle_plan
    out = handle_plan({})  # no lists → empty, no crash
    assert out["worklist"] == [] and out["resolved"] == []
