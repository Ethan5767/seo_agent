from pipeline.scanner.migration import migration_rows

def test_migration_diff_flags_lost_urls():
    rows = migration_rows({"pages": {"/old": {}}}, {"pages": {}})
    assert rows[0]["severity"] == "error"
