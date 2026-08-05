"""The three emitter defects the July end-to-end dry run surfaced (2026-07-21).

Each would break the first real cycle, and each is now guarded here:

  1. a `types` card grid without a `subtitle` emits TS that fails `tsc` and kills
     the whole build (TypesSection.subtitle is mandatory);
  2. a newly emitted spoke/subservice with no inbound link is an orphan — in the
     sitemap, crawlable, zero inbound internal links (THE Acme orphan bug);
  3. emit demoted an over-160 metaDescription to a ride-along WARN and shipped it,
     while the built gate 2_desc_120_160 BLOCKS it — a page could pass emit then
     fail the build.
"""
from __future__ import annotations

from dataclasses import replace

from pipeline.generate.models import (
    CURATION_CODES,
    Hero,
    PageDraft,
    Section,
    effective_len,
)
from pipeline.generate import validators
from pipeline.generate.distill import _derive_types_subtitle, _generic_section, RawBlock
from pipeline.generate.emit_ts import wire_inbound_link


def _hero(**kw):
    base = dict(badge_icon="shield", badge_text="Licensed",
                title="Soffit Installation", description="Vented soffit, done right.")
    base.update(kw)
    return Hero(**base)


def _draft(**kw):
    base = dict(url_path="charlotte-nc/matthews/soffit-installation",
                page_kind="subservice", city="Matthews", state="NC",
                service="Soffit Installation", h1="Soffit Installation",
                meta_title="Soffit Installation Matthews NC",
                meta_description="d", hero=_hero())
    base.update(kw)
    return PageDraft(**base)


def _types(subtitle):
    props = {"label": "Soffit Materials", "title": "Soffit Materials We Install",
             "cards": [{"icon": "x", "title": "Vinyl", "description": "y"},
                       {"icon": "x", "title": "Aluminum", "description": "y"}]}
    if subtitle is not None:
        props["subtitle"] = subtitle
    return Section("types", props, core_body=True)


# ── DEFECT 1 — a `types` section always has a subtitle ────────────────────────

def test_types_section_without_subtitle_is_blocked():
    """The loud backstop: an invalid `types` entry can never silently build."""
    draft = _draft(sections=[_types(None)])
    fs = validators.v5b_types_subtitle(draft)
    assert [f.code for f in fs] == ["types_subtitle_missing"]
    assert fs[0].severity == "block"


def test_types_section_with_empty_subtitle_is_blocked():
    draft = _draft(sections=[_types("   ")])
    assert [f.code for f in validators.v5b_types_subtitle(draft)] == ["types_subtitle_missing"]


def test_types_section_with_subtitle_passes():
    draft = _draft(sections=[_types("Each material performs differently in the Charlotte climate.")])
    assert validators.v5b_types_subtitle(draft) == []


def test_distill_derives_a_subtitle_from_the_section_framing():
    """distill guarantees the field even when the DOCX carries no 'Subtitle:' line —
    verbatim authored H2/label, never an invented claim."""
    # label distinct from H2: the label is the authored framing to fall back to.
    assert _derive_types_subtitle("Why Homeowners Install Now", "What Drives Installation") \
        == "Why Homeowners Install Now"
    # no distinct label: the H2 itself, never empty.
    assert _derive_types_subtitle("Soffit Materials", "Soffit Materials") == "Soffit Materials"


def test_generic_section_always_carries_a_subtitle():
    """A card-grid built from a source section with NO subtitle line still emits a
    `types` section whose props include a non-empty subtitle."""
    def rb(i, label, value, text):
        return RawBlock(index=i, kind="paragraph", style="normal",
                        label=label, value=value, text=text)
    blocks = [
        rb(0, "Section Label", "Why Install Soffit Now", "Section Label: Why Install Soffit Now"),
        rb(1, "H2", "What Drives Soffit Installation", "H2: What Drives Soffit Installation"),
        rb(2, "Card 1", "Ventilation", "Card 1: Ventilation"),
        rb(3, "", "", "Better attic airflow reduces heat load."),
        rb(4, "Card 2", "Moisture", "Card 2: Moisture"),
        rb(5, "", "", "Sealed eaves keep wind-driven rain out."),
    ]
    sec = _generic_section("WHY INSTALL SECTION", blocks, "july.docx", "Matthews")
    assert sec is not None and sec.type == "types"
    sub = sec.props.get("subtitle")
    assert isinstance(sub, str) and sub.strip()          # mandatory, never empty
    # and the loud validator agrees the emitted section is valid
    assert validators.v5b_types_subtitle(_draft(sections=[sec])) == []


# ── DEFECT 2 — a new spoke/subservice is wired non-orphan by construction ──────

_PARENT_FILE = """\
export const matthewsNC: ServicePage = {
  slug: 'charlotte-nc/matthews',
  sections: [
    {
      type: 'related-services',
      label: 'Matthews Services',
      title: 'Specialized Work in Matthews',
      subtitle: 'Explore the specific service your project needs.',
      services: [
        { title: 'Siding Installation Matthews', description: 'New siding.', url: '/charlotte-nc/matthews/siding-installation/', icon: 'fas fa-house-chimney-window' },
      ],
    },
  ],
};

export const allLocationPages: ServicePage[] = [
  matthewsNC,
];
"""


def test_new_subservice_gets_an_inbound_link_from_its_parent():
    draft = _draft()
    new_text, finding = wire_inbound_link(_PARENT_FILE, draft)
    assert finding is None
    # the parent now links the child — non-orphan by construction
    assert "url: '/charlotte-nc/matthews/soffit-installation/'" in new_text
    # the pre-existing sibling card is preserved
    assert "url: '/charlotte-nc/matthews/siding-installation/'" in new_text


def test_inbound_link_wiring_is_idempotent():
    draft = _draft()
    once, _ = wire_inbound_link(_PARENT_FILE, draft)
    twice, finding = wire_inbound_link(once, draft)
    assert finding is None
    assert twice == once                      # a re-run adds nothing


def test_missing_parent_refuses_rather_than_ship_an_orphan():
    draft = _draft(url_path="charlotte-nc/nowhere/soffit-installation")
    _, finding = wire_inbound_link(_PARENT_FILE, draft)
    assert finding is not None and finding.severity == "block"
    assert finding.code == "orphan_no_parent"


def test_parent_without_related_services_refuses():
    no_rs = """\
export const matthewsNC: ServicePage = {
  slug: 'charlotte-nc/matthews',
  sections: [ { type: 'content-block', label: 'x', title: 'y', content: ['z'] } ],
};
export const allLocationPages: ServicePage[] = [ matthewsNC ];
"""
    _, finding = wire_inbound_link(no_rs, _draft())
    assert finding is not None and finding.severity == "block"
    assert finding.code == "orphan_no_related_services"


def test_hub_page_is_not_wired_here():
    """A 1-segment hub has no parent in the location data — out of scope, no finding."""
    draft = _draft(url_path="charlotte-nc", page_kind="hub")
    text, finding = wire_inbound_link(_PARENT_FILE, draft)
    assert finding is None and text == _PARENT_FILE


# ── DEFECT 3 — an over-band metaDescription is CURATE, not a shipped WARN ──────

def test_meta_over_160_is_curate_and_holds_the_page():
    over = ("Professional soffit installation in Matthews, NC. Vented, solid, vinyl, "
            "aluminum, fiber cement. GAF Master Elite. HOA documentation. Free estimate. "
            "Call today for a fast quote.")
    assert effective_len(over) > 160
    fs = validators.v2b_meta_description(_draft(meta_description=over))
    assert [f.code for f in fs] == ["meta_description_too_long"]
    assert fs[0].severity == "curate"                     # HELD (exit 15), not shipped
    assert fs[0].is_curate


def test_meta_over_band_code_is_a_curation_code():
    """Registered so a careless severity edit can never make it advisory."""
    assert "meta_description_too_long" in CURATION_CODES


def test_meta_in_band_is_clean():
    # Content Team Operating Standard (2026-07-29) §04: 130-150, never outside.
    ok = ("Professional soffit installation in Matthews, NC by Acme Roofing, GAF "
          "Master Elite certified since 2000. Free written estimate today.")
    assert validators.META_DESC_MIN <= effective_len(ok) <= validators.META_DESC_MAX_EFFECTIVE, effective_len(ok)
    assert validators.v2b_meta_description(_draft(meta_description=ok)) == []


def test_meta_under_band_is_only_a_warn():
    """Short is below-optimal, not build-breaking — it must NOT hold the page."""
    short = "Soffit installation in Matthews, NC. Free estimate."
    assert effective_len(short) < validators.META_DESC_MIN
    fs = validators.v2b_meta_description(_draft(meta_description=short))
    assert [f.code for f in fs] == ["meta_description_length"]
    assert fs[0].severity == "warn"


def test_emit_curate_proposes_a_boundary_safe_trim():
    over = ("Professional soffit installation in Matthews, NC. Vented, solid, vinyl, "
            "aluminum, fiber cement. GAF Master Elite. HOA documentation. Free estimate. "
            "Call today for a fast quote.")
    draft = _draft(meta_description=over)
    f = validators.v2b_meta_description(draft)[0]
    fix = validators.propose_fix(draft, f)
    assert str(validators.META_DESC_MAX_EFFECTIVE) in fix and "trim" in fix.lower()
