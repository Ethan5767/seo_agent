"""measure.py — live-site measurement as typed Findings.

Hermetic: check_page takes already-fetched HTML, so nothing here touches the
network. The fingerprint-stability tests at the bottom are the ones that matter
most; they are the property phase 3's ratchet depends on.
"""
from __future__ import annotations

import json
import sys
import textwrap
from datetime import date

import pytest
import yaml

from pipeline.audit import measure as m

URL = "https://example.com/roofing/"

CFG = {
    "domain": "example.com",
    "schema_type": "RoofingContractor",
    "ga4_id": "G-TESTID1234",
    "nap": {"phone": "(704) 555-0100", "phone_tel": "17045550100"},
    "forbidden_phrases": [
        {"pattern": r"\$[0-9]", "reason": "no dollar amounts on site"},
        {"pattern": "—", "reason": "no em dashes in deliverables"},
    ],
}


def build_page(*, title="Roofing Replacement and Repair in Charlotte, NC",
               desc=("Charlotte roof replacement and repair from a local crew, with "
                     "a written estimate before any work begins and a warranty on "
                     "every job we complete."),
               h1_count=1, canonical=URL, noindex=False, og_image=True,
               schema_types=("RoofingContractor", "FAQPage", "BreadcrumbList"),
               body="", images=('<img src="/hero.jpg" alt="A finished roof">',),
               ga4=True, words=600):
    """A page that passes every check by default. Each keyword trips exactly one."""
    head = []
    if title is not None:
        head.append(f"<title>{title}</title>")
    if desc is not None:
        head.append(f'<meta name="description" content="{desc}">')
    if canonical is not None:
        head.append(f'<link rel="canonical" href="{canonical}">')
    if og_image:
        head.append('<meta property="og:image" content="/og.jpg">')
    if noindex:
        head.append('<meta name="robots" content="noindex">')
    schema = "".join(f'<script type="application/ld+json">{{"@type":"{t}"}}</script>'
                     for t in schema_types)
    ga = ('<script src="https://www.googletagmanager.com/gtag/js?id=G-TESTID1234"></script>'
          if ga4 else "")
    filler = " ".join(["shingle"] * words)
    h1s = "<h1>Roofing in Charlotte, NC</h1>" * h1_count
    return textwrap.dedent(f"""\
        <!DOCTYPE html><html lang="en"><head>{''.join(head)}{schema}{ga}</head>
        <body><main>{h1s}
        <p>Call <a href="tel:17045550100">(704) 555-0100</a> for an estimate.</p>
        {''.join(images)}
        <p>{filler}</p>
        {body}
        </main></body></html>
    """)


def check(html, url=URL, status=200, cfg=None):
    return m.check_page(url, html, status, cfg if cfg is not None else CFG)


def codes(findings):
    return sorted(f.code for f in findings)


# ── the clean baseline ───────────────────────────────────────────────────────

def test_clean_page_has_no_findings():
    """build_page()'s defaults satisfy every check. If this fails, read which
    codes came back — a threshold or a regex is off, not the test."""
    assert check(build_page()) == []


# ── one test per code ────────────────────────────────────────────────────────

def test_status_not_200():
    f = check(build_page(), status=404)
    assert "health.status_not_200" in codes(f)
    assert [x for x in f if x.code == "health.status_not_200"][0].detail == "status=404"


def test_title_missing():
    c = codes(check(build_page(title=None)))
    assert "health.title_missing" in c
    assert "health.title_length" not in c, "missing and out-of-band are exclusive"


def test_title_length():
    f = check(build_page(title="Roofing"))
    assert "health.title_length" in codes(f)
    assert [x for x in f if x.code == "health.title_length"][0].detail == "len=7"


def test_desc_missing():
    c = codes(check(build_page(desc=None)))
    assert "health.desc_missing" in c
    assert "health.desc_length" not in c


def test_desc_length():
    assert "health.desc_length" in codes(check(build_page(desc="Too short.")))


def test_h1_count_zero_and_many():
    assert "health.h1_count" in codes(check(build_page(h1_count=0)))
    f = check(build_page(h1_count=3))
    assert [x for x in f if x.code == "health.h1_count"][0].detail == "count=3"


def test_canonical_mismatch_absent_and_wrong():
    f = check(build_page(canonical=None))
    assert [x for x in f if x.code == "health.canonical_mismatch"][0].detail == "absent"
    assert "health.canonical_mismatch" in codes(
        check(build_page(canonical="https://example.com/other-page/")))


def test_noindex_present():
    assert "health.noindex_present" in codes(check(build_page(noindex=True)))


def test_og_image_missing():
    assert "health.og_image_missing" in codes(check(build_page(og_image=False)))


def test_schema_findings():
    c = codes(check(build_page(schema_types=())))
    assert "health.schema_business_missing" in c
    assert "health.schema_faq_missing" in c
    assert "health.schema_breadcrumb_missing" in c


def test_schema_business_context_is_the_required_type():
    f = check(build_page(schema_types=("FAQPage", "BreadcrumbList")))
    biz = [x for x in f if x.code == "health.schema_business_missing"][0]
    assert biz.context == "RoofingContractor"


def test_forbidden_phrase_one_per_rule():
    f = check(build_page(body="<p>Roofs from $5,000 and up — call today.</p>"))
    hits = [x for x in f if x.code == "health.forbidden_phrase"]
    assert len(hits) == 2, "one finding per matching rule, not one per page"
    assert sorted(h.context for h in hits) == sorted([r"\$[0-9]", "—"])


def test_forbidden_phrase_ignores_script_blocks():
    """Next RSC flight payloads carry $1 / $L3 tokens. audit_live stripped
    <script> before the sweep to stop them false-positiving the dollar rule."""
    page = build_page(body='<script>self.__next_f.push([1,"$1 $L3"])</script>')
    assert "health.forbidden_phrase" not in codes(check(page))


def test_tel_and_phone_missing():
    page = build_page().replace('href="tel:17045550100"', 'href="#"').replace(
        "(704) 555-0100", "call us")
    c = codes(check(page))
    assert "health.tel_link_missing" in c
    assert "health.phone_missing" in c


def test_ga4_missing():
    assert "health.ga4_missing" in codes(check(build_page(ga4=False)))


def test_thin_content():
    f = check(build_page(words=50))
    assert "health.thin_content" in codes(f)
    assert [x for x in f if x.code == "health.thin_content"][0].detail.startswith("words=")


# ── the two deliberate behavior changes ──────────────────────────────────────

def test_img_alt_is_per_image_with_src_as_context():
    page = build_page(images=('<img src="/a.jpg">', '<img src="/b.jpg">',
                              '<img src="/c.jpg" alt="fine">'))
    hits = [x for x in check(page) if x.code == "health.img_alt_missing"]
    assert len(hits) == 2
    assert sorted(h.context for h in hits) == ["/a.jpg", "/b.jpg"]
    assert len({h.fingerprint for h in hits}) == 2, "distinct images, distinct findings"


def test_decorative_alt_is_not_a_missing_alt():
    """B-009. `alt=""` is the WCAG marker for a decorative image, not an absent
    alt. The old `alt="[^"]+"` test failed on the empty string and reported every
    correctly-marked icon: 1158 of 1272 findings on the first leeserie.com run."""
    page = build_page(images=('<img src="/icon.svg" alt="">',
                              '<img src="/hero.jpg" alt="A roof">',
                              '<img src="/real.jpg">'))
    hits = [x for x in check(page) if x.code == "health.img_alt_missing"]
    assert [h.context for h in hits] == ["/real.jpg"]


def test_a_dominant_code_is_warned_about(capsys):
    """A single check owning half a run is the shape a false positive makes."""
    m.warn_dominant_code([m.Finding(gate="site_health", code="health.img_alt_missing",
                                    location="/") for _ in range(30)])
    assert "health.img_alt_missing is 30/30" in capsys.readouterr().err


def test_a_mixed_run_is_not_warned_about(capsys):
    findings = ([m.Finding(gate="site_health", code="health.a", location="/")] * 10 +
                [m.Finding(gate="site_health", code="health.b", location="/")] * 9 +
                [m.Finding(gate="site_health", code="health.c", location="/")] * 9)
    m.warn_dominant_code(findings)
    assert capsys.readouterr().err == ""


def test_page_with_zero_images_has_no_alt_finding():
    """audit_live.py used `len(imgs) > 0 and not missing_alt`, so an image-free
    page reported an alt violation. That is a false positive."""
    assert "health.img_alt_missing" not in codes(check(build_page(images=())))


def test_repeated_identical_findings_get_distinct_ordinals():
    """Two images sharing a src on one page must not collapse to one fingerprint."""
    page = build_page(images=('<img src="/a.jpg">', '<img src="/a.jpg">'))
    hits = [x for x in check(page) if x.code == "health.img_alt_missing"]
    assert len(hits) == 2
    assert sorted(h.ordinal for h in hits) == [0, 1]
    assert len({h.fingerprint for h in hits}) == 2


# ── config-driven skipping ───────────────────────────────────────────────────

def test_unset_config_keys_skip_their_checks_rather_than_fail():
    """No declared phone or GA4 id means those checks cannot be measured. A
    finding on every page would be a fabricated result, so they are skipped.
    Task 3's CLI prints a warning naming each skipped check."""
    bare = {"domain": "example.com", "schema_type": "RoofingContractor",
            "nap": {}, "forbidden_phrases": []}
    c = codes(check(build_page(ga4=False), cfg=bare))
    assert "health.tel_link_missing" not in c
    assert "health.phone_missing" not in c
    assert "health.ga4_missing" not in c


# ── the fingerprint properties phase 3 depends on ────────────────────────────

def test_location_is_the_path_never_the_absolute_url():
    f = check(build_page(title="Short"))
    assert all(x.location == "/roofing/" for x in f)


def test_gate_is_site_health_on_every_finding():
    assert all(x.gate == "site_health" for x in check(build_page(title="Short")))


def test_fingerprint_is_stable_across_identical_runs():
    a = check(build_page(title="Short"))
    b = check(build_page(title="Short"))
    assert [x.fingerprint for x in a] == [x.fingerprint for x in b]


def test_fingerprint_unchanged_when_only_detail_changes():
    """A title going from 7 to 12 characters is the SAME finding getting slightly
    different. If this breaks, the ratchet reports resolved-and-new instead of
    persisting, and run #2 becomes unreadable."""
    a = [x for x in check(build_page(title="Short")) if x.code == "health.title_length"][0]
    b = [x for x in check(build_page(title="Short Title!")) if x.code == "health.title_length"][0]
    assert a.detail != b.detail
    assert a.fingerprint == b.fingerprint


# ── the network seam (curl monkeypatched; still no network) ──────────────────

def test_check_url_returns_findings_and_reachable(monkeypatch):
    monkeypatch.setattr(m, "curl_status", lambda url: 200)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: build_page(title="Short"))
    findings, reachable = m.check_url(URL, CFG)
    assert reachable is True
    assert "health.title_length" in codes(findings)


def test_check_url_marks_status_zero_unreachable_and_returns_no_findings(monkeypatch):
    """status 0 is curl's connection failure. It is NOT a 404 — a 404 is a
    reachable page with a finding. An unreachable URL must contribute nothing,
    so a dead host cannot look like a clean site."""
    monkeypatch.setattr(m, "curl_status", lambda url: 0)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pytest.fail("must not fetch"))
    findings, reachable = m.check_url(URL, CFG)
    assert (findings, reachable) == ([], False)


def test_check_url_404_is_reachable_with_a_finding(monkeypatch):
    monkeypatch.setattr(m, "curl_status", lambda url: 404)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "<html></html>")
    findings, reachable = m.check_url(URL, CFG)
    assert reachable is True
    assert "health.status_not_200" in codes(findings)


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/roofing/</loc></url>
  <url><loc>https://example.com/roofing/</loc></url>
  <url><loc>  https://example.com/siding/  </loc></url>
</urlset>"""


def test_discover_urls_reads_the_live_sitemap(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: SITEMAP)
    assert m.discover_urls(CFG, []) == [
        "https://example.com/", "https://example.com/roofing/", "https://example.com/siding/"]


def test_discover_urls_dedupes_preserving_order(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: SITEMAP)
    urls = m.discover_urls(CFG, [])
    assert len(urls) == len(set(urls))


def test_discover_urls_honors_limit(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: SITEMAP)
    assert m.discover_urls(CFG, [], limit=2) == [
        "https://example.com/", "https://example.com/roofing/"]


def test_discover_urls_explicit_args_skip_the_sitemap(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pytest.fail("must not fetch"))
    assert m.discover_urls(CFG, ["/roofing/", "https://example.com/siding"]) == [
        "https://example.com/roofing/", "https://example.com/siding/"]


def test_discover_urls_root_path_does_not_double_slash(monkeypatch):
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pytest.fail("must not fetch"))
    assert m.discover_urls(CFG, ["/"]) == ["https://example.com/"]


def test_discover_urls_unreachable_sitemap_raises_unreachable(monkeypatch):
    """curl returns '' on failure. No sitemap and no --url means no sources at
    all, which is exit 19 territory, not a green run over zero pages."""
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "")
    with pytest.raises(m.Unreachable):
        m.discover_urls(CFG, [])


def test_discover_urls_sitemap_without_loc_tags_raises_usage(monkeypatch):
    """Fetched but malformed is a different failure from unreachable: something
    answered, it just was not a sitemap. That is exit 2."""
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "<html>404 not found</html>")
    with pytest.raises(m.UsageError):
        m.discover_urls(CFG, [])


# ── the CLI ──────────────────────────────────────────────────────────────────

@pytest.fixture
def project(tmp_path):
    """A client project holding just docs/client-config.yml."""
    proj = tmp_path / "client"
    (proj / "docs").mkdir(parents=True)
    (proj / "docs" / "client-config.yml").write_text(yaml.safe_dump(CFG, sort_keys=False))
    return proj


def run(monkeypatch, project, argv, pages):
    """Drive main() with sys.argv and a fake network. `pages` maps URL -> html,
    or URL -> None to simulate an unreachable host."""
    monkeypatch.setattr("sys.argv", ["wf-site-health", "--project", str(project)] + argv)
    monkeypatch.setattr(m, "curl_status", lambda url: 0 if pages.get(url) is None else 200)
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: pages.get(url) or "")
    return m.main()


def artifact(project):
    month = date.today().strftime("%Y-%m")
    return json.loads((project / "docs" / "audit" / month / "findings.json").read_text())


def test_clean_site_exits_0(monkeypatch, project):
    code = run(monkeypatch, project, ["--url", "/roofing/"],
               {"https://example.com/roofing/": build_page()})
    assert code == 0
    assert artifact(project)["findings"] == []


def test_findings_exit_1_and_are_written(monkeypatch, project):
    code = run(monkeypatch, project, ["--url", "/roofing/"],
               {"https://example.com/roofing/": build_page(title="Short")})
    assert code == 1
    doc = artifact(project)
    assert doc["schema"] == "site-health/1"
    assert doc["domain"] == "example.com"
    assert doc["urls_checked"] == 1
    assert doc["urls_unreachable"] == 0
    assert any(f["code"] == "health.title_length" for f in doc["findings"])
    assert all(len(f["fingerprint"]) == 16 for f in doc["findings"])


def test_every_url_unreachable_exits_19_and_writes_nothing(monkeypatch, project):
    """The load-bearing exit. A run where nothing answered must be red, never a
    green report with zero findings."""
    code = run(monkeypatch, project, ["--url", "/roofing/", "--url", "/siding/"],
               {"https://example.com/roofing/": None, "https://example.com/siding/": None})
    assert code == 19
    month = date.today().strftime("%Y-%m")
    assert not (project / "docs" / "audit" / month / "findings.json").exists()


def test_partial_outage_still_reports_with_the_count_visible(monkeypatch, project):
    code = run(monkeypatch, project, ["--url", "/roofing/", "--url", "/dead/"],
               {"https://example.com/roofing/": build_page(), "https://example.com/dead/": None})
    assert code == 0
    doc = artifact(project)
    assert (doc["urls_checked"], doc["urls_unreachable"]) == (1, 1)


def test_sitemap_without_loc_exits_2(monkeypatch, project):
    monkeypatch.setattr("sys.argv", ["wf-site-health", "--project", str(project)])
    monkeypatch.setattr(m, "curl", lambda url, cache_bust=True: "<html>nope</html>")
    assert m.main() == 2


def test_artifact_is_byte_identical_across_two_runs(monkeypatch, project):
    """sort_findings + sorted JSON keys. A churning artifact would produce a diff
    on every run and make the PR unreadable."""
    pages = {"https://example.com/roofing/": build_page(title="Short", images=(
        '<img src="/b.jpg">', '<img src="/a.jpg">'))}
    run(monkeypatch, project, ["--url", "/roofing/"], pages)
    month = date.today().strftime("%Y-%m")
    path = project / "docs" / "audit" / month / "findings.json"
    first = path.read_bytes()
    run(monkeypatch, project, ["--url", "/roofing/"], pages)
    assert path.read_bytes() == first


def test_unset_config_keys_are_warned_about(monkeypatch, project, capsys):
    """A skipped check must never be silent — that is the failure mode where a
    green report means 'not measured' rather than 'fine'."""
    bare = {"domain": "example.com", "schema_type": "RoofingContractor"}
    (project / "docs" / "client-config.yml").write_text(yaml.safe_dump(bare))
    run(monkeypatch, project, ["--url", "/roofing/"],
        {"https://example.com/roofing/": build_page()})
    err = capsys.readouterr().err
    assert "nap.phone_tel" in err and "ga4_id" in err


# ── --with-serp is actually wired (B-007: implemented is not wired) ───────────

def test_with_serp_passes_the_configs_seed_queries_to_the_provider(tmp_path, monkeypatch):
    """A green unit test on serp_findings proves the function works, not that
    anything calls it. This asserts the call site: the flag reaches the provider
    AND carries the config's seed_queries, not an empty list."""
    from pipeline.audit import measure as m

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "client-config.yml").write_text(
        "client_slug: acme\ndomain: acme.com\ntier: 1\n"
        "seed_queries: ['metal roofing tampa', 'roof repair cost']\n")

    seen = {}

    def fake_serp(domain, queries=None):
        seen["domain"], seen["queries"] = domain, queries
        return [], "ok: 2/2 queries measured"

    monkeypatch.setattr(m, "serp_findings", fake_serp)
    monkeypatch.setattr(m, "discover_urls", lambda *a, **k: ["https://acme.com/"])
    monkeypatch.setattr(m, "check_url", lambda *a, **k: ([], True))
    monkeypatch.setattr(sys, "argv",
                        ["wf-site-measure", "--project", str(tmp_path), "--with-serp"])

    m.main()

    assert seen["domain"] == "acme.com"
    assert seen["queries"] == ["metal roofing tampa", "roof repair cost"]

    doc = json.loads((tmp_path / "docs" / "audit" /
                      date.today().strftime("%Y-%m") / "findings.json").read_text())
    assert doc["providers"]["serp"] == "ok: 2/2 queries measured", \
        "the status string must land in the artifact, or a skip reads as a pass"
