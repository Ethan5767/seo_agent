"""Keyword clustering — pure, offline, no model call.

Grouping is by shared head phrase, which is crude and explainable on purpose: a
cluster whose rule you can read is one an operator can argue with.
"""
from pipeline.scanner.clusters import (
    MIN_CLUSTER, cluster_rows, plan_clusters,
)

ROOFING = [
    {"what": "roof repair austin", "detail": "1,200/mo", "fix": "commercial"},
    {"what": "roof repair cost", "detail": "800/mo", "fix": "commercial"},
    {"what": "emergency roof repair", "detail": "400/mo", "fix": "commercial"},
    {"what": "metal roof installation", "detail": "600/mo", "fix": "commercial"},
    {"what": "metal roof cost", "detail": "300/mo", "fix": "commercial"},
    {"what": "gutter cleaning", "detail": "100/mo", "fix": "commercial"},
]


def test_specific_clusters_form_before_a_broad_term_can_absorb_them():
    """The defect this design exists to avoid: frequency alone picks the
    broadest term, and the broadest term claims everything. "roof" swallowed
    both real clusters into one group of five, which is the original list with a
    label on it rather than a plan."""
    heads = [c["head"] for c in plan_clusters(ROOFING)]
    assert "roof repair" in heads and "metal roof" in heads
    assert "roof" not in heads, "a single broad word must not become the cluster"


def test_a_keyword_belongs_to_exactly_one_cluster():
    clusters = plan_clusters(ROOFING)
    seen = [k for c in clusters for k in c["keywords"]]
    assert len(seen) == len(set(seen)), "a keyword appears in two clusters"


def test_nothing_is_silently_dropped():
    """A plan that loses half its input is worse than one that shows the rest."""
    clusters = plan_clusters(ROOFING)
    placed = {k for c in clusters for k in c["keywords"]}
    assert placed == {r["what"] for r in ROOFING}
    assert any(c["head"] == "unclustered" for c in clusters), "the loner needs a home"


def test_clusters_are_ordered_by_the_opportunity_they_represent():
    vols = [c["volume"] for c in plan_clusters(ROOFING) if c["head"] != "unclustered"]
    assert vols == sorted(vols, reverse=True)


def test_volume_totals_and_member_order():
    c = next(c for c in plan_clusters(ROOFING) if c["head"] == "roof repair")
    assert c["volume"] == 2400 and c["size"] == 3
    assert c["keywords"][0] == "roof repair austin", "highest volume leads"


def test_a_single_keyword_never_earns_a_page_of_its_own():
    assert MIN_CLUSTER >= 2
    only = plan_clusters([{"what": "gutter cleaning", "detail": "100/mo"}])
    assert [c["head"] for c in only] == ["unclustered"]


def test_intent_is_reported_only_when_the_members_agree():
    mixed = [
        {"what": "roof repair cost", "detail": "10/mo", "fix": "commercial"},
        {"what": "roof repair guide", "detail": "10/mo", "fix": "informational"},
    ]
    assert plan_clusters(mixed)[0]["intent"] == "", "disagreeing members claim no intent"
    agreed = [dict(r, fix="commercial") for r in mixed]
    assert plan_clusters(agreed)[0]["intent"] == "commercial"


def test_a_keyword_with_no_volume_is_still_planned():
    """Zero is a missing figure, not a reason to drop the keyword."""
    rows = [{"what": "roof repair austin"}, {"what": "roof repair cost"}]
    c = plan_clusters(rows)[0]
    assert c["size"] == 2 and c["volume"] == 0


def test_total_over_malformed_and_empty_input():
    for bad in ([], None, [None, 7, {}], [{"what": ""}], [{"detail": "5/mo"}]):
        assert plan_clusters(bad) == [] or all("head" in c for c in plan_clusters(bad))


def test_stopwords_never_become_a_cluster_head():
    rows = [{"what": "how to fix a roof"}, {"what": "how to clean a roof"}]
    heads = [c["head"] for c in plan_clusters(rows)]
    for junk in ("how", "to", "a", "how to"):
        assert junk not in heads, f"{junk!r} carries no topical signal"


def test_cluster_rows_are_info_and_never_graded():
    """A cluster is an opportunity, not a defect. Grading it would put "you have
    not written this page" in the same bucket as a broken canonical."""
    rows = cluster_rows(ROOFING)
    assert rows and all(r["severity"] == "info" for r in rows)
    assert all(r["code"].startswith("cluster.") for r in rows)
    assert all(r["what"] and r["why"] and r["fix"] for r in rows)


def test_cluster_rows_carry_their_keywords_for_the_expandable_list():
    rows = cluster_rows(ROOFING)
    top = next(r for r in rows if "roof repair" in r["code"])
    assert "roof repair austin" in top["pages"]
