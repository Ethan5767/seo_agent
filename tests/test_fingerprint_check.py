"""fingerprint-check — invisible-character scrub, and the one script-aware exemption.

The gate is never-baselineable, so a false positive on legitimate content blocks
a client's every PR with no recording that can accept it. Khmer writes without
spaces between words and uses U+200B to mark where a line may break; that is
orthography, not an AI-clipboard fingerprint. Measured on `lee-series-web`:
`lib/i18n.ts` carries 28 of them inside Khmer sentences.

The exemption is deliberately narrow. Only U+200B, only when a neighbouring
character is Khmer. Everything else — U+200C, U+200D, bidi controls, the tag
block — still fires in every context, Khmer included.
"""
from __future__ import annotations

from pipeline.gates.fingerprint_check import is_word_break_hint, scan_text

# Real strings, not synthesised ones. The Khmer is lifted from lee's i18n file.
KHMER_WITH_BREAKS = "យើង​នឹង​ត្រឡប់​ទៅ​អ្នក​វិញ"
KHMER_PLAIN = "សូមទាក់ទងមកយើងខ្ញុំគ្រប់ពេល។"


def labels(text: str) -> list[str]:
    return [label for _, _, label in scan_text(text)]


def test_khmer_word_breaks_are_not_fingerprints():
    """The 28-hit case from lee. Five U+200B, all doing Khmer word breaking."""
    assert KHMER_WITH_BREAKS.count("​") == 5
    assert scan_text(KHMER_WITH_BREAKS) == []


def test_the_same_character_in_latin_text_still_fires():
    """The exemption is about the neighbours, not about the file."""
    hits = labels("the quick​brown fox")
    assert len(hits) == 1
    assert "U+200B" in hits[0]


def test_khmer_and_latin_in_one_document_are_judged_separately():
    """A Khmer block does not launder a zero-width space in the English copy."""
    hits = labels(f"<p>{KHMER_WITH_BREAKS}</p>\n<p>free​shipping</p>")
    assert len(hits) == 1
    assert "U+200B" in hits[0]


def test_only_zwsp_is_exempt_never_the_joiner():
    """U+200D is not Khmer word breaking, and lee's privacy page carried a real
    one inside an empty Webflow paragraph. It must still fail, in any script."""
    for text in (f"{KHMER_PLAIN}‍{KHMER_PLAIN}", "<p>‍</p>"):
        hits = labels(text)
        assert len(hits) == 1
        assert "U+200D" in hits[0]


def test_zwsp_between_two_khmer_characters_reads_both_neighbours():
    khmer = KHMER_PLAIN[0]
    assert is_word_break_hint(f"{khmer}​{khmer}", 1)
    assert is_word_break_hint(f"{khmer}​A", 1)      # trailing Latin still exempt
    assert is_word_break_hint(f"A​{khmer}", 1)      # leading Latin still exempt
    assert not is_word_break_hint("A​B", 1)


def test_a_zwsp_at_either_end_of_a_file_does_not_crash_the_neighbour_lookup():
    """Index 0 has no `before`; the last index has no `after`."""
    assert labels("​") == [l for l in labels("​")]  # no IndexError
    assert len(labels("​")) == 1
    assert scan_text(f"​{KHMER_PLAIN[0]}") == []
    assert scan_text(f"{KHMER_PLAIN[0]}​") == []


def test_bidi_and_tag_characters_are_untouched_by_the_exemption():
    khmer = KHMER_PLAIN[0]
    assert len(labels(f"{khmer}‮{khmer}")) == 1      # RLO next to Khmer
    assert len(labels(f"{khmer}\U000e0041{khmer}")) == 1  # tag char next to Khmer
