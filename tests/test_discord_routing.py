"""Routing tests for Discord intake — BUG-012, BUG-013.

The dangerous case is Pat: ONE channel (#blueline_mechanical) is the shared
drop point for TWO client sites, North (blueline.example.com) and South
(blueline.example.com). Mapping that channel to a single slug files every
North drop as South, silently, and a cycle published to the wrong division is
not something a gate downstream can catch.

So the rule these tests lock down: on a shared channel, route confidently or
route to `unrouted`. Never pick between two clients on a coin flip.
"""

import pytest

from pipeline.intake.discord_intake import route

Pat = "1000000000000000001"  # shared two-division channel
Dana = "1000000000000000002"  # single-client channel

MAPPING = {
    Dana: "acme-roofing",
    Pat: {
        "slugs": ["blueline-hvac", "blueline-hvac-north"],
        "hints": {
            "blueline-hvac": ["south", "florida", "Blueline industries", "bluelinemechanical"],
            "blueline-hvac-north": ["north", "bluelinemech", "blh north", "new jersey"],
        },
    },
}
SLUGS = ["acme-roofing", "northstar-landscaping", "crestline-restoration", "blueline-hvac", "blueline-hvac-north"]


def r(filename, text="", channel=Pat):
    return route(filename, text, channel, MAPPING, SLUGS)


# ── single-client channel still short-circuits ──

def test_single_client_channel_maps_directly():
    assert r("anything at all.docx", channel=Dana) == "acme-roofing"


# ── shared channel: filename disambiguates ──

@pytest.mark.parametrize("filename,expected", [
    ("BLH North - July 2026 Work File.docx", "blueline-hvac-north"),
    ("bluelinemech july work file.docx", "blueline-hvac-north"),
    ("Blueline Industries - July 2026.docx", "blueline-hvac"),
    ("BLH Florida July.docx", "blueline-hvac"),
    ("south division content.docx", "blueline-hvac"),
    ("New Jersey location pages.docx", "blueline-hvac-north"),
])
def test_shared_channel_routes_by_filename(filename, expected):
    assert r(filename) == expected


def test_message_body_can_disambiguate_when_filename_cannot():
    assert r("work-file.docx", "here's the north division stuff") == "blueline-hvac-north"
    assert r("work-file.docx", "florida pages for this cycle") == "blueline-hvac"


# ── the important one: refuse to guess ──

def test_ambiguous_filename_is_unrouted_not_a_coin_flip():
    """No hint matches -> a human triages. Never default to one division."""
    assert r("July 2026 Work File.docx") == "unrouted"
    assert r("work-file.docx") == "unrouted"
    assert r("content.docx", "here is this month's content") == "unrouted"


def test_a_tie_between_two_clients_is_unrouted():
    """Equal-length hints for both divisions must not silently pick one."""
    # "north" (5) and "south" (5) both present and the same length
    assert r("north and south combined.docx") == "unrouted"


def test_longer_hint_wins_over_shorter():
    """'Blueline industries' (20) beats 'north' (5) when both appear."""
    assert r("Blueline Industries north office update.docx") == "blueline-hvac"


# ── regression: the slug mismatch that orphaned Discord content ──

#: THE canonical slug set (Alex, 2026-07-31): client_slug in each client repo's
#: docs/client-config.yml is authoritative. _registry.yaml, ~/.aeo-tracker/ and
#: foundation-backlinks/clients/ all match it. This REVERSES the BUG-012-era
#: intake slugs (northstar-landscaping / crestline-restoration), which existed only in the two
#: v2 intake configs and are now retired.
CANONICAL = {"acme-roofing", "northstar-landscaping", "crestline-restoration",
             "blueline-hvac", "blueline-hvac-north"}


def test_slugs_are_the_client_repo_slugs():
    """Discord must speak the same slug as the client repos (BUG-012's fix,
    re-anchored to the repo-config slugs as canonical)."""
    for s in SLUGS:
        assert s in CANONICAL
    # retired intake-only slug shapes must never come back
    assert "northstar-topsoil" not in SLUGS          # person/brand hybrids
    assert "lee-crestline" not in SLUGS
    assert "blueline_mechanical" not in SLUGS        # underscores are not kebab-case


def test_committed_intake_configs_use_canonical_slugs():
    """The committed intake configs (the .example files, in this template) must
    agree on one canonical kebab-case slug set — Discord and Drive speaking
    different slugs is how content gets filed to the wrong client."""
    import re
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    kebab = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    dis = yaml.safe_load((root / "config/discord-intake.example.yml").read_text())
    dis_slugs = set()
    for v in (dis.get("discord") or {}).get("channels", {}).values():
        slugs = v.get("slugs", [v]) if isinstance(v, dict) else [v]
        for s in slugs:
            assert kebab.match(s), f"discord-intake uses non-kebab slug {s!r}"
            dis_slugs.add(s)
    drv = yaml.safe_load((root / "config/drive-intake.example.yml").read_text())
    drv_slugs = {c.get("slug") for c in drv.get("clients", [])}
    for s in drv_slugs:
        assert kebab.match(s), f"drive-intake uses non-kebab slug {s!r}"
    assert dis_slugs <= drv_slugs, (
        f"discord routes slugs the drive roster does not know: {dis_slugs - drv_slugs}")


def test_unknown_channel_falls_back_to_filename_matching():
    assert route("acme roofing july.docx", "", "999", MAPPING, SLUGS) == "acme-roofing"
    assert route("mystery.docx", "", "999", MAPPING, SLUGS) == "unrouted"
