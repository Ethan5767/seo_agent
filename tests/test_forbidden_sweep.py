"""forbidden_sweep — the legal-exposure gate. Highest priority.

The RSC-masking test (test_script_style_masking_*) is the one that stops the
<script>/<style> masking fix silently regressing: a Next.js flight payload is
full of `$1` / `$L3` / `$5` tokens that the `\\$[0-9]` dollar rule would match,
so if masking breaks, every static-export page false-positives and the gate
either becomes noise everyone ignores or blocks every deploy.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from pipeline.gates.forbidden_sweep import (
    SCRIPT_STYLE_RE,
    blank_keep_lines,
    load_phrases,
    scan_built,
)


# ── RSC / script / style masking ─────────────────────────────────────────────

def test_script_style_masking_hides_rsc_dollar_tokens(make_project, rsc_payload_html):
    """With masking intact, ONLY the visible $5,000 matches the dollar rule.

    The fixture carries 4 more `$N` tokens inside <script>/<style> ($5 in CSS,
    $5 and $1 in the first flight push, $5000 in the second). All must be masked;
    exactly ONE (the body $5,000) may survive. This is the regression tripwire —
    if masking becomes a no-op this count jumps to 5 and the test goes red.
    """
    proj = make_project(pages={"/roof-replacement/": rsc_payload_html})
    dollar_only = [{"pattern": r"\$[0-9]", "reason": "no dollar amounts"}]
    hits = scan_built(proj, dollar_only, {}, str(proj / "out"))
    assert hits == 1, f"expected exactly the visible $5,000, got {hits} (RSC tokens leaked?)"


def test_visible_violations_all_match(make_project, rsc_payload_html, forbidden_rules):
    """A visible $5,000, an em dash, and an insurance phrase each produce a hit."""
    proj = make_project(pages={"/roof-replacement/": rsc_payload_html})
    hits = scan_built(proj, forbidden_rules, {}, str(proj / "out"))
    assert hits == 3, f"expected dollar + em-dash + insurance = 3 hits, got {hits}"


def test_l3_token_never_matches_dollar_rule():
    """`$L3` is `$` + letter, NOT `$` + digit — it must not match even unmasked.
    Guards against someone 'fixing' masking by loosening the dollar pattern."""
    import re
    assert re.search(r"\$[0-9]", "$L3") is None
    assert re.search(r"\$[0-9]", "$5") is not None


def test_masking_is_line_preserving():
    """Blanking a script must keep the line count so reported line numbers stay
    truthful (the whole reason it blanks instead of deleting)."""
    html = "line1\n<script>\na\nb\n</script>\nline6"
    masked = SCRIPT_STYLE_RE.sub(blank_keep_lines, html)
    assert masked.count("\n") == html.count("\n")
    assert "a" not in masked and "b" not in masked


# ── empty ruleset => exit 4 (never a silent pass) ────────────────────────────

def test_empty_ruleset_exits_4(make_project):
    """No in-config forbidden_phrases and no banned-phrases.txt => refuse to run
    an empty legal gate. Exit 4, not a green pass."""
    cfg = {
        "client": "empty-client",
        "topology_class": "single-site-single-state",
        "states_served": ["NC"],
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
        # deliberately NO forbidden_phrases
    }
    proj = make_project(config=cfg, pages={"/x/": "<html><body>hi</body></html>"})
    r = subprocess.run(
        [sys.executable, "-m", "pipeline.gates.forbidden_sweep", "built", str(proj)],
        capture_output=True, text=True,
    )
    assert r.returncode == 4, f"expected exit 4 on empty ruleset, got {r.returncode}\n{r.stderr}"


# ── union of in-config forbidden_phrases + docs/banned-phrases.txt ───────────

def test_union_loads_both_sources(make_project):
    """Both the in-config block AND docs/banned-phrases.txt must load — neither
    source silently shadows the other."""
    cfg = {
        "client": "union-client",
        "topology_class": "single-site-single-state",
        "states_served": ["NC"],
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
        "forbidden_phrases": [{"pattern": r"\$[0-9]", "reason": "in-config dollar rule"}],
    }
    banned = "# ledger\nwaive your deductible\nfree system\n"
    proj = make_project(config=cfg, banned=banned)
    rules, _cfg = load_phrases(proj, None)
    patterns = [r["pattern"] for r in rules]
    assert r"\$[0-9]" in patterns, "in-config rule missing from the union"
    # banned-phrases.txt lines get a (?i) prefix when they lack one
    assert "(?i)waive your deductible" in patterns, "banned-phrases.txt line missing"
    assert "(?i)free system" in patterns
    assert len(rules) == 3, f"expected 3 unique rules, got {len(rules)}: {patterns}"


def test_union_dedupes_by_pattern(make_project):
    """A pattern present in BOTH sources appears once (deduped by pattern string)."""
    cfg = {
        "client": "dedupe-client",
        "topology_class": "single-site-single-state",
        "states_served": ["NC"],
        "repo": {"framework": "nextjs-app-router", "build_output_dir": "out"},
        "forbidden_phrases": [{"pattern": "(?i)waive your deductible", "reason": "config"}],
    }
    banned = "waive your deductible\n"  # same pattern after (?i) prefix
    proj = make_project(config=cfg, banned=banned)
    rules, _ = load_phrases(proj, None)
    patterns = [r["pattern"] for r in rules]
    assert patterns.count("(?i)waive your deductible") == 1
