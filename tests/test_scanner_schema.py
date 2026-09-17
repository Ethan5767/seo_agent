from pipeline.scanner.schema_check import schema_rows


def test_valid_jsonld_ok():
    html = '<script type="application/ld+json">{"@context":"x","@type":"LocalBusiness"}</script>'
    by = {r["what"]: r for r in schema_rows(html)}
    assert by["Valid JSON-LD"]["severity"] == "ok"
    assert by["Schema types"]["detail"] == "LocalBusiness"


def test_broken_jsonld_error():
    html = '<script type="application/ld+json">{ broken json,, }</script>'
    by = {r["what"]: r for r in schema_rows(html)}
    assert by["Valid JSON-LD"]["severity"] == "error"


def test_missing_type_warns():
    html = '<script type="application/ld+json">{"name":"x"}</script>'
    by = {r["what"]: r for r in schema_rows(html)}
    assert by["Schema @type"]["severity"] == "warn"


def test_no_schema_warns():
    assert schema_rows("<html></html>")[0]["severity"] == "warn"
