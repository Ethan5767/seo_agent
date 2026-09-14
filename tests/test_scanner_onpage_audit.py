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


# ── 2026-09-14: Crawl Issues on DataForSEO was blank after a clean crawl ──────

def test_a_passed_problem_check_is_a_row_not_silence():
    """25 pages, zero 4xx/broken/orphan: the parser emitted nothing for them, so
    Crawl Issues (DataForSEO) was an empty table after a successful crawl."""
    pages = [{"url": f"https://x.com/{i}", "checks": {"is_4xx_code": False, "is_broken": False, "no_title": True}}
             for i in range(3)]
    by = {r["code"]: r for r in parse_onpage_checks(pages)}
    assert by["dfs.op.is_4xx_code"]["severity"] == "ok"
    assert by["dfs.op.is_4xx_code"]["detail"] == "0 of 3 page(s)"
    assert by["dfs.op.is_broken"]["severity"] == "ok"
    assert by["dfs.op.no_title"]["severity"] == "error"


def test_a_check_dataforseo_did_not_report_gets_no_row():
    rows = parse_onpage_checks([{"checks": {"no_title": False}}])
    assert [r["code"] for r in rows] == ["dfs.op.no_title"]


def test_duplicate_labels_match_dataforseo_definitions():
    """docs.dataforseo.com/v3/on_page-pages: duplicate_title_tag is "page with
    more than one title tag", not pages sharing a title. The site-wide checks are
    duplicate_title / duplicate_description."""
    assert CHECKS["duplicate_title_tag"][0] == "Multiple title tags on a page"
    assert CHECKS["duplicate_meta_tags"][0] == "Repeated meta tags on a page"
    assert CHECKS["duplicate_title"][0] == "Duplicate page titles"
    assert CHECKS["duplicate_description"][0] == "Duplicate meta descriptions"


def test_status_counts_problems_not_passes():
    fake = lambda d, mp: ([{"checks": {"no_h1_tag": True, "is_https": True, "is_4xx_code": False}}], 0.0, None)
    rows, status, _ = site_audit_full("x.com", crawl=fake)
    assert "1 check(s) flagged" in status
    assert "passed" in status


def test_site_health_reports_site_wide_duplicates_from_duplicate_tags():
    """B-132: DataForSEO's per-page checks carry no duplicate keys; the free
    on_page/duplicate_tags endpoint does."""
    def crawl(domain, mp):
        return ([{"url": "https://x.com/a", "checks": {"no_title": False}},
                 {"url": "https://x.com/b", "checks": {"no_title": False}}], 0.0008, None, "TASK1")

    calls = []

    def call(path, payload=None, **k):
        calls.append((path, payload[0]))
        if payload[0]["type"] == "duplicate_title":
            return {"tasks": [{"result": [{"items": [
                {"accumulator": "Departments & Clinics | Orienda Hospital", "total_count": 2,
                 "pages": [{"url": "https://x.com/a"}, {"url": "https://x.com/b"}]}]}]}]}, None
        return {"tasks": [{"result": [{"items": []}]}]}, None

    rows, status, cost = site_audit_full("x.com", crawl=crawl, call=call)
    by = {r["code"]: r for r in rows}
    assert [c for c, _ in [(p, b["type"]) for p, b in calls]] == ["/v3/on_page/duplicate_tags"] * 2
    assert all(b["id"] == "TASK1" for _, b in calls)
    title = by["dfs.op.duplicate_title"]
    assert title["severity"] == "warn" and "Departments & Clinics" in title["why"]
    assert title["pages"] == ["https://x.com/a", "https://x.com/b"]
    assert by["dfs.op.duplicate_description"]["severity"] == "ok"


def test_crawl_injected_without_task_id_skips_duplicates():
    rows, _, _ = site_audit_full("x.com", crawl=lambda d, mp: ([{"checks": {"no_h1_tag": True}}], 0.0, None),
                                 call=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no task, no call")))
    assert not any("duplicate" in r["code"] for r in rows)
