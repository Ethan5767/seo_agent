"""Offline tests for wf-seed-queries. Pure functions plus a stubbed CLI; no
network, no agent, no `claude` on PATH required."""
import json
import subprocess
import sys

import pytest

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


# ── brand_names: the navigational drop ───────────────────────────────────────

def test_the_trade_name_counts_as_the_brand_not_just_the_legal_name():
    """The motivating case. `legal_name` carries an entity suffix; the query
    people actually type is the trade name in nap.name. Reading only
    business.legal_name makes the drop silently do nothing on real configs."""
    names = sq.brand_names({"business": {"legal_name": "Lee Serie Co., Ltd."},
                            "nap": {"name": "LEE SERIE"}})
    assert "lee serie" in names
    assert "lee serie co., ltd." in names


def test_the_slug_is_a_brand_spelling_too():
    assert "acme roofing" in sq.brand_names({"client_slug": "acme-roofing"})


def test_a_config_with_no_name_anywhere_yields_no_brands_not_a_blank_one():
    """A blank brand in the set would match every empty line."""
    assert sq.brand_names({}) == set()


# ── parse_reply: the validation ──────────────────────────────────────────────

def test_a_json_array_becomes_the_query_list():
    out, dropped = sq.parse_reply('["Stretch Mark Cream", "rice cake cleanser"]',
                                  brands=set(), limit=40)
    assert out == ["stretch mark cream", "rice cake cleanser"]
    assert dropped == []


def test_a_fenced_array_still_parses():
    """Models fence JSON however firmly you ask them not to."""
    out, _ = sq.parse_reply('```json\n["stretch mark cream"]\n```', set(), 40)
    assert out == ["stretch mark cream"]


def test_the_bare_brand_name_is_dropped_and_the_drop_is_reported():
    """You always rank #1 for your own name, so tracking it buys a permanently
    green finding at full price. The agent is told to drop these; this is the
    backstop, and it says so rather than deleting silently."""
    out, dropped = sq.parse_reply('["lee serie", "stretch mark cream"]',
                                  brands={"lee serie"}, limit=40)
    assert out == ["stretch mark cream"]
    assert any("navigational" in d for d in dropped)


def test_the_brand_inside_a_longer_query_survives():
    """`lee serie` is navigational. `lee serie stretch mark cream review` is
    commercial and worth tracking - substring matching would kill both."""
    out, _ = sq.parse_reply('["lee serie stretch mark cream review"]',
                            brands={"lee serie"}, limit=40)
    assert out == ["lee serie stretch mark cream review"]


def test_a_long_people_also_ask_question_survives():
    """The recipe asks for PAA questions and they run to a dozen words. The
    line-oriented draft deleted these with a >10-word 'that is prose' rule -
    the highest-intent queries thrown away by the filter meant to protect them."""
    q = "how long does it take for stretch mark cream to work on old marks"
    out, _ = sq.parse_reply(json.dumps([q]), set(), 40)
    assert out == [q]


def test_duplicates_collapse_case_insensitively_keeping_first_order():
    out, dropped = sq.parse_reply('["Rice Cake Cleanser", "rice cake cleanser", "sunscreen"]',
                                  set(), 40)
    assert out == ["rice cake cleanser", "sunscreen"]
    assert any("duplicate" in d for d in dropped)


def test_prose_is_not_a_partial_guess_it_is_nothing():
    """The reply is either a JSON array or it is unusable. Recovering 'some' of
    a malformed reply pastes invented text into a config that fingerprints it
    forever; main turns the empty list into a loud exit 20 instead."""
    out, _ = sq.parse_reply("Here are the queries I generated:\nstretch mark cream\n",
                            set(), 40)
    assert out == []


def test_a_json_object_is_not_a_query_list():
    out, _ = sq.parse_reply('{"queries": ["stretch mark cream"]}', set(), 40)
    assert out == []


def test_non_string_entries_are_dropped_and_named():
    out, dropped = sq.parse_reply('["stretch mark cream", 42, null]', set(), 40)
    assert out == ["stretch mark cream"]
    assert any("not a string" in d for d in dropped)


def test_the_limit_truncates_because_every_query_costs_money():
    out, dropped = sq.parse_reply(json.dumps([f"query {i}" for i in range(50)]),
                                  set(), limit=5)
    assert len(out) == 5
    assert any("past --limit 5" in d for d in dropped)


# ── unwrap_envelope ──────────────────────────────────────────────────────────

def test_the_envelope_yields_its_result_field():
    ok, text = sq.unwrap_envelope(json.dumps(
        {"type": "result", "result": '["a"]', "is_error": False, "subtype": "success"}))
    assert (ok, text) == (True, '["a"]')


def test_an_envelope_flagged_is_error_is_a_failure_despite_exit_zero():
    """remediate.py:291 checks all three for this reason: a claude run can exit
    0 and still have failed."""
    ok, _ = sq.unwrap_envelope(json.dumps(
        {"result": "rate limited", "is_error": True}))
    assert ok is False


def test_a_non_envelope_stdout_is_passed_through_not_discarded():
    """If the CLI changes shape, degrade to the old behaviour rather than
    reporting a confident empty list."""
    assert sq.unwrap_envelope('["a"]') == (True, '["a"]')


# ── the agent's authority ────────────────────────────────────────────────────

def test_the_agent_gets_websearch_and_no_write_tools(monkeypatch):
    """The one safety property this module claims. CLAUDE.md: what keeps agent
    authorship safe is not the prompt. Without this assertion someone can add
    Write/Edit/Bash or --permission-mode acceptEdits and every other test in
    this file stays green while the command gains write authority inside a
    client checkout."""
    seen = {}

    class FakeProc:
        returncode = 0

        def communicate(self, prompt, timeout=None):
            return '{"result": "[]"}', ""

    def fake_popen(argv, **kw):
        seen["argv"] = argv
        seen["kw"] = kw
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    sq.run_agent("prompt", "sonnet", 60)

    argv = seen["argv"]
    assert "--allowedTools" in argv
    assert argv[argv.index("--allowedTools") + 1] == "WebSearch"
    for forbidden in ("Write", "Edit", "Bash", "--permission-mode", "--add-dir",
                      "--dangerously-skip-permissions"):
        assert forbidden not in argv, f"{forbidden} must never reach the seed-query agent"
    # Merged stderr would put CLI warnings inside the payload we json.loads.
    assert seen["kw"]["stderr"] is subprocess.PIPE


def test_a_nonzero_exit_reports_stderr_not_a_clean_empty_list(monkeypatch):
    class FakeProc:
        returncode = 1

        def communicate(self, prompt, timeout=None):
            return "", "not logged in"

    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: FakeProc())
    ok, text = sq.run_agent("p", "sonnet", 60)
    assert ok is False and "not logged in" in text


# ── gather_facts + build_prompt ──────────────────────────────────────────────

def test_only_pages_that_answered_become_facts(monkeypatch):
    """An unreachable page contributes nothing rather than an empty line -
    blank facts in the prompt read to the model as 'this page has no topic'."""
    pages = {"https://x.com/a/": "<title>Rice Cake Cleanser</title><h1>Cleanser</h1>",
             "https://x.com/b/": ""}
    monkeypatch.setattr(sq, "curl", lambda url, **kw: pages.get(url, ""))
    facts = sq.gather_facts(list(pages))
    assert len(facts) == 1
    assert "Rice Cake Cleanser" in facts[0] and "/a/" in facts[0]


def test_a_page_with_an_h1_but_no_title_has_no_double_separator(monkeypatch):
    monkeypatch.setattr(sq, "curl", lambda url, **kw: "<h1>Rice Cake Cleanser</h1>")
    assert sq.gather_facts(["https://x.com/products/"]) == \
        ["/products/ - Rice Cake Cleanser"]


def test_the_prompt_carries_the_facts_the_brand_and_the_limit():
    prompt = sq.build_prompt(
        {"business": {"legal_name": "LEE SERIE"}, "domain": "x.com",
         "primary_metro": "Phnom Penh", "industry": "skincare"},
        ["/a/ - Rice Cake Cleanser"], limit=40)
    assert "Rice Cake Cleanser" in prompt
    assert "lee serie" in prompt.lower()
    assert "Phnom Penh" in prompt
    assert "at most 40 queries" in prompt


def test_the_prompt_asks_for_json_and_forbids_inventing_products():
    """Derivation only, never invention (CLAUDE.md). The grounding is worthless
    if the agent is free to expand past it."""
    prompt = sq.build_prompt({"business": {"legal_name": "X"}, "domain": "x.com"},
                             ["/a/ - Cleanser"], limit=10)
    assert "navigational" in prompt.lower()
    assert "do not invent" in prompt.lower()
    assert "JSON array" in prompt


# ── the CLI ──────────────────────────────────────────────────────────────────

def _stub_run(monkeypatch, argv=("wf-seed-queries", "--project", "."), **over):
    """The whole CLI with the network and the agent stubbed out."""
    monkeypatch.setattr(sq.shutil, "which", over.get("which", lambda n: "/usr/bin/claude"))
    monkeypatch.setattr(sq, "load_config", over.get(
        "load_config",
        lambda d: {"domain": "x.com", "business": {"legal_name": "LEE SERIE"}}))
    monkeypatch.setattr(sq, "urls_or_refuse", over.get(
        "urls_or_refuse", lambda cfg, a, limit: (["https://x.com/a/"], 0)))
    monkeypatch.setattr(sq, "curl", over.get("curl", lambda url, **kw: "<title>T</title>"))
    monkeypatch.setattr(sq, "run_agent", over.get("run_agent", lambda p, m, t: (True, "[]")))
    monkeypatch.setattr(sys, "argv", list(argv))


def test_the_command_prints_a_pasteable_yaml_block(monkeypatch, capsys):
    """End to end with the network and the agent stubbed. B-007: a green unit
    test on parse_reply proves the parser works, not that main calls it."""
    _stub_run(monkeypatch, run_agent=lambda p, m, t: (
        True, '["lee serie", "rice cake cleanser", "best cleanser kh"]'))
    assert sq.main() == 0
    out = capsys.readouterr().out
    assert "seed_queries:" in out
    assert "  - rice cake cleanser" in out
    assert "  - lee serie\n" not in out      # the brand was dropped as navigational


def test_the_crawl_max_and_limit_flags_reach_the_code_that_uses_them(monkeypatch, capsys):
    """Otherwise either flag can be replaced with a constant and nothing fails."""
    seen = {}

    def spy_urls(cfg, a, limit):
        seen["crawl_max"] = limit
        return ["https://x.com/a/"], 0

    _stub_run(monkeypatch,
              argv=("wf-seed-queries", "--crawl-max", "7", "--limit", "2"),
              urls_or_refuse=spy_urls,
              run_agent=lambda p, m, t: (True, '["a q", "b q", "c q"]'))
    assert sq.main() == 0
    assert seen["crawl_max"] == 7
    assert capsys.readouterr().out.count("  - ") == 2


def test_an_unreachable_sitemap_is_the_refusal_measure_py_already_defines(monkeypatch):
    """discover_urls raises; borrowing it bare turned the most likely first-run
    failure into a traceback and exit 1."""
    _stub_run(monkeypatch, urls_or_refuse=lambda cfg, a, limit: ([], 19))
    assert sq.main() == 19


def test_no_page_answered_is_a_named_refusal(monkeypatch, capsys):
    """Exit 19. A run that measured nothing must be red, never an empty list
    that reads as 'this site has no topics'."""
    _stub_run(monkeypatch, curl=lambda url, **kw: "")
    assert sq.main() == 19
    assert "no page answered" in capsys.readouterr().err.lower()


def test_an_agent_that_returns_prose_is_exit_20_with_the_raw_reply(monkeypatch, capsys):
    _stub_run(monkeypatch, run_agent=lambda p, m, t: (True, "Here are your queries:"))
    assert sq.main() == 20
    err = capsys.readouterr().err
    assert "no usable quer" in err.lower()
    assert "Here are your queries:" in err


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


# ── write_seed_queries: the config-editing seam ──────────────────────────────

def test_write_seed_queries_appends_a_new_block_when_the_key_is_absent(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("domain: example.com\ntier: 1\n")
    code = sq.write_seed_queries(target, ["Top AI agency in Cambodia"])
    assert code == 0
    text = target.read_text()
    assert "seed_queries:" in text
    assert "  - Top AI agency in Cambodia" in text
    assert "domain: example.com" in text
    assert "tier: 1" in text


def test_write_seed_queries_can_write_twice_in_a_row(tmp_path):
    """The blocker the review caught: the first write's own output (a trailing
    comment on the seed_queries: line) must be re-parseable by the second."""
    target = tmp_path / "client-config.yml"
    target.write_text("tier: 1\n")
    assert sq.write_seed_queries(target, ["first term"]) == 0
    assert sq.write_seed_queries(target, ["second term"]) == 0
    text = target.read_text()
    assert "  - first term" in text
    assert "  - second term" in text
    assert text.index("- first term") < text.index("- second term")


def test_write_seed_queries_appends_to_an_existing_block(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("seed_queries:\n  - existing term\ntier: 1\n")
    code = sq.write_seed_queries(target, ["new term"])
    assert code == 0
    text = target.read_text()
    assert text.index("- existing term") < text.index("- new term")
    assert text.count("tier: 1") == 1


def test_write_seed_queries_dedupes_case_insensitively(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("seed_queries:\n  - Existing Term\n")
    code = sq.write_seed_queries(target, ["existing term"])
    assert code == 0
    assert target.read_text().count("  - ") == 1


def test_write_seed_queries_collapses_internal_whitespace(tmp_path):
    """Finding.context (baseline.py) normalizes whitespace before fingerprinting
    a SERP finding's query. Storing the raw double-spaced text here would make
    a stored term never match its own finding — collapse on write instead."""
    target = tmp_path / "client-config.yml"
    target.write_text("tier: 1\n")
    code = sq.write_seed_queries(target, ["  top   ai  agency  "])
    assert code == 0
    assert "  - top ai agency\n" in target.read_text()


def test_write_seed_queries_refuses_a_flow_style_list(tmp_path):
    target = tmp_path / "client-config.yml"
    original = "seed_queries: [already, here]\n"
    target.write_text(original)
    code = sq.write_seed_queries(target, ["new term"])
    assert code == 4
    assert target.read_text() == original


def test_write_seed_queries_rejects_blank_input(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("tier: 1\n")
    code = sq.write_seed_queries(target, ["   ", ""])
    assert code == 4
    assert target.read_text() == "tier: 1\n"


def test_write_seed_queries_inserts_right_after_the_last_existing_item_even_with_a_trailing_key(tmp_path):
    target = tmp_path / "client-config.yml"
    target.write_text("seed_queries:\n  - one\n  - two\ntier: 1\n")
    code = sq.write_seed_queries(target, ["three"])
    assert code == 0
    text = target.read_text()
    assert text == "seed_queries:\n  - one\n  - two\n  - three\ntier: 1\n"


# ── --write on the CLI: exit 4 (not 2) when the config is missing ────────────

def test_write_flag_on_a_missing_config_exits_4(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv",
        ["wf-seed-queries", "--project", str(tmp_path), "--write", "a term"])
    assert sq.main() == 4
