"""Platform tiers — the safety rule as data. Green auto-posts, yellow is queued
for human approval, red is never automated (Wikipedia: COI/paid-editing policy,
permanent public history). Unknown platforms are NOT green on purpose: a typo or
new platform must fall through to a loud skip, never to auto-posting.

Reddit is green (operator opted into auto-posting for brand-mention reach), but
carries a real shadowban risk on fresh accounts — the poster keeps its own
draft-first gate (`--live` posts to the account's own profile, `--publish` to a
real subreddit) so a run can be proven before it touches a community."""
from __future__ import annotations

GREEN = ["medium", "devto", "hashnode", "tumblr", "blogger", "reddit"]
YELLOW = ["quora"]
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
