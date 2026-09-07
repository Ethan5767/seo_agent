"""DataForSEO ranked-keywords parser + caller (offline, canned response)."""
from pipeline.scanner.dataforseo import parse_ranked_keywords, ranked_keywords

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
