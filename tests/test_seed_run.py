"""Dispatch routes each draft by tier; run_seed is the offline end-to-end with an
injected claude runner and the stub poster, so it makes no network calls and
needs no accounts. A gap whose generation fails is recorded in `dropped`, never
crashing the run."""
from __future__ import annotations

import json

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import Draft
from pipeline.seed.posters import PostResult
from pipeline.seed.run import dispatch, run_seed


def _draft(platform: str) -> Draft:
    g = Gap(brand="Acme", platform=platform, topic="t", target_keyword="k",
            angle="a", url_target="https://acme.com")
    return Draft(gap=g, title=f"Title {platform}", body="body",
                 brand_mention="Acme (https://acme.com).")


def test_dispatch_routes_by_tier(tmp_path):
    drafts = [_draft("devto"), _draft("reddit"), _draft("wikipedia"),
              _draft("mastodon")]
    results = dispatch(drafts, str(tmp_path / "drafts"))
    by_platform = {r.platform: r for r in results}
    assert by_platform["devto"].status == "posted"
    assert by_platform["reddit"].status == "queued"
    assert by_platform["wikipedia"].status == "skipped"
    assert by_platform["wikipedia"].detail == "never-auto"
    assert by_platform["mastodon"].status == "skipped"
    assert "unknown" in by_platform["mastodon"].detail


def _fake_runner(prompt: str) -> str:
    inner = {"title": "Generated", "body": "# b\nAcme rocks",
             "brand_mention": "Acme (https://acme.com/widget)."}
    return json.dumps({"result": json.dumps(inner)})


def test_run_seed_end_to_end_offline(tmp_path):
    log = run_seed(
        gaps_path="tests/fixtures/seed_gaps.json",
        out_dir=str(tmp_path),
        drafts_dir=str(tmp_path / "drafts"),
        runner=_fake_runner,
    )
    # fixture has devto(green), reddit(yellow), wikipedia(red)
    assert log["counts"]["posted"] == 1
    assert log["counts"]["queued"] == 1
    assert log["counts"]["skipped"] == 1
    assert log["mode"] == "dry-run"
    # log file written
    written = json.loads((tmp_path / "seed-log.json").read_text())
    assert written["counts"] == log["counts"]
    # yellow draft file exists
    assert (tmp_path / "drafts").exists()


def test_run_seed_records_generation_failure_as_dropped(tmp_path):
    def boom(prompt: str) -> str:
        raise RuntimeError("claude down")

    log = run_seed(
        gaps_path="tests/fixtures/seed_gaps.json",
        out_dir=str(tmp_path),
        drafts_dir=str(tmp_path / "drafts"),
        runner=boom,
    )
    assert log["counts"]["posted"] == 0
    # red (wikipedia) is skipped BEFORE generation, so it never calls the runner;
    # only the two green/yellow gaps reach generation and fail.
    assert log["counts"]["dropped"] == 2
    assert log["counts"]["skipped"] == 1
    assert any("claude down" in d["_reason"] for d in log["dropped"])
