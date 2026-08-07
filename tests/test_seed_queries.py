"""Offline tests for wf-seed-queries. Both pure functions, no network, no agent."""
import sys

import pipeline.audit.seed_queries as sq


# ── page_facts: the grounding ────────────────────────────────────────────────

def test_the_title_and_every_h1_come_back():
    html = ("<html><head><title>Rice Cake Cleanser | LEE SERIE</title></head>"
            "<body><h1>Rice Cake Cleanser</h1><h1>How To Use</h1></body></html>")
    title, h1s = sq.page_facts(html)
    assert title == "Rice Cake Cleanser | LEE SERIE"
    assert h1s == ["Rice Cake Cleanser", "How To Use"]


def test_tags_inside_an_h1_do_not_leak_into_the_text():
    """A styled h1 is the common case, not the exception. Without stripping,
    the grounding facts carry markup into the prompt."""
    _, h1s = sq.page_facts("<h1>Stretch <span>Marks</span> Set</h1>")
    assert h1s == ["Stretch Marks Set"]


def test_a_page_with_no_title_is_empty_not_an_exception():
    assert sq.page_facts("<html><body><p>hi</p></body></html>") == ("", [])


# ── parse_query_list: the validation ─────────────────────────────────────────

def test_numbering_and_bullets_are_stripped_off_the_agents_lines():
    """The CLI is told one query per line, but models number things anyway."""
    out = sq.parse_query_list("1. stretch mark cream\n- rice cake cleanser\n* sunscreen kh\n",
                              brand="LEE SERIE", limit=40)
    assert out == ["stretch mark cream", "rice cake cleanser", "sunscreen kh"]


def test_the_bare_brand_name_is_dropped_as_navigational():
    """You always rank #1 for your own name, so tracking it buys a permanently
    green finding at full price. The agent is told to drop these; this is the
    backstop for when it does not."""
    out = sq.parse_query_list("lee serie\nLEE SERIE\nstretch mark cream\n",
                              brand="LEE SERIE", limit=40)
    assert out == ["stretch mark cream"]


def test_the_brand_inside_a_longer_query_survives():
    """`lee serie` is navigational. `lee serie stretch mark cream review` is
    commercial and worth tracking - substring matching would kill both."""
    out = sq.parse_query_list("lee serie stretch mark cream review\n",
                              brand="LEE SERIE", limit=40)
    assert out == ["lee serie stretch mark cream review"]


def test_duplicates_collapse_case_insensitively_keeping_first_order():
    out = sq.parse_query_list("Rice Cake Cleanser\nrice cake cleanser\nsunscreen\n",
                              brand="X", limit=40)
    assert out == ["rice cake cleanser", "sunscreen"]


def test_prose_lines_are_not_queries():
    """Models preface lists. A sentence is not a search query."""
    out = sq.parse_query_list(
        "Here are the queries I generated based on the page titles:\n"
        "stretch mark cream\n", brand="X", limit=40)
    assert out == ["stretch mark cream"]


def test_the_limit_truncates_because_every_query_costs_money():
    out = sq.parse_query_list("\n".join(f"query {i}" for i in range(50)),
                              brand="X", limit=5)
    assert len(out) == 5


# ── gather_facts + build_prompt ──────────────────────────────────────────────

def test_only_pages_that_answered_become_facts(monkeypatch):
    """An unreachable page contributes nothing rather than an empty line -
    blank facts in the prompt read to the model as 'this page has no topic'."""
    pages = {"https://x.com/a/": "<title>Rice Cake Cleanser</title><h1>Cleanser</h1>",
             "https://x.com/b/": ""}
    monkeypatch.setattr(sq, "curl", lambda url, **kw: pages.get(url, ""))
    facts = sq.gather_facts({"domain": "x.com"}, list(pages))
    assert len(facts) == 1
    assert "Rice Cake Cleanser" in facts[0] and "/a/" in facts[0]


def test_the_prompt_carries_the_facts_the_brand_and_the_limit():
    prompt = sq.build_prompt(
        {"business": {"legal_name": "LEE SERIE"}, "domain": "x.com",
         "primary_metro": "Phnom Penh", "industry": "skincare"},
        ["/a/ - Rice Cake Cleanser"], limit=40)
    assert "Rice Cake Cleanser" in prompt
    assert "LEE SERIE" in prompt
    assert "Phnom Penh" in prompt
    assert "40" in prompt


def test_the_prompt_forbids_inventing_products():
    """Derivation only, never invention (CLAUDE.md). The grounding is worthless
    if the agent is free to expand past it."""
    prompt = sq.build_prompt({"business": {"legal_name": "X"}, "domain": "x.com"},
                             ["/a/ - Cleanser"], limit=10)
    assert "navigational" in prompt.lower()
    assert "do not invent" in prompt.lower()


# ── the CLI ──────────────────────────────────────────────────────────────────

def _stub_run(monkeypatch, **over):
    """The whole CLI with the network and the agent stubbed out."""
    monkeypatch.setattr(sq.shutil, "which", over.get("which", lambda n: "/usr/bin/claude"))
    monkeypatch.setattr(sq, "load_config", over.get(
        "load_config",
        lambda d: {"domain": "x.com", "business": {"legal_name": "LEE SERIE"}}))
    monkeypatch.setattr(sq, "discover_urls",
                        lambda cfg, args, limit=None: ["https://x.com/a/"])
    monkeypatch.setattr(sq, "curl", over.get("curl", lambda url, **kw: "<title>T</title>"))
    monkeypatch.setattr(sq, "run_agent", over.get("run_agent", lambda p, m, t: (True, "")))
    monkeypatch.setattr(sys, "argv", ["wf-seed-queries", "--project", "."])


def test_the_command_prints_a_pasteable_yaml_block(monkeypatch, capsys):
    """End to end with the network and the agent stubbed. B-007: a green unit
    test on parse_query_list proves the parser works, not that main calls it."""
    _stub_run(monkeypatch, run_agent=lambda p, m, t: (
        True, "lee serie\nrice cake cleanser\nbest cleanser kh\n"))
    assert sq.main() == 0
    out = capsys.readouterr().out
    assert "seed_queries:" in out
    assert "  - rice cake cleanser" in out
    assert "  - lee serie\n" not in out      # the brand was dropped as navigational


def test_no_page_answered_is_a_named_refusal(monkeypatch, capsys):
    """Exit 19, matching measure.py's Unreachable. A run that measured nothing
    must be red, never an empty list that reads as 'this site has no topics'."""
    _stub_run(monkeypatch, curl=lambda url, **kw: "")
    assert sq.main() == 19
    assert "no page answered" in capsys.readouterr().err.lower()


def test_an_agent_that_returns_nothing_usable_is_exit_20(monkeypatch, capsys):
    _stub_run(monkeypatch, run_agent=lambda p, m, t: (True, "Here are your queries:\n"))
    assert sq.main() == 20
    assert "no usable quer" in capsys.readouterr().err.lower()


def test_an_agent_that_failed_is_exit_20_with_its_output(monkeypatch, capsys):
    _stub_run(monkeypatch, run_agent=lambda p, m, t: (False, "timed out after 600s"))
    assert sq.main() == 20
    assert "timed out" in capsys.readouterr().err


def test_no_claude_on_path_refuses_before_crawling(monkeypatch, capsys):
    """Crawling 40 pages and then discovering there is no writer wastes the
    operator's time and the client's bandwidth."""
    crawled = []
    _stub_run(monkeypatch, which=lambda n: None,
              curl=lambda url, **kw: crawled.append(url) or "<title>T</title>")
    assert sq.main() == 2
    assert "claude" in capsys.readouterr().err.lower()
    assert crawled == []
