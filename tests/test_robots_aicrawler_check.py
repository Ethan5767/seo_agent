"""Tests for the static AI-crawler robots.txt gate.

This gate had none. It is one of the two things standing between a client and
being invisible to AI answers, and its whole verdict rests on a hand-rolled
robots.txt parser — group boundaries, wildcard-vs-specific precedence, and
Allow-beats-Disallow-on-a-tie — none of which was covered anywhere.

The classification is as load-bearing as the parsing. A crawler in the wrong
class produces a verdict that is wrong in BOTH directions: `ChatGPT-User` sat in
the citation list, so a "blocked" verdict told a client they were shut out of
ChatGPT when OpenAI's own docs say robots.txt may not apply to that bot, and a
"pass" promised a control they do not have.
"""
from __future__ import annotations

import io
import contextlib
from pathlib import Path

import pytest

from pipeline.gates import robots_aicrawler_check as gate
from pipeline.gates.robots_aicrawler_check import (
    DEFAULT_CITATION_UAS, DEFAULT_TRAINING_UAS, DEFAULT_USER_TRIGGERED_UAS,
    ROBOTS_HONOURING_USER_UAS, parse_groups, resolve_ua_lists, root_blocked,
    rules_for_ua,
)


def run(tmp_path: Path, robots: str | None, argv_extra=(), env=None, monkeypatch=None):
    """Run the gate over a build dir. `robots=None` writes no robots.txt."""
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    if robots is not None:
        (out / "robots.txt").write_text(robots)
    if env and monkeypatch:
        for k, v in env.items():
            monkeypatch.setenv(k, v)
    argv = ["wf-robots-aicrawler-check", "--out", str(out), *argv_extra]
    if monkeypatch:
        monkeypatch.setattr("sys.argv", argv)
    else:  # pragma: no cover - every caller passes monkeypatch
        raise AssertionError("monkeypatch required")
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = gate.main()
    return code, buf.getvalue()


ALLOW_ALL = "User-agent: *\nAllow: /\n"


# ── the verdict ──────────────────────────────────────────────────────────────

def test_an_allow_all_robots_passes(tmp_path, monkeypatch):
    code, out = run(tmp_path, ALLOW_ALL, monkeypatch=monkeypatch)
    assert code == 0
    assert "PASS: robots.txt allows every citation crawler at root" in out


def test_a_missing_robots_is_red_with_a_paste_ready_fix(tmp_path, monkeypatch):
    # An implicit default-allow is not the same as a declared policy, and the
    # remedy has to be copyable or nobody applies it.
    code, out = run(tmp_path, None, monkeypatch=monkeypatch)
    assert code == 1
    assert "robots.txt MISSING" in out
    assert "User-agent: OAI-SearchBot\n    Allow: /" in out
    assert "User-agent: GPTBot\n    Disallow: /" in out


def test_a_blanket_disallow_blocks_every_citation_crawler(tmp_path, monkeypatch):
    code, out = run(tmp_path, "User-agent: *\nDisallow: /\n", monkeypatch=monkeypatch)
    assert code == 1
    assert out.count("RED  [") == len(DEFAULT_CITATION_UAS)
    assert "citation crawler(s) Disallowed" in out


def test_one_blocked_citation_crawler_is_enough_to_fail(tmp_path, monkeypatch):
    code, out = run(tmp_path, ALLOW_ALL + "\nUser-agent: PerplexityBot\nDisallow: /\n",
                    monkeypatch=monkeypatch)
    assert code == 1
    assert "RED  [PerplexityBot]" in out
    assert "PASS [Googlebot]" in out


def test_blocking_a_subdirectory_is_not_the_aeo_zeroing_case(tmp_path, monkeypatch):
    # `Disallow: /admin` is ordinary hygiene. Failing on it would make the gate
    # noise, and an operator who learns to ignore a gate has no gate.
    code, _ = run(tmp_path, "User-agent: *\nDisallow: /admin\nDisallow: /cart\n",
                  monkeypatch=monkeypatch)
    assert code == 0


def test_blocking_training_crawlers_is_a_choice_not_a_failure(tmp_path, monkeypatch):
    robots = ALLOW_ALL + "".join(f"\nUser-agent: {ua}\nDisallow: /\n" for ua in DEFAULT_TRAINING_UAS)
    code, out = run(tmp_path, robots, monkeypatch=monkeypatch)
    assert code == 0, "opting out of model training must never red a client's PR"
    assert "INFO [GPTBot] Disallowed" in out


# ── the parser the verdict rests on ──────────────────────────────────────────

def test_consecutive_user_agent_lines_share_one_group():
    groups = parse_groups("User-agent: A\nUser-agent: B\nDisallow: /\n")
    assert len(groups) == 1
    assert groups[0][0] == ["a", "b"]


def test_a_new_group_starts_at_the_first_agent_after_a_rule():
    groups = parse_groups("User-agent: A\nDisallow: /\nUser-agent: B\nAllow: /\n")
    assert [g[0] for g in groups] == [["a"], ["b"]]


def test_comments_and_unknown_directives_are_ignored():
    groups = parse_groups("# lead\nUser-agent: A  # trailing\nCrawl-delay: 10\nSitemap: x\nDisallow: /\n")
    assert groups == [(["a"], [("disallow", "/")])]


def test_a_specific_group_beats_the_wildcard():
    groups = parse_groups("User-agent: *\nDisallow: /\nUser-agent: Googlebot\nAllow: /\n")
    rules, specific = rules_for_ua(groups, "Googlebot")
    assert specific is True
    assert root_blocked(rules) is False


def test_no_matching_group_at_all_is_default_allow():
    rules, specific = rules_for_ua(parse_groups("User-agent: Bingbot\nDisallow: /\n"), "PerplexityBot")
    assert (rules, specific) == (None, False)
    assert root_blocked(None) is False


def test_allow_wins_a_tie_with_disallow():
    # Google's own resolution order. Getting this backwards would fail sites
    # whose robots.txt is correct.
    assert root_blocked([("disallow", "/"), ("allow", "/")]) is False


def test_an_empty_disallow_means_allow_all():
    assert root_blocked([("disallow", "")]) is False


def test_matching_is_case_insensitive():
    groups = parse_groups("User-agent: googlebot\nDisallow: /\n")
    rules, specific = rules_for_ua(groups, "Googlebot")
    assert specific is True and root_blocked(rules) is True


# ── classification: which list a bot lands in IS the verdict ─────────────────

def test_the_three_classes_do_not_overlap():
    cit, trn, usr = (set(DEFAULT_CITATION_UAS), set(DEFAULT_TRAINING_UAS),
                     set(DEFAULT_USER_TRIGGERED_UAS) | set(ROBOTS_HONOURING_USER_UAS))
    assert cit & trn == set()
    assert cit & usr == set(), "a user-triggered fetcher graded as a citation crawler is wrong twice"
    assert trn & usr == set()


def test_chatgpt_user_is_not_graded_as_a_citation_crawler():
    # OpenAI documents that robots.txt rules may not apply to it. Grading it told
    # clients they were shut out of ChatGPT when they were not.
    assert "ChatGPT-User" not in DEFAULT_CITATION_UAS
    assert "ChatGPT-User" in DEFAULT_USER_TRIGGERED_UAS


def test_every_major_vendor_has_a_citation_bot_in_the_gating_list():
    for vendor in ("OAI-SearchBot", "PerplexityBot", "Googlebot", "Bingbot",
                   "Claude-SearchBot", "Applebot", "Amzn-SearchBot", "meta-webindexer"):
        assert vendor in DEFAULT_CITATION_UAS, f"{vendor} is ungated, so a block on it is invisible"


def test_user_triggered_fetchers_are_reported_and_never_gated(tmp_path, monkeypatch):
    robots = ALLOW_ALL + "".join(
        f"\nUser-agent: {ua}\nDisallow: /\n" for ua in DEFAULT_USER_TRIGGERED_UAS)
    code, out = run(tmp_path, robots, monkeypatch=monkeypatch)
    assert code == 0
    assert "user-triggered fetchers (INFO only, never gate)" in out
    for ua in DEFAULT_USER_TRIGGERED_UAS:
        assert f"INFO [{ua}] Disallowed" in out
        assert "robots.txt may not apply" in out


def test_the_one_fetcher_that_honours_robots_is_labelled_differently(tmp_path, monkeypatch):
    code, out = run(tmp_path, "User-agent: Claude-User\nDisallow: /\n", monkeypatch=monkeypatch)
    assert code == 0
    line = next(l for l in out.splitlines() if "[Claude-User]" in l)
    assert "Disallowed" in line
    assert "honours robots.txt, so this directive is real" in line


# ── UA lists resolve without a code edit ─────────────────────────────────────

def test_env_overrides_beat_the_defaults(monkeypatch):
    monkeypatch.setenv("CITATION_UAS", "NewSearchBot, OtherBot")
    monkeypatch.setenv("TRAINING_UAS", "NewTrainBot")
    monkeypatch.setenv("USER_TRIGGERED_UAS", "NewUserBot")
    cit, trn, usr = resolve_ua_lists(None, None)
    assert cit == ["NewSearchBot", "OtherBot"] and trn == ["NewTrainBot"] and usr == ["NewUserBot"]


def test_config_supplies_the_lists_when_env_does_not(tmp_path, monkeypatch):
    monkeypatch.delenv("CITATION_UAS", raising=False)
    monkeypatch.delenv("USER_TRIGGERED_UAS", raising=False)
    docs = tmp_path / "docs"; docs.mkdir()
    (docs / "client-config.yml").write_text(
        "ai_crawlers:\n  citation_uas: [ConfigBot]\n  user_triggered_uas: [ConfigUserBot]\n")
    cit, trn, usr = resolve_ua_lists(str(tmp_path), None)
    assert cit == ["ConfigBot"]
    assert usr == ["ConfigUserBot"]
    assert trn == list(DEFAULT_TRAINING_UAS), "an absent key must fall through, not blank the list"


@pytest.mark.parametrize("body", ["", "not: [a mapping", "- a\n- list\n"])
def test_an_unreadable_config_falls_back_instead_of_crashing(tmp_path, body):
    docs = tmp_path / "docs"; docs.mkdir()
    (docs / "client-config.yml").write_text(body)
    cit, trn, usr = resolve_ua_lists(str(tmp_path), None)
    assert cit == list(DEFAULT_CITATION_UAS)
    assert usr[-1] == "Claude-User"


def test_the_honouring_fetcher_is_named_even_though_it_is_not_in_the_default_list():
    # DEFAULT_USER_TRIGGERED_UAS holds the ones that may ignore robots.txt;
    # Claude-User is kept separate because its note differs. It must still be
    # reported, or the one honest directive in the class goes unmentioned.
    _, _, usr = resolve_ua_lists(None, None)
    assert "Claude-User" in usr


# ── B-080: the matcher direction ─────────────────────────────────────────────

def test_a_training_optout_never_blocks_its_citation_sibling(tmp_path, monkeypatch):
    # The exact robots.txt Apple documents for opting out of model training.
    # Before B-080 this failed the PR for blocking Applebot, which it allows.
    robots = ALLOW_ALL + "\nUser-agent: Applebot-Extended\nDisallow: /\n"
    code, out = run(tmp_path, robots, monkeypatch=monkeypatch)
    assert code == 0, "opting Applebot-Extended out must not read as blocking Applebot"
    assert "PASS [Applebot]" in out
    assert "INFO [Applebot-Extended] Disallowed" in out


def test_the_token_matches_forwards_only():
    assert gate._agent_matches("applebot", "applebot-extended") is True
    assert gate._agent_matches("applebot-extended", "applebot") is False
    assert gate._agent_matches("googlebot", "googlebot") is True
    assert gate._agent_matches("bot", "googlebot") is False, \
        "a substring anywhere must not match, or every bot matches every group"


def test_the_longest_matching_token_wins_regardless_of_order():
    forward = parse_groups("User-agent: Applebot\nAllow: /\n"
                           "User-agent: Applebot-Extended\nDisallow: /\n")
    reverse = parse_groups("User-agent: Applebot-Extended\nDisallow: /\n"
                           "User-agent: Applebot\nAllow: /\n")
    for groups in (forward, reverse):
        assert root_blocked(rules_for_ua(groups, "Applebot")[0]) is False
        assert root_blocked(rules_for_ua(groups, "Applebot-Extended")[0]) is True
