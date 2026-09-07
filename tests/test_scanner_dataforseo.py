"""DataForSEO ranked-keywords parser + caller (offline, canned response)."""
from pipeline.scanner.dataforseo import (
    parse_ranked_keywords, ranked_keywords, cost_of, result_items,
)


def test_cost_of_reads_top_level_cost():
    assert cost_of({"cost": 0.0123}) == 0.0123
    assert cost_of({}) == 0.0
    assert cost_of({"cost": "bad"}) == 0.0


def test_result_items_digs_the_nest():
    assert result_items({"tasks": [{"result": [{"items": [{"k": 1}]}]}]}) == [{"k": 1}]
    assert result_items({}) == []
    assert result_items({"tasks": []}) == []

# A minimal response mirroring DataForSEO's ranked_keywords shape.
DOC = {"cost": 0.0123, "tasks": [{"result": [{"items": [
    {"keyword_data": {"keyword": "hospital phnom penh",
                      "keyword_info": {"search_volume": 1200}},
     "ranked_serp_element": {"serp_item": {"rank_absolute": 3}}},
    {"keyword_data": {"keyword": "best clinic cambodia",
                      "keyword_info": {"search_volume": 300}},
     "ranked_serp_element": {"serp_item": {"rank_absolute": 18}}},
    {"keyword_data": {"keyword": "orienda hospital",
                      "keyword_info": {"search_volume": 90}},
     "ranked_serp_element": {"serp_item": {"rank_absolute": 55}}},
]}]}]}


def test_parse_orders_by_rank_and_grades():
    rows = parse_ranked_keywords(DOC)
    assert [r["what"].split('"')[1] for r in rows] == [
        "hospital phnom penh", "best clinic cambodia", "orienda hospital"]
    sev = {r["what"].split('"')[1]: r["severity"] for r in rows}
    assert sev["hospital phnom penh"] == "ok"      # page 1
    assert sev["best clinic cambodia"] == "warn"   # page 2-3
    assert sev["orienda hospital"] == "info"       # beyond


def test_ranked_keywords_uses_injected_call_and_reports_cost():
    rows, status, cost = ranked_keywords("x.com", call=lambda p, b: (DOC, None))
    assert status.startswith("ok:")
    assert len(rows) == 3
    assert cost == 0.0123  # the real cost DataForSEO reported


def test_call_error_degrades_to_status_not_crash():
    rows, status, cost = ranked_keywords("x.com", call=lambda p, b: (None, "skipped: creds unset"))
    assert rows == [] and "skipped" in status and cost == 0.0


# ── Task 2: Site Health card (DataForSEO on-page audit) ──────────────────────
from pipeline.scanner.dataforseo import site_audit
from pipeline.lib.baseline import Finding


def test_site_audit_maps_findings_to_rows_offline():
    fake_run = lambda d, n: (
        [Finding("dataforseo", "dfs.broken_links", "/a/", detail="404"),
         Finding("dataforseo", "dfs.orphan_page", "/b/"),
         Finding("dataforseo", "dfs.duplicate_title", "/c/")],
        "ok: crawled 20 pages")
    rows, status, cost = site_audit("x.com", max_pages=20, run=fake_run)
    by = {r["code"]: r for r in rows}
    assert by["dfs.broken_links"]["severity"] == "error"
    assert by["dfs.orphan_page"]["severity"] == "warn"
    assert by["dfs.duplicate_title"]["severity"] == "warn"
    # every row carries why + fix
    assert all(r["why"] and r["fix"] for r in rows)
    # cost is a labelled per-page estimate for the crawl
    assert "est" in status and cost > 0


def test_site_audit_empty_crawl_is_clean_not_crash():
    rows, status, cost = site_audit("x.com", run=lambda d, n: ([], "ok: 0 issues"))
    assert rows == []
