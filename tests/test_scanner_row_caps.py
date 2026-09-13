"""Paid-row caps: what we ask DataForSEO for must equal what we keep.

These guards deliberately do NOT live in `tests/test_scanner_dataforseo.py`.
That file is deselected from every default run by `-k 'not dataforseo'` in
pyproject's pytest addopts (B-050), so tests written there are never collected -
which is exactly what happened when these were first written. Nothing here
touches the network; the name is what excluded them, not the behaviour.
"""
# ── the ask and the keep must not drift ──────────────────────────────────────

def test_every_request_limit_is_the_named_cap_not_a_literal():
    """The parsers kept 15 rows while the requests asked for 50 or 100, so every
    paid call billed for depth and then discarded it: 85 of 100 ranked keywords,
    85 of 100 gap rows, 35 of 50 ideas. The rows are already bought by the time
    a parser sees them, so slicing them off saved nothing and is why the keyword
    screens looked thin. One constant now, asked for and kept."""
    import re
    import pathlib
    src = pathlib.Path("pipeline/scanner/dataforseo.py").read_text()
    literals = re.findall(r'"limit":\s*(\d+)', src)
    assert literals == [], f"hardcoded request limits found: {literals}"


def test_parsers_keep_what_the_requests_ask_for():
    from pipeline.scanner import dataforseo as d
    for fn in (d.parse_ranked_keywords, d.parse_search_volume, d.parse_keyword_ideas,
               d.parse_keyword_suggestions, d.parse_keyword_difficulty,
               d.parse_search_intent):
        default = fn.__defaults__[-1]
        assert default == d.TOP_ROWS, f"{fn.__name__} keeps {default}, not TOP_ROWS"


def test_a_parser_really_returns_more_than_the_old_fifteen():
    """Behaviour, not just the constant: feed 60 items and expect 60 back."""
    from pipeline.scanner.dataforseo import parse_keyword_ideas
    doc = {"tasks": [{"result": [{"items": [
        {"keyword": f"kw{i}", "keyword_info": {"search_volume": 100 + i}}
        for i in range(60)]}]}]}
    assert len(parse_keyword_ideas(doc)) == 60


def test_competitors_stay_a_shortlist():
    """Past a handful, competitor rows are long-tail domains nobody acts on."""
    from pipeline.scanner import dataforseo as d
    assert d.TOP_COMPETITORS < d.TOP_ROWS
