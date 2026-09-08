"""MVP posters. `stub_post` is the green-tier stand-in: it performs NO HTTP and
requires NO account — it records what it would post so the log never claims a
live post that did not happen. `write_draft_file` is the real yellow-tier action:
it writes a markdown draft for a human to review and post by hand.

Real green posters (post_devto, post_medium, ...) are added post-MVP as
identical-shape functions that replace stub_post — one per platform, env creds,
loud skip on missing creds, following pipeline/audit/providers.py."""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from pipeline.seed.generate import Draft


@dataclass
class PostResult:
    platform: str
    status: str            # "posted" | "queued" | "skipped"
    url: str | None = None
    detail: str | None = None


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:60].rstrip("-")


def write_draft_file(draft: Draft, drafts_dir: str) -> PostResult:
    os.makedirs(drafts_dir, exist_ok=True)
    slug = slugify(draft.title) or "untitled"
    path = os.path.join(drafts_dir, f"{draft.gap.platform}-{slug}.md")
    content = (
        f"# {draft.title}\n\n"
        f"> platform: {draft.gap.platform} | keyword: {draft.gap.target_keyword}\n"
        f"> brand mention: {draft.brand_mention}\n\n"
        f"{draft.body}\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return PostResult(platform=draft.gap.platform, status="queued", detail=path)


def stub_post(draft: Draft) -> PostResult:
    return PostResult(
        platform=draft.gap.platform,
        status="posted",
        url=None,
        detail=f"stub: would POST to {draft.gap.platform}: {draft.title}",
    )


# ── Dev.to — the first real green poster ─────────────────────────────────────
#
# One function, env creds only, loud skip on a missing key — the providers.py
# discipline. build_devto_payload is pure (testable); the HTTP call is injectable
# as `call` so the suite never touches the network. Draft-first: `published`
# defaults to False, so a live run creates an UNPUBLISHED Dev.to draft the
# operator verifies before anything goes public.

DEVTO_ENDPOINT = "https://dev.to/api/articles"


def build_devto_payload(draft: Draft, published: bool = False) -> dict:
    return {"article": {
        "title": draft.title,
        "body_markdown": draft.body,
        "published": published,
        "canonical_url": draft.gap.url_target,
    }}


def _http_post_devto(payload: dict, key: str):
    """(json, error). Never raises: a platform that is down is a skip, not a crash."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        DEVTO_ENDPOINT, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "api-key": key,
            # Dev.to sits behind Cloudflare, which 403s the default
            # "Python-urllib/x" UA as a bot. A real UA is required to POST.
            "User-Agent": "seo_agent-seed/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from {DEVTO_ENDPOINT}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def post_devto(draft: Draft, published: bool = False, call=None) -> PostResult:
    key = os.environ.get("DEVTO_API_KEY")
    if not key:
        return PostResult(platform="devto", status="skipped",
                          detail="no DEVTO_API_KEY")
    call = call or _http_post_devto
    resp, err = call(build_devto_payload(draft, published), key)
    if err:
        return PostResult(platform="devto", status="skipped", detail=err)
    return PostResult(platform="devto", status="posted",
                      url=(resp or {}).get("url"),
                      detail="published" if published else "draft (unpublished)")


# ── Reddit — real green poster (operator opted into auto-posting) ─────────────
#
# Reddit is strict: OAuth2 script-app creds (client id/secret + account
# user/pass), a proper User-Agent (a generic one is hard-blocked), and a target
# subreddit. A self-post is LIVE immediately — Reddit has no draft — so the
# safety gate is where it goes: draft-first (`publish=False`) posts to the
# account's OWN profile (`u_<username>`), and only `publish=True` posts to the
# real subreddit. Two HTTP calls (token, submit), both injectable for offline
# tests. Shadowban risk on fresh accounts is real; that is the operator's call.

REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_SUBMIT_URL = "https://oauth.reddit.com/api/submit"
_REDDIT_ENV = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
               "REDDIT_USERNAME", "REDDIT_PASSWORD")


def build_reddit_submit(draft: Draft, sr: str) -> dict:
    text = f"{draft.body}\n\n{draft.brand_mention}"
    return {"sr": sr, "kind": "self", "title": draft.title,
            "text": text, "api_type": "json"}


def _reddit_token(cid: str, csec: str, user: str, pw: str, ua: str):
    """(token, error). Never raises."""
    basic = base64.b64encode(f"{cid}:{csec}".encode()).decode()
    data = urllib.parse.urlencode(
        {"grant_type": "password", "username": user, "password": pw}).encode()
    req = urllib.request.Request(
        REDDIT_TOKEN_URL, data=data, method="POST",
        headers={"Authorization": f"Basic {basic}", "User-Agent": ua,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            tok = json.loads(r.read().decode()).get("access_token")
            return (tok, None) if tok else (None, "no access_token in reddit response")
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from reddit token"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _http_submit_reddit(fields: dict, token: str, ua: str):
    """(json, error). Never raises."""
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        REDDIT_SUBMIT_URL, data=data, method="POST",
        headers={"Authorization": f"bearer {token}", "User-Agent": ua,
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from {REDDIT_SUBMIT_URL}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def post_reddit(draft: Draft, publish: bool = False,
                auth=None, submit=None) -> PostResult:
    creds = {k: os.environ.get(k) for k in _REDDIT_ENV}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        return PostResult(platform="reddit", status="skipped",
                          detail=f"missing env: {', '.join(missing)}")
    user = creds["REDDIT_USERNAME"]
    sub = (draft.gap.subreddit or "").strip()
    if publish and not sub:
        return PostResult(platform="reddit", status="skipped",
                          detail="reddit --publish needs a subreddit on the gap")
    target = sub if publish else f"u_{user}"   # draft-first: own profile
    ua = os.environ.get("REDDIT_USER_AGENT") or f"seo_agent-seed/1.0 by /u/{user}"

    auth = auth or _reddit_token
    token, err = auth(creds["REDDIT_CLIENT_ID"], creds["REDDIT_CLIENT_SECRET"],
                      user, creds["REDDIT_PASSWORD"], ua)
    if err:
        return PostResult(platform="reddit", status="skipped", detail=err)

    submit = submit or _http_submit_reddit
    resp, err = submit(build_reddit_submit(draft, target), token, ua)
    if err:
        return PostResult(platform="reddit", status="skipped", detail=err)
    errors = (((resp or {}).get("json") or {}).get("errors")) or []
    if errors:
        return PostResult(platform="reddit", status="skipped",
                          detail=f"reddit api errors: {errors}")
    url = (((resp or {}).get("json") or {}).get("data") or {}).get("url")
    return PostResult(platform="reddit", status="posted", url=url,
                      detail=(f"posted to r/{sub}" if publish
                              else f"draft: posted to profile u_{user}"))


# ── green-tier router ────────────────────────────────────────────────────────
#
# Maps a green platform to its real poster; anything without one yet falls back
# to the stub, so adding a platform is one branch. `green_poster(live, ...)`
# returns the callable dispatch() uses: the stub when not live (safe default),
# the real routed poster when live.

def green_poster(live: bool, publish: bool = False, devto_call=None,
                 reddit_auth=None, reddit_submit=None):
    if not live:
        return stub_post

    def _route(draft: Draft) -> PostResult:
        p = draft.gap.platform
        if p == "devto":
            return post_devto(draft, published=publish, call=devto_call)
        if p == "reddit":
            return post_reddit(draft, publish=publish,
                               auth=reddit_auth, submit=reddit_submit)
        return stub_post(draft)  # no real poster for this platform yet

    return _route
