"""Generation is a claude CLI subprocess behind an injectable `run` seam, so the
suite is fully offline. build_prompt and parse_result are pure; parse_result must
survive both bare JSON and the ```json fenced form the model sometimes emits."""
from __future__ import annotations

import json

import pytest

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import build_prompt, parse_result, draft, Draft

GAP = Gap(brand="Acme", platform="devto", topic="best widget for remote teams",
          target_keyword="remote team widget", angle="compare on setup speed",
          url_target="https://acme.com/widget")

INNER = {"title": "5 Widgets for Remote Teams",
         "body": "# Widgets\nAcme is a solid pick...",
         "brand_mention": "Acme (https://acme.com/widget) sets up in minutes."}


def _claude_stdout(inner: dict, fenced: bool = False) -> str:
    text = json.dumps(inner)
    if fenced:
        text = f"```json\n{text}\n```"
    return json.dumps({"type": "result", "subtype": "success",
                       "is_error": False, "result": text})


def test_build_prompt_includes_gap_facts():
    p = build_prompt(GAP)
    for needle in ("Acme", "devto", "remote team widget",
                   "https://acme.com/widget", "compare on setup speed"):
        assert needle in p
    # must instruct JSON-only output with the three keys
    assert "title" in p and "body" in p and "brand_mention" in p


def test_parse_result_bare_json():
    d = parse_result(_claude_stdout(INNER))
    assert d == INNER


def test_parse_result_fenced_json():
    d = parse_result(_claude_stdout(INNER, fenced=True))
    assert d == INNER


def test_parse_result_bad_input_raises():
    with pytest.raises(ValueError):
        parse_result("not json at all")


def test_draft_uses_injected_runner():
    calls = []

    def fake_run(prompt: str) -> str:
        calls.append(prompt)
        return _claude_stdout(INNER)

    d = draft(GAP, run=fake_run)
    assert isinstance(d, Draft)
    assert d.title == INNER["title"]
    assert d.body == INNER["body"]
    assert d.brand_mention == INNER["brand_mention"]
    assert d.gap is GAP
    assert "Acme" in calls[0]  # the runner got the built prompt
