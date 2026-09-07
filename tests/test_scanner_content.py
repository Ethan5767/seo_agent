from pipeline.scanner.content import content_rows

THIN = "<html><body><p>hi there</p></body></html>"
RICH = ("<html><body>" + "<h2>A</h2><h2>B</h2><h2>C</h2>"
        "<table><tr><td>2024: 45%</td></tr></table>"
        "<p>" + ("word " * 900) + "</p></body></html>")


def test_thin_prose_flags_low_info_gain():
    by = {r["what"]: r for r in content_rows(THIN)}
    assert by["Content depth"]["severity"] == "warn"
    assert by["Original data"]["severity"] == "warn"
    assert by["Comprehensiveness"]["severity"] == "warn"


def test_rich_page_passes():
    by = {r["what"]: r for r in content_rows(RICH)}
    assert by["Content depth"]["severity"] == "ok"
    assert by["Original data"]["severity"] == "ok"        # has a table
    assert by["Comprehensiveness"]["severity"] == "ok"    # 3 H2s
