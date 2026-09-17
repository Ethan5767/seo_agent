"""Tests for the auto-merge decision layer (pipeline/lib/automerge.py).

Task 2: risk_level() — decides whether a change is safe to auto-merge or must
go to a human. High risk = escalate to a human; low risk = eligible for auto.
"""

from pipeline.lib.automerge import (
    risk_level,
    AutoMergePolicy,
    DEFAULT_POLICY,
    decide,
    Decision,
)

# A client that has switched auto-merge ON (default is OFF).
ENABLED = AutoMergePolicy(enabled=True)
# All 19 gates green.
ALL_GREEN = {"tier": True, "provenance": True, "acceptance": True, "orphan": True}


# ── Task 3: the eligibility decision (gates + tier + risk -> AUTO / HUMAN) ────

def test_disabled_policy_always_human():
    d = decide(gate_results=ALL_GREEN, tier="T1", creates=[], text="ok", policy=DEFAULT_POLICY)
    assert d.action == "HUMAN"
    assert "disabled" in d.reason.lower()


def test_all_green_low_risk_t1_is_auto():
    d = decide(gate_results=ALL_GREEN, tier="T1", creates=[], text="Open at 8am.", policy=ENABLED)
    assert d.action == "AUTO"


def test_a_failing_gate_forces_human():
    failed = dict(ALL_GREEN, orphan=False)
    d = decide(gate_results=failed, tier="T1", creates=[], text="ok", policy=ENABLED)
    assert d.action == "HUMAN"
    assert "orphan" in d.reason.lower()


def test_high_risk_tier_forces_human_even_if_all_green():
    d = decide(gate_results=ALL_GREEN, tier="T2", creates=[], text="ok", policy=ENABLED)
    assert d.action == "HUMAN"


def test_medical_claim_forces_human_even_if_all_green():
    d = decide(gate_results=ALL_GREEN, tier="T1", creates=[], text="This cures the disease.", policy=ENABLED)
    assert d.action == "HUMAN"


def test_new_page_forces_human_even_if_all_green():
    d = decide(gate_results=ALL_GREEN, tier="T1", creates=["src/app/x/page.tsx"], text="ok", policy=ENABLED)
    assert d.action == "HUMAN"


def test_empty_gate_results_is_human():
    # No gate evidence at all is never a pass.
    d = decide(gate_results={}, tier="T1", creates=[], text="ok", policy=ENABLED)
    assert d.action == "HUMAN"


def test_decision_carries_a_reason():
    d = decide(gate_results=ALL_GREEN, tier="T1", creates=[], text="ok", policy=ENABLED)
    assert isinstance(d, Decision)
    assert d.reason  # non-empty explanation always


# ── Task 1: the auto-merge policy (the rules, as data) ───────────────────────

def test_default_policy_is_off():
    # Auto-merge must be opt-in per client — never on by default.
    assert DEFAULT_POLICY.enabled is False


def test_default_policy_allows_only_t1():
    assert DEFAULT_POLICY.allowed_tiers == frozenset({"T1"})


def test_default_policy_requires_all_gates():
    assert DEFAULT_POLICY.require_all_gates_pass is True


def test_policy_is_immutable():
    # Frozen so a stray edit can't silently loosen the safety rules.
    import dataclasses
    try:
        DEFAULT_POLICY.enabled = True  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("policy should be immutable")


def test_policy_can_be_enabled_per_client():
    on = AutoMergePolicy(enabled=True)
    assert on.enabled is True
    # enabling does not loosen the other rails
    assert on.allowed_tiers == frozenset({"T1"})
    assert on.require_all_gates_pass is True


def test_t1_copy_edit_is_low_risk():
    # A plain T1 copy edit with no new files and benign text: safe to automate.
    assert risk_level(tier="T1", creates=[], text="Our bakery opens at 8am.") == "low"


def test_t2_is_high_risk():
    # T2 adds new content — always escalate.
    assert risk_level(tier="T2", creates=[], text="A new blog post.") == "high"


def test_t3_is_high_risk():
    # T3 can touch anything not denied — always escalate.
    assert risk_level(tier="T3", creates=[], text="Restructure nav.") == "high"


def test_creating_a_new_page_is_high_risk():
    # Even at T1, creating a file is a new page — escalate.
    assert risk_level(tier="T1", creates=["src/app/new-page/page.tsx"], text="hi") == "high"


def test_medical_claim_is_high_risk():
    # YMYL: a medical/treatment claim must never auto-merge.
    assert risk_level(tier="T1", creates=[], text="This treatment cures the disease.") == "high"


def test_legal_claim_is_high_risk():
    # YMYL: legal advice must never auto-merge.
    assert risk_level(tier="T1", creates=[], text="Free legal advice from our attorney.") == "high"


def test_no_declared_tier_is_high_risk():
    # No tier declared means nothing is authorized — escalate by default.
    assert risk_level(tier="", creates=[], text="anything") == "high"


def test_ymyl_match_is_case_insensitive():
    assert risk_level(tier="T1", creates=[], text="MEDICATION and DOSAGE details.") == "high"
