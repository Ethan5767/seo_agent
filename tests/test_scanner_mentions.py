from pipeline.scanner.mentions import parse_mentions, brand_mentions


def test_mentions_found_positive():
    doc = {"tasks": [{"result": [{"total_count": 42,
            "sentiment_connotations": {"positive": 30, "negative": 5}}]}]}
    by = {r["what"]: r for r in parse_mentions(doc, "Orienda")}
    assert by["Web mentions"]["severity"] == "ok" and "42" in by["Web mentions"]["detail"]
    assert by["Mention sentiment"]["severity"] == "ok"


def test_mentions_negative_warns():
    doc = {"tasks": [{"result": [{"total_count": 10,
            "sentiment_connotations": {"positive": 2, "negative": 8}}]}]}
    by = {r["what"]: r for r in parse_mentions(doc, "X")}
    assert by["Mention sentiment"]["severity"] == "warn"


def test_no_mentions_info():
    assert parse_mentions({"tasks": [{"result": [{"total_count": 0}]}]}, "X")[0]["severity"] == "info"


def test_brand_mentions_caller_and_no_brand():
    rows, status, cost = brand_mentions("")
    assert rows == [] and "skipped" in status
    doc = {"cost": 0.04, "tasks": [{"result": [{"total_count": 5}]}]}
    rows, status, cost = brand_mentions("X", call=lambda p, b: (doc, None))
    assert cost == 0.04 and rows[0]["what"] == "Web mentions"
