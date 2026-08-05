"""Placement lint — make the wrong-file footgun LOUD (the operator's doctrine 2026-07-31).

Plain phrases belong in docs/banned-phrases.txt; regex rules belong in the YAML
forbidden_phrases block. Adding to the wrong file fails silently — the canonical
failure is Crestline's plain `free system` txt line matching every form the YAML
rule's negative lookahead deliberately excepts (133 false blocks, July 2026).

The lint is advisory by contract: stderr only, never fatal, never a detection
change (the union of both sources stays the union).
"""
from __future__ import annotations

from pathlib import Path

from pipeline.gates.forbidden_sweep import (
    lint_phrase_placement,
    load_phrases,
)

BP = Path("docs/banned-phrases.txt")

CRESTLINE_FREE_SYSTEM = {
    "pattern": (r"\bfree (new )?system\b(?!\s+(inspection|estimate|quote|consultation|"
                r"assessment|evaluation|consult|check|tarp))|no out of pocket|"
                r"zero out of pocket|insurance pays 100%"),
    "reason": "compound phrase exception: 'free system inspection/estimate/quote' is allowed",
}


# ── regex constructs in banned-phrases.txt ───────────────────────────────────

def test_txt_line_with_metachars_warns():
    """'$0 deductible' compiled as regex has an anchor mid-pattern and can never
    match — exactly the silent failure the lint exists to surface."""
    warns = lint_phrase_placement([], [(11, "$0 deductible")], BP)
    assert len(warns) == 1
    assert "$0 deductible" in warns[0] and "regex metacharacters" in warns[0]


def test_plain_txt_lines_stay_quiet():
    """Ordinary prose — apostrophes, hyphens, %, commas — must not warn."""
    lines = [(1, "we waive your deductible"), (2, "100% claim approval"),
             (3, "insurance-fluent"), (4, "we work for you, not the insurance")]
    assert lint_phrase_placement([], lines, BP) == []


# ── bare phrases in the YAML block ───────────────────────────────────────────

def test_plain_yaml_pattern_warns_when_ledger_exists(tmp_path):
    bp = tmp_path / "banned-phrases.txt"
    bp.write_text("something\n")
    warns = lint_phrase_placement([{"pattern": "we handle the deductible"}], [], bp)
    assert len(warns) == 1
    assert "canonical home for plain phrases" in warns[0]


def test_plain_yaml_pattern_quiet_without_ledger(tmp_path):
    """No banned-phrases.txt -> the YAML block is the only home; nothing to say."""
    bp = tmp_path / "banned-phrases.txt"  # does not exist
    assert lint_phrase_placement([{"pattern": "we handle the deductible"}], [], bp) == []


def test_regex_yaml_pattern_never_warns(tmp_path):
    bp = tmp_path / "banned-phrases.txt"
    bp.write_text("something\n")
    assert lint_phrase_placement([{"pattern": r"\$[0-9]"}], [], bp) == []


# ── the Crestline failure shape: plain prefix defeats a coded exception ────────

def test_prefix_defeat_warns_on_crestline_shape():
    txt = [(43, "completely free system"), (44, "free system"), (45, "free new system")]
    warns = lint_phrase_placement([CRESTLINE_FREE_SYSTEM], txt, BP)
    defeats = [w for w in warns if "defeating the coded exception" in w]
    assert len(defeats) == 3, warns
    assert any("free system inspection" in w for w in defeats)


def test_prefix_defeat_quiet_for_unrelated_and_unexcepted_lines():
    """'no out of pocket' matches an alternative WITHOUT a lookahead (still
    banned in every form) and 'no cost to you' is unrelated — both quiet."""
    txt = [(13, "no out of pocket"), (41, "no cost to you")]
    assert lint_phrase_placement([CRESTLINE_FREE_SYSTEM], txt, BP) == []


# ── wired into load_phrases: loud on stderr, never fatal, union unchanged ────

def test_load_phrases_lints_but_union_is_unchanged(make_project, capsys):
    cfg = {
        "client": "lint-client",
        "topology_class": "single-site-single-state",
        "states_served": ["MD"],
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
        "forbidden_phrases": [CRESTLINE_FREE_SYSTEM],
    }
    banned = "free system\n$0 deductible\n"
    proj = make_project(config=cfg, banned=banned)
    rules, _ = load_phrases(proj, None)
    err = capsys.readouterr().err
    assert "[LINT]" in err and "defeating the coded exception" in err
    # detection semantics untouched: both txt lines still load into the union
    patterns = [r["pattern"] for r in rules]
    assert "(?i)free system" in patterns and "(?i)$0 deductible" in patterns
    assert len(rules) == 3
