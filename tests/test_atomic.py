"""A reader never sees a half-written artifact.

Every arrow in this pipeline is a JSON file, and a plain `write_text` truncates
the file to zero bytes BEFORE it writes any content. Anything that ends the
process in that window - Ctrl-C on a long measure, an OOM kill, a runner
timeout, a full disk - leaves the next stage reading damage.

The dangerous part is that the damage is quiet. An empty `findings.json` is not
an error to the ratchet; it is a site with no findings, so every real finding
files as RESOLVED and the next worklist is empty.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from pipeline.lib.atomic import write_atomic, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]


def test_the_content_lands(tmp_path):
    p = write_json_atomic(tmp_path / "a.json", {"b": 1, "a": 2})
    assert json.loads(p.read_text()) == {"a": 2, "b": 1}


def test_the_artifact_convention_is_pretty_sorted_and_newline_terminated(tmp_path):
    # Byte-for-byte stability matters: `wf-site-plan` is asserted to be
    # byte-identical over an unchanged cycle, and these files are diffed in PRs.
    p = write_json_atomic(tmp_path / "a.json", {"b": 1, "a": 2})
    assert p.read_text() == '{\n  "a": 2,\n  "b": 1\n}\n'


def test_missing_parent_directories_are_created(tmp_path):
    p = write_json_atomic(tmp_path / "docs" / "audit" / "2026-09" / "findings.json", {})
    assert p.is_file()


def test_no_temporary_file_is_left_behind(tmp_path):
    write_json_atomic(tmp_path / "a.json", {"x": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_a_failed_write_leaves_the_previous_artifact_intact(tmp_path):
    # The whole point. A document that cannot be serialised must not have already
    # destroyed last cycle's file by the time it is discovered.
    p = tmp_path / "findings.json"
    write_json_atomic(p, {"schema": "site-health/1", "findings": [1, 2, 3]})
    before = p.read_text()

    with pytest.raises(TypeError):
        write_json_atomic(p, {"bad": {1, 2}})  # a set is not JSON

    assert p.read_text() == before
    assert [x.name for x in tmp_path.iterdir()] == ["findings.json"]


def test_an_interrupt_mid_write_leaves_the_previous_artifact_intact(tmp_path, monkeypatch):
    # KeyboardInterrupt is not an Exception, so `except Exception` would miss it -
    # and Ctrl-C during a long measure is exactly the interruption this exists for.
    p = tmp_path / "worklist.json"
    write_atomic(p, "original\n")

    real_replace = os.replace

    def boom(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        write_atomic(p, "replacement\n")
    monkeypatch.setattr(os, "replace", real_replace)

    assert p.read_text() == "original\n"
    assert [x.name for x in tmp_path.iterdir()] == ["worklist.json"], "a temp file survived"


def test_the_temp_file_is_a_sibling_not_in_tmp(tmp_path, monkeypatch):
    # A rename across filesystems is not atomic, and /tmp is very often a
    # different filesystem from the client repo being written into.
    seen = {}
    import tempfile as _t
    real = _t.mkstemp

    def spy(*a, **kw):
        seen["dir"] = kw.get("dir")
        return real(*a, **kw)

    monkeypatch.setattr(_t, "mkstemp", spy)
    write_atomic(tmp_path / "sub" / "a.json", "{}")
    assert seen["dir"] == str(tmp_path / "sub")


def test_replacing_an_existing_file_never_shortens_it_first(tmp_path, monkeypatch):
    # What a plain write_text does: truncate, then write. A reader scheduled in
    # between sees zero bytes. Here the old content is readable right up until
    # the rename.
    p = tmp_path / "a.json"
    write_atomic(p, "x" * 500)
    observed = []
    real_replace = os.replace

    def watch(src, dst):
        observed.append(Path(dst).read_text())  # what a reader would see now
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", watch)
    write_atomic(p, "y" * 3)
    assert observed == ["x" * 500], "the old file was modified before the swap"
    assert p.read_text() == "yyy"


def test_unicode_survives_the_round_trip(tmp_path):
    doc = {"title": "Rénovation de toiture — Montréal", "q": "ラーメン"}
    p = write_json_atomic(tmp_path / "a.json", doc)
    assert json.loads(p.read_text()) == doc


# ── it stays the way artifacts are written ───────────────────────────────────

#: Files whose truncation silently corrupts a cycle rather than raising.
CYCLE_ARTIFACTS = ("findings.json", "worklist.json", "changelog.json",
                   "gate-baseline.json", "report.md")


def test_no_cycle_artifact_is_written_with_a_plain_write_text():
    offenders = []
    for path in sorted((ROOT / "pipeline").rglob("*.py")):
        if path.name == "atomic.py":
            continue
        body = re.sub(r'"""[\s\S]*?"""', "", path.read_text())
        for i, line in enumerate(body.splitlines(), 1):
            if ".write_text(" not in line and "json.dump(" not in line:
                continue
            if any(name in line for name in CYCLE_ARTIFACTS):
                offenders.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "a cycle artifact is written non-atomically; use write_json_atomic:\n  "
        + "\n  ".join(offenders)
    )
