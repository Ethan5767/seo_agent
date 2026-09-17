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


def test_aeo_clean_robots_reports_the_crawler_checks_as_passing():
    """A check that ran and passed emits its code with severity "ok", not no row
    at all: the report views key on the code, so a codeless pass was invisible
    and a clean site rendered an empty screen."""
    robots = "User-agent: *\nAllow: /\n"
    rows = aeo_rows(robots, '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>')
    by_code = {r["code"]: r for r in rows}
    for code in ("aeo.crawler_blocked", "health.schema_business_missing"):
        assert code in by_code, f"a passing check must still emit {code}"
        assert by_code[code]["severity"] == "ok", f"{code} must pass here"
        assert by_code[code]["fix"] == "passing"


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
    # 1 error + 1 warn gradeable, 0 passing, plus a perf info row that is not
    # gradeable at all -> 0% passed. Was `100 - 10 - 3` under the penalty model,
    # which read as 87% "healthy" for a page where every graded check failed.
    assert report["score"] == 0
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
    blocked_citation = [r for r in rows
                        if r["code"] == "aeo.crawler_blocked" and r["severity"] != "ok"]
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
    assert not any(r["code"] == "health.schema_business_missing" and r["severity"] != "ok"
                   for r in rows), (
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
    assert not any(r["code"] == "health.schema_business_missing" and r["severity"] != "ok"
                   for r in rows)


def test_answer_engine_schema_types_are_reported():
    """QAPage, HowTo and Article-with-author are the types answer engines lean
    on hardest for attribution. Only FAQPage and LocalBusiness were recognised."""
    rows = aeo_rows("User-agent: *\nAllow: /\n", "<html><body><p>hi</p></body></html>")
    assert any(r["code"] == "aeo.answer_schema_missing" and r["severity"] != "ok"
               for r in rows), (
        "a page with no answer-engine schema must say so"
    )


def test_answer_engine_schema_passes_when_present():
    html = (
        '<script type="application/ld+json">'
        '{"@type":"HowTo","name":"Fix a roof"}</script>'
    )
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    missing = [r for r in rows
               if r["code"] == "aeo.answer_schema_missing" and r["severity"] != "ok"]
    assert missing == [], f"HowTo should satisfy the answer-schema check, got {missing}"


def test_article_without_an_author_is_flagged():
    """An Article with no author is hard for an engine to cite confidently."""
    html = '<script type="application/ld+json">{"@type":"Article","headline":"X"}</script>'
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    assert any(r["code"] == "aeo.article_author_missing" for r in rows)


def test_article_with_an_author_passes_the_check_rather_than_vanishing():
    """The check used to emit a row only when it failed, so an Article that named
    its author passed silently - the same invisible-pass hole as the codeless
    pass rows."""
    html = (
        '<script type="application/ld+json">'
        '{"@type":"Article","headline":"X","author":{"@type":"Person","name":"A"}}</script>'
    )
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    row = [r for r in rows if r["code"] == "aeo.article_author_missing"]
    assert len(row) == 1 and row[0]["severity"] == "ok"


def test_a_page_that_is_not_an_article_is_not_judged_on_authorship():
    """Not applicable is not the same as passing: a non-Article emits no row."""
    html = '<script type="application/ld+json">{"@type":"LocalBusiness"}</script>'
    rows = aeo_rows("User-agent: *\nAllow: /\n", html)
    assert [r for r in rows if r["code"] == "aeo.article_author_missing"] == []


def test_the_pass_row_is_stamped_with_the_checks_first_code():
    """A check can fail for several reasons but passes as one thing, so its pass
    row carries codes[0]. That makes the FIRST code the check's identity to the
    ratchet and to the report views: reorder a check's codes and you rename it.
    Pinned here because the assumption is invisible at the call site."""
    from pipeline.scanner.audit import SEO_CHECKS, seo_rows
    html = ("<html><head><title>A Perfectly Ordinary Page Title Here</title>"
            '<meta name="description" content="' + "x" * 130 + '">'
            '<link rel="canonical" href="https://x.com/"></head>'
            "<body><h1>One</h1></body></html>")
    rows = seo_rows("https://x.com/", html, 200, {})
    by_what = {r["what"]: r for r in rows if r["fix"] == "passing"}
    for label, codes, _why in SEO_CHECKS:
        if label in by_what:
            assert by_what[label]["code"] == codes[0], (
                f"the pass row for {label!r} must carry codes[0], not {by_what[label]['code']!r}"
            )


# ── The health score ─────────────────────────────────────────────────────────
#
# One formula, in one place, with properties worth pinning. The old model was
# `max(0, 100 - 10*errors - 3*warns)`, and the web tier carried two more with
# different weights and floors, so one scan had three health numbers (B-055).


def _graded_rows(ok=0, warn=0, error=0, info=0):
    return ([{"code": "onpage.charset", "severity": "ok"}] * ok
            + [{"code": "onpage.charset", "severity": "warn"}] * warn
            + [{"code": "onpage.charset", "severity": "error"}] * error
            + [{"code": "onpage.charset", "severity": "info"}] * info)


def test_health_score_is_the_weighted_share_of_gradeable_checks_that_passed():
    from pipeline.scanner.audit import health_score
    assert health_score(_graded_rows(ok=14, warn=21, error=8, info=8)) == 33
    assert health_score(_graded_rows(ok=10)) == 100
    assert health_score(_graded_rows(error=10)) == 0


def test_info_rows_are_not_gradeable_and_move_nothing():
    """An info row reports a fact rather than a verdict. Counting it as a pass
    would let a site raise its health by adding unjudgeable observations."""
    from pipeline.scanner.audit import health_score
    base = _graded_rows(ok=5, warn=5)
    assert health_score(base) == health_score(base + _graded_rows(info=500))


def test_nothing_gradeable_scores_None_rather_than_zero():
    """A scan that measured nothing must not report 0% health - that reads as
    'everything is broken' instead of 'we did not look'. Same rule as the gates:
    a check that scanned nothing never reports a verdict."""
    from pipeline.scanner.audit import health_score
    assert health_score(_graded_rows(info=9)) is None
    assert health_score([]) is None


def test_fixing_a_finding_can_only_raise_the_score():
    """Monotonicity, which the penalty model did not have. Some suite tools document
    that its own score can fall while the issue count falls; a number that moves
    the wrong way cannot be reported against month over month."""
    from pipeline.scanner.audit import health_score
    prev = None
    for fixed in range(0, 21):          # move findings one at a time into ok
        s = health_score(_graded_rows(ok=fixed, warn=20 - fixed, info=3))
        if prev is not None:
            assert s >= prev, f"score fell from {prev} to {s} after fixing one more finding"
        prev = s
    assert prev == 100


def test_the_score_never_saturates_away_the_difference():
    """The old model clamped at 0, so a site with 10 errors and one with 400
    were indistinguishable - exactly where a client most needs to see progress."""
    from pipeline.scanner.audit import health_score
    bad = health_score(_graded_rows(error=400))
    better = health_score(_graded_rows(ok=200, error=200))
    assert bad == 0 and better == 50, "half the errors fixed must show as movement"


def test_assemble_ships_the_score_version_beside_the_score():
    """So a score change caused by US is distinguishable from one caused by the
    site. Lighthouse has revised its weights five times."""
    from pipeline.scanner.audit import assemble, HEALTH_SCORE_VERSION
    out = assemble({"seo": [{"code": "x", "severity": "ok"}]})
    assert out["score"] == 100
    assert out["score_version"] == HEALTH_SCORE_VERSION


def test_the_score_ships_its_own_denominator():
    """A score is only comparable between scans that graded the same checks.
    Enabling a tool raises it with no change to the site - adding the 28
    on-page checks moved a real scan from 33 to 51 - so the denominator has to
    travel with the number or two scores get compared that never should be."""
    from pipeline.scanner.audit import assemble
    # "seo": since score version 3 only the on-page audit's groups are graded.
    few = assemble({"seo": [{"code": "x", "severity": "ok"},
                            {"code": "y", "severity": "error"}]})
    many = assemble({"seo": [{"code": "x", "severity": "ok"},
                           {"code": "y", "severity": "error"}]
                          + [{"code": f"z{i}", "severity": "ok"} for i in range(8)]})
    assert few["score"] == 50 and few["graded"] == 2
    assert many["score"] == 90 and many["graded"] == 10, \
        "same one failure, higher score, because more checks ran"


# ── a page that was never fetched is not a page that passed (B-074) ──────────
#
# The scanner graded a site it never reached at 40/100 with 23 checks marked
# "ok" — including tech.https and onpage.mixed_content, on a response that never
# arrived. `health_score` already refuses to score an empty grade set, and its
# docstring says why; the guard never fired because ~20 row builders take only
# `html` and cannot tell "" (unfetched) from "" (a page with no such feature).
#
# This is the same rule the gates settled on as exit 4: absence of evidence is
# not evidence of compliance.

def test_an_unfetched_page_produces_no_gradeable_rows():
    from pipeline.scanner.audit import assemble
    rows = [{"code": "tech.https", "what": "HTTPS", "severity": "ok"},
            {"code": "health.title_missing", "what": "Title", "severity": "error"}]
    out = assemble({"seo": rows}, reachable=False)
    counts = out["counts"]
    assert counts["ok"] == 0, "nothing can pass on a page that was never fetched"
    assert counts["error"] == 0 and counts["warn"] == 0, (
        "and nothing can fail either — we did not look")
    assert out["score"] is None, (
        "a scan that measured nothing must report no score, not 40/100")
    assert out["graded"] == 0


def test_an_unfetched_page_says_so_in_every_group():
    from pipeline.scanner.audit import assemble
    out = assemble({"seo": [{"code": "x", "what": "X", "severity": "ok"}],
                    "onpage": [{"code": "y", "what": "Y", "severity": "warn"}]},
                   reachable=False)
    for group in ("seo", "onpage"):
        assert len(out[group]) == 1, f"{group}: one honest row, not the invented set"
        row = out[group][0]
        assert row["severity"] == "info", "not measured is not a verdict"
        assert "not measured" in row["what"].lower()


def test_a_reachable_page_is_unaffected():
    from pipeline.scanner.audit import assemble
    rows = [{"code": "tech.https", "what": "HTTPS", "severity": "ok"},
            {"code": "health.title_missing", "what": "Title", "severity": "error"}]
    out = assemble({"seo": rows})
    assert out["counts"]["ok"] == 1 and out["counts"]["error"] == 1
    assert out["score"] == 50
