"""One parser, and proof the six it replaced were wrong in ways that mattered.

There were six `<loc>` regexes and four `<title>` regexes in this repo. Some were
case-sensitive on a case-insensitive format, one matched without a closing tag,
one only matched absolute URLs, and NONE of them decoded XML entities - which is
not an edge case, because a sitemap is required to escape `&` and every
paginated or filtered URL on a real site has one.

Each test below names the consequence, not just the input.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.lib.html import decode_entities, inner_text, page_title, sitemap_locs

ROOT = Path(__file__).resolve().parents[1]


def sm(*locs: str) -> str:
    body = "".join(f"<url><loc>{l}</loc></url>" for l in locs)
    return f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'


# ── the entity bug, which every one of the six had ───────────────────────────

def test_an_escaped_ampersand_comes_back_as_an_ampersand():
    # A sitemap MUST escape `&`. Handing back the literal `&amp;` means the URL
    # is fetched wrong (404), diffed against the route list wrong (mismatch),
    # and reported as a broken or orphaned page that is perfectly fine.
    assert sitemap_locs(sm("https://x.test/a?page=2&amp;sort=new")) == [
        "https://x.test/a?page=2&sort=new"
    ]


def test_a_title_with_an_escaped_ampersand_is_measured_at_its_real_length():
    # `health.title_length` counts characters. "Roof &amp; Gutter" is 17 to a raw
    # regex and 13 to a reader, and the check has a 30-60 window.
    t = page_title("<title>Roof &amp; Gutter</title>")
    assert t == "Roof & Gutter"
    assert len(t) == 13


def test_two_titles_differing_only_in_escaping_compare_equal():
    # The duplicate-title check compares strings. These are the same title.
    assert page_title("<title>A &amp; B</title>") == page_title("<title>A &#38; B</title>")


@pytest.mark.parametrize("raw,expected", [
    ("&lt;script&gt;", "<script>"),
    ("&#x2019;", "’"),
    ("&nbsp;", "\xa0"),
    ("&nosuchentity;", "&nosuchentity;"),  # left alone, never raised on
])
def test_entity_decoding_covers_the_forms_a_generator_emits(raw, expected):
    assert decode_entities(raw) == expected


# ── the shapes real sitemaps come in ─────────────────────────────────────────

def test_uppercase_and_namespaced_tags_are_still_locs():
    # `<LOC>` is legal XML and `<sm:loc>` is what a generator that declares the
    # namespace with a prefix emits. Half the old patterns were case-sensitive
    # and none handled a prefix, so those sitemaps parsed as zero URLs - and a
    # sitemap with zero URLs reads as "no sitemap" to every consumer.
    xml = "<url><LOC>https://x.test/a</LOC></url><url><sm:loc>https://x.test/b</sm:loc></url>"
    assert sitemap_locs(xml) == ["https://x.test/a", "https://x.test/b"]


def test_cdata_is_unwrapped():
    assert sitemap_locs("<loc><![CDATA[https://x.test/a?a=1&b=2]]></loc>") == [
        "https://x.test/a?a=1&b=2"
    ]


def test_whitespace_and_newlines_inside_the_element_are_collapsed():
    assert sitemap_locs("<loc>\n  https://x.test/a\n</loc>") == ["https://x.test/a"]


def test_attributes_on_the_element_do_not_break_the_match():
    assert sitemap_locs('<loc xml:lang="en">https://x.test/a</loc>') == ["https://x.test/a"]


def test_a_site_relative_loc_is_returned_as_written():
    # Legal, and what several static generators emit. bootstrap_config's pattern
    # required `https?://` and therefore saw nothing on those sites, so topology
    # detection returned "TODO" for every one of them.
    assert sitemap_locs(sm("/services/roofing/")) == ["/services/roofing/"]


def test_an_empty_loc_names_no_url_and_is_dropped():
    assert sitemap_locs("<loc></loc><loc>   </loc><loc>https://x.test/a</loc>") == [
        "https://x.test/a"
    ]


def test_a_duplicate_loc_is_kept():
    # A sitemap listing the same URL twice is a finding for the caller to report.
    # Deduping here would hide it.
    assert sitemap_locs(sm("https://x.test/a", "https://x.test/a")) == [
        "https://x.test/a", "https://x.test/a",
    ]


def test_a_truncated_element_is_not_a_url():
    # `validate.py` matched `<loc>\s*([^<\s]+)` with no closing tag, so half a
    # tag in a truncated sitemap counted as a valid entry and the gate reported
    # the sitemap as fine.
    assert sitemap_locs("<url><loc>https://x.test/a") == []


def test_order_is_document_order():
    assert sitemap_locs(sm("https://x.test/c", "https://x.test/a", "https://x.test/b")) == [
        "https://x.test/c", "https://x.test/a", "https://x.test/b",
    ]


@pytest.mark.parametrize("value", [None, "", "not xml at all", "<html><body>hi</body></html>"])
def test_nothing_that_is_not_a_sitemap_yields_urls(value):
    assert sitemap_locs(value) == []


# ── titles ───────────────────────────────────────────────────────────────────

def test_absent_and_empty_titles_are_different_facts():
    # "no <title> element" and "a <title> the author left blank" are different
    # defects, and the presence checks are built on the difference.
    assert page_title("<html><body>no head</body></html>") is None
    assert page_title("<title></title>") == ""


def test_a_title_split_across_lines_is_one_title():
    # The `[^<]+` patterns matched this; the point is that it stays collapsed to
    # what a browser shows in the tab, which is what the length check measures.
    assert page_title("<title>\n  Metal Roofing\n  In Austin\n</title>") == "Metal Roofing In Austin"


def test_attributes_and_casing_on_the_title_element():
    assert page_title('<TITLE data-x="1">Hello</TITLE>') == "Hello"


def test_only_the_first_title_is_returned():
    # Two titles is a defect, and it is onpage's defect to report. A caller
    # asking for "the title" gets the one a browser would use.
    assert page_title("<title>First</title><title>Second</title>") == "First"


def test_markup_inside_a_title_is_literal_text():
    # Title content is RCDATA: a browser shows `<span>` in a title as typed.
    # Stripping it here would report a title the page does not have.
    assert page_title("<title>A<span>B</span></title>") == "A<span>B</span>"


def test_inner_text_strips_markup_for_elements_that_actually_contain_it():
    # The `<h1>` case, which is why seed_queries needs a second function.
    assert inner_text("Metal Roofing In <span>Austin</span>") == "Metal Roofing In Austin"
    assert inner_text("Roof &amp; Gutter") == "Roof & Gutter"
    assert inner_text(None) == ""


# ── it stays one parser ──────────────────────────────────────────────────────

SOURCES = sorted(
    p for p in (ROOT / "pipeline").rglob("*.py")
    if p.name != "html.py"
)


def strip_comments_and_strings(text: str) -> str:
    """Docstrings quote the patterns they replaced; a raw grep matches those."""
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    text = re.sub(r"'''[\s\S]*?'''", "", text)
    return re.sub(r"^\s*#.*$", "", text, flags=re.M)


@pytest.mark.parametrize("needle,what", [
    ("<loc", "a <loc> parser"),
    ("<title", "a <title> parser"),
])
def test_no_module_grows_its_own_parser_again(needle, what):
    offenders = []
    for path in SOURCES:
        body = strip_comments_and_strings(path.read_text())
        for line in body.splitlines():
            if not any(c in line for c in ("re.compile", "re.search", "re.findall", "re.finditer")):
                continue
            if needle in line.lower():
                offenders.append(f"{path.relative_to(ROOT)}: {line.strip()}")
    assert not offenders, (
        f"{what} outside pipeline/lib/html.py. Eight of these disagreed with each "
        f"other before they were consolidated:\n  " + "\n  ".join(offenders)
    )
