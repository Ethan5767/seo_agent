"""Pre-flight fix suggestions must be ALEX'S RULINGS (2026-07-31), not generic.

The fix-list ships to the content team; a generic "rewrite the sentence" row
trains them to guess, and guessing is how '25+ trucks' came back three days
after the '50+' fix. Wherever the client's own config carries the ruling
(trust_signals.fleet_phrasing_rule, a rule's reason field), the suggestion
quotes it verbatim.
"""
from __future__ import annotations

from pipeline.intake.preflight_docx import _dollar_fix, _explain, _magnitude_words

NORTHSTAR_CFG = {
    "trust_signals": {
        "fleet_phrasing_rule": (
            "NEVER say '50+ trucks' or 'fleet of 50' — Casey has 10+ trucks growing. "
            "Use 'tri-axle fleet' / 'growing tri-axle fleet' / 'full tri-axle fleet' / "
            "'professional tri-axle fleet' instead."),
    },
}

BRUSH_REASON = (
    "Casey 2026-07-23: accepting brush requires a NJDEP Class B recycling approval, "
    "which his A-901 license does NOT include. Regulatory issue, banned site-wide. "
    "Clearing-service copy = 'vegetation' / 'overgrowth' instead.")


# ── trucks: config-sourced fleet phrasing, regression note on 25+ ────────────

def test_trucks_25_suggests_config_fleet_phrasing_and_regression_note():
    why, fix = _explain(r"25\+\s*(tri-axle|truck|trucks|dump truck)",
                        "FACTUALLY WRONG: Casey has 10+ trucks growing.",
                        "Our 25+ truck fleet handles hauling.", "25+ truck",
                        cfg=NORTHSTAR_CFG)
    assert '"growing tri-axle fleet"' in fix and '"full tri-axle fleet"' in fix
    assert "regression" in fix and "2026-05-02" in fix
    assert "fleet_phrasing_rule" not in fix  # replacements resolved, not referenced
    assert "10+ trucks" in why  # the client's own rule text, verbatim


def test_trucks_50_no_regression_note():
    _why, fix = _explain(r"50\+\s*(tri-axle|truck|trucks|dump truck)", "overcount",
                         "Our 50+ trucks are ready.", "50+ trucks", cfg=NORTHSTAR_CFG)
    assert '"tri-axle fleet"' in fix
    assert "regression" not in fix


def test_trucks_without_config_falls_back_to_reason():
    """No trust_signals in cfg -> mine the rule's own reason for the phrasing."""
    _why, fix = _explain(
        r"25\+\s*(truck|trucks)",
        "FACTUALLY WRONG: use 'tri-axle fleet' / 'growing tri-axle fleet' instead.",
        "Our 25+ trucks.", "25+ trucks", cfg=None)
    assert '"tri-axle fleet"' in fix and '"growing tri-axle fleet"' in fix


# ── brush: NJDEP ruling, replacements from the rule's reason ─────────────────

def test_brush_suggests_vegetation_overgrowth_with_njdep_reason():
    why, fix = _explain(r"(?i)\bbrush\b", BRUSH_REASON,
                        "Wooded lots and brush-covered land get cleared.", "brush")
    assert '"vegetation"' in fix and '"overgrowth"' in fix
    assert "NJDEP" in fix and "2026-07-23" in fix
    assert "NJDEP Class B" in why  # reason string preferred when the rule carries one


# ── AOB: the ruling, plainly, no pending decision ────────────────────────────

def test_aob_states_the_ruling():
    why, fix = _explain(
        "AOB|assignment of benefits|sign the claim over",
        "Fla. Stat. §123.4567 SB 2-A — AOB prohibited on post-2023 FL policies",
        "Do you accept Assignment of Benefits (AOB)?", "AOB")
    assert "no decision is pending" in why
    assert "written report" in fix
    assert "homeowner files their own claim" in fix.replace("the homeowner files", "homeowner files")
    assert "§123.4567" in fix


# ── dollars: pricing -> phone CTA, market context -> written words ───────────

def test_market_context_dollars_become_written_words():
    text = "Median home values in Matthews reach $485,000, and buyers expect documentation."
    _why, fix = _explain(r"\$[0-9]", "no dollar amounts", text, "$4")
    assert "market context" in fix
    assert "mid six figures" in fix          # 485,000 -> the written-word band
    assert "call for a free estimate" not in fix


def test_own_pricing_dollars_point_at_the_phone():
    text = "Soffit replacement typically runs $8.00 to $20.00 per linear foot."
    _why, fix = _explain(r"\$[0-9]", "no dollar amounts", text, "$8")
    assert "price for our own work" in fix and "phone" in fix


def test_cost_section_location_counts_as_pricing():
    """A bare table cell under COST SECTION carries no pricing keyword, but the
    location says it IS the client's own price ladder -> phone CTA, not
    written-word market framing."""
    fix = _dollar_fix("$1.50 to $4.00", "$1", where="COST SECTION / table r2c2")
    assert "price for our own work" in fix


def test_magnitude_words_bands():
    assert _magnitude_words("485,000", None) == "mid six figures"
    assert _magnitude_words("767,000", None) == "high six figures"
    assert _magnitude_words("500", "million") == "millions of dollars"
    assert _magnitude_words("1.5", "billion") == "billions of dollars"
