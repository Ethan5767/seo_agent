"""Posters for the MVP: a stub green poster (no HTTP, no accounts) and the real
yellow draft-file writer. The stub records exactly what it WOULD post so the log
is honest that nothing went live yet."""
from __future__ import annotations

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import Draft
from pipeline.seed.posters import slugify, write_draft_file, stub_post, PostResult

GAP = Gap(brand="Acme", platform="reddit", topic="how do you pick a team widget",
          target_keyword="team widget", angle="honest tradeoffs",
          url_target="https://acme.com/widget")
DRAFT = Draft(gap=GAP, title="How Do You Pick a Team Widget?",
              body="# Thoughts\nAcme is one option...",
              brand_mention="Acme (https://acme.com/widget) is one option.")


def test_slugify_basic():
    assert slugify("How Do You Pick a Team Widget?") == "how-do-you-pick-a-team-widget"


def test_slugify_trims_and_caps_length():
    assert slugify("  Hello,  World!!  ") == "hello-world"
    assert len(slugify("word " * 40)) <= 60


def test_write_draft_file_writes_and_reports(tmp_path):
    res = write_draft_file(DRAFT, str(tmp_path / "drafts"))
    assert res.platform == "reddit"
    assert res.status == "queued"
    written = (tmp_path / "drafts" / "reddit-how-do-you-pick-a-team-widget.md")
    assert written.exists()
    text = written.read_text()
    assert "How Do You Pick a Team Widget?" in text
    assert "Acme (https://acme.com/widget)" in text
    assert res.detail == str(written)


def test_stub_post_reports_would_post_without_url():
    res = stub_post(DRAFT)
    assert isinstance(res, PostResult)
    assert res.status == "posted"
    assert res.url is None
    assert "would POST to reddit" in res.detail
    assert "How Do You Pick a Team Widget?" in res.detail
