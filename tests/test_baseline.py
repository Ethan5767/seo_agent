"""baseline.py — the pre-existing-debt ratchet. Protects the gates from being
silently disarmed and stops regressions being laundered into 'accepted debt'.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.lib import baseline as bl

BAD_PAGE = (
    "<!DOCTYPE html><html><head><title>Roofing in Town, NC</title></head>"
    "<body><main><h1>Roofing</h1><h2>Our Services</h2>"
    "<p>We install and repair roofs across the area.</p></main></body></html>"
)


# ── fingerprint determinism + measured-quantity exclusion ────────────────────

def test_fingerprint_is_deterministic():
    a = bl.fingerprint("capsule_check", "capsule.interrogative_h2", "/roofing/", "ctx", 0)
    b = bl.fingerprint("capsule_check", "capsule.interrogative_h2", "/roofing/", "ctx", 0)
    assert a == b and len(a) == 16


def test_fingerprint_excludes_measured_quantities():
    """`detail` carries word/sentence counts and byte sizes. Two findings that
    differ ONLY in detail must share a fingerprint — else a page getting slightly
    worse silently 'becomes new' and breaks the ratchet."""
    f1 = bl.Finding("capsule_check", "capsule.answer_first", "/roofing/", detail="words=45 sentences=2")
    f2 = bl.Finding("capsule_check", "capsule.answer_first", "/roofing/", detail="words=999 sentences=9")
    assert f1.fingerprint == f2.fingerprint


def test_fingerprint_context_whitespace_normalized():
    a = bl.Finding("check_headings", "case", "/x/", context="Our  Team").fingerprint
    b = bl.Finding("check_headings", "case", "/x/", context="Our Team").fingerprint
    assert a == b


def test_baseline_write_is_byte_identical(tmp_path):
    """Two records over identical findings produce byte-identical files."""
    findings = [
        bl.Finding("capsule_check", "capsule.interrogative_h2", "/roofing/"),
        bl.Finding("noncommodity_check", "noncommodity.no_proprietary_token", "/siding/"),
    ]
    findings = bl.sort_findings(bl.assign_ordinals(findings))
    b = bl.Baseline()
    for f in findings:
        b.entries[f.fingerprint] = f.to_entry("2026-07-20")
    p1, p2 = tmp_path / "a.json", tmp_path / "b.json"
    b.write(p1, "test", recorded="2026-07-20")
    b.write(p2, "test", recorded="2026-07-20")
    assert p1.read_bytes() == p2.read_bytes()


# ── NEVER_BASELINEABLE enforcement ───────────────────────────────────────────

@pytest.mark.parametrize("gate", sorted(bl.NEVER_BASELINEABLE))
def test_assert_baselineable_refuses_safety_gates(gate):
    with pytest.raises(bl.BaselineError):
        bl.assert_baselineable(gate)


def test_baseline_load_rejects_smuggled_safety_gate(tmp_path):
    """A baseline file that smuggles a NEVER-baselineable entry is refused on
    load — you cannot disarm forbidden_sweep by editing the JSON."""
    doc = {
        "schema": bl.SCHEMA,
        "project": "evil",
        "entries": [{
            "gate": "forbidden_sweep",
            "code": "forbidden_phrase",
            "fingerprint": "deadbeefdeadbeef",
            "location": "/x/ [we waive your deductible]",
            "recorded": "2026-07-20",
        }],
    }
    p = tmp_path / "gate-baseline.json"
    p.write_text(json.dumps(doc))
    with pytest.raises(bl.BaselineError):
        bl.Baseline.load(p)


def test_cli_refuses_safety_gate_exit_3(make_project):
    proj = make_project()
    r = subprocess.run(
        [sys.executable, "-m", "pipeline.lib.baseline",
         "--project", str(proj), "--gates", "forbidden_sweep"],
        capture_output=True, text=True,
    )
    assert r.returncode == 3, f"expected exit 3, got {r.returncode}\n{r.stderr}"


# ── partition: new finding caught, baselined ones silent ─────────────────────

def test_partition_isolates_new_from_baselined():
    baselined = bl.Finding("capsule_check", "capsule.interrogative_h2", "/roofing/")
    new = bl.Finding("capsule_check", "capsule.interrogative_h2", "/siding/")
    b = bl.Baseline([baselined.to_entry("2026-07-20")])
    v = bl.partition("capsule_check", [baselined, new], b)
    assert [f.location for f in v.preexisting] == ["/roofing/"]
    assert [f.location for f in v.new] == ["/siding/"]
    assert v.blocking == v.new


# ── anti-laundering: the ratchet CLI (exit codes 2 / 1 / 0) ──────────────────

def _run_baseline(proj: Path, bl_path: Path, *flags):
    return subprocess.run(
        [sys.executable, "-m", "pipeline.lib.baseline",
         "--project", str(proj), "--out", str(bl_path),
         "--gates", "capsule_check", *flags],
        capture_output=True, text=True,
    )


def test_ratchet_full_lifecycle(make_project):
    """Record -> re-record refused (exit 2) -> a new finding blocks --check
    (exit 1) and cannot be laundered by --refresh alone (exit 1); only
    --accept-new grows the baseline (exit 0)."""
    proj = make_project(pages={"/roofing/": BAD_PAGE})
    bl_path = proj / "docs" / "gate-baseline.json"

    # 1. initial record — one pre-existing capsule finding accepted as debt
    r = _run_baseline(proj, bl_path)
    assert r.returncode == 0, f"initial record failed: {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert bl_path.is_file()
    recorded = json.loads(bl_path.read_text())
    assert recorded["total"] == 1

    # 2. re-recording over an existing baseline is refused (laundering guard)
    r = _run_baseline(proj, bl_path)
    assert r.returncode == 2, f"expected exit 2 on re-record, got {r.returncode}\n{r.stderr}"

    # 3. introduce a NEW finding on a second page
    (proj / "out" / "siding").mkdir(parents=True, exist_ok=True)
    (proj / "out" / "siding" / "index.html").write_text(BAD_PAGE)

    # --check must FAIL on the new finding (exit 1)
    r = _run_baseline(proj, bl_path, "--check")
    assert r.returncode == 1, f"expected exit 1 on new finding, got {r.returncode}\n{r.stdout}"

    # --refresh alone refuses to GROW the baseline (exit 1)
    r = _run_baseline(proj, bl_path, "--refresh")
    assert r.returncode == 1, f"--refresh must not grow the baseline, got {r.returncode}\n{r.stdout}"

    # --refresh --accept-new deliberately accepts it (exit 0)
    r = _run_baseline(proj, bl_path, "--refresh", "--accept-new")
    assert r.returncode == 0, f"--accept-new should grow, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    grown = json.loads(bl_path.read_text())
    assert grown["total"] == 2
