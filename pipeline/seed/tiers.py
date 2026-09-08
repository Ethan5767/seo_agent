"""Platform tiers — the safety rule as data. Green auto-posts, yellow is queued
for human approval, red is never automated (Wikipedia: COI/paid-editing policy,
permanent public history). Unknown platforms are NOT green on purpose: a typo or
new platform must fall through to a loud skip, never to auto-posting."""
from __future__ import annotations

GREEN = ["medium", "devto", "hashnode", "tumblr", "blogger"]
YELLOW = ["reddit", "quora"]
RED = ["wikipedia"]


def tier_of(platform: str) -> str:
    p = (platform or "").strip().lower()
    if p in GREEN:
        return "green"
    if p in YELLOW:
        return "yellow"
    if p in RED:
        return "red"
    return "unknown"
