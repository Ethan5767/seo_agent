from pipeline.scanner.rendering import diff_documents, rendering_rows


def test_raw_rendered_diff_flags_content_links_metadata_and_schema():
    raw = '<html><head><title>Old</title></head><body><main>short</main></body></html>'
    rendered = '<html><head><title>New</title><meta name="description" content="x"><script type="application/ld+json">{"@type":"Article"}</script></head><body><main>lots of rendered content here</main><a href="/new">new</a></body></html>'
    codes = {row["code"] for row in diff_documents("https://example.test/", raw, rendered)}
    assert {"render.content_delta", "render.link_delta", "render.metadata_delta", "render.meta_delta", "render.schema_delta"} <= codes


def test_missing_browser_is_an_explicit_low_confidence_state():
    rows = rendering_rows("https://example.test/", "<html></html>", None, "Playwright is not installed")
    assert rows[0]["code"] == "render.unavailable"
    assert rows[0]["confidence"] == "low"
