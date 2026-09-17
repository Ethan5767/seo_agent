"""Playbooks: how to fix a finding, in two registers.

A finding used to give one line - "add FAQPage, QAPage, HowTo or Article
JSON-LD, whichever matches the page" - which names the defect and leaves the
reader to work out which type applies, which fields are required, where the
block goes and how to tell it landed. An audit that only names the defect makes
the reader do the work.

Two registers, because two people read this. `plain`/`impact` are for the client,
who does not write code and must never be shown a finding code or a block of
JSON-LD. `steps`/`snippet`/`verify` are for whoever implements.
"""
import re

from pipeline.scanner.recommendations import (
    RECOMMENDATIONS, EFFORTS, playbook, has_playbook, plain_coverage,
)


def _written():
    return [c for c in RECOMMENDATIONS if has_playbook(c)]


def test_playbook_returns_the_same_shape_for_an_unknown_code():
    """An unwritten playbook is empty, never None: a caller renders 'no steps
    recorded' instead of crashing, and the gap stays visible."""
    pb = playbook("nope.nope")
    assert pb["steps"] == [] and pb["snippet"] == "" and pb["plain"] == ""
    assert pb["why"] and pb["fix"], "the generic copy still applies"
    assert pb["severity"] == "warn"


def test_every_written_playbook_has_real_steps():
    written = _written()
    assert written, "no playbooks written at all"
    for code in written:
        pb = playbook(code)
        assert len(pb["steps"]) >= 3, f"{code}: a two-step playbook is still a hint"
        for step in pb["steps"]:
            assert len(step) > 25, f"{code}: step too short to be actionable: {step!r}"
        assert pb["verify"], f"{code}: a fix with no way to check it is not finished"
        assert pb["effort"] in EFFORTS, f"{code}: unknown effort {pb['effort']!r}"


def test_a_written_playbook_also_speaks_to_the_client():
    """The technical half is useless to the person paying for it."""
    for code in _written():
        pb = playbook(code)
        assert pb["plain"], f"{code}: no plain-language summary for the client"
        assert pb["impact"], f"{code}: no statement of what it costs the client"


def test_the_client_register_carries_no_jargon():
    """What a client must never be shown: a finding code, a tag, a schema type,
    a file name, or a CLI command."""
    banned = re.compile(
        r"""\bJSON-LD\b|\bschema\.org\b|<[a-z]+[ >/]|robots\.txt|\.tsx?\b|
            \bcurl\b|\bHTML\b|\bAPI\b|[a-z_]+\.[a-z_]+\.[a-z_]+|\bmeta tag\b""",
        re.IGNORECASE | re.VERBOSE,
    )
    for code in _written():
        pb = playbook(code)
        for field in ("plain", "impact"):
            hit = banned.search(pb[field])
            assert not hit, f"{code}.{field} shows the client jargon: {hit.group(0)!r}"


def test_the_client_register_stays_short():
    """One sentence each. A paragraph is a report, not a summary."""
    for code in _written():
        pb = playbook(code)
        assert len(pb["plain"]) <= 200, f"{code}: plain summary is too long"
        assert len(pb["impact"]) <= 200, f"{code}: impact line is too long"


def test_no_playbook_promises_a_ranking_or_a_number_it_cannot_know():
    """The provenance rule applies to our own copy as much as to the agent's."""
    bad = re.compile(r"\b(guarantee|will rank|rank #?\d|\d+% (more|increase)|double your)\b", re.IGNORECASE)
    for code in _written():
        pb = playbook(code)
        blob = " ".join([pb["plain"], pb["impact"], pb["verify"], *pb["steps"]])
        hit = bad.search(blob)
        assert not hit, f"{code} promises an outcome it cannot know: {hit.group(0)!r}"


def test_no_playbook_uses_an_em_dash():
    """These strings can reach a client report and a client repo, and the em-dash
    gate accepts no baseline."""
    for code in _written():
        pb = playbook(code)
        blob = " ".join([pb["plain"], pb["impact"], pb["verify"], pb["snippet"], *pb["steps"]])
        assert "—" not in blob, f"{code} contains an em dash"


def test_every_playbook_code_is_one_the_scanner_emits():
    """A playbook for a code nothing produces would never be reachable."""
    import pathlib
    src = "\n".join(
        p.read_text() for p in pathlib.Path("pipeline/scanner").glob("*.py")
    )
    for code in _written():
        family = code.split(".")[0]
        assert f'"{code}"' in src or f'make_row("{family}")' in src, \
            f"playbook '{code}' matches nothing the scanner emits"


def test_coverage_is_reported_rather_than_assumed():
    c = plain_coverage()
    assert c["codes"] == len(RECOMMENDATIONS)
    # Plain copy can exist WITHOUT steps: an optional finding is a choice, so
    # there is nothing to instruct. The implication runs one way only - every
    # finding with steps must also speak to the client.
    assert c["plain"] >= len(_written()), "a written playbook is missing plain copy"
    # The gap is meant to be visible: these codes still fall back to `why`,
    # which is operator language.
    assert isinstance(c["missing_plain"], list)


# ── Rules taken from published style guidance, not from taste ────────────────
#
# GOV.UK ("Plain English is mandatory for all of GOV.UK"): split sentences over
# 25 words. Nielsen Norman Group: 15-20 words is better, and text above a
# 10-12th grade reading level "requires too much mental effort, even for highly
# educated people". Sitebulb publishes the two-sentence house style this table
# follows, written so an agency can paste it straight into a client report.


def test_client_sentences_stay_under_the_plain_english_limit():
    for code in _written():
        pb = playbook(code)
        for field in ("plain", "impact"):
            for sentence in re.split(r"(?<=[.!?])\s+", pb[field]):
                words = len(sentence.split())
                assert words <= 25, (
                    f"{code}.{field}: {words}-word sentence exceeds the 25-word "
                    f"plain-English limit: {sentence!r}"
                )


def test_every_playbook_says_when_the_client_will_see_it_work():
    """The sentence that protects the relationship in week three.

    Google's own guidance is the honest form: "Some changes might take effect in
    a few hours, others could take several months." Without it, every finding
    implicitly promises next week.
    """
    for code in _written():
        assert playbook(code)["timeline"], f"{code}: no timeline for the client"


def test_no_timeline_promises_a_date_or_a_ranking():
    """A range, never a date; an effect, never a position. "No one can guarantee
    a #1 ranking on Google" - Google Search Central."""
    bad = re.compile(r"\b(guarantee|rank #?\d|position \d|by (next )?(week|month)|\d+ days exactly)\b",
                     re.IGNORECASE)
    for code in _written():
        tl = playbook(code)["timeline"]
        hit = bad.search(tl)
        assert not hit, f"{code} timeline promises something unknowable: {hit.group(0)!r}"


def test_an_optional_finding_says_so_and_asks_for_nothing():
    """A severity system with no documented bottom tier reads as an infinite
    to-do list. Search Console says "there is nothing you need to do"; other tools
    says "feel free to ignore this recommendation". Ours needs the same escape."""
    optional = [c for c in RECOMMENDATIONS if RECOMMENDATIONS[c].get("optional")]
    assert optional, "no finding is marked as a legitimate choice rather than a defect"
    for code in optional:
        pb = playbook(code)
        assert pb["severity"] != "error", f"{code} cannot be both optional and an error"
        blob = (pb["plain"] + " " + pb["impact"] + " " + pb["timeline"]).lower()
        assert any(p in blob for p in ("no action needed", "nothing you need to do",
                                       "it is a choice", "feel free to ignore")), \
            f"{code} is optional but never tells the client they may leave it"
