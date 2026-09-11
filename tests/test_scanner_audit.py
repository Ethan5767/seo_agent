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


# ── AEO strengthening ────────────────────────────────────────────────────────
# Three gaps found auditing our own tool: training crawlers were never checked
# (only citation crawlers), the business-schema test was a bare substring match
# that missed every subtype, and only two schema types were recognised at all.

def test_training_crawlers_reported_separately_from_citation_crawlers():
    """Blocking a training crawler is a choice; blocking a citation crawler is a
    problem. Reporting them the same way loses the distinction that matters."""
    robots = (
        "User-agent: GPTBot\nDisallow: /\n\n"
        "User-agent: ClaudeBot\nDisallow: /\n\n"
        "User-agent: *\nAllow: /\n"
    )
    rows = aeo_rows(robots, "<html></html>")
    codes = {r["code"] for r in rows}
    assert "aeo.training_crawler_blocked" in codes, (
        "a blocked training crawler must be reported under its own code"
    )
    # GPTBot and ClaudeBot are training crawlers, not citation crawlers, so
    # blocking them must NOT be reported as a blocked citation crawler.
    blocked_citation = [r for r in rows if r["code"] == "aeo.crawler_blocked"]
    assert blocked_citation == [], (
        f"training crawlers were misreported as citation crawlers: {blocked_citation}"
    )


def test_blocking_a_training_crawler_is_not_an_error():
    """Many clients deliberately block training crawlers. It is information, not
    a defect, so it must never carry error severity."""
    robots = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    rows = aeo_rows(robots, "<html></html>")
    training = [r for r in rows if r["code"] == "aeo.training_crawler_blocked"]
    assert training, "expected a training-crawler row"
    for r in training:
        assert r["severity"] in ("info", "ok"), (
            f"blocking a training crawler is a choice, got severity {r['severity']!r}"
        )


def test_blocking_a_citation_crawler_is_still_a_problem():
    """The distinction must not weaken the check that matters: a blocked
    citation crawler means the site cannot be cited at all."""
    robots = "User-agent: PerplexityBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
    rows = aeo_rows(robots, "<html></html>")
    assert any(r["code"] == "aeo.crawler_blocked" for r in rows)


def test_business_schema_accepts_a_subtype():
    """The old check was `'"@type":"LocalBusiness"' not in html`, so a dentist,
    restaurant or clinic using a proper schema.org subtype was reported as
    having no business schema at all."""
    html = '<script type="application/ld+json">{"@type":"Dentist","name":"X"}</script>'
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    assert not any(r["code"] == "health.schema_business_missing" for r in rows), (
        "a LocalBusiness subtype must count as business schema"
    )


def test_business_schema_found_inside_a_graph():
    """Real sites commonly nest entities in @graph; a substring match over the
    raw HTML happened to work, but only by accident of formatting."""
    html = (
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@graph":[{"@type":"WebSite"},'
        '{"@type":"LocalBusiness","name":"X"}]}</script>'
    )
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    assert not any(r["code"] == "health.schema_business_missing" for r in rows)


def test_answer_engine_schema_types_are_reported():
    """QAPage, HowTo and Article-with-author are the types answer engines lean
    on hardest for attribution. Only FAQPage and LocalBusiness were recognised."""
    rows = aeo_rows("User-agent: *\nAllow: /\n", "<html><body><p>hi</p></body></html>")
    assert any(r["code"] == "aeo.answer_schema_missing" for r in rows), (
        "a page with no answer-engine schema must say so"
    )


def test_answer_engine_schema_passes_when_present():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"HowTo","name":"Fix a roof"}</script>'
    )
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    missing = [r for r in rows if r["code"] == "aeo.answer_schema_missing"]
    assert missing == [], f"HowTo should satisfy the answer-schema check, got {missing}"


def test_article_without_an_author_is_flagged():
    """An Article with no author is hard for an engine to cite confidently."""
    html = '<script type="application/ld+json">{"@type":"Article","headline":"X"}</script>'
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    assert any(r["code"] == "aeo.article_author_missing" for r in rows)


def test_article_with_an_author_is_not_flagged():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Article","headline":"X","author":{"@type":"Person","name":"A"}}</script>'
    )
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    assert not any(r["code"] == "aeo.article_author_missing" for r in rows)
