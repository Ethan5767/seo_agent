"""E-E-A-T checker: 4 pillars, every row carries the evidence it was judged on.

Google has no E-E-A-T score; its rater guidelines describe what raters look for,
and health pages (YMYL) are held to the strictest bar. So this checks signals a
page can show, reads them from JSON-LD rather than loose keyword matches (the
previous version passed "Social proof" on any page containing a star character),
and never invents a total.
"""
from pipeline.scanner.eeat import eeat_rows, jsonld_objects, PILLARS

URL = "https://hospital.example/en/departments/cardiology"

MEDICAL_RICH = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Hospital","name":"Example Hospital","sameAs":["https://www.facebook.com/examplehospital","https://en.wikipedia.org/wiki/Example_Hospital"],
  "address":{"@type":"PostalAddress","streetAddress":"1 Main St","addressLocality":"Phnom Penh"},
  "aggregateRating":{"@type":"AggregateRating","ratingValue":"4.7","reviewCount":"212"}},
 {"@type":"MedicalWebPage","name":"Cardiology","dateModified":"2026-08-01","lastReviewed":"2026-07-20",
  "reviewedBy":{"@type":"Person","name":"Dr Sok Dara","jobTitle":"Head of Cardiology","honorificSuffix":"MD"},
  "author":{"@type":"Person","name":"Dr Sok Dara","jobTitle":"Head of Cardiology","sameAs":["https://www.linkedin.com/in/sokdara"]}}
]}
</script></head><body><main>
<p class="byline">Written by <strong>Dr Sok Dara, MD</strong></p>
<p>Medically reviewed by Dr Chan Vanna, FRCS. Last updated 1 August 2026.</p>
<p>Accredited by Joint Commission International (JCI) since 2021.</p>
<p>See <a href="https://www.who.int/health-topics/cardiovascular-diseases">WHO guidance</a>.</p>
<h2>Patient story: recovering after bypass surgery</h2>
<a href="tel:+85523000000">Call</a> <a href="/en/about">About us</a>
<a href="/en/privacy-policy">Privacy</a> <a href="/en/terms">Terms</a>
<p>This information is not a substitute for professional medical advice.</p>
</main></body></html>"""

MEDICAL_BARE = """<html><body><main><h1>Cardiology department</h1>
<p>Our doctors treat heart conditions for patients across Cambodia.</p>
<p>We are proud of our awards ★★★★★</p></main></body></html>"""

NON_MEDICAL = """<html><body><main><h1>Roof repair</h1><p>We fix roofs.</p></main></body></html>"""


def by_code(rows):
    return {r["code"]: r for r in rows}


def test_every_row_names_its_pillar_and_is_an_eeat_code():
    for r in eeat_rows(MEDICAL_RICH, URL):
        assert r["code"].startswith("eeat.")
        assert r["what"].split(" · ")[0] in PILLARS


def test_jsonld_is_parsed_through_graph_and_nesting():
    types = {t for o in jsonld_objects(MEDICAL_RICH) for t in o["@types"]}
    assert {"hospital", "medicalwebpage", "person", "postaladdress", "aggregaterating"} <= types


def test_a_well_marked_medical_page_passes_with_evidence():
    rows = by_code(eeat_rows(MEDICAL_RICH, URL))
    for code in ("eeat.author_byline", "eeat.author_schema", "eeat.credentials", "eeat.author_sameas",
                 "eeat.medical_review", "eeat.freshness", "eeat.org_schema", "eeat.org_sameas",
                 "eeat.accreditation", "eeat.citations", "eeat.about_page", "eeat.https",
                 "eeat.contact", "eeat.policies", "eeat.medical_disclaimer", "eeat.reviews", "eeat.first_hand"):
        assert rows[code]["severity"] == "ok", (code, rows[code])
    assert "Dr Sok Dara" in rows["eeat.author_schema"]["detail"]
    assert "Head of Cardiology" in rows["eeat.author_schema"]["detail"]
    assert "who.int" in rows["eeat.citations"]["detail"]
    assert "Joint Commission" in rows["eeat.accreditation"]["detail"]
    assert "4.7" in rows["eeat.reviews"]["detail"] and "212" in rows["eeat.reviews"]["detail"]


def test_a_bare_medical_page_is_held_to_the_ymyl_bar():
    rows = by_code(eeat_rows(MEDICAL_BARE, URL))
    for code in ("eeat.author_byline", "eeat.author_schema", "eeat.medical_review",
                 "eeat.medical_disclaimer", "eeat.contact", "eeat.policies", "eeat.org_schema"):
        assert rows[code]["severity"] in ("warn", "error"), (code, rows[code])


def test_stars_and_the_word_award_are_not_evidence():
    """The old check passed Social proof and Authoritativeness on exactly this."""
    rows = by_code(eeat_rows(MEDICAL_BARE, URL))
    assert rows["eeat.reviews"]["severity"] != "ok"
    assert rows["eeat.accreditation"]["severity"] != "ok"


def test_medical_only_checks_do_not_apply_to_other_sites():
    rows = by_code(eeat_rows(NON_MEDICAL, "https://roofs.example/"))
    assert "eeat.medical_review" not in rows
    assert "eeat.medical_disclaimer" not in rows
    assert rows["eeat.author_byline"]["severity"] in ("info", "warn")


def test_http_page_fails_trust():
    rows = by_code(eeat_rows(MEDICAL_RICH, "http://hospital.example/en"))
    assert rows["eeat.https"]["severity"] == "error"


def test_invalid_rating_markup_is_not_a_pass():
    html = ('<script type="application/ld+json">{"@type":"Hospital","name":"H",'
            '"aggregateRating":{"@type":"AggregateRating","ratingValue":"great"}}</script>')
    rows = by_code(eeat_rows(html, URL))
    assert rows["eeat.reviews"]["severity"] != "ok"
    assert "ratingValue" in rows["eeat.reviews"]["why"]


def test_broken_jsonld_never_crashes():
    rows = eeat_rows('<script type="application/ld+json">{not json</script><p>hi</p>', URL)
    assert any(r["code"] == "eeat.author_schema" for r in rows)


def test_empty_page_is_safe():
    assert isinstance(eeat_rows("", URL), list)


def test_about_evidence_is_the_clean_path():
    rows = by_code(eeat_rows('<a href="/en/about">About</a>', URL))
    assert rows["eeat.about_page"]["detail"] == "/en/about"
