from pipeline.scanner.index_reconcile import reconcile_index


def test_reconcile_reports_index_buckets_and_uninspected_urls():
    rows = reconcile_index(
        {"https://example.test/", "https://example.test/about"},
        {"https://example.test/", "https://example.test/about", "https://example.test/contact"},
        [
            {"url": "https://example.test/", "indexed": True},
            {"url": "https://example.test/about", "coverageState": "Crawled - currently not indexed"},
        ],
    )
    by_code = {row["code"]: row for row in rows}
    assert by_code["index.indexed"]["severity"] == "ok"
    assert by_code["index.crawled_not_indexed"]["severity"] == "error"
    assert by_code["index.not_inspected"]["detail"] == "1 URL(s)"


def test_reconcile_degrades_honestly_without_search_console_data():
    rows = reconcile_index(set(), set(), None)
    assert rows[0]["code"] == "index.gsc_connection_required"
    assert rows[0]["confidence"] == "low"
