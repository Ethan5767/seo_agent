"""The three-state forbidden-phrase ledger: rules / declared-empty / absent.

Both legal gates refused any client who had not written a ruleset, which is
correct as a default (a silent green over zero rules is the failure the suite
exists to prevent) but left no way to say "this client genuinely has none".
`forbidden_phrases: []` is that declaration.

The middle state is the whole test. `[]` present must SKIP; the key absent must
still exit 4. If those two ever collapse into one behaviour, a half-finished
config silently disarms the legal gate, which is the bug this shape prevents.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from pipeline.lib.common import ruleset_declared_empty

BASE_CONFIG = """\
client: acme
domain: acme.test
topology: single-location-single-city
tier: 1
"""


def write_client(tmp_path, forbidden_block: str):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "client-config.yml").write_text(BASE_CONFIG + forbidden_block, encoding="utf-8")
    return tmp_path


def run_gate(module: str, *args):
    return subprocess.run([sys.executable, "-m", module, *args],
                          capture_output=True, text=True)


# ── the predicate itself ─────────────────────────────────────────────────────

@pytest.mark.parametrize("cfg,expected", [
    ({"forbidden_phrases": []}, True),                    # the declaration
    ({}, False),                                          # nobody decided
    ({"forbidden_phrases": None}, False),                 # bare key, abandoned
    ({"forbidden_phrases": [{"pattern": "free roof"}]}, False),   # real rules
    ({"forbidden_phrases": ""}, False),                   # not a list
])
def test_only_an_empty_list_is_a_declaration(cfg, expected):
    assert ruleset_declared_empty(cfg) is expected


# ── forbidden_sweep ──────────────────────────────────────────────────────────

def test_sweep_skips_on_a_declared_empty_ledger(tmp_path):
    project = write_client(tmp_path, "forbidden_phrases: []\n")
    (project / "out").mkdir()
    r = run_gate("pipeline.gates.forbidden_sweep", "built", str(project), "--build-dir", "out")
    assert r.returncode == 0, r.stderr
    assert "[SKIP]" in r.stdout
    # The skip must never read as a clean sweep.
    assert "clean" not in r.stdout.lower() or "not a clean sweep" in r.stdout


def test_sweep_still_refuses_when_nobody_declared_anything(tmp_path):
    project = write_client(tmp_path, "")
    (project / "out").mkdir()
    r = run_gate("pipeline.gates.forbidden_sweep", "built", str(project), "--build-dir", "out")
    assert r.returncode == 4
    assert "Refusing to run an empty legal gate" in r.stderr


def test_sweep_refuses_a_bare_key_with_no_value(tmp_path):
    """`forbidden_phrases:` parses to None — a config someone abandoned, not a
    decision. It must not buy the skip."""
    project = write_client(tmp_path, "forbidden_phrases:\n")
    (project / "out").mkdir()
    r = run_gate("pipeline.gates.forbidden_sweep", "built", str(project), "--build-dir", "out")
    assert r.returncode == 4


# ── rules_selftest ───────────────────────────────────────────────────────────

def test_selftest_skips_on_a_declared_empty_ledger(tmp_path):
    project = write_client(tmp_path, "forbidden_phrases: []\n")
    r = run_gate("pipeline.gates.rules_selftest", str(project))
    assert r.returncode == 0, r.stderr
    assert "[SKIP]" in r.stdout
    assert "not\na ruleset that passed" in r.stdout or "not a ruleset that passed" in r.stdout


def test_selftest_still_refuses_when_nobody_declared_anything(tmp_path):
    project = write_client(tmp_path, "")
    r = run_gate("pipeline.gates.rules_selftest", str(project))
    assert r.returncode == 4
    assert "Refusing to self-test an empty legal ruleset" in r.stderr


# ── the declaration cannot be made by the agent ──────────────────────────────

def test_the_declaration_lives_on_the_deny_floor():
    """The skip is only safe because the file carrying it is one the agent can
    never edit, at any tier. If that ever stops being true, this shape becomes a
    self-disarming gate."""
    from pipeline.lib.common import DEFAULT_DENY
    assert "docs/client-config.yml" in DEFAULT_DENY


# ── the ledger is a UNION, so the declaration has to read both halves ────────

def test_a_populated_txt_ledger_beats_a_declared_empty_config(tmp_path):
    """The gate enforces the union of the config block and docs/banned-phrases.txt.
    Reading only the config made `forbidden_phrases: []` satisfiable by DELETING
    the other half — measured 2026-08-10 as exit 3 before the delete, exit 0 after."""
    project = write_client(tmp_path, "forbidden_phrases: []\n")
    (project / "docs" / "banned-phrases.txt").write_text("we waive your deductible\n")
    (project / "out").mkdir()
    (project / "out" / "index.html").write_text(
        "<html><body><p>we waive your deductible</p></body></html>")

    assert ruleset_declared_empty({"forbidden_phrases": []}, project) is False
    r = run_gate("pipeline.gates.forbidden_sweep", "built", str(project), "--build-dir", "out")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "[SKIP]" not in r.stdout


def test_deleting_the_txt_ledger_cannot_manufacture_the_skip(tmp_path):
    """Belt: the predicate reads both halves. Braces: the agent cannot produce the
    state anyway, because the ledger is on the deny floor at every tier."""
    from pipeline.lib.common import DEFAULT_DENY, tier_verdict
    assert "docs/banned-phrases.txt" in DEFAULT_DENY
    for tier in (1, 2, 3):
        profile = {"tier": tier, "text_paths": ["**/*"], "deny": DEFAULT_DENY}
        ok, why = tier_verdict(profile, "docs/banned-phrases.txt", "D")
        assert ok is False, f"T{tier} could delete the legal ledger: {why}"


def test_a_comments_only_ledger_still_blocks_the_declaration(tmp_path):
    """Fails CLOSED on purpose. A ledger holding only comments carries no rules, so
    being strict here costs a client one deleted file — while being lenient means
    the skip turns on whenever someone comments a ledger out, which is a plausible
    accident and an invisible one. For a legal gate, take the annoying direction."""
    project = write_client(tmp_path, "forbidden_phrases: []\n")
    (project / "docs" / "banned-phrases.txt").write_text("# nothing yet\n\n")
    assert ruleset_declared_empty({"forbidden_phrases": []}, project) is False


def test_a_whitespace_only_ledger_is_treated_as_absent(tmp_path):
    """The one lenient case: a file with nothing in it at all is not a ledger."""
    project = write_client(tmp_path, "forbidden_phrases: []\n")
    (project / "docs" / "banned-phrases.txt").write_text("\n\n  \n")
    assert ruleset_declared_empty({"forbidden_phrases": []}, project) is True


def test_a_real_ruleset_is_unaffected_by_any_of_this(tmp_path):
    project = write_client(tmp_path, textwrap.dedent("""\
        forbidden_phrases:
          - pattern: "(?i)\\\\bfree roof\\\\b"
            reason: "no free-roof claims"
        """))
    r = run_gate("pipeline.gates.rules_selftest", str(project))
    assert r.returncode == 0, r.stderr
    assert "[SKIP]" not in r.stdout
