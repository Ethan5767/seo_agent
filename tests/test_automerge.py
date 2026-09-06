"""Tests for the auto-merge decision layer (pipeline/lib/automerge.py).

Task 2: risk_level() — decides whether a change is safe to auto-merge or must
go to a human. High risk = escalate to a human; low risk = eligible for auto.
"""

from pipeline.lib.automerge import risk_level, AutoMergePolicy, DEFAULT_POLICY


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
