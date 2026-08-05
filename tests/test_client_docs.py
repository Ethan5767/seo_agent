"""Tests for the client-repo docs contract and cycle path resolution.

The append helpers are the dangerous ones: `seo-work-log.md` and
`seo-progress.md` are append-only by contract, and both hold the only durable
record of what shipped. A bug that truncates either is unrecoverable, so the
tests below assert existing content survives every write.
"""

from pathlib import Path

import pytest

from pipeline.lib.client_docs import (
    INTAKE_ARCHIVE_FILE,
    POST_MORTEM_FILE,
    REQUIRED,
    append_progress,
    append_work_log,
    audit,
    cycle_paths,
)


# ── path resolution ──

def test_cycle_paths_are_the_canonical_layout(tmp_path: Path):
    p = cycle_paths(tmp_path, "2026-07-29")
    assert p.intake_file == tmp_path / "docs/intake-archive/2026-07-29" / INTAKE_ARCHIVE_FILE
    assert p.post_mortem == tmp_path / "docs/cycle-logs/2026-07-29" / POST_MORTEM_FILE
    assert p.work_log == tmp_path / "docs/seo-work-log.md"
    assert p.progress_log == tmp_path / "docs/seo-progress.md"


def test_cycle_paths_creates_nothing_until_ensure(tmp_path: Path):
    """Resolution must be pure — a dry run should not litter the repo."""
    p = cycle_paths(tmp_path, "2026-07-29")
    assert not p.intake_dir.exists()
    assert not p.cycle_log_dir.exists()
    p.ensure()
    assert p.intake_dir.is_dir() and p.cycle_log_dir.is_dir()


def test_ensure_is_idempotent(tmp_path: Path):
    cycle_paths(tmp_path, "2026-07-29").ensure()
    cycle_paths(tmp_path, "2026-07-29").ensure()  # must not raise


@pytest.mark.parametrize("bad", ["2026-7-9", "July 2026", "20260729", "", "2026-07-29/x"])
def test_cycle_date_must_be_iso(bad):
    """A malformed date would silently create a junk folder in a client repo."""
    with pytest.raises(ValueError):
        cycle_paths(Path("/tmp"), bad)


def test_backfill_writes_into_its_own_cycle_not_today(tmp_path: Path):
    p = cycle_paths(tmp_path, "2026-05-31")
    assert "2026-05-31" in str(p.intake_file)


# ── append helpers: history must survive ──

def test_work_log_puts_newest_at_top_and_keeps_the_old_entry(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/seo-work-log.md").write_text(
        "# SEO Work Log — x\n\nLatest run at top. **Append-only.**\n\n---\n\n"
        "## 2026-06-29 — June cycle (SHIPPED)\n\nold entry body\n"
    )
    append_work_log(tmp_path, "## 2026-07-29 — July cycle (SHIPPED)\n\nnew entry body")
    out = (tmp_path / "docs/seo-work-log.md").read_text()

    assert "old entry body" in out, "append must never destroy history"
    assert "new entry body" in out
    assert out.index("2026-07-29") < out.index("2026-06-29"), "newest must be first"
    assert out.index("Latest run at top") < out.index("2026-07-29"), "header stays on top"


def test_work_log_survives_a_file_with_no_separator(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/seo-work-log.md").write_text("# SEO Work Log — x\nno separator here\n")
    append_work_log(tmp_path, "## 2026-07-29 — entry")
    out = (tmp_path / "docs/seo-work-log.md").read_text()
    assert "no separator here" in out
    assert "2026-07-29" in out


def test_work_log_creates_the_file_when_absent(tmp_path: Path):
    append_work_log(tmp_path, "## 2026-07-29 — first ever entry")
    assert "first ever entry" in (tmp_path / "docs/seo-work-log.md").read_text()


def test_progress_appends_at_the_bottom_keeping_prior_runs(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/seo-progress.md").write_text(
        "# SEO Progress Log — x\n\nOne line per pipeline run. Append-only.\n\n---\n\n"
        "2026-06-29 — June run\n"
    )
    append_progress(tmp_path, "2026-07-29 — July run")
    out = (tmp_path / "docs/seo-progress.md").read_text()

    assert "2026-06-29 — June run" in out, "append must never destroy history"
    assert out.index("2026-06-29") < out.index("2026-07-29"), "oldest first, matching live format"


def test_repeated_appends_accumulate(tmp_path: Path):
    for i in range(3):
        append_progress(tmp_path, f"2026-07-2{i} — run {i}")
    out = (tmp_path / "docs/seo-progress.md").read_text()
    for i in range(3):
        assert f"run {i}" in out


# ── the contract itself ──

def test_audit_reports_everything_missing_on_an_empty_repo(tmp_path: Path):
    missing_req, _ = audit(tmp_path)
    assert len(missing_req) == len(REQUIRED)


def test_audit_is_clean_once_the_tree_exists(tmp_path: Path):
    for d in REQUIRED:
        t = tmp_path / d.path
        if d.is_dir:
            t.mkdir(parents=True, exist_ok=True)
        else:
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text("x")
    missing_req, _ = audit(tmp_path)
    assert missing_req == []
