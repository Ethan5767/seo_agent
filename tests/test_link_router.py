"""Tests for shared-link routing — folder first, then contents, refuse on conflict.

The failure this guards against: publishing one client's cycle to another
client's website. No downstream gate can catch it, because the content is
perfectly valid — it is just on the wrong company's site. So every ambiguous
case must return `unrouted`.
"""

import pytest

from pipeline.intake.link_router import (
    extract_file_id,
    resolve,
    route_by_content,
    signatures,
)

CLIENTS = [
    {"slug": "acme-roofing", "domain": "acmeroofing.example",
     "aliases": ["Dana acme", "acme roofing", "acme"]},
    {"slug": "northstar-landscaping", "domain": "northstar.example",
     "aliases": ["Northstar Landscaping", "Casey northstar", "northstar"]},
    {"slug": "blueline-hvac", "domain": "bluelineindustries.example",
     "aliases": ["Blueline industries", "Casey Blueline & sons", "blh"]},
    {"slug": "blueline-hvac-north", "domain": "bluelinenj.example",
     "aliases": ["Blueline Mechanical north", "Blueline north", "blh north"]},
    {"slug": "crestline-restoration", "domain": "crestline.example",
     "aliases": ["crestline restorations", "crestline restoration"]},
]
SIGS = signatures(CLIENTS)
FOLDERS = {"FOLDER_ACME": "acme-roofing", "FOLDER_NORTH": "blueline-hvac-north"}


# ── link parsing ──

@pytest.mark.parametrize("url,expected", [
    ("https://docs.google.com/document/d/1b1rJgmyl7ebaZAKONnX8Jkh6vsL0zpF3/edit?usp=sharing",
     "1b1rJgmyl7ebaZAKONnX8Jkh6vsL0zpF3"),
    ("https://drive.google.com/file/d/1wG1PYXdGCJqJRAeVrON4oK3sO2obOx37/view",
     "1wG1PYXdGCJqJRAeVrON4oK3sO2obOx37"),
    ("https://drive.google.com/drive/folders/1Xy4G_nALxbVXFENE-sfRC_jK_mWAdN79",
     "1Xy4G_nALxbVXFENE-sfRC_jK_mWAdN79"),
    ("https://docs.google.com/document/d/1aGzyj-RKg69wgG2MjVeQDAbpI2e9uPJ/edit?tab=t.33dze",
     "1aGzyj-RKg69wgG2MjVeQDAbpI2e9uPJ"),
])
def test_extract_file_id_handles_googles_link_shapes(url, expected):
    assert extract_file_id(url) == expected


def test_extract_file_id_ignores_non_drive_urls():
    assert extract_file_id("https://example.com/page") is None
    assert extract_file_id("") is None


# ── signatures come from clients.yml, not a hand-kept list ──

def test_signatures_include_domain_and_bare_brand():
    assert "acmeroofing.example" in SIGS["acme-roofing"]
    assert "acmeroofing" in SIGS["acme-roofing"]


def test_signatures_drop_short_aliases_that_would_false_positive():
    """'blh' appears inside ordinary words; it must never be a signature."""
    assert "blh" not in SIGS["blueline-hvac"]


# ── content routing ──

def test_content_identifies_the_dominant_client():
    text = "Service page content for Acme Roofing. " * 20 + "Visit acmeroofing.example for roofing."
    slug, scores = route_by_content(text, SIGS)
    assert slug == "acme-roofing"
    assert scores["acme-roofing"] > 0


def test_two_clients_in_one_doc_is_not_routed():
    """A shared template or cross-reference must go to a human, not a coin flip."""
    text = ("acmeroofing.example acme acme " * 5) + ("northstar.example northstar northstar " * 5)
    slug, _ = route_by_content(text, SIGS)
    assert slug is None


def test_a_single_passing_mention_is_not_enough():
    slug, _ = route_by_content("Some generic copy mentioning acme once.", SIGS)
    assert slug is None


def test_the_two_blueline2_divisions_are_distinguishable():
    north = "bluelinenj.example " * 10 + "Blueline north content"
    south = "bluelineindustries.example " * 10 + "Blueline industries florida"
    assert route_by_content(north, SIGS)[0] == "blueline-hvac-north"
    assert route_by_content(south, SIGS)[0] == "blueline-hvac"


# ── combining the signals ──

def test_folder_alone_routes_a_doc_with_no_content_signal():
    v = resolve({"parents": ["FOLDER_ACME"]}, [], "generic copy", FOLDERS, SIGS)
    assert v.slug == "acme-roofing" and v.how == "folder"


def test_content_alone_routes_a_team_owned_share_with_no_parents():
    """The real case: 78 links in Discord, none with a visible parent."""
    v = resolve({"parents": []}, [], "acmeroofing.example acmeroofing acmeroofing acmeroofing", FOLDERS, SIGS)
    assert v.slug == "acme-roofing" and v.how == "content"


def test_both_signals_agreeing_is_the_strongest_result():
    v = resolve({"parents": ["FOLDER_ACME"]}, [], "acmeroofing.example acmeroofing acmeroofing", FOLDERS, SIGS)
    assert v.slug == "acme-roofing" and v.how == "folder+content"


def test_conflict_between_folder_and_content_refuses_to_route():
    """A doc filed under North whose body is all Acme. Never publish that."""
    v = resolve({"parents": ["FOLDER_NORTH"]}, [],
                "acmeroofing.example acmeroofing acmeroofing acmeroofing", FOLDERS, SIGS)
    assert v.slug is None
    assert v.how == "conflict"
    assert "blueline-hvac-north" in v.detail and "acme-roofing" in v.detail


def test_ancestors_are_walked_not_just_direct_parents():
    v = resolve({"parents": ["SOME_MONTH_FOLDER"]}, ["SOME_CYCLE_FOLDER", "FOLDER_ACME"],
                "generic", FOLDERS, SIGS)
    assert v.slug == "acme-roofing"


def test_no_signal_anywhere_is_unrouted():
    v = resolve({"parents": []}, [], "generic marketing copy", FOLDERS, SIGS)
    assert v.slug is None and v.how == "none"
    assert not v.routed
