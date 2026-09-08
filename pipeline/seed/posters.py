"""MVP posters. `stub_post` is the green-tier stand-in: it performs NO HTTP and
requires NO account — it records what it would post so the log never claims a
live post that did not happen. `write_draft_file` is the real yellow-tier action:
it writes a markdown draft for a human to review and post by hand.

Real green posters (post_devto, post_medium, ...) are added post-MVP as
identical-shape functions that replace stub_post — one per platform, env creds,
loud skip on missing creds, following pipeline/audit/providers.py."""
from __future__ import annotations

import os
import re
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
