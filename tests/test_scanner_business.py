from pipeline.scanner.business_data import parse_gbp, gbp_local


def test_gbp_parses_rating_category_nap():
    doc = {"tasks": [{"result": [{"items": [{
        "rating": {"value": 4.6, "votes_count": 120},
        "category": "Hospital", "address": "St 1", "phone": "+855", "is_claimed": True}]}]}]}
    by = {r["what"]: r for r in parse_gbp(doc)}
    assert by["Reviews"]["severity"] == "ok" and "4.6" in by["Reviews"]["detail"]
    assert by["Primary category"]["severity"] == "ok" and by["Primary category"]["detail"] == "Hospital"
    assert by["NAP"]["severity"] == "ok"


def test_gbp_low_rating_and_missing_bits_warn():
    doc = {"tasks": [{"result": [{"items": [{"rating": {"value": 3.2, "votes_count": 4}}]}]}]}
    by = {r["what"]: r for r in parse_gbp(doc)}
    assert by["Reviews"]["severity"] == "warn"       # < 4.0
    assert by["Primary category"]["severity"] == "warn"
    assert by["NAP"]["severity"] == "warn"


def test_gbp_no_profile_warns():
    assert parse_gbp({"tasks": [{"result": [{"items": []}]}]})[0]["severity"] == "warn"


def test_gbp_caller_injected():
    doc = {"cost": 0.02, "tasks": [{"result": [{"items": [{"category": "Clinic", "address": "x", "phone": "1"}]}]}]}
    rows, status, cost = gbp_local("Orienda", call=lambda p, b: (doc, None))
    assert cost == 0.02 and any(r["what"] == "Primary category" for r in rows)
