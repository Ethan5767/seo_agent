"""emitter models.py + validators — the anti-fabrication and severity invariants.

The emitter's whole safety story is: it never invents a value to get a page past
a gate, and a harm-class finding can never be quietly demoted to advisory. Both
are guarded here.
"""
from __future__ import annotations

import pytest

from pipeline.generate import models
from pipeline.generate.models import (
    CURATION_CODES,
    HARM_CODES,
    Hero,
    PageDraft,
    ValidationFinding,
    apply_severity_policy,
    block,
    curate,
    to_brief,
    warn,
)
from pipeline.generate import validators
from pipeline.generate.emit_ts import EmitResult, HELD_FOR_CURATION_EXIT


def _hero(**kw):
    base = dict(badge_icon="shield", badge_text="Licensed",
                title="Roofing Services", description="Fast, local roofing.")
    base.update(kw)
    return Hero(**base)


def _draft(**kw):
    base = dict(url_path="/roofing/", page_kind="hub", city="", state="NC",
                service="roofing", h1="Roofing Services",
                meta_title="Roofing", meta_description="d", hero=_hero())
    base.update(kw)
    return PageDraft(**base)


# ── the import-time disjointness invariant ───────────────────────────────────

def test_curation_and_harm_codes_are_disjoint():
    """The invariant models.py asserts at import time: no harm-class code may be
    demoted to a mere curation judgment."""
    assert CURATION_CODES & HARM_CODES == frozenset()


def test_harm_codes_never_demoted_by_policy():
    """apply_severity_policy demotes curation codes to 'curate' but leaves harm
    codes hard-blocking."""
    findings = [block("forbidden_phrase", "banned"), block("hero_rule", "too long")]
    out = {f.code: f.severity for f in apply_severity_policy(findings)}
    assert out["forbidden_phrase"] == "block"      # harm stays block
    assert out["hero_rule"] == "curate"            # curation judgment demoted


def test_validation_finding_rejects_unknown_severity():
    with pytest.raises(ValueError):
        ValidationFinding(code="x", severity="whoops", message="m")


# ── the emitter never fabricates a proprietary value ─────────────────────────

def test_generic_page_blocks_never_invents_a_token():
    """A page with zero allow-list tokens yields a BLOCKING finding — and the
    brief still carries an EMPTY proprietary_variable, never a made-up value."""
    cfg = {"required_phrases": ["Matthews", "Mint Hill"], "nap": {"city": "Charlotte"}}
    draft = _draft(hero=_hero(title="Generic Roofing Services",
                              description="We install roofs."))
    findings = validators.s21_proprietary(draft, cfg)
    assert any(f.code == "no_proprietary_token" and f.is_block for f in findings)
    # the anti-fabrication guarantee: nothing invented into the draft or brief
    assert draft.proprietary_variables == []
    assert to_brief(draft)["proprietary_variable"] == ""


def test_empty_allowlist_is_a_block_not_a_silent_pass():
    """No allow-list at all => block('proprietary_allow_list_empty'), mirroring
    the gate's exit-4 refusal — never a green pass."""
    draft = _draft()
    findings = validators.s21_proprietary(draft, cfg={})
    assert any(f.code == "proprietary_allow_list_empty" and f.is_block for f in findings)


def test_present_token_passes_cleanly():
    cfg = {"required_phrases": ["Matthews"]}
    draft = _draft(hero=_hero(title="Roofing in Matthews, NC",
                              description="Local roofing in Matthews."))
    assert validators.s21_proprietary(draft, cfg) == []


# ── exit-code contract: 0 / 1 / 9 / 15 distinct ──────────────────────────────

def test_exit_codes_distinct_and_severity_ordered():
    refused = EmitResult(); refused.refused.append(("/a/", [block("forbidden_phrase", "x")]))
    held = EmitResult(); held.held.append(("/a/", [curate("hero_rule", "x")]))
    flagged = EmitResult(); flagged.flagged.append(("/a/", [warn("card_grid_count", "x")]))
    clean = EmitResult(); clean.written.append("/a/")

    codes = {
        "refused": refused.exit_code,
        "held": held.exit_code,
        "flagged": flagged.exit_code,
        "clean": clean.exit_code,
    }
    assert codes == {"refused": 9, "held": HELD_FOR_CURATION_EXIT, "flagged": 1, "clean": 0}
    assert len(set(codes.values())) == 4, "exit codes must be distinct"


def test_refused_outranks_held_outranks_flagged():
    """Most severe wins when multiple outcomes coexist."""
    r = EmitResult()
    r.flagged.append(("/a/", [warn("card_grid_count", "x")]))
    r.held.append(("/b/", [curate("hero_rule", "x")]))
    assert r.exit_code == HELD_FOR_CURATION_EXIT   # held outranks flagged
    r.refused.append(("/c/", [block("forbidden_phrase", "x")]))
    assert r.exit_code == 9                          # refused outranks all


# ── BUG-020: Crestline's multi-state schema nests keywords under states[] ───────
def test_state_scoped_reads_nested_and_flat_schemas():
    from pipeline.generate.brief import _flat_strings, _state_scoped
    flat = {"target_keywords": {"primary": ["roof repair charlotte nc"]}}
    nested = {"states": [
        {"name": "Maryland", "seo_round_1": True,
         "target_keywords": {"primary": ["roof repair baltimore md"]}},
        {"name": "Virginia", "seo_round_1": False,
         "target_keywords": {"primary": ["roof repair richmond va"]}},
    ]}
    assert _flat_strings(_state_scoped(flat, "target_keywords")) == \
        ["roof repair charlotte nc"]
    got = _flat_strings(_state_scoped(nested, "target_keywords"))
    assert got == ["roof repair baltimore md"]          # active state included
    assert "roof repair richmond va" not in got          # round-1 false excluded
