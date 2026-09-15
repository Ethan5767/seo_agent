"""Plan stage — the ratchet. Compare this scan's findings to the previous scan
and turn them into a prioritised worklist.

Pure: `build_plan(current, previous)` takes two lists of finding rows (each with
at least `code`, `severity`, `what`, `fix`, `tool`) and returns
`{"worklist": [...], "resolved": [...], "counts": {...}}`. Findings are matched
by their stable `code`, so the same issue lines up across scans.

Statuses:
  NEW         in current, not in previous
  PERSISTING  in both, severity unchanged (or improved but still open)
  REGRESSION  in both, severity got worse (e.g. warn -> error)
  RESOLVED    in previous, gone from current (a win, not a worklist item)

`ok`/`info` rows are signals, not action items, so they never enter the worklist.
"""
from __future__ import annotations

SEV_RANK = {"error": 2, "warn": 1, "info": 0, "ok": 0}
_ACTIONABLE = ("error", "warn")

# Lower priority number = do it first.
_STATUS_RANK = {"NEW": 0, "REGRESSION": 0, "PERSISTING": 1}


def classify(cur: dict, prev: dict | None) -> str:
    if prev is None:
        return "NEW"
    if SEV_RANK.get(cur.get("severity"), 0) > SEV_RANK.get(prev.get("severity"), 0):
        return "REGRESSION"
    return "PERSISTING"


def _priority(status: str, severity: str) -> int:
    # severity dominates (all errors before warns), then NEW/REGRESSION before
    # PERSISTING: NEW-error/regression → PERSISTING-error → NEW-warn → PERSISTING-warn
    return (2 - SEV_RANK.get(severity, 0)) * 10 + _STATUS_RANK.get(status, 2)


def _by_code(rows: list[dict]) -> dict:
    """Index findings by their stable code, keeping the worst severity if a code
    repeats within one scan. Codeless rows are dropped — they can't be ratcheted
    (nothing stable to match across scans)."""
    by: dict = {}
    for r in rows or []:
        code = r.get("code")
        if not code:
            continue
        if code not in by or SEV_RANK.get(r.get("severity"), 0) > SEV_RANK.get(by[code].get("severity"), 0):
            by[code] = r
    return by


def build_plan(current: list[dict], previous: list[dict]) -> dict:
    cur_by_code = _by_code(current)
    prev_by_code = _by_code(previous)

    worklist: list[dict] = []
    for code, r in cur_by_code.items():
        if r.get("severity") not in _ACTIONABLE:
            continue
        status = classify(r, prev_by_code.get(code))
        worklist.append({**r, "status": status,
                         "priority": _priority(status, r.get("severity"))})

    # RESOLVED = an actionable finding last time that is no longer actionable.
    #
    # "gone from the report" is not the same as "fixed": a tool that did not run
    # this month also produces no row. Since a check that passes now emits its
    # own code with severity "ok" (`audit._pass_row`), a present-but-ok row is
    # positive proof of a fix, and absence is the weaker inference we still
    # accept for the codes that have no pass row.
    #
    # B-121: absence only counts when the tool that produces the finding RAN in
    # this scan. A tool that was paused, over budget, errored or simply left out
    # of a section scan files nothing, and its findings used to be counted as
    # fixed and dropped from the worklist. Such findings stay open, marked.
    ran = {r.get("tool") for r in (current or [])
           if r.get("tool") and not str(r.get("code") or "").startswith("unavailable.")}
    resolved = []
    for code, r in prev_by_code.items():
        if r.get("severity") not in _ACTIONABLE:
            continue
        now = cur_by_code.get(code)
        if now is not None:
            if now.get("severity") not in _ACTIONABLE:
                resolved.append(r)          # checked again and passing: proof
            continue
        tool = r.get("tool")
        if not tool or tool in ran:
            resolved.append(r)              # its tool ran and no longer finds it
            continue
        status = "PERSISTING"
        worklist.append({**r, "status": status, "priority": _priority(status, r.get("severity")),
                         "note": f"not re-checked in this scan: {tool} did not run"})

    worklist.sort(key=lambda w: (w["priority"], w.get("code", "")))
    for i, w in enumerate(worklist):
        w["priority"] = i + 1  # dense 1..N so the UI/tests get a clean order

    counts = {"NEW": 0, "PERSISTING": 0, "REGRESSION": 0, "RESOLVED": len(resolved)}
    for w in worklist:
        counts[w["status"]] += 1
    return {"worklist": worklist, "resolved": resolved, "counts": counts}
