"""Posters for the MVP: a stub green poster (no HTTP, no accounts) and the real
yellow draft-file writer. The stub records exactly what it WOULD post so the log
is honest that nothing went live yet."""
from __future__ import annotations

from pipeline.seed.gaps import Gap
from pipeline.seed.generate import Draft
from pipeline.seed.posters import (slugify, write_draft_file, stub_post, PostResult,
                                   build_devto_payload, post_devto, green_poster,
                                   build_reddit_submit, post_reddit)

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


# ── Reddit real poster ───────────────────────────────────────────────────────

REDDIT_GAP = Gap(brand="Acme", platform="reddit", topic="team widgets",
                 target_keyword="team widget", angle="a",
                 url_target="https://acme.com/widget", subreddit="smallbusiness")
REDDIT_DRAFT = Draft(gap=REDDIT_GAP, title="How we pick team widgets",
                     body="Some thoughts.",
                     brand_mention="We use Acme (https://acme.com/widget).")

REDDIT_CREDS = {"REDDIT_CLIENT_ID": "cid", "REDDIT_CLIENT_SECRET": "csec",
                "REDDIT_USERNAME": "acmebot", "REDDIT_PASSWORD": "pw"}


def _set_reddit_creds(monkeypatch):
    for k, v in REDDIT_CREDS.items():
        monkeypatch.setenv(k, v)


def test_build_reddit_submit_is_a_self_post():
    f = build_reddit_submit(REDDIT_DRAFT, "smallbusiness")
    assert f["sr"] == "smallbusiness"
    assert f["kind"] == "self"
    assert f["title"] == "How we pick team widgets"
    assert "Acme (https://acme.com/widget)" in f["text"]
    assert f["api_type"] == "json"


def test_post_reddit_loud_skip_without_creds(monkeypatch):
    for k in REDDIT_CREDS:
        monkeypatch.delenv(k, raising=False)
    res = post_reddit(REDDIT_DRAFT)
    assert res.status == "skipped"
    assert "REDDIT_" in res.detail


def test_post_reddit_draft_first_targets_profile(monkeypatch):
    _set_reddit_creds(monkeypatch)
    seen = {}

    def fake_auth(cid, csec, user, pw, ua):
        return ("tok", None)

    def fake_submit(fields, token, ua):
        seen["fields"] = fields
        return ({"json": {"errors": [],
                          "data": {"url": "https://reddit.com/r/u_acmebot/x"}}}, None)

    res = post_reddit(REDDIT_DRAFT, publish=False, auth=fake_auth, submit=fake_submit)
    assert res.status == "posted"
    # draft-first: not published → posted to the account's own profile, not the sub
    assert seen["fields"]["sr"] == "u_acmebot"
    assert res.url == "https://reddit.com/r/u_acmebot/x"


def test_post_reddit_publish_targets_subreddit(monkeypatch):
    _set_reddit_creds(monkeypatch)
    seen = {}

    def fake_auth(cid, csec, user, pw, ua):
        return ("tok", None)

    def fake_submit(fields, token, ua):
        seen["fields"] = fields
        return ({"json": {"errors": [],
                          "data": {"url": "https://reddit.com/r/smallbusiness/y"}}}, None)

    res = post_reddit(REDDIT_DRAFT, publish=True, auth=fake_auth, submit=fake_submit)
    assert res.status == "posted"
    assert seen["fields"]["sr"] == "smallbusiness"


def test_post_reddit_publish_without_subreddit_is_loud_skip(monkeypatch):
    _set_reddit_creds(monkeypatch)
    g = Gap(brand="Acme", platform="reddit", topic="t", target_keyword="k",
            angle="a", url_target="https://acme.com")  # no subreddit
    d = Draft(gap=g, title="T", body="b", brand_mention="Acme.")
    res = post_reddit(d, publish=True,
                      auth=lambda *a: ("tok", None), submit=lambda *a: ({}, None))
    assert res.status == "skipped"
    assert "subreddit" in res.detail


def test_post_reddit_auth_error_is_loud_skip(monkeypatch):
    _set_reddit_creds(monkeypatch)

    def fake_auth(cid, csec, user, pw, ua):
        return (None, "HTTP 401 from reddit token")

    res = post_reddit(REDDIT_DRAFT, auth=fake_auth, submit=lambda *a: ({}, None))
    assert res.status == "skipped"
    assert "401" in res.detail


def test_post_reddit_api_errors_are_loud_skip(monkeypatch):
    _set_reddit_creds(monkeypatch)

    def fake_submit(fields, token, ua):
        return ({"json": {"errors": [["RATELIMIT", "try later", "vdelay"]]}}, None)

    res = post_reddit(REDDIT_DRAFT, auth=lambda *a: ("tok", None), submit=fake_submit)
    assert res.status == "skipped"
    assert "RATELIMIT" in res.detail


def test_green_poster_routes_reddit_when_live(monkeypatch):
    _set_reddit_creds(monkeypatch)

    def fake_auth(cid, csec, user, pw, ua):
        return ("tok", None)

    def fake_submit(fields, token, ua):
        return ({"json": {"errors": [], "data": {"url": "https://reddit.com/x"}}}, None)

    poster = green_poster(live=True, publish=False,
                          reddit_auth=fake_auth, reddit_submit=fake_submit)
    res = poster(REDDIT_DRAFT)
    assert res.status == "posted"
    assert res.url == "https://reddit.com/x"
