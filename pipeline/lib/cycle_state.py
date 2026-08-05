"""Shared cycle state — so whoever is online can run the pipeline without redoing
work the other person already did.

**The problem.** Alex and Robin both drive this pipeline and never see each
other's screens. The ingest ledger (`.drive-intake-state.json`) only stops a
*file* being downloaded twice, and it lives in a CI cache or on one laptop. There
was nothing recording that a *step* — distill, emit, gates, ship — had already
been done, by whom, and when. So the second person to sit down either repeats
work or, worse, guesses.

**The mechanism is git.** State lives in the CLIENT repo at
`docs/cycle-logs/<cycle>/cycle-state.json`, alongside that cycle's post-mortem.
Pull before you start (the `CLAUDE.md` rule) and you have the other side's
progress. Push when you finish and they have yours. No server, no service, no
extra credential — the thing both of you already do is the sync.

**Why the client repo and not here.** Model A: the client repo is that client's
single source of truth. It is also the only place that survives a cache eviction,
a new laptop, or a runner being torn down.

Every step records **who** ran it and **when**. Re-running a completed step is a
no-op that says who already did it, unless explicitly forced.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

STATE_FILE = "cycle-state.json"
SCHEMA_VERSION = 1

# The cycle, in order. A step may be skipped, but the order is how `next_step`
# decides what to do, and how `render` shows progress.
STEPS: list[tuple[str, str]] = [
    ("intake",   "Retrieve this cycle's team content (Drive folder or shared link)"),
    ("distill",  "DOCX to structured content"),
    ("classify", "Decide per page: new, update, or skip"),
    ("emit",     "Write typed data files into the client repo"),
    ("gates",    "Run the quality suite against a real build"),
    ("pr",       "Open the pull request"),
    ("merged",   "Alex merged it"),
    ("deployed", "Deployed to production"),
    ("verified", "Live-verified: 200s, content present, no orphans"),
]
STEP_NAMES = [s for s, _ in STEPS]

PENDING, RUNNING, DONE, SKIPPED, FAILED = "pending", "running", "done", "skipped", "failed"


def actor() -> str:
    """Who is running this. git identity first — it is what both sides already set."""
    for cmd in (["git", "config", "user.name"], ["git", "config", "user.email"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout.strip()
            if out:
                return out
        except Exception:
            pass
    return os.environ.get("USER") or os.environ.get("GITHUB_ACTOR") or "unknown"


def state_path(repo: Path, cycle: str) -> Path:
    return repo / "docs" / "cycle-logs" / cycle / STATE_FILE


@dataclass
class CycleState:
    repo: Path
    client: str
    cycle: str
    data: dict

    # ── load / save ──

    @classmethod
    def load(cls, repo: Path, client: str, cycle: str) -> "CycleState":
        p = state_path(repo, cycle)
        if p.is_file():
            try:
                return cls(repo, client, cycle, json.loads(p.read_text()))
            except Exception:
                print(f"WARN: {p} is unreadable — starting a fresh cycle state. "
                      f"The old file is left in place; do not overwrite it blindly.")
        return cls(repo, client, cycle, {
            "version": SCHEMA_VERSION, "client": client, "cycle": cycle,
            "steps": {name: {"status": PENDING} for name in STEP_NAMES},
        })

    def save(self) -> Path:
        p = state_path(self.repo, self.cycle)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.data, indent=2, sort_keys=True) + "\n")
        return p

    # ── query ──

    def step(self, name: str) -> dict:
        return self.data.setdefault("steps", {}).setdefault(name, {"status": PENDING})

    def is_done(self, name: str) -> bool:
        return self.step(name)["status"] in (DONE, SKIPPED)

    def next_step(self) -> str | None:
        """First step not yet done. None means the cycle is complete."""
        for name in STEP_NAMES:
            if not self.is_done(name):
                return name
        return None

    def claim(self, name: str, force: bool = False) -> tuple[bool, str]:
        """Should I run this step? Returns (go_ahead, reason).

        This is the whole point: if the other person already did it, say so and
        do not repeat the work.
        """
        s = self.step(name)
        if s["status"] in (DONE, SKIPPED) and not force:
            return False, (f"already {s['status']} by {s.get('by', '?')} "
                           f"on {(s.get('at') or '?')[:16]} — {s.get('detail', '')}".rstrip(" -"))
        if s["status"] == RUNNING and not force:
            return False, (f"another run claimed this at {(s.get('at') or '?')[:16]} "
                           f"({s.get('by', '?')}). Use --force if that run died.")
        return True, "not done yet"

    # ── record ──

    def mark(self, name: str, status: str, detail: str = "", at: str = "") -> "CycleState":
        self.data.setdefault("steps", {})[name] = {
            "status": status, "by": actor(), "at": at, "detail": detail,
        }
        return self

    # ── display ──

    def render(self) -> str:
        icon = {DONE: "✅", SKIPPED: "⏭️ ", RUNNING: "⏳", FAILED: "❌", PENDING: "⬜"}
        lines = [f"{self.client} — cycle {self.cycle}", ""]
        for name, desc in STEPS:
            s = self.step(name)
            who = f"  ({s.get('by')}, {(s.get('at') or '')[:16]})" if s.get("by") else ""
            detail = f"  {s['detail']}" if s.get("detail") else ""
            lines.append(f"  {icon.get(s['status'], '⬜')} {name:9} {desc}{who}{detail}")
        nxt = self.next_step()
        lines += ["", f"NEXT: {nxt}" if nxt else "CYCLE COMPLETE — nothing left to run."]
        return "\n".join(lines)
