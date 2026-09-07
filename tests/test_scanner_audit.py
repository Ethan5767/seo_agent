from pipeline.scanner.audit import seo_rows, aeo_rows, perf_rows, assemble

BAD = ("<!DOCTYPE html><html><head>"
       "<title>Way too long a title that runs well past the sixty character ceiling for sure</title>"
       "</head><body><main><h1>One</h1><p>tiny</p></main></body></html>")


def test_seo_rows_flag_title_and_desc():
    rows = seo_rows("https://x.com/p/", BAD, 200, {})
    codes = {r["code"] for r in rows}
    assert "health.title_length" in codes
    assert "health.desc_missing" in codes
    for r in rows:
        assert r["what"] and r["why"] and r["fix"]


def test_seo_rows_show_passes_too_nothing_hidden():
    # BAD fails title/desc but passes many checks -> the passing ones appear green.
    rows = seo_rows("https://x.com/p/", BAD, 200, {})
    passes = [r for r in rows if r["severity"] == "ok"]
    assert passes, "passing checks must be shown, not hidden"
    # the full checklist is represented (every SEO check is present as pass or fail)
    labels = {r["what"] for r in rows}
    assert "Single main heading (H1)" in labels


def test_aeo_flags_missing_robots():
    rows = aeo_rows(None, "<html></html>")
    assert any(r["code"] == "aeo.robots_missing" for r in rows)


def test_aeo_flags_blocked_citation_crawler():
    robots = "User-agent: PerplexityBot\nDisallow: /\n"
    rows = aeo_rows(robots, "<html></html>")
    blocked = [r for r in rows if r["code"] == "aeo.crawler_blocked"]
    assert any("PerplexityBot" in r["detail"] for r in blocked)


def test_aeo_clean_robots_has_no_crawler_rows():
    robots = "User-agent: *\nAllow: /\n"
    rows = aeo_rows(robots, '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>')
    assert not any(r["code"] == "aeo.crawler_blocked" for r in rows)
    assert not any(r["code"] == "health.schema_business_missing" for r in rows)


def test_perf_disabled_when_no_crux():
    rows = perf_rows(None)
    assert rows and rows[0]["code"] == "crux.disabled"
    assert rows[0]["severity"] == "info"


def test_perf_shows_every_metric_pass_and_fail():
    metrics = [
        {"metric": "LCP", "p75": 2100, "good": 2500, "verdict": "good"},
        {"metric": "INP", "p75": 620, "good": 200, "verdict": "poor"},
    ]
    rows = perf_rows((metrics, "ok"))
    lcp = next(r for r in rows if r["code"] == "crux.lcp")
    inp = next(r for r in rows if r["code"] == "crux.inp")
    assert "2100" in lcp["what"] and lcp["severity"] == "ok"
    assert inp["severity"] == "error"  # poor -> error


def test_perf_no_field_data_is_info_not_faked():
    rows = perf_rows(([], "no field data: too little traffic"))
    assert rows[0]["code"] == "crux.nodata"
    assert rows[0]["severity"] == "info"


def test_assemble_scores_and_groups():
    seo = [{"code": "health.title_length", "severity": "error", "what": "", "why": "", "fix": "", "detail": ""}]
    aeo = [{"code": "aeo.crawler_blocked", "severity": "warn", "what": "", "why": "", "fix": "", "detail": "GPTBot"}]
    perf = perf_rows(None)
    report = assemble(seo, aeo, perf)
    assert report["score"] == 100 - 10 - 3
    assert report["seo"] and report["aeo"] and report["perf"]
    assert report["counts"]["error"] == 1
