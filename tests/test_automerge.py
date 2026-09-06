"""Tests for the auto-merge decision layer (pipeline/lib/automerge.py).

Task 2: risk_level() — decides whether a change is safe to auto-merge or must
go to a human. High risk = escalate to a human; low risk = eligible for auto.
"""

from pipeline.lib.automerge import risk_level


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
