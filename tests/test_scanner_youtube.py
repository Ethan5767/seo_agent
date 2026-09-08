"""YouTube Data v3 video metadata — pure parser + composed video audit, offline."""
from pipeline.scanner.youtube import parse_videos, video_rows_full

YT = {"items": [
    {"id": "abc123XYZ_1", "snippet": {
        "title": "How to fix a roof", "description": "Step-by-step guide with real footage.",
        "publishedAt": "2024-01-01T00:00:00Z",
        "thumbnails": {"high": {"url": "https://i.ytimg.com/abc.jpg"}}},
     "contentDetails": {"duration": "PT5M30S"}},
]}
EMBED = '<iframe src="https://www.youtube.com/embed/abc123XYZ_1"></iframe>'


def test_parse_videos_extracts_six_params():
    v = parse_videos(YT)[0]
    assert v["title"] == "How to fix a roof"
    assert v["description"].startswith("Step-by-step")
    assert v["thumbnail"].endswith("abc.jpg")
    assert v["published"] == "2024-01-01T00:00:00Z"
    assert v["duration"] == "PT5M30S"
    assert v["url"] == "https://youtu.be/abc123XYZ_1"


def test_video_rows_full_adds_metadata_when_key():
    rows, status, cost = video_rows_full(EMBED, call=lambda ids, key: (YT, None), key="k")
    whats = [r["what"] for r in rows]
    assert "Video snippets" in whats          # existing schema check kept
    assert "Video metadata" in whats           # new API metadata row
    assert cost == 0.0


def test_video_rows_full_flags_thin_metadata():
    thin = {"items": [{"id": "abc123XYZ_1", "snippet": {
        "title": "clip", "description": "", "publishedAt": "2024", "thumbnails": {}},
        "contentDetails": {"duration": "PT10S"}}]}
    rows, status, cost = video_rows_full(EMBED, call=lambda ids, key: (thin, None), key="k")
    by = {r["what"]: r for r in rows}
    assert by["Video metadata"]["severity"] == "warn"   # empty description


def test_no_video_is_ok():
    rows, status, cost = video_rows_full("<p>no video here</p>")
    assert rows[0]["severity"] == "ok"


def test_fetch_error_is_honest_skip():
    rows, status, cost = video_rows_full(EMBED, call=lambda ids, key: (None, "HTTPError"), key="k")
    by = {r["what"]: r for r in rows}
    assert by["Video metadata"]["severity"] == "info" and "couldn" in by["Video metadata"]["why"].lower()


def test_no_key_skips_api_but_keeps_schema():
    rows, status, cost = video_rows_full(EMBED, key="")   # no key → no API call
    whats = [r["what"] for r in rows]
    assert "Video snippets" in whats and "Video metadata" not in whats
