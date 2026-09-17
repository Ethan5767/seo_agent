"""Production monitor (pipeline/scanner/monitor.py).

The MONITOR stage is the only thing watching a client's live site after a merge,
and until now it existed solely as a GitHub Actions workflow inside the client's
repo (.github/workflows/seo-health.reusable.yml). Nothing in the product could
run it or show what it found.

Same checks as that workflow, so the two cannot drift: every route answers 200
with a real body, carries a title, an h1, a canonical and JSON-LD; the sitemap
still lists what it should; the AI citation crawlers still reach the edge.

Pure: routes and fetchers are injected. No network in these tests.
"""
from pipeline.scanner.monitor import monitor_rows, routes_to_watch

PAGE = ('<html><head><title>T</title><link rel="canonical" href="https://x.com/">'
        '<script type="application/ld+json">{"@type":"Hospital"}</script></head>'
        '<body><h1>H</h1>' + ("padding " * 900) + '</body></html>')
SITEMAP = ("<urlset><url><loc>https://x.com/</loc></url><url><loc>https://x.com/a</loc></url>"
           "<url><loc>https://x.com/b</loc></url></urlset>")
ROBOTS_OK = "User-agent: *\nAllow: /\n"
# PerplexityBot is a CITATION crawler — the ones an answer engine quotes from.
# GPTBot is a TRAINING crawler; blocking it is a legitimate client choice and
# must not be reported as a monitor failure (B-080's distinction).
ROBOTS_BLOCKS = "User-agent: PerplexityBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
ROBOTS_TRAINING_ONLY = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"


def _fetch(pages):
    def fetch(url, **kw):
        body, status = pages.get(url, ("", 404))
        return {"body": body, "status": status, "headers": {}, "chain": [{"status": status, "location": ""}]}
    return fetch


def _by(rows):
    return {r["code"]: r for r in rows}


# ── which routes get watched ────────────────────────────────────────────────

def test_routes_come_from_the_sitemap_capped_and_always_include_home():
    got = routes_to_watch("https://x.com/", SITEMAP, limit=2)
    assert got[0] == "https://x.com/", "the home page is always watched"
    assert len(got) == 2


def test_with_no_sitemap_the_home_page_is_still_watched():
    assert routes_to_watch("https://x.com/", None) == ["https://x.com/"]


# ── the route checks ────────────────────────────────────────────────────────

def test_a_healthy_site_passes_every_check():
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_OK, limit=2,
                        fetch=_fetch({"https://x.com/": (PAGE, 200), "https://x.com/a": (PAGE, 200)}))
    by = _by(rows)
    assert by["monitor.routes_live"]["severity"] == "ok"
    assert by["monitor.page_furniture"]["severity"] == "ok"
    assert by["monitor.ai_crawlers"]["severity"] == "ok"


def test_a_route_that_stops_answering_is_an_error_and_is_named():
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_OK, limit=2,
                        fetch=_fetch({"https://x.com/": (PAGE, 200), "https://x.com/a": ("", 500)}))
    row = _by(rows)["monitor.routes_live"]
    assert row["severity"] == "error"
    assert row["pages"] == ["https://x.com/a"]
    assert "500" in row["detail"]


def test_a_200_that_returns_a_blank_shell_is_not_healthy():
    """The failure mode a plain uptime check misses: the server answers, the
    page is empty. 5000 bytes is the workflow's own floor."""
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_OK, limit=2,
                        fetch=_fetch({"https://x.com/": (PAGE, 200), "https://x.com/a": ("<html></html>", 200)}))
    row = _by(rows)["monitor.blank_shell"]
    assert row["severity"] == "error"
    assert row["pages"] == ["https://x.com/a"]


def test_missing_title_h1_canonical_or_schema_is_reported_per_route():
    bare = "<html><head></head><body><p>" + ("x " * 3000) + "</p></body></html>"
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_OK, limit=2,
                        fetch=_fetch({"https://x.com/": (PAGE, 200), "https://x.com/a": (bare, 200)}))
    row = _by(rows)["monitor.page_furniture"]
    assert row["severity"] == "error"
    assert "https://x.com/a" in row["pages"]
    for missing in ("title", "h1", "canonical", "JSON-LD"):
        assert missing in row["why"] or missing in row["detail"], missing


def test_the_sitemap_shrinking_below_the_expected_floor_is_reported():
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_OK, min_sitemap=10,
                        fetch=_fetch({"https://x.com/": (PAGE, 200)}))
    row = _by(rows)["monitor.sitemap_size"]
    assert row["severity"] == "error"
    assert "3" in row["detail"] and "10" in row["detail"]


def test_no_expected_floor_reports_the_count_without_judging_it():
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_OK,
                        fetch=_fetch({"https://x.com/": (PAGE, 200)}))
    row = _by(rows)["monitor.sitemap_size"]
    assert row["severity"] == "ok"
    assert "3" in row["detail"]


def test_an_ai_citation_crawler_blocked_at_the_edge_is_an_error():
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_BLOCKS,
                        fetch=_fetch({"https://x.com/": (PAGE, 200)}))
    row = _by(rows)["monitor.ai_crawlers"]
    assert row["severity"] == "error"
    assert "PerplexityBot" in row["detail"]


def test_blocking_only_a_training_crawler_is_the_clients_choice_not_a_failure():
    """Opting out of model training is a legitimate decision. The monitor guards
    the crawlers an answer engine CITES from, and must not report the other."""
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots=ROBOTS_TRAINING_ONLY, limit=1,
                        fetch=_fetch({"https://x.com/": (PAGE, 200)}))
    assert _by(rows)["monitor.ai_crawlers"]["severity"] == "ok"


def test_no_robots_at_all_is_reported_rather_than_passed():
    rows = monitor_rows("https://x.com/", sitemap=SITEMAP, robots="",
                        fetch=_fetch({"https://x.com/": (PAGE, 200)}))
    row = _by(rows)["monitor.ai_crawlers"]
    assert row["severity"] == "warn"


def test_an_origin_that_answers_nothing_never_reads_as_healthy():
    rows = monitor_rows("https://x.com/", sitemap=None, robots=None,
                        fetch=_fetch({}))
    by = _by(rows)
    assert by["monitor.routes_live"]["severity"] == "error"
    assert all(r["severity"] != "ok" for r in rows), "nothing may pass when nothing answered"


# ── the endpoint the live screen polls ──────────────────────────────────────
#
# A monitor you have to press is not monitoring (operator, 2026-09-16). The
# screen polls this endpoint, so it must be cheap and must NOT write a scan:
# a row saved every minute would bury the audit history it shares a table with.

def test_handle_monitor_returns_rows_and_when_it_checked():
    from pipeline.scanner.server import handle_monitor
    out = handle_monitor({"url": "https://x.com/"},
                         fetch=_fetch({"https://x.com/": (PAGE, 200)}),
                         files=lambda origin: (ROBOTS_OK, SITEMAP))
    assert out["domain"] == "x.com"
    assert out["checked_at"], "the screen shows how fresh this is"
    assert {r["code"] for r in out["rows"]} >= {"monitor.routes_live", "monitor.ai_crawlers"}
    assert out["counts"]["ok"] >= 1


def test_handle_monitor_without_a_url_says_so_rather_than_guessing():
    from pipeline.scanner.server import handle_monitor
    out = handle_monitor({})
    assert out["rows"] == []
    assert "url" in out["error"]


def test_handle_monitor_counts_failing_checks_for_the_headline():
    from pipeline.scanner.server import handle_monitor
    out = handle_monitor({"url": "https://x.com/", "routes": ["https://x.com/", "https://x.com/gone"]},
                         fetch=_fetch({"https://x.com/": (PAGE, 200)}),
                         files=lambda origin: (ROBOTS_OK, SITEMAP))
    assert out["counts"]["error"] >= 1
