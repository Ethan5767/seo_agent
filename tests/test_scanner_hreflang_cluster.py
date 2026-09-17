from pipeline.scanner.validate import hreflang_cluster_rows


def test_hreflang_cluster_requires_return_links_and_live_targets():
    pages = [
        {"url": "https://example.test/en/", "status": 200, "html": '<link rel="alternate" hreflang="fr" href="https://example.test/fr/">'},
        {"url": "https://example.test/fr/", "status": 404, "html": '<link rel="alternate" hreflang="en" href="https://example.test/en/">'},
    ]
    rows = hreflang_cluster_rows(pages)
    codes = {row["code"] for row in rows}
    assert "valid.hreflang_broken_target" in codes
