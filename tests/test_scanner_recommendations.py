from pipeline.scanner.recommendations import RECOMMENDATIONS, recommend


def test_known_code_has_why_and_fix():
    r = recommend("health.title_length")
    assert r["why"] and r["fix"]
    assert "title" in r["fix"].lower()


def test_every_table_entry_is_complete():
    for code, r in RECOMMENDATIONS.items():
        assert r.get("why"), code
        assert r.get("fix"), code


def test_unknown_code_falls_back_not_crashes():
    r = recommend("health.some_future_code")
    assert r["why"] and r["fix"]
