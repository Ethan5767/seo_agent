from pipeline.scanner.security import security_rows


def test_security_checks_mixed_content_and_injection_signals():
    rows = security_rows("https://example.test/", '<script src="http://evil.test/x.js"></script> viagra')
    by_code = {row["code"]: row for row in rows}
    assert by_code["security.mixed_content"]["severity"] == "error"
    assert by_code["security.injection_heuristic"]["severity"] == "warn"


def test_security_cloaking_check_compares_responses():
    rows = security_rows("https://example.test/", "", normal_html="<p>a</p>", crawler_html="<p>b</p>")
    assert next(row for row in rows if row["code"] == "security.cloaking")["severity"] == "error"
