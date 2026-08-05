"""rules-selftest — the ruleset's own gate (never-baselineable).

Regression contract: each of the three shipped ruleset bugs is reproduced
synthetically and must FAIL the gate — BUG-018 (dead `$` line in
banned-phrases.txt), BUG-019 (case-sensitive rule lets "free system" escape), and
the Crestline union-defeat (plain txt line beats a YAML negative-lookahead
exception). Plus: fixtures run through the ACTUAL production matcher, proven by
an equivalence test against forbidden_sweep's built mode.
"""
from __future__ import annotations

import yaml

from pipeline.gates.forbidden_sweep import scan_built
from pipeline.gates.rules_selftest import selftest

FREE_ROOF_RULE = {
    "pattern": (r"(?i)\bfree (new )?system\b(?!\s+(inspection|estimate|quote|"
                r"consultation|assessment|evaluation|consult|check|tarp))"),
    "reason": "compound exception: 'free system inspection/estimate' is allowed",
}
DEDUCTIBLE_RULE = {"pattern": r"(?i)we (pay|cover|waive) your deductible",
                   "reason": "deductible waiver banned"}


def _fixtures(proj, must=(), must_not=()):
    (proj / "docs" / "rule-fixtures.yml").write_text(
        yaml.safe_dump({"must_match": list(must), "must_not_match": list(must_not)}))


def _cfg(*rules):
    return {"client": "selftest-client", "topology_class": "single-site-single-state",
            "states_served": ["NC"],
            "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
            "forbidden_phrases": list(rules)}


# ── the three regression classes ─────────────────────────────────────────────

def test_bug018_dead_txt_rule_fails(make_project):
    """A bare `$` in banned-phrases.txt is a mid-pattern anchor: the line loads,
    compiles, matches nothing. WARN in the sweep — FAIL here."""
    proj = make_project(config=_cfg(DEDUCTIBLE_RULE), banned="$0 deductible\n")
    fails, _, _ = selftest(proj)
    assert any("DEAD RULE (BUG-018 class)" in f and "$0 deductible" in f for f in fails)


def test_bug019_case_sensitive_rule_warns_and_fixture_fails(make_project):
    """A lowercase-only rule: the case audit warns, and a Title-Case must_match
    sample proves the escape as a hard failure."""
    proj = make_project(config=_cfg({"pattern": "free system", "reason": "banned"}))
    _fixtures(proj, must=["Ask About Our Free System Today"])
    fails, warns, _ = selftest(proj)
    assert any("BUG-019" in w for w in warns)
    assert any("must_match NOT matched" in f for f in fails)


def test_bug019_case_sensitive_optout_is_quiet(make_project):
    proj = make_project(config=_cfg(
        {"pattern": "AOB", "reason": "FL AOB ban", "case_sensitive": True}))
    _, warns, _ = selftest(proj)
    assert not any("BUG-019" in w for w in warns)


def test_union_defeat_fails(make_project):
    """The Crestline shape: plain `free system` txt line matches the very forms the
    YAML lookahead excepts."""
    proj = make_project(config=_cfg(FREE_ROOF_RULE), banned="free system\n")
    fails, _, _ = selftest(proj)
    assert any("UNION DEFEAT (free system class)" in f for f in fails)


# ── fixture self-test through the production matcher ─────────────────────────

def test_green_ruleset_with_proving_fixtures(make_project):
    proj = make_project(config=_cfg(FREE_ROOF_RULE, DEDUCTIBLE_RULE))
    _fixtures(proj,
              must=["Get a free system after the storm.",
                    "We Pay Your Deductible on approved claims."],
              must_not=["Call today for a free system inspection.",
                        "Charlotte's trusted metal roofing crew."])
    fails, warns, n = selftest(proj)
    assert fails == [] and n == 2
    assert not any("no must_match fixture" in w for w in warns)


def test_must_not_match_violation_fails_naming_the_rule(make_project):
    proj = make_project(config=_cfg(DEDUCTIBLE_RULE))
    _fixtures(proj, must=["we pay your deductible"],
              must_not=["We cover your deductible questions honestly."])
    fails, _, _ = selftest(proj)
    assert any("must_not_match MATCHED" in f and "deductible" in f for f in fails)


def test_unproven_exception_fails(make_project):
    """A negative lookahead with no must_not_match exercising it = the free system
    failure waiting to recur."""
    proj = make_project(config=_cfg(FREE_ROOF_RULE))
    _fixtures(proj, must=["free system giveaway"], must_not=["nice clean sentence"])
    fails, _, _ = selftest(proj)
    assert any("exception unproven" in f for f in fails)


def test_bad_regex_fails_compile_check(make_project):
    proj = make_project(config=_cfg({"pattern": "free (roof", "reason": "broken"}))
    fails, _, _ = selftest(proj)
    assert any("does not compile" in f for f in fails)


def test_bootstrap_no_fixture_file_warns_not_fails(make_project):
    proj = make_project(config=_cfg(DEDUCTIBLE_RULE))
    fails, warns, _ = selftest(proj)
    assert fails == []
    assert any("rule-fixtures.yml missing" in w for w in warns)


def test_uncovered_rules_warn(make_project):
    proj = make_project(config=_cfg(DEDUCTIBLE_RULE, FREE_ROOF_RULE))
    _fixtures(proj, must=["we pay your deductible"],
              must_not=["free system inspection offer"])
    fails, warns, _ = selftest(proj)
    assert fails == []
    assert any("no must_match fixture" in w for w in warns)


def test_bracket_anchored_rule_exercisable_via_wrap(make_project):
    """Body-text samples get built-HTML `>…<` context, so angle-bracket-aware
    rules (BLH-North's name rule shape) are provable from plain sentences."""
    rule = {"pattern": r"(?i)>\s*[^<]*\bCasey\s+Blueline\b[^<]*<",
            "reason": "wrong division name"}
    proj = make_project(config=_cfg(rule))
    _fixtures(proj, must=["Casey Blueline crews serve Florida."],
              must_not=["Blueline Mechanical serves New Jersey."])
    fails, _, _ = selftest(proj)
    assert fails == []


def test_fixture_verdicts_agree_with_built_sweep(make_project, capsys):
    """Equivalence: a sample the selftest calls a hit IS a hit for the real
    built sweep on real HTML, and a must_not sample is not."""
    cfg = _cfg(FREE_ROOF_RULE, DEDUCTIBLE_RULE)
    hit, clean = "We waive your deductible, guaranteed.", "Book a free system estimate."
    proj = make_project(config=cfg, pages={
        "hit": f"<html><body><p>{hit}</p></body></html>",
        "clean": f"<html><body><p>{clean}</p></body></html>"})
    _fixtures(proj, must=[hit], must_not=[clean])
    fails, _, _ = selftest(proj)
    assert fails == []  # selftest: hit matched, clean unmatched
    from pipeline.gates.forbidden_sweep import load_phrases
    rules, c = load_phrases(proj, None)
    hits = scan_built(proj, rules, c, None)
    capsys.readouterr()
    assert hits == 1  # built sweep agrees: exactly the must_match page flags


def test_empty_ruleset_refuses(make_project):
    cfg = _cfg()
    cfg.pop("forbidden_phrases")
    proj = make_project(config=cfg)
    fails, warns, n = selftest(proj)
    assert fails is None and warns is None and n == 0
