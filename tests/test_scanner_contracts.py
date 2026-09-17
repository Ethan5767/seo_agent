from pipeline.scanner import server
from pipeline.scanner.contracts import normalize_finding


def test_catalog_exposes_required_tool_metadata():
    catalog = server.tool_catalog()
    required = {"name", "data_source", "cost_per_run", "requires_auth", "avg_runtime"}
    assert catalog
    assert all(required <= row.keys() for row in catalog)
    assert {row["data_source"] for row in catalog} >= {"own_crawler", "dataforseo", "source"}


def test_finding_normalization_preserves_legacy_fields_and_adds_contract():
    tool = next(t for t in server.TOOLS if t.key == "tech")
    finding = normalize_finding({
        "code": "tech.https", "severity": "warn", "what": "HTTPS", "why": "secure it",
        "fix": "serve HTTPS", "pages": ["https://example.test/"], "detail": "http",
    }, tool)
    assert finding["what"] == "HTTPS"
    assert finding["affected_urls"] == ["https://example.test/"]
    assert finding["why_it_matters"] == "secure it"
    assert finding["how_to_fix"] == "serve HTTPS"
    assert finding["source_tool"] == "tech"
    assert finding["confidence"] == "high"
