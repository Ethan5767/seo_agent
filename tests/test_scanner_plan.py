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


def test_a_passing_row_resolves_last_month_s_finding():
    """A check that now passes emits its own code with severity "ok"
    (`audit._pass_row`). The old rule was "gone from the report", so the pass row
    kept the finding alive: the code WAS in the current scan, so it counted as
    neither resolved nor as a work item, and it silently fell out of both lists.
    """
    out = build_plan([f("a", "ok")], [f("a", "error")])
    assert [r["code"] for r in out["resolved"]] == ["a"]
    assert out["counts"]["RESOLVED"] == 1
    assert out["worklist"] == []          # an "ok" row is never a work item


def test_an_absent_finding_still_resolves():
    """The weaker inference stays for the codes that have no pass row, but only
    when the finding's tool ran this scan (B-121): here tool "t" produced "b"."""
    out = build_plan([f("b", "ok")], [f("a", "error")])
    assert [r["code"] for r in out["resolved"]] == ["a"]


def test_a_still_failing_finding_is_not_resolved():
    out = build_plan([f("a", "error")], [f("a", "error")])
    assert out["resolved"] == []
    assert out["worklist"][0]["status"] == "PERSISTING"


# ── B-121: a tool that did not run cannot resolve its findings ────────────────

def _f(code, sev, tool, what="x"):
    return {"code": code, "severity": sev, "tool": tool, "what": what, "fix": "f"}


def test_a_finding_whose_tool_did_not_run_stays_open():
    previous = [_f("dfs.broken_backlinks", "warn", "Backlinks (DataForSEO)", "89 broken backlinks")]
    current = [_f("unavailable.backlinks", "info", "Backlinks (DataForSEO)"),
               _f("health.title_missing", "ok", "On-page SEO")]
    plan = build_plan(current, previous)
    assert plan["counts"]["RESOLVED"] == 0
    carried = [w for w in plan["worklist"] if w["code"] == "dfs.broken_backlinks"]
    assert carried and carried[0]["status"] == "PERSISTING"
    assert "not re-checked" in carried[0]["note"]


def test_a_tool_left_out_of_a_section_scan_does_not_resolve_either():
    previous = [_f("dfs.broken_backlinks", "warn", "Backlinks (DataForSEO)")]
    current = [_f("tech.https", "ok", "Technical")]
    plan = build_plan(current, previous)
    assert plan["counts"]["RESOLVED"] == 0
    assert any(w["code"] == "dfs.broken_backlinks" for w in plan["worklist"])


def test_a_tool_that_ran_and_no_longer_finds_it_resolves():
    previous = [_f("dfs.broken_backlinks", "warn", "Backlinks (DataForSEO)")]
    current = [_f("dfs.backlinks", "info", "Backlinks (DataForSEO)")]
    plan = build_plan(current, previous)
    assert [r["code"] for r in plan["resolved"]] == ["dfs.broken_backlinks"]
    assert not any(w["code"] == "dfs.broken_backlinks" for w in plan["worklist"])


def test_a_pass_row_is_proof_whatever_the_tool_field_says():
    previous = [_f("health.title_missing", "error", "On-page SEO")]
    current = [_f("health.title_missing", "ok", "")]
    assert build_plan(current, previous)["counts"]["RESOLVED"] == 1


def test_rows_without_a_tool_keep_the_old_absence_rule():
    previous = [{"code": "tech.https", "severity": "error", "what": "x", "fix": "f"}]
    assert build_plan([], previous)["counts"]["RESOLVED"] == 1
