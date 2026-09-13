from pipeline.scanner.onpage_audit import parse_onpage_checks, site_audit_full, CHECKS


def test_map_has_many_checks():
    assert len(CHECKS) >= 35  # site-wide audit breadth


def test_parse_flags_problems_and_counts_pages():
    pages = [
        {"checks": {"no_title": True, "is_4xx_code": False, "is_https": True, "seo_friendly_url": True}},
        {"checks": {"no_title": True, "broken_links": True, "is_https": True, "seo_friendly_url": True}},
    ]
    by = {r["what"]: r for r in parse_onpage_checks(pages)}
    assert by["Missing title"]["detail"] == "2 page(s)" and by["Missing title"]["severity"] == "error"
    assert by["Broken links"]["detail"] == "1 page(s)" and by["Broken links"]["severity"] == "error"
    # good-signal flags true on every page -> a pass row
    assert by["HTTPS"]["severity"] == "ok"
    assert by["SEO-friendly URLs"]["severity"] == "ok"


def test_flagged_rows_carry_affected_page_urls():
    pages = [
        {"url": "https://x.com/a", "checks": {"no_title": True}},
        {"url": "https://x.com/b", "checks": {"no_title": True}},
    ]
    by = {r["what"]: r for r in parse_onpage_checks(pages)}
    assert by["Missing title"]["pages"] == ["https://x.com/a", "https://x.com/b"]


def test_missing_url_degrades_to_empty_pages():
    by = {r["what"]: r for r in parse_onpage_checks([{"checks": {"no_title": True}}])}
    assert by["Missing title"]["pages"] == []  # no url key → still works, just no list


def test_clean_pages_no_problem_rows():
    pages = [{"checks": {"is_https": True, "seo_friendly_url": True, "no_title": False}}]
    rows = parse_onpage_checks(pages)
    assert not any(r["severity"] in ("error", "warn") for r in rows)


def test_site_audit_full_injected_crawl():
    fake = lambda d, mp: ([{"checks": {"no_h1_tag": True, "is_https": True}}], 0.06, None)
    rows, status, cost = site_audit_full("x.com", crawl=fake)
    assert cost == 0.06 and any(r["code"] == "dfs.op.no_h1_tag" for r in rows)
    assert "check(s) flagged" in status


def test_site_audit_full_error_degrades():
    fake = lambda d, mp: ([], 0.0, "skipped: creds unset")
    rows, status, cost = site_audit_full("x.com", crawl=fake)
    assert rows == [] and "skipped" in status
