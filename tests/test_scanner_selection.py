from pipeline.scanner import server


def fake_fetch(url):
    return ("<html><head><title>T</title></head><body><h1>H</h1>"
            "<main>hi</main></body></html>", 200, "", None)


def _ran(selected):
    ran = []

    def cap(name, state, rows, status, cost):
        if state == "running":
            ran.append(name)

    server.build_report("https://x.com", fetch=fake_fetch, crux=None,
                        selected=selected, on_tool=cap)
    return ran


def test_selection_filters_to_one_tool():
    assert _ran({"seo"}) == ["On-page SEO"]


def test_selection_multiple_free_tools():
    ran = _ran({"seo", "aeo", "tech"})
    assert set(ran) == {"On-page SEO", "AI visibility (AEO)", "Technical"}


def test_source_tool_without_repo_reports_instead_of_running():
    # 'source' selected but no repo/token: the card still appears (it used to
    # vanish, D12), and the source fetch is never attempted. The named row is
    # asserted in test_spend_gate.py::test_source_without_token_says_so.
    assert _ran({"source"}) == ["Source code"]


def test_empty_selection_runs_nothing():
    # An explicit empty set runs zero tools (the /scan endpoint rejects this so
    # a zero-tool run can never report a clean score — see do_POST guard).
    assert _ran(set()) == []


def test_catalog_shape():
    cat = server.tool_catalog()
    assert cat, "catalog should be non-empty"
    assert all({"key", "label", "group", "cost", "cost_num"} <= set(t) for t in cat)
    keys = {t["key"] for t in cat}
    assert {"seo", "site", "rankings", "source"} <= keys
    groups = {t["group"] for t in cat}
    assert {"free", "dataforseo", "source"} <= groups
