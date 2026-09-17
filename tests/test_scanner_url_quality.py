from pipeline.scanner.url_quality import url_quality_rows

def test_url_quality_flags_mixed_protocol_and_case():
    rows = url_quality_rows(["https://example.com/a", "http://example.com/A/"])
    codes = {r["code"] for r in rows}
    assert "url.url_protocol_consistency" in codes
    assert "url.url_case_consistency" in codes
