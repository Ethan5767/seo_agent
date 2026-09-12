"""content.py — tier-1 / tier-2 outreach drafts via the `claude` CLI.

Same mechanism as pipeline/seed/generate: shell out to `claude` on the operator's
subscription (no API key, no per-token cost). build_prompt is pure; the
subprocess is injected as `run` so the draft can be exercised offline.

Tier 1 = basic natural LSI keyword variations and standard topical alignment.
Tier 2 = localized / professional copy: regional phrasing, cultural references,
richer LSI clusters. Both are held to the same house rules the gates enforce on
client copy: derive, never invent; Title Case headings; no em dashes.
"""
from __future__ import annotations

import subprocess

_TIER_NOTE = {
    1: ("Tier 1: use basic, natural LSI keyword variations and standard topical "
        "alignment. Keep it simple and readable."),
    2: ("Tier 2: write localized, professional copy — regional phrasing, cultural "
        "references where apt, and richer LSI keyword clusters."),
}


def build_prompt(domain: str, tier: int, topics: list) -> str:
    note = _TIER_NOTE.get(tier or 1, _TIER_NOTE[1])
    topic_line = ", ".join(topics) if topics else "the client's core services"
    return (
        f"Write a short guest-article outreach pitch and a ~150-word body snippet "
        f"suitable for earning a backlink on {domain}. Target topics: {topic_line}. "
        f"{note} "
        f"Ground every statement — invent no facts, statistics, ratings, prices, or "
        f"credentials. Use Title Case for any heading and do not use em dashes."
    )


def _run_claude(prompt: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:200]}")
    return proc.stdout.strip()


def draft(domain: str, tier: int = 1, topics: list | None = None, run=None) -> str:
    """Outreach draft text for one domain. Raises RuntimeError if claude fails."""
    run = run or _run_claude
    return run(build_prompt(domain, tier or 1, topics or []))
