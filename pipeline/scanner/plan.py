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

    # RESOLVED = an actionable finding present last time, gone now.
    resolved = [r for code, r in prev_by_code.items()
                if r.get("severity") in _ACTIONABLE and code not in cur_by_code]

    worklist.sort(key=lambda w: (w["priority"], w.get("code", "")))
    for i, w in enumerate(worklist):
        w["priority"] = i + 1  # dense 1..N so the UI/tests get a clean order

    counts = {"NEW": 0, "PERSISTING": 0, "REGRESSION": 0, "RESOLVED": len(resolved)}
    for w in worklist:
        counts[w["status"]] += 1
    return {"worklist": worklist, "resolved": resolved, "counts": counts}
