"""MVP posters. `stub_post` is the green-tier stand-in: it performs NO HTTP and
requires NO account — it records what it would post so the log never claims a
live post that did not happen. `write_draft_file` is the real yellow-tier action:
it writes a markdown draft for a human to review and post by hand.

Real green posters (post_devto, post_medium, ...) are added post-MVP as
identical-shape functions that replace stub_post — one per platform, env creds,
loud skip on missing creds, following pipeline/audit/providers.py."""
from __future__ import annotations

import json
import os
import re
import urllib.error
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


# ── green-tier router ────────────────────────────────────────────────────────
#
# Maps a green platform to its real poster; anything without one yet falls back
# to the stub, so adding a platform is one dict entry. `green_poster(live, ...)`
# returns the callable dispatch() uses: the stub when not live (safe default),
# the real routed poster when live.

def green_poster(live: bool, publish: bool = False, devto_call=None):
    if not live:
        return stub_post

    def _route(draft: Draft) -> PostResult:
        if draft.gap.platform == "devto":
            return post_devto(draft, published=publish, call=devto_call)
        return stub_post(draft)  # no real poster for this platform yet

    return _route
