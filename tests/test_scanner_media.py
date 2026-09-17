from pipeline.scanner.media import media_rows


def test_media_tool_checks_image_attributes_and_video_signals():
    html = '<img src="/hero.jpg"><video src="/tour.mp4">video</video>'
    codes = {row["code"] for row in media_rows(html)}
    assert {"media.image_alt", "media.image_dimensions", "media.image_format", "media.video_schema", "media.video_captions"} <= codes
    assert next(row for row in media_rows(html) if row["code"] == "media.image_alt")["severity"] == "warn"


def test_media_tool_reports_a_passing_image_and_video_schema():
    html = '<img src="/hero.webp" alt="A hospital" width="1200" height="600" loading="lazy"><script type="application/ld+json">{"@type":"VideoObject"}</script>'
    rows = media_rows(html)
    assert next(row for row in rows if row["code"] == "media.image_alt")["severity"] == "ok"
    assert next(row for row in rows if row["code"] == "media.video_schema")["severity"] == "ok"
