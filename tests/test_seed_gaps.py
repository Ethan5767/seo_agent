"""parse_gaps turns the measure agent's gaps.json rows into Gap objects. A
malformed row (missing/blank field) is dropped WITH a reason, never silently —
same discipline as the providers' loud skips: a silent drop would make a run
look complete when it seeded fewer gaps than it was handed."""
from __future__ import annotations

from pipeline.seed.gaps import parse_gaps, Gap, REQUIRED

GOOD = {
    "brand": "Acme",
    "platform": "devto",
    "topic": "best widget for teams",
    "target_keyword": "team widget",
    "angle": "compare on setup speed",
    "url_target": "https://acme.com/widget",
}


def test_parses_a_good_row():
    gaps, dropped = parse_gaps([GOOD])
    assert dropped == []
    assert gaps == [Gap(brand="Acme", platform="devto",
                        topic="best widget for teams",
                        target_keyword="team widget",
                        angle="compare on setup speed",
                        url_target="https://acme.com/widget")]


def test_drops_row_missing_field_with_reason():
    bad = {k: v for k, v in GOOD.items() if k != "url_target"}
    gaps, dropped = parse_gaps([bad])
    assert gaps == []
    assert len(dropped) == 1
    assert "url_target" in dropped[0]["_reason"]


def test_drops_row_with_blank_field():
    bad = {**GOOD, "brand": "   "}
    gaps, dropped = parse_gaps([bad])
    assert gaps == []
    assert "brand" in dropped[0]["_reason"]


def test_mixed_batch_keeps_good_drops_bad():
    bad = {**GOOD, "platform": ""}
    gaps, dropped = parse_gaps([GOOD, bad, GOOD])
    assert len(gaps) == 2
    assert len(dropped) == 1


def test_required_fields_frozen():
    assert REQUIRED == ("brand", "platform", "topic",
                        "target_keyword", "angle", "url_target")


def test_optional_subreddit_carried_when_present():
    row = {**GOOD, "platform": "reddit", "subreddit": "smallbusiness"}
    gaps, dropped = parse_gaps([row])
    assert dropped == []
    assert gaps[0].subreddit == "smallbusiness"


def test_subreddit_defaults_empty_when_absent():
    gaps, _ = parse_gaps([GOOD])
    assert gaps[0].subreddit == ""
