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


# ── Task 4: Rankings (domain overview + SERP position + aggregator) ──────────
from pipeline.scanner.dataforseo import (
    parse_domain_overview, domain_overview, parse_serp_rank, serp_rank, rankings,
)

OVERVIEW_DOC = {"cost": 0.002, "tasks": [{"result": [{"items": [
    {"metrics": {"organic": {"count": 120, "etv": 3400.5, "pos_1": 4}}}]}]}]}
SERP_DOC = {"cost": 0.0011, "tasks": [{"result": [{"items": [
    {"type": "organic", "domain": "other.com", "rank_absolute": 1},
    {"type": "organic", "domain": "x.com", "rank_absolute": 5}]}]}]}


def test_domain_overview_parses_footprint():
    rows = parse_domain_overview(OVERVIEW_DOC)
    assert rows[0]["code"] == "dfs.domain_overview"
    assert "120 keywords" in rows[0]["what"]
    assert "3400" in rows[0]["fix"] or "3401" in rows[0]["fix"]


def test_serp_rank_finds_the_client_position():
    rows = parse_serp_rank(SERP_DOC, "x.com", "hospital")
    assert rows[0]["what"] == '"hospital" — rank #5' and rows[0]["severity"] == "ok"


def test_serp_rank_absent_is_a_warn():
    rows = parse_serp_rank({"tasks": [{"result": [{"items": []}]}]}, "x.com", "kw")
    assert rows[0]["severity"] == "warn" and "not in top 20" in rows[0]["what"]


def test_rankings_aggregates_and_sums_cost():
    def fake_call(path, body):
        if "ranked_keywords" in path:
            return {"cost": 0.01, "tasks": [{"result": [{"items": [
                {"keyword_data": {"keyword": "kw", "keyword_info": {"search_volume": 10}},
                 "ranked_serp_element": {"serp_item": {"rank_absolute": 2}}}]}]}]}, None
        if "domain_rank_overview" in path:
            return OVERVIEW_DOC, None
        if "serp/google" in path:
            return SERP_DOC, None
        return {}, None
    rows, status, cost = rankings("x.com", keywords=["hospital"], call=fake_call)
    assert cost == round(0.01 + 0.002 + 0.0011, 4)     # exact sum of each call
    codes = {r["code"] for r in rows}
    assert {"dfs.ranked_keyword", "dfs.domain_overview", "dfs.serp_rank"} <= codes


# ── Task 5: Keywords (volume, ideas, gap, competitors, aggregator) ───────────
from pipeline.scanner.dataforseo import (
    parse_search_volume, parse_keyword_gap, parse_competitors, keywords_card,
)


def test_search_volume_parses_flat_google_ads_items():
    doc = {"tasks": [{"result": [{"items": [
        {"keyword": "hospital phnom penh", "search_volume": 1200}]}]}]}
    rows = parse_search_volume(doc)
    assert rows[0]["code"] == "dfs.keyword_volume" and "1200/mo" in rows[0]["what"]


def test_keyword_gap_is_a_warn_opportunity():
    doc = {"tasks": [{"result": [{"items": [
        {"keyword_data": {"keyword": "icu cambodia", "keyword_info": {"search_volume": 90}}}]}]}]}
    rows = parse_keyword_gap(doc, "rival.com")
    assert rows[0]["code"] == "dfs.keyword_gap" and rows[0]["severity"] == "warn"
    assert "rival.com" in rows[0]["why"]


def test_competitors_parsed():
    doc = {"tasks": [{"result": [{"items": [{"domain": "rival.com"}]}]}]}
    assert parse_competitors(doc)[0]["what"] == "rival.com"


def test_keywords_card_aggregates_and_sums_cost():
    def fake_call(path, body):
        if "competitors_domain" in path:
            return {"cost": 0.005, "tasks": [{"result": [{"items": [{"domain": "rival.com"}]}]}]}, None
        if "domain_intersection" in path:
            return {"cost": 0.01, "tasks": [{"result": [{"items": [
                {"keyword_data": {"keyword": "icu cambodia", "keyword_info": {"search_volume": 90}}}]}]}]}, None
        if "search_volume" in path:
            return {"cost": 0.02, "tasks": [{"result": [{"items": [{"keyword": "hospital", "search_volume": 1200}]}]}]}, None
        if "keyword_ideas" in path:
            return {"cost": 0.008, "tasks": [{"result": [{"items": [
                {"keyword": "clinic", "keyword_info": {"search_volume": 300}}]}]}]}, None
        return {}, None
    rows, status, cost = keywords_card("x.com", keywords=["hospital"], call=fake_call)
    codes = {r["code"] for r in rows}
    assert {"dfs.competitor", "dfs.keyword_gap", "dfs.keyword_volume", "dfs.keyword_idea"} <= codes
    assert cost == round(0.005 + 0.01 + 0.02 + 0.008, 4)


# ── Task 6: AI visibility (LLM mentions) ─────────────────────────────────────
from pipeline.scanner.dataforseo import parse_llm_mentions, llm_mentions


def test_llm_mentions_cited_is_ok():
    doc = {"tasks": [{"result": [{"items": [
        {"ai_provider": "chatgpt"}, {"ai_provider": "perplexity"}]}]}]}
    rows = parse_llm_mentions(doc, "Orienda")
    assert rows[0]["severity"] == "ok" and "cited 2 time" in rows[0]["what"]


def test_llm_mentions_absent_is_warn_gap():
    rows = parse_llm_mentions({"tasks": [{"result": [{"items": []}]}]}, "Orienda")
    assert rows[0]["severity"] == "warn" and "not cited" in rows[0]["what"]


def test_llm_mentions_caller_injected():
    rows, status, cost = llm_mentions("Orienda", "x.com",
                                      call=lambda p, b: ({"cost": 0.03, "tasks": [{"result": [{"items": [{"model": "gpt"}]}]}]}, None))
    assert cost == 0.03 and rows[0]["severity"] == "ok"
