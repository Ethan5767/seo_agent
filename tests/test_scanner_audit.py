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
    report = assemble({"seo": seo, "aeo": aeo, "perf": perf})
    assert report["score"] == 100 - 10 - 3
    assert report["seo"] and report["aeo"] and report["perf"]
    assert report["counts"]["error"] == 1


# ── Task 7: answer-first structure gap check (DataForSEO has no tool for this) ─
def test_answer_structure_flagged_when_absent():
    rows = aeo_rows("User-agent: *\nAllow: /\n", "<html><body><h2>Our Services</h2></body></html>")
    by = {r["what"]: r for r in rows}
    assert by["Answer-first structure"]["severity"] == "warn"


def test_answer_structure_passes_with_interrogative_heading():
    html = "<html><body><h2>How much does a roof cost?</h2><p>About $X.</p></body></html>"
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    by = {r["what"]: r for r in rows}
    assert by["Answer-first structure"]["severity"] == "ok"


def test_answer_structure_passes_with_faq_schema():
    html = '<html><body><script type="application/ld+json">{"@type":"FAQPage"}</script></body></html>'
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    by = {r["what"]: r for r in rows}
    assert by["Answer-first structure"]["severity"] == "ok"


# ── GEO / answer-readiness: the evidence-based AI-citation levers ─────────────
def test_aeo_geo_signals_present():
    rich = ('<html><body>We served 12,450 patients in 2023, a 38% increase. '
            '<blockquote>According to the WHO study, ...</blockquote>'
            '<table><tr><td>2023</td><td>45%</td></tr></table></body></html>')
    by = {r["what"]: r for r in aeo_rows("User-agent: *\nAllow: /\n", rich)}
    assert by["Statistics and data"]["severity"] == "ok"
    assert by["Quotes and citations"]["severity"] == "ok"
    assert by["Data tables"]["severity"] == "ok"


def test_aeo_geo_signals_absent():
    plain = "<html><body><p>We are a great hospital with good care and friendly staff.</p></body></html>"
    by = {r["what"]: r for r in aeo_rows("User-agent: *\nAllow: /\n", plain)}
    assert by["Statistics and data"]["severity"] == "warn"   # no concrete figures
    assert by["Quotes and citations"]["severity"] == "info"
    assert by["Data tables"]["severity"] == "info"
