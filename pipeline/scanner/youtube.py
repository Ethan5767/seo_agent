"""YouTube Data v3 — pull real metadata for embedded videos so we can judge
video SEO/AEO, not just whether VideoObject schema exists.

The SOP's "Video Snippet & Multimedia" step: extract the six core params
(thumbnail, title, description, upload date, duration, video URL) and confirm
crawlers can build a rich video snippet. `parse_videos` is pure (canned YouTube
API response in, video dicts out); `video_rows_full` composes the existing
schema check with the live metadata via an injectable caller.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from pipeline.scanner.extra_checks import find_video_ids, video_rows
from pipeline.scanner.rows import make_row

_row = make_row("video")


def parse_videos(doc: dict) -> list[dict]:
    """The six core params per video from a YouTube videos.list response."""
    out: list[dict] = []
    for it in (doc or {}).get("items") or []:
        sn = it.get("snippet") or {}
        cd = it.get("contentDetails") or {}
        vid = it.get("id")
        thumbs = sn.get("thumbnails") or {}
        thumb = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
        out.append({"id": vid, "title": sn.get("title", ""), "description": sn.get("description", ""),
                    "thumbnail": thumb, "published": sn.get("publishedAt", ""),
                    "duration": cd.get("duration", ""), "url": f"https://youtu.be/{vid}"})
    return out


def video_rows_full(html: str, call=None, key: str = "") -> tuple:
    """(rows, status, cost) — VideoObject schema check + live YouTube metadata."""
    ids = find_video_ids(html)
    native = "<video" in (html or "").lower()
    if not ids and not native:
        return ([_row("Video snippets", "ok",
                      "No embedded video on this page — nothing to optimise.", "passing")], "ok", 0.0)

    rows = list(video_rows(html))  # keep the existing VideoObject schema row
    if ids and key:
        call = call or _yt_fetch
        doc, err = call(ids, key)
        if err:
            rows.append(_row("Video metadata", "info",
                             f"Couldn't fetch YouTube metadata ({err}) — schema check still applies.",
                             "verify the YouTube Data API key + quota"))
        else:
            vids = parse_videos(doc)
            thin = [v for v in vids if not (v.get("description") or "").strip()]
            titles = ", ".join(v.get("title") or v.get("id") for v in vids)[:80]
            rows.append(_row("Video metadata", "warn" if thin else "ok",
                             f"{len(thin)} of {len(vids)} video(s) have no description — thin metadata weakens video SEO and AI citation."
                             if thin else
                             f"{len(vids)} video(s) carry full metadata (title, description, duration, thumbnail).",
                             "add descriptions on YouTube for those videos" if thin else "passing",
                             detail=titles))
    return rows, "ok", 0.0


def _yt_fetch(ids: list, key: str) -> tuple:
    q = urllib.parse.urlencode({"part": "snippet,contentDetails", "id": ",".join(ids), "key": key})
    try:
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/videos?{q}", timeout=30) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}"
    except Exception as exc:
        return None, type(exc).__name__
