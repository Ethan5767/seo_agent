"""measure.py — live-site measurement as typed Findings.

Hermetic: check_page takes already-fetched HTML, so nothing here touches the
network. The fingerprint-stability tests at the bottom are the ones that matter
most; they are the property phase 3's ratchet depends on.
"""
from __future__ import annotations

import json
import textwrap
from datetime import date

import pytest
import yaml

from pipeline.audit import measure as m

URL = "https://example.com/roofing/"

CFG = {
    "domain": "example.com",
    "schema_type": "RoofingContractor",
    "ga4_id": "G-TESTID1234",
    "nap": {"phone": "(704) 555-0100", "phone_tel": "17045550100"},
    "forbidden_phrases": [
        {"pattern": r"\$[0-9]", "reason": "no dollar amounts on site"},
        {"pattern": "—", "reason": "no em dashes in deliverables"},
    ],
}


def build_page(*, title="Roofing Replacement and Repair in Charlotte, NC",
               desc=("Charlotte roof replacement and repair from a local crew, with "
                     "a written estimate before any work begins and a warranty on "
                     "every job we complete."),
               h1_count=1, canonical=URL, noindex=False, og_image=True,
               schema_types=("RoofingContractor", "FAQPage", "BreadcrumbList"),
               body="", images=('<img src="/hero.jpg" alt="A finished roof">',),
               ga4=True, words=600):
    """A page that passes every check by default. Each keyword trips exactly one."""
    head = []
    if title is not None:
        head.append(f"<title>{title}</title>")
    if desc is not None:
        head.append(f'<meta name="description" content="{desc}">')
    if canonical is not None:
        head.append(f'<link rel="canonical" href="{canonical}">')
    if og_image:
        head.append('<meta property="og:image" content="/og.jpg">')
    if noindex:
        head.append('<meta name="robots" content="noindex">')
    schema = "".join(f'<script type="application/ld+json">{{"@type":"{t}"}}</script>'
                     for t in schema_types)
    ga = ('<script src="https://www.googletagmanager.com/gtag/js?id=G-TESTID1234"></script>'
          if ga4 else "")
    filler = " ".join(["shingle"] * words)
    h1s = "<h1>Roofing in Charlotte, NC</h1>" * h1_count
    return textwrap.dedent(f"""\
        <!DOCTYPE html><html lang="en"><head>{''.join(head)}{schema}{ga}</head>
        <body><main>{h1s}
        <p>Call <a href="tel:17045550100">(704) 555-0100</a> for an estimate.</p>
        {''.join(images)}
        <p>{filler}</p>
        {body}
        </main></body></html>
    """)


def check(html, url=URL, status=200, cfg=None):
    return m.check_page(url, html, status, cfg if cfg is not None else CFG)


def codes(findings):
    return sorted(f.code for f in findings)


# ── the clean baseline ───────────────────────────────────────────────────────

def test_clean_page_has_no_findings():
    """build_page()'s defaults satisfy every check. If this fails, read which
    codes came back — a threshold or a regex is off, not the test."""
    assert check(build_page()) == []


# ── one test per code ────────────────────────────────────────────────────────

def test_status_not_200():
    f = check(build_page(), status=404)
    assert "health.status_not_200" in codes(f)
    assert [x for x in f if x.code == "health.status_not_200"][0].detail == "status=404"


def test_title_missing():
    c = codes(check(build_page(title=None)))
    assert "health.title_missing" in c
    assert "health.title_length" not in c, "missing and out-of-band are exclusive"


def test_title_length():
    f = check(build_page(title="Roofing"))
    assert "health.title_length" in codes(f)
    assert [x for x in f if x.code == "health.title_length"][0].detail == "len=7"


def test_desc_missing():
    c = codes(check(build_page(desc=None)))
    assert "health.desc_missing" in c
    assert "health.desc_length" not in c


def test_desc_length():
    assert "health.desc_length" in codes(check(build_page(desc="Too short.")))


def test_h1_count_zero_and_many():
    assert "health.h1_count" in codes(check(build_page(h1_count=0)))
    f = check(build_page(h1_count=3))
    assert [x for x in f if x.code == "health.h1_count"][0].detail == "count=3"


def test_canonical_mismatch_absent_and_wrong():
    f = check(build_page(canonical=None))
    assert [x for x in f if x.code == "health.canonical_mismatch"][0].detail == "absent"
    assert "health.canonical_mismatch" in codes(
        check(build_page(canonical="https://example.com/other-page/")))


def test_noindex_present():
    assert "health.noindex_present" in codes(check(build_page(noindex=True)))


def test_og_image_missing():
    assert "health.og_image_missing" in codes(check(build_page(og_image=False)))


def test_schema_findings():
    c = codes(check(build_page(schema_types=())))
    assert "health.schema_business_missing" in c
    assert "health.schema_faq_missing" in c
    assert "health.schema_breadcrumb_missing" in c


def test_schema_business_context_is_the_required_type():
    f = check(build_page(schema_types=("FAQPage", "BreadcrumbList")))
    biz = [x for x in f if x.code == "health.schema_business_missing"][0]
    assert biz.context == "RoofingContractor"


def test_forbidden_phrase_one_per_rule():
    f = check(build_page(body="<p>Roofs from $5,000 and up — call today.</p>"))
    hits = [x for x in f if x.code == "health.forbidden_phrase"]
    assert len(hits) == 2, "one finding per matching rule, not one per page"
    assert sorted(h.context for h in hits) == sorted([r"\$[0-9]", "—"])


def test_forbidden_phrase_ignores_script_blocks():
    """Next RSC flight payloads carry $1 / $L3 tokens. audit_live stripped
    <script> before the sweep to stop them false-positiving the dollar rule."""
    page = build_page(body='<script>self.__next_f.push([1,"$1 $L3"])</script>')
    assert "health.forbidden_phrase" not in codes(check(page))


def test_tel_and_phone_missing():
    page = build_page().replace('href="tel:17045550100"', 'href="#"').replace(
        "(704) 555-0100", "call us")
    c = codes(check(page))
    assert "health.tel_link_missing" in c
    assert "health.phone_missing" in c


def test_ga4_missing():
    assert "health.ga4_missing" in codes(check(build_page(ga4=False)))


def test_thin_content():
    f = check(build_page(words=50))
    assert "health.thin_content" in codes(f)
    assert [x for x in f if x.code == "health.thin_content"][0].detail.startswith("words=")


# ── the two deliberate behavior changes ──────────────────────────────────────

def test_img_alt_is_per_image_with_src_as_context():
    page = build_page(images=('<img src="/a.jpg">', '<img src="/b.jpg">',
                              '<img src="/c.jpg" alt="fine">'))
    hits = [x for x in check(page) if x.code == "health.img_alt_missing"]
    assert len(hits) == 2
    assert sorted(h.context for h in hits) == ["/a.jpg", "/b.jpg"]
    assert len({h.fingerprint for h in hits}) == 2, "distinct images, distinct findings"


def test_page_with_zero_images_has_no_alt_finding():
    """audit_live.py used `len(imgs) > 0 and not missing_alt`, so an image-free
    page reported an alt violation. That is a false positive."""
    assert "health.img_alt_missing" not in codes(check(build_page(images=())))


def test_repeated_identical_findings_get_distinct_ordinals():
    """Two images sharing a src on one page must not collapse to one fingerprint."""
    page = build_page(images=('<img src="/a.jpg">', '<img src="/a.jpg">'))
    hits = [x for x in check(page) if x.code == "health.img_alt_missing"]
    assert len(hits) == 2
    assert sorted(h.ordinal for h in hits) == [0, 1]
    assert len({h.fingerprint for h in hits}) == 2


# ── config-driven skipping ───────────────────────────────────────────────────

def test_unset_config_keys_skip_their_checks_rather_than_fail():
    """No declared phone or GA4 id means those checks cannot be measured. A
    finding on every page would be a fabricated result, so they are skipped.
    Task 3's CLI prints a warning naming each skipped check."""
    bare = {"domain": "example.com", "schema_type": "RoofingContractor",
            "nap": {}, "forbidden_phrases": []}
    c = codes(check(build_page(ga4=False), cfg=bare))
    assert "health.tel_link_missing" not in c
    assert "health.phone_missing" not in c
    assert "health.ga4_missing" not in c


# ── the fingerprint properties phase 3 depends on ────────────────────────────

def test_location_is_the_path_never_the_absolute_url():
    f = check(build_page(title="Short"))
    assert all(x.location == "/roofing/" for x in f)


def test_gate_is_site_health_on_every_finding():
    assert all(x.gate == "site_health" for x in check(build_page(title="Short")))


def test_fingerprint_is_stable_across_identical_runs():
    a = check(build_page(title="Short"))
    b = check(build_page(title="Short"))
    assert [x.fingerprint for x in a] == [x.fingerprint for x in b]


def test_fingerprint_unchanged_when_only_detail_changes():
    """A title going from 7 to 12 characters is the SAME finding getting slightly
    different. If this breaks, the ratchet reports resolved-and-new instead of
    persisting, and run #2 becomes unreadable."""
    a = [x for x in check(build_page(title="Short")) if x.code == "health.title_length"][0]
    b = [x for x in check(build_page(title="Short Title!")) if x.code == "health.title_length"][0]
    assert a.detail != b.detail
    assert a.fingerprint == b.fingerprint
