"""P0-4 (ENGINE-FIXES-2026-08 fix 4): heading→marker mapping order and vocabulary.

The 2026-08 Crestline run: FAQ headings embed the page's service name
("Frequently Asked Questions About Storm Damage Restoration in Parkville"),
and with topic patterns ranked above the FAQ pattern, 'storm damage' claimed
the heading. The FAQ section then rode the wrong marker, _faq_pairs found 0
pairs, and the capsule check paired question-with-question on exactly the 8
storm pages (22 blocking → 8 after this fix, zero content changes). Also:
the mapping stamped a ACME-named marker onto every client's pages.
"""

import re

from pipeline.generate.distill import _BUILDER_MARKERS, _HUB_TITLE_MARKERS


def _first_marker(title: str) -> str | None:
    for pattern, name in _HUB_TITLE_MARKERS:
        if re.search(pattern, title, re.I):
            return name
    return None


def test_faq_outranks_embedded_topic_words():
    assert _first_marker(
        'Frequently Asked Questions About Storm Damage Restoration in Parkville'
    ) == 'FAQ SECTION'
    assert _first_marker(
        'Frequently Asked Questions About Our Process and Financing'
    ) == 'FAQ SECTION'


def test_faqs_abbreviation_variants_match():
    assert _first_marker('Storm Damage Restoration FAQs') == 'FAQ SECTION'
    assert _first_marker('Roof Replacement FAQ') == 'FAQ SECTION'


def test_topic_headings_still_map_when_not_faq():
    assert _first_marker('What Storm Damage Looks Like on Parkville Roofs') \
        == 'STORM AND INSURANCE SECTION'
    assert _first_marker('Our Storm Damage Restoration Process') \
        == 'STORM AND INSURANCE SECTION'
    assert _first_marker('Why Parkville Homeowners Choose Crestline Restorations') \
        == 'WHY CHOOSE SECTION'


def test_no_client_named_markers_in_the_mapping():
    """Engine vocabulary must be client-neutral — a ACME-named marker was
    being stamped onto Crestline and Northstar pages (cross-client contamination)."""
    for _, name in _HUB_TITLE_MARKERS:
        assert 'ACME' not in name.upper(), name


def test_legacy_acme_marker_still_builder_collapses():
    """Existing Acme team docs write the legacy marker explicitly — it must
    keep resolving to the same builder as the canonical name."""
    assert _BUILDER_MARKERS['WHY ACME SECTION'] == _BUILDER_MARKERS['WHY CHOOSE SECTION']
