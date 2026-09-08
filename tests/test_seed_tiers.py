"""Tier membership is the safety rule in code: green auto-posts, yellow queues,
red never, unknown is skipped loudly. A platform silently defaulting to green
would auto-post somewhere we never vetted — so unknown must NOT be green."""
from __future__ import annotations

from pipeline.seed.tiers import tier_of, GREEN, YELLOW, RED


def test_green_platforms():
    for p in ("medium", "devto", "hashnode", "tumblr", "blogger"):
        assert tier_of(p) == "green"


def test_yellow_platforms():
    for p in ("reddit", "quora"):
        assert tier_of(p) == "yellow"


def test_red_platform():
    assert tier_of("wikipedia") == "red"


def test_case_insensitive():
    assert tier_of("DevTo") == "green"
    assert tier_of("Reddit") == "yellow"


def test_unknown_is_not_green():
    assert tier_of("mastodon") == "unknown"
    assert tier_of("") == "unknown"


def test_tier_lists_are_disjoint():
    assert set(GREEN) & set(YELLOW) == set()
    assert set(GREEN) & set(RED) == set()
    assert set(YELLOW) & set(RED) == set()
