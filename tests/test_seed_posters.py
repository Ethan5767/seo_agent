"""Posters for the MVP: a stub green poster (no HTTP, no accounts) and the real
yellow draft-file writer. The stub records exactly what it WOULD post so the log
is honest that nothing went live yet."""
from __future__ import annotations

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import Draft
from pipeline.seed.posters import (slugify, write_draft_file, stub_post, PostResult,
                                   build_devto_payload, post_devto, green_poster)

GAP = Gap(brand="Acme", platform="reddit", topic="how do you pick a team widget",
          target_keyword="team widget", angle="honest tradeoffs",
          url_target="https://acme.com/widget")
DRAFT = Draft(gap=GAP, title="How Do You Pick a Team Widget?",
              body="# Thoughts\nAcme is one option...",
              brand_mention="Acme (https://acme.com/widget) is one option.")

DEVTO_GAP = Gap(brand="Acme", platform="devto", topic="widgets",
                target_keyword="team widget", angle="a",
                url_target="https://acme.com/widget")
DEVTO_DRAFT = Draft(gap=DEVTO_GAP, title="Team Widgets", body="# W\nAcme...",
                    brand_mention="Acme (https://acme.com/widget).")


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


# ── Dev.to real poster ───────────────────────────────────────────────────────

def test_build_devto_payload_draft_by_default():
    p = build_devto_payload(DEVTO_DRAFT)
    assert p["article"]["title"] == "Team Widgets"
    assert p["article"]["body_markdown"] == "# W\nAcme..."
    assert p["article"]["published"] is False          # draft-first safety
    assert p["article"]["canonical_url"] == "https://acme.com/widget"


def test_build_devto_payload_publish_true_when_asked():
    p = build_devto_payload(DEVTO_DRAFT, published=True)
    assert p["article"]["published"] is True


def test_post_devto_loud_skip_without_key(monkeypatch):
    monkeypatch.delenv("DEVTO_API_KEY", raising=False)
    res = post_devto(DEVTO_DRAFT)
    assert res.status == "skipped"
    assert "DEVTO_API_KEY" in res.detail


def test_post_devto_posts_with_injected_call(monkeypatch):
    monkeypatch.setenv("DEVTO_API_KEY", "test-key")
    seen = {}

    def fake_call(payload, key):
        seen["payload"] = payload
        seen["key"] = key
        return ({"url": "https://dev.to/acme/team-widgets-123"}, None)

    res = post_devto(DEVTO_DRAFT, call=fake_call)
    assert res.status == "posted"
    assert res.url == "https://dev.to/acme/team-widgets-123"
    assert seen["key"] == "test-key"
    assert seen["payload"]["article"]["published"] is False


def test_post_devto_http_error_is_loud_skip(monkeypatch):
    monkeypatch.setenv("DEVTO_API_KEY", "test-key")

    def fake_call(payload, key):
        return (None, "HTTP 422 from https://dev.to/api/articles")

    res = post_devto(DEVTO_DRAFT, call=fake_call)
    assert res.status == "skipped"
    assert "422" in res.detail


def test_green_poster_stub_when_not_live():
    poster = green_poster(live=False, publish=False)
    res = poster(DEVTO_DRAFT)
    assert "would POST" in res.detail          # stub


def test_green_poster_routes_devto_when_live(monkeypatch):
    monkeypatch.setenv("DEVTO_API_KEY", "k")

    def fake_call(payload, key):
        return ({"url": "https://dev.to/x"}, None)

    poster = green_poster(live=True, publish=True, devto_call=fake_call)
    res = poster(DEVTO_DRAFT)
    assert res.status == "posted"
    assert res.url == "https://dev.to/x"


def test_green_poster_unknown_green_platform_falls_back_to_stub():
    # tumblr has no real poster yet → stub, even when live
    d = Draft(gap=Gap(brand="B", platform="tumblr", topic="t",
                      target_keyword="k", angle="a", url_target="https://b.com"),
              title="T", body="b", brand_mention="B.")
    poster = green_poster(live=True, publish=True)
    res = poster(d)
    assert "would POST to tumblr" in res.detail
