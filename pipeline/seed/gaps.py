"""Parse the measure agent's gaps.json into Gap objects. Pure: takes an
already-loaded list of dicts (run.py owns the file read). A row missing any
required field, or carrying a blank one, is dropped WITH a reason so the run log
can show exactly what the agent handed us that we could not use."""
from __future__ import annotations

from dataclasses import dataclass

REQUIRED = ("brand", "platform", "topic", "target_keyword", "angle", "url_target")


@dataclass
class Gap:
    brand: str
    platform: str
    topic: str
    target_keyword: str
    angle: str
    url_target: str


def parse_gaps(rows: list[dict]) -> tuple[list[Gap], list[dict]]:
    gaps: list[Gap] = []
    dropped: list[dict] = []
    for row in rows:
        missing = [f for f in REQUIRED
                   if not str(row.get(f, "")).strip()]
        if missing:
            dropped.append({**row, "_reason": f"missing/blank: {', '.join(missing)}"})
            continue
        gaps.append(Gap(**{f: str(row[f]).strip() for f in REQUIRED}))
    return gaps, dropped
