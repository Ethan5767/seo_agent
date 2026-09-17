"""Remediate stage (web MVP) — the bridge from Plan to fixes.

Plan produces a prioritised worklist. Remediate answers, for each item: *what
kind of fix is this, and can the Model-B code agent do it, or does a human?* The
classification is deterministic from the finding's stable `code` prefix — no
LLM, no network, no cost — so it's fully unit-testable and defensible.

Lanes and who fixes them:
  code      On-page & source code   — page tags + repo files the agent edits   (auto)
  perf      Performance             — CWV / Lighthouse, code + config           (auto)
  config    Config & crawlability   — robots.txt / crawler access              (auto)
  content   Content & authoring     — real writing (depth, stats, answers)     (manual)
  strategy  Off-page & strategy     — rankings/keywords/backlinks, off the page (manual)

`auto` is a property of the lane: the three code/config lanes are what a
tier-bounded agent can safely change inside the client repo; content and
strategy need a person. Unknown codes fall to `strategy`/manual — we never claim
we can auto-fix something we don't recognise.
"""
from __future__ import annotations

# (key, label, auto-fixable-by-agent, effort)
_LANES = {
    "code":     ("On-page & source code", True,  "moderate"),
    "perf":     ("Performance",           True,  "moderate"),
    "config":   ("Config & crawlability", True,  "quick"),
    "content":  ("Content & authoring",   False, "deep"),
    "strategy": ("Off-page & strategy",   False, "deep"),
}
_LANE_ORDER = ["code", "perf", "config", "content", "strategy"]

# Codes that look like code (`health.*`) but are really authoring, not a tag edit.
_CONTENT_HEALTH = {"health.thin_content"}
# AEO content signals (authoring) vs AEO crawl config (an edit).
_CONTENT_AEO = {"aeo.statistics", "aeo.citations", "aeo.data_tables", "aeo.no_answer_structure"}


def classify_fix(code: str) -> tuple[str, str, bool, str]:
    """(lane_key, lane_label, auto, effort) for a finding code. Deterministic."""
    c = code or ""
    lane = _lane_key(c)
    label, auto, effort = _LANES[lane]
    return lane, label, auto, effort


def _lane_key(c: str) -> str:
    if c in _CONTENT_HEALTH or c in _CONTENT_AEO:
        return "content"
    if c.startswith("src."):
        return "code"
    if c.startswith("crux") or c.startswith("lh.perf") or "perf" in c:
        return "perf"
    if c.startswith("health.") or c.startswith("lh."):
        return "code"          # page tags, metadata, on-page audits — repo edits
    if c.startswith("aeo.robots") or c == "aeo.crawler_blocked" or c == "aeo.robots_missing":
        return "config"
    if c.startswith("aeo."):
        return "content"       # remaining AEO signals are authoring
    if c.startswith("content.") or c.startswith("video"):
        return "content"
    if c.startswith("dfs.") or c.startswith("rank") or c.startswith("kw") or c.startswith("keyword"):
        return "strategy"
    return "strategy"          # unknown → manual, never a false auto-fix claim


def build_remediation(worklist: list[dict]) -> dict:
    """Enrich each worklist item with lane/auto/effort, group into lanes ordered
    by their most-urgent item, and count auto vs manual. `worklist` is Plan's
    output (already priority-sorted); order is preserved in `steps`."""
    steps: list[dict] = []
    for r in worklist or []:
        lane, label, auto, effort = classify_fix(r.get("code", ""))
        steps.append({**r, "lane": lane, "lane_label": label, "auto": auto, "effort": effort})

    counts = {"total": len(steps), "auto": 0, "manual": 0, "error": 0, "warn": 0}
    for s in steps:
        counts["auto" if s["auto"] else "manual"] += 1
        sev = s.get("severity")
        if sev in ("error", "warn"):
            counts[sev] += 1

    # Group into lanes; a lane's rank is its best (lowest) item priority so the
    # most urgent lane leads.
    grouped: dict[str, list[dict]] = {}
    for s in steps:
        grouped.setdefault(s["lane"], []).append(s)

    def _best(items: list[dict]) -> int:
        return min((i.get("priority", 1_000_000) for i in items), default=1_000_000)

    lanes = []
    for key in sorted(grouped, key=lambda k: (_best(grouped[k]), _LANE_ORDER.index(k))):
        label, auto, _effort = _LANES[key]
        lanes.append({"key": key, "label": label, "auto": auto,
                      "items": sorted(grouped[key], key=lambda i: i.get("priority", 0))})

    return {"steps": steps, "lanes": lanes, "counts": counts}
