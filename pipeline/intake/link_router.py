#!/usr/bin/env python3
"""Resolve which client a shared Google Doc belongs to — by folder, then by content.

**Why this exists.** The team drops Google Doc *links* in Discord, not attachments.
The 2026-07-28 poll found **78 Drive links and zero DOCX**. Those docs live in the
team's own Drive and are shared with us, so from our account they have **no visible
parent folder** — the folder check alone cannot route them.

So routing uses two independent signals and cross-checks them:

  1. **Folder parentage (strongest).** Walk the doc's ancestors. If one is a
     client's pinned `drive_folder_id`, that is the client. Deterministic, no
     guessing. Works for anything inside the Meridian-owned tree.

  2. **Content signature.** Export the doc as text and count each client's domain
     and brand tokens, taken straight from `clients.yml`. A client wins only by a
     decisive margin over the runner-up. Verified on four real shared docs:
     674 / 1557 / 215 / 190 hits for the correct client and **zero** for any other.

  3. **Cross-check.** If folder says one client and content says another, that is a
     CONFLICT — a doc filed in the wrong folder, or the wrong link pasted. Refuse
     and flag. Publishing a cycle to the wrong client's website is not something
     any downstream gate can catch, because the content itself is valid.

Nothing here guesses. Every uncertain case returns `unrouted` for a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A client wins on content only if it beats the runner-up by this factor. Two
# clients in one doc means a cross-reference, a shared template, or the wrong
# link — all of which a human should look at.
DOMINANCE = 3.0
MIN_HITS = 3

DRIVE_ID_RE = re.compile(
    r"(?:/d/|/document/d/|/file/d/|/folders/|[?&]id=)([A-Za-z0-9_-]{20,})"
)


def extract_file_id(url: str) -> str | None:
    """Pull the Drive file id out of any of Google's link shapes."""
    m = DRIVE_ID_RE.search(url or "")
    return m.group(1) if m else None


def signatures(clients: list[dict]) -> dict[str, list[str]]:
    """Build per-client content signatures from clients.yml — no hand-maintained list.

    Domain first (strongest single token), then aliases long enough not to collide.
    Short aliases like "blh" are skipped: they appear inside ordinary words and
    would produce false hits.
    """
    out: dict[str, list[str]] = {}
    for c in clients:
        slug = c.get("slug")
        if not slug:
            continue
        toks = []
        dom = (c.get("domain") or "").strip().lower()
        if dom:
            toks.append(dom)
            toks.append(dom.rsplit(".", 1)[0])  # bare brand, e.g. "acme"
        toks += [a.strip().lower() for a in (c.get("aliases") or []) if len(a.strip()) >= 6]
        out[slug] = sorted({t for t in toks if t})
    return out


@dataclass
class Verdict:
    slug: str | None            # None => unrouted
    how: str                    # folder | content | folder+content | conflict | none
    detail: str = ""
    scores: dict = field(default_factory=dict)

    @property
    def routed(self) -> bool:
        return self.slug is not None


def route_by_folder(file_meta: dict, ancestors: list[str],
                    folder_to_slug: dict[str, str]) -> str | None:
    """Return the client slug if any ancestor is a pinned client folder."""
    for fid in [*(file_meta.get("parents") or []), *ancestors]:
        if fid in folder_to_slug:
            return folder_to_slug[fid]
    return None


def route_by_content(text: str, sigs: dict[str, list[str]]) -> tuple[str | None, dict]:
    """Count brand/domain tokens per client. Winner needs a decisive margin."""
    low = (text or "").lower()
    scores = {s: sum(low.count(t) for t in toks) for s, toks in sigs.items()}
    scores = {s: n for s, n in scores.items() if n}
    if not scores:
        return None, {}
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_slug, top_n = ranked[0]
    if top_n < MIN_HITS:
        return None, scores
    if len(ranked) > 1 and top_n < ranked[1][1] * DOMINANCE:
        return None, scores  # two clients present — a human decides
    return top_slug, scores


def resolve(file_meta: dict, ancestors: list[str], text: str,
            folder_to_slug: dict[str, str], sigs: dict[str, list[str]]) -> Verdict:
    """Combine both signals and refuse on conflict."""
    by_folder = route_by_folder(file_meta, ancestors, folder_to_slug)
    by_content, scores = route_by_content(text, sigs)

    if by_folder and by_content:
        if by_folder == by_content:
            return Verdict(by_folder, "folder+content", "both signals agree", scores)
        return Verdict(
            None, "conflict",
            f"folder says {by_folder!r} but content reads as {by_content!r} — "
            f"the doc is filed under the wrong client, or the wrong link was shared. "
            f"Refusing to route.", scores)

    if by_folder:
        return Verdict(by_folder, "folder", "matched a pinned client folder", scores)

    if by_content:
        return Verdict(by_content, "content",
                       "no visible parent folder (team-owned share); "
                       "identified from document contents", scores)

    if scores:
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:3]
        return Verdict(None, "none",
                       f"no client is dominant enough — {top}", scores)
    return Verdict(None, "none", "no client signal in folder path or contents", scores)
