"""Tests for Drive intake selection logic — BUG-001, BUG-002, BUG-008, BUG-009.

These cover the pure functions only. Everything here is deliberately reachable
without the Google API client: `drive_intake` imports the google libraries inside
functions, not at module scope, so selection logic is testable with no network,
no credentials, and no mocks.

Each test names the bug it locks down. If one of these goes red, a real
production failure mode has come back.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pipeline.intake.drive_intake import (
    file_fingerprint,
    is_archive_folder,
    is_settling,
    parse_month_folder,
)


# ── BUG-001: month folder names are the selector, so parsing must be tolerant ──

@pytest.mark.parametrize("name,expected", [
    # The two conventions actually in use across client Drives
    ("January 2026", (2026, 1)),
    ("July 2026", (2026, 7)),
    ("1. January", (2026, 1)),
    ("7. July", (2026, 7)),
    ("12. December", (2026, 12)),
    # Variants that show up when a human types the folder name
    ("01 - January", (2026, 1)),
    ("Jan 2026", (2026, 1)),
    ("Jul 2026", (2026, 7)),
    ("2026-07", (2026, 7)),
    ("2026_07", (2026, 7)),
    ("May", (2026, 5)),
    ("  July 2026  ", (2026, 7)),
    # An explicit year in the name always beats the default
    ("March 2025", (2025, 3)),
])
def test_parse_month_folder_accepts_real_names(name, expected):
    assert parse_month_folder(name, default_year=2026) == expected


@pytest.mark.parametrize("name", [
    "GBP", "Client Worksheet", "Meridian Materials", "Worksheets",
    "From Team", "Client Work", "GSC Data", "Archive", "", "   ",
    "Monthly Reports", "13. Smarch",
])
def test_parse_month_folder_rejects_non_months(name):
    """A false positive here would silently redirect the whole cycle."""
    assert parse_month_folder(name, default_year=2026) is None


def test_parse_month_folder_needs_a_year_when_none_is_given():
    assert parse_month_folder("January", default_year=None) is None
    assert parse_month_folder("January", default_year=2026) == (2026, 1)


# ── BUG-008: an archive folder must never be mistaken for the live one ──

@pytest.mark.parametrize("name", [
    "OLD | Casey - Northstar Landscaping",
    "Archive", "Archives", "ARCHIVED backup", "Deprecated",
    "Superseded", "DO NOT USE", "Golden Roofing OLD",
])
def test_is_archive_folder_detects_archives(name):
    assert is_archive_folder(name) is True


@pytest.mark.parametrize("name", [
    "Casey - Northstar Landscaping",
    "Pat - Casey Blueline & Sons",
    "Dana Oms - Acme Roofing",
    "Lee - Crestline Restoration - roofing",
    # Regression: a substring test flags these because of the "old" inside
    # "Gold". Both are live-client shaped names and must NOT be filtered.
    "Gold Standard",
    "Goldsmith Contracting",
    "Golden Gate Roofing",
])
def test_is_archive_folder_does_not_flag_live_folders(name):
    assert is_archive_folder(name) is False


# ── BUG-009: one living Doc, edited all month ──

def test_fingerprint_prefers_md5_then_version_then_mtime():
    assert file_fingerprint({"md5Checksum": "abc", "version": "9", "modifiedTime": "t"}) == "abc"
    # Native Google Docs have NO md5 — version is what makes them trackable
    assert file_fingerprint({"version": "105", "modifiedTime": "t"}) == "105"
    assert file_fingerprint({"modifiedTime": "t"}) == "t"
    assert file_fingerprint({}) == ""


def test_fingerprint_changes_when_a_google_doc_is_edited():
    """The real scenario: same file id, same name, new version after an edit."""
    before = {"id": "x", "version": "105", "modifiedTime": "2026-07-27T10:47:13Z"}
    after = {"id": "x", "version": "106", "modifiedTime": "2026-07-28T09:02:00Z"}
    assert file_fingerprint(before) != file_fingerprint(after)


def test_settle_window_holds_back_a_doc_being_edited_right_now():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)
    editing_now = {"modifiedTime": now.isoformat().replace("+00:00", "Z")}
    finished = {"modifiedTime": (now - timedelta(hours=30)).isoformat().replace("+00:00", "Z")}
    assert is_settling(editing_now, cutoff) is True
    assert is_settling(finished, cutoff) is False


def test_settle_window_disabled_lets_everything_through():
    now = datetime.now(timezone.utc)
    assert is_settling({"modifiedTime": now.isoformat().replace("+00:00", "Z")}, None) is False


def test_settle_window_does_not_crash_on_a_bad_timestamp():
    """Never drop a file because its timestamp was unparseable — fail open."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
    assert is_settling({"modifiedTime": "not-a-date"}, cutoff) is False
    assert is_settling({}, cutoff) is False
