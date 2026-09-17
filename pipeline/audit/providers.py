#!/usr/bin/env python3
"""providers.py — the four external measurement sources (v3 §5, phase 6).

Phase 1 measured a live site with `curl` and no accounts. This adds what HTTP
alone cannot see:

| Source | Buys | Cost |
|---|---|---|
| **CrUX** | *field* Core Web Vitals — what Google actually ranks on, not Lighthouse's lab numbers | free |
| **Google Search Console** | impressions, clicks, CTR, position, and query cannibalization | free |
| **DataForSEO On-Page** | crawl-wide truth: broken pages, redirect chains, click depth, duplicate meta | ~$0.25 per 2,000-page crawl |
| **Bright Data SERP** | rank and absence for the config's `seed_queries` — the queries GSC cannot see | per request |

GSC reports only queries that already have impressions, so it is blind by
construction to "we rank nowhere for this". That single gap is why the SERP
source exists; anything GSC can already answer is left to `gsc_findings`.

ONE MODULE, FOUR FUNCTIONS
--------------------------
Not a `providers/` package with an ABC and a registry. v3 §5 is explicit: add the
abstraction when a second vendor in a category lands, not in advance of one.
Bright Data is the first SERP vendor, so it is still one function.

EVERY PROVIDER IS OPTIONAL AND EVERY SKIP IS LOUD
-------------------------------------------------
Credentials come from the environment and nowhere else — no `.env` is read and
nothing is stored in either repo. A provider with no credentials returns
`([], "skipped: ...")`, and `measure.py` records that string in `findings.json`
under `providers`. This matters more than it looks: **a provider that silently
returned nothing would make a site look cleaner than the last cycle**, and the
ratchet would report the difference as RESOLVED. A skip is not a measurement.

The parse functions are pure and take already-fetched payloads. That is the
testable seam — the whole suite runs offline, exactly as `check_page` does.

Environment:
  CRUX_API_KEY            CrUX / PageSpeed Insights API key
  GSC_ACCESS_TOKEN        OAuth access token with webmasters.readonly
  GSC_SITE_URL            property id (default: `sc-domain:<domain>`)
  DATAFORSEO_LOGIN        DataForSEO account
  DATAFORSEO_PASSWORD
  BRIGHTDATA_API_KEY      Bright Data SERP zone API key
  BRIGHTDATA_SERP_ZONE    the SERP zone name
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from pipeline.lib.baseline import Finding, assign_ordinals
from pipeline.lib.common import curl_final_host

# ── field Core Web Vitals thresholds (Google's own "good" boundaries) ────────
CWV_GOOD = {
    "largest_contentful_paint": 2500,       # ms
    "interaction_to_next_paint": 200,       # ms
    "cumulative_layout_shift": 0.10,        # unitless
}
CWV_CODES = {
    "largest_contentful_paint": "crux.lcp_above_good",
    "interaction_to_next_paint": "crux.inp_above_good",
    "cumulative_layout_shift": "crux.cls_above_good",
}

GSC_MIN_IMPRESSIONS = 100       # below this, CTR is noise
GSC_LOW_CTR = 0.02
GSC_CANNIBAL_MIN_IMPRESSIONS = 50
# Decay: the page must have had real demand to lose, or a big percentage drop on
# a tiny base reads as a crisis and spends the client's one content edit badly.
GSC_DECAY_MIN_PREV = 100
GSC_DECAY_MIN_DROP = 0.30
# Striking distance: already on page one's shoulder, not already won, and with
# enough demand that moving it is worth a person's afternoon.
GSC_STRIKING_MIN_POS = 5.0
GSC_STRIKING_MAX_POS = 15.0
GSC_STRIKING_MIN_IMPRESSIONS = 50
DFS_MAX_CLICK_DEPTH = 3
# Named by intent, not by page count: at ten results a page, "page two" would end
# at 20, and 30 is page three's boundary. The bands are "already visible" and
# "close enough that copy can move it" — the page number is not the point.
SERP_TOP_PAGE = 10              # already on page one: nothing to remediate
SERP_REACHABLE_MAX = 30         # beyond this the fix is content, not copy


# ── HTTP (stdlib only — the repo's one runtime dependency stays PyYAML) ──────

def _request(url: str, payload=None, headers=None, timeout: int = 45):
    """(json, error). Never raises: a provider that is down is a skip, not a crash."""
    # Strict zero-spend safety: block outbound network requests to paid vendor endpoints
    if "api.dataforseo.com" in url or "api.brightdata.com" in url:
        return None, "PAID_API_SPEND_FROZEN: live paid network requests disabled to guarantee $0.00 spend"
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs,
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from {url.split('?')[0]}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


# ── CrUX — field Core Web Vitals ─────────────────────────────────────────────

def parse_crux(record: dict, location: str) -> list:
    """Findings for one CrUX record. Fires on any metric outside Google's "good"
    band, carrying the p75 as `detail` — which the fingerprint excludes, so a page
    whose LCP degrades stays PERSISTING instead of pretending to be NEW."""
    out = []
    for metric, good in CWV_GOOD.items():
        p75 = ((record.get("metrics") or {}).get(metric) or {}).get("percentiles", {}).get("p75")
        if p75 is None:
            continue
        try:
            value = float(p75)
        except (TypeError, ValueError):
            continue
        if value > good:
            out.append(Finding("crux", CWV_CODES[metric], location,
                               detail=f"p75={p75} (good <= {good})"))
    return out


def _same_site(resolved: str, domain: str) -> bool:
    """True if `resolved` is `domain`, `www.<domain>`, or a subdomain of it.

    CrUX has real field data for domains this pipeline has no business
    reporting as a client's own — most notably an auth wall's own domain
    (vercel.com, *.pages.dev's SSO host, cloudflareaccess.com), which
    curl_final_host correctly follows to and reports (B-037). A resolved host
    that isn't the same site is not trusted; the caller falls back to the
    literal configured domain instead.
    """
    resolved = resolved.split(":")[0]  # drop a port, if curl reported one
    return resolved == domain or resolved == f"www.{domain}" or resolved.endswith(f".{domain}")


CWV_LABELS = {
    "largest_contentful_paint": "LCP",
    "interaction_to_next_paint": "INP",
    "cumulative_layout_shift": "CLS",
}
# Google's "needs improvement / poor" boundary (above this p75 = poor).
CWV_POOR = {
    "largest_contentful_paint": 4000,
    "interaction_to_next_paint": 500,
    "cumulative_layout_shift": 0.25,
}


def _crux_verdict(metric: str, value: float) -> str:
    if value <= CWV_GOOD[metric]:
        return "good"
    return "needs-improvement" if value <= CWV_POOR[metric] else "poor"


def crux_metrics(domain: str, urls=None) -> tuple:
    """(metrics, status) — every CWV metric with its p75 and verdict, PASS and
    FAIL, for display. Unlike crux_findings (which only fires on problems), this
    surfaces the good values too, so an operator sees the real numbers. Same host
    resolution as crux_findings."""
    key = os.environ.get("CRUX_API_KEY")
    if not key:
        return [], "skipped: CRUX_API_KEY unset"
    endpoint = f"https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={key}"
    resolved = curl_final_host(f"https://{domain}")
    report_domain = resolved if resolved and _same_site(resolved, domain) else domain
    doc, err = _request(endpoint, {"origin": f"https://{report_domain}"})
    note = f" (resolved to {report_domain})" if report_domain != domain else ""
    if err:
        if "404" in err:
            return [], f"no field data: CrUX has no record for {report_domain}{note}"
        return [], f"error: {err}{note}"
    record = (doc or {}).get("record") or {}
    metrics = []
    for metric, good in CWV_GOOD.items():
        p75 = ((record.get("metrics") or {}).get(metric) or {}).get("percentiles", {}).get("p75")
        if p75 is None:
            continue
        try:
            value = float(p75)
        except (TypeError, ValueError):
            continue
        metrics.append({
            "metric": CWV_LABELS[metric], "p75": p75, "good": good,
            "verdict": _crux_verdict(metric, value),
        })
    return metrics, f"ok{note}"


def crux_findings(domain: str, urls=None) -> tuple:
    """(findings, status). Origin-level by default; per-URL when `urls` is given.

    A 404 from CrUX means the origin has too little traffic to have field data.
    That is a fact about the dataset, not a defect in the site, so it emits no
    finding — but it is reported in the status so nobody reads the silence as a
    pass.

    Origin-level queries target the domain's REAL serving host, not the literal
    config string. CrUX is not redirect-aware: a client configured as the bare
    apex that 301s to `www` (or vice versa) has almost no Chrome navigations
    recorded against the un-redirected host, so querying it returns "no record"
    even when the real origin has field data. Proven live 2026-08-14: bare
    `wikipedia.org` had no CrUX record, `en.wikipedia.org` — the real serving
    origin — did. `curl_final_host` (built for B-037) resolves it; the result is
    only trusted when `_same_site` agrees it's the configured domain or one of
    its subdomains — otherwise (unresolvable, or an auth wall's own domain) this
    falls back to the literal string, so the fix is never worse than before it
    and never reports a stranger's Core Web Vitals as the client's. Per-URL mode
    is untouched — those URLs are already absolute.
    """
    key = os.environ.get("CRUX_API_KEY")
    if not key:
        return [], "skipped: CRUX_API_KEY unset"

    endpoint = f"https://chromeuxreport.googleapis.com/v1/records:queryRecord?key={key}"
    if urls:
        targets = [("url", u, "/" + u.split("//", 1)[-1].split("/", 1)[-1]) for u in urls]
        report_domain = domain
    else:
        resolved = curl_final_host(f"https://{domain}")
        report_domain = resolved if resolved and _same_site(resolved, domain) else domain
        targets = [("origin", f"https://{report_domain}", "/")]

    findings, missing, errors = [], 0, []
    for field, value, location in targets:
        doc, err = _request(endpoint, {field: value})
        if err:
            if "404" in err:
                missing += 1
            else:
                errors.append(err)
            continue
        findings += parse_crux((doc or {}).get("record") or {}, location)

    resolved_note = f" (resolved to {report_domain})" if report_domain != domain else ""
    if errors:
        return assign_ordinals(findings), \
            f"partial: {len(errors)} request(s) failed ({errors[0]}){resolved_note}"
    if missing == len(targets):
        return [], f"no field data: CrUX has no record for {report_domain} " \
                   f"(too little traffic){resolved_note}"
    return assign_ordinals(findings), f"ok: {len(targets)} record(s){resolved_note}"


# ── Google Search Console ────────────────────────────────────────────────────

def parse_gsc_pages(rows: list, measured_urls=None) -> list:
    """Per-page findings: low CTR on real impression volume, and — when the
    measured URL set is known — pages the index never showed at all."""
    out, seen = [], set()
    for row in rows:
        page = (row.get("keys") or [""])[0]
        path = "/" + page.split("//", 1)[-1].split("/", 1)[-1] if "//" in page else page
        seen.add(path.rstrip("/") + "/")
        impressions = row.get("impressions") or 0
        ctr = row.get("ctr") or 0.0
        if impressions >= GSC_MIN_IMPRESSIONS and ctr < GSC_LOW_CTR:
            out.append(Finding("gsc", "gsc.low_ctr", path,
                               detail=f"ctr={ctr:.3f} impressions={int(impressions)} "
                                      f"position={row.get('position', 0):.1f}"))
    for url in measured_urls or []:
        path = "/" + url.split("//", 1)[-1].split("/", 1)[-1] if "//" in url else url
        if path.rstrip("/") + "/" not in seen:
            out.append(Finding("gsc", "gsc.no_impressions", path,
                               detail="0 impressions in the window"))
    return out


def parse_gsc_cannibalization(rows: list) -> list:
    """One finding per query answered by two or more of the client's own pages.

    `context` is the query, so the fingerprint is stable while the pages and
    positions underneath it move around.
    """
    by_query: dict = {}
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        query, page = keys[0], keys[1]
        if (row.get("impressions") or 0) < GSC_CANNIBAL_MIN_IMPRESSIONS:
            continue
        by_query.setdefault(query, []).append((page, row.get("position") or 999))

    out = []
    for query, pages in sorted(by_query.items()):
        if len(pages) < 2:
            continue
        pages.sort(key=lambda p: p[1])
        best = pages[0][0]
        path = "/" + best.split("//", 1)[-1].split("/", 1)[-1] if "//" in best else best
        out.append(Finding("gsc", "gsc.cannibalization", path, context=query,
                           detail=f"{len(pages)} pages compete; best position "
                                  f"{pages[0][1]:.1f}"))
    return out


def _form_post(url: str, payload: dict, headers: dict) -> tuple:
    """(json, error) for an `application/x-www-form-urlencoded` POST.

    Separate from `_request`, which sends JSON. Google's token endpoint accepts
    form encoding only. Kept as its own function so the tests can replace it.
    """
    data = urllib.parse.urlencode(payload).encode()
    hdrs = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from {url.split('?')[0]}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


GSC_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def gsc_access_token() -> tuple:
    """(access_token, error). Prefers a refresh token so this can run unattended.

    `GSC_ACCESS_TOKEN` is an OAuth ACCESS token: it dies after about an hour.
    That is the whole reason the GSC lane has never run on a schedule — by the
    time a monthly cycle fires, whatever an operator pasted has expired, and the
    lane reports a skip that reads like "nothing to see here". A refresh token
    does not expire, so with GSC_REFRESH_TOKEN + GSC_CLIENT_ID +
    GSC_CLIENT_SECRET the cycle can mint its own access token every run.

    A direct GSC_ACCESS_TOKEN still wins when set, because it is what an
    operator uses to try one run by hand.

    Every failure path returns a NAMED error rather than an empty result: sharp
    edge #6 — a provider that returned nothing because it was never asked must
    never be indistinguishable from a site with nothing wrong.
    """
    direct = os.environ.get("GSC_ACCESS_TOKEN")
    if direct:
        return direct, None

    refresh = os.environ.get("GSC_REFRESH_TOKEN")
    if not refresh:
        return None, "skipped: neither GSC_ACCESS_TOKEN nor GSC_REFRESH_TOKEN is set"

    missing = [name for name in ("GSC_CLIENT_ID", "GSC_CLIENT_SECRET")
               if not os.environ.get(name)]
    if missing:
        return None, (f"skipped: GSC_REFRESH_TOKEN is set but {' and '.join(missing)} "
                      f"{'is' if len(missing) == 1 else 'are'} missing, so it cannot be exchanged")

    doc, err = _form_post(GSC_TOKEN_ENDPOINT, {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": os.environ["GSC_CLIENT_ID"],
        "client_secret": os.environ["GSC_CLIENT_SECRET"],
    }, {})
    if err:
        return None, f"failed: refreshing the GSC token: {err}"
    token = (doc or {}).get("access_token")
    if not token:
        return None, "failed: the token endpoint returned no access_token"
    return token, None


def _path_of(page: str) -> str:
    """A GSC `page` key -> the site-relative path the rest of the pipeline uses."""
    return "/" + page.split("//", 1)[-1].split("/", 1)[-1] if "//" in page else page


def parse_gsc_decay(prev_rows: list, curr_rows: list) -> list:
    """Pages whose impressions fell materially between two equal windows.

    This is the highest-value content finding available, and it is the one the
    content lane could never produce: a page losing demand is invisible in its
    own HTML. Nothing about the markup changes when a page starts dying.

    Two guards, both deliberate. A page must have had real volume BEFORE
    (`GSC_DECAY_MIN_PREV`) — a 90% fall on 30 impressions is noise, and pointing
    a client at it burns the one content edit they were going to make this month.
    And a page absent from the previous window is new, not decayed.
    """
    prev = {_path_of((r.get("keys") or [""])[0]): (r.get("impressions") or 0)
            for r in prev_rows}
    out = []
    for row in curr_rows:
        path = _path_of((row.get("keys") or [""])[0])
        before = prev.get(path, 0)
        if before < GSC_DECAY_MIN_PREV:
            continue
        after = row.get("impressions") or 0
        drop = (before - after) / before
        if drop >= GSC_DECAY_MIN_DROP:
            out.append(Finding("gsc", "gsc.impressions_decay", path,
                               detail=f"impressions {int(before)} -> {int(after)} "
                                      f"({drop * 100:.0f}% down)"))
    return out


def parse_gsc_striking_distance(rows: list) -> list:
    """Query/page pairs already ranking 5-15 on a query with real demand.

    The band is the point. Below 5 the page has already won and an edit risks
    what it has; beyond ~20 the gap is rarely closed by copy, so recommending a
    rewrite there is selling work that will not pay. This is the only lane in
    which "improve this content" is a defensible instruction, and until now the
    pipeline had no way to identify it.

    `context` is the QUERY, never the position: position moves weekly, and
    fingerprinting it would make every one of these findings NEW on every cycle
    and empty the ratchet of meaning. The number goes in `detail`, which is
    never fingerprinted.
    """
    out = []
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        query, page = keys[0], keys[1]
        position = row.get("position") or 999
        impressions = row.get("impressions") or 0
        if impressions < GSC_STRIKING_MIN_IMPRESSIONS:
            continue
        if not (GSC_STRIKING_MIN_POS <= position <= GSC_STRIKING_MAX_POS):
            continue
        out.append(Finding("gsc", "gsc.striking_distance", _path_of(page),
                           context=query,
                           detail=f"position {position:.1f}, {int(impressions)} impressions"))
    return out


def queries_for_page(rows: list) -> dict:
    """{path: [(query, impressions), ...]} highest-impression first.

    The grounding layer. Every content and AEO check in the scanner judges a
    page's HTML without knowing what the page is FOR — so "1,200 words" is
    reported as a fact about the markup rather than as short or long for the
    thing the page is actually trying to answer. This is the cheapest way to
    close that gap: GSC already knows, per page, the real queries and their
    volume, and it costs nothing.
    """
    by_path: dict = {}
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        query, page = keys[0], keys[1]
        by_path.setdefault(_path_of(page), []).append((query, row.get("impressions") or 0))
    for path in by_path:
        by_path[path].sort(key=lambda qi: qi[1], reverse=True)
    return by_path


def gsc_findings(domain: str, urls=None, days: int = 28) -> tuple:
    token, auth_err = gsc_access_token()
    if not token:
        return [], auth_err
    site = os.environ.get("GSC_SITE_URL") or f"sc-domain:{domain}"

    from datetime import date, timedelta
    end = date.today() - timedelta(days=2)        # GSC data lags ~2 days
    start = end - timedelta(days=days)
    endpoint = ("https://searchconsole.googleapis.com/webmasters/v3/sites/"
                f"{urllib.parse.quote(site, safe='')}/searchAnalytics/query")
    headers = {"Authorization": f"Bearer {token}"}
    window = {"startDate": start.isoformat(), "endDate": end.isoformat()}

    pages, err = _request(endpoint, dict(window, dimensions=["page"], rowLimit=5000), headers)
    if err:
        return [], f"failed: {err}"
    queries, err2 = _request(endpoint, dict(window, dimensions=["query", "page"],
                                            rowLimit=5000), headers)

    # The window immediately before this one, same length, so decay is measured
    # against a like-for-like period rather than against "last month" as a vague
    # idea. Its failure is not fatal: a first cycle has no prior data to compare
    # against and must still return everything else.
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days)
    prev, err3 = _request(endpoint, {"startDate": prev_start.isoformat(),
                                     "endDate": prev_end.isoformat(),
                                     "dimensions": ["page"], "rowLimit": 5000}, headers)

    findings = parse_gsc_pages((pages or {}).get("rows") or [], urls)
    if not err2:
        query_rows = (queries or {}).get("rows") or []
        findings += parse_gsc_cannibalization(query_rows)
        findings += parse_gsc_striking_distance(query_rows)
    if not err3:
        findings += parse_gsc_decay((prev or {}).get("rows") or [],
                                    (pages or {}).get("rows") or [])

    status = f"ok: {len((pages or {}).get('rows') or [])} page rows, {window['startDate']}..{window['endDate']}"
    notes = []
    if err2:
        notes.append(f"query dimension failed: {err2}")
    if err3:
        notes.append(f"no prior window, decay not measured: {err3}")
    return assign_ordinals(findings), status + (f" ({'; '.join(notes)})" if notes else "")


# ── DataForSEO On-Page ───────────────────────────────────────────────────────

DFS_CHECK_CODES = {
    "duplicate_title": "dfs.duplicate_title",
    "duplicate_description": "dfs.duplicate_description",
    "duplicate_content": "dfs.duplicate_content",
    "is_redirect": "dfs.redirect",
    "canonical_chain": "dfs.canonical_chain",
    "is_orphan_page": "dfs.orphan_page",
    "broken_links": "dfs.broken_links",
    "large_page_size": "dfs.large_page_size",
    "no_image_alt": "dfs.image_alt_missing",
}


def parse_dataforseo_pages(items: list) -> list:
    """Findings from `/v3/on_page/pages` items — the crawl-wide facts a per-page
    HTTP check cannot see (depth from the homepage, duplicates across the site,
    redirect chains)."""
    out = []
    for page in items or []:
        url = page.get("url") or ""
        path = "/" + url.split("//", 1)[-1].split("/", 1)[-1] if "//" in url else url
        status = page.get("status_code")
        if isinstance(status, int) and status >= 400:
            out.append(Finding("dataforseo", "dfs.broken_page", path,
                               detail=f"status={status}"))
        depth = page.get("click_depth")
        if isinstance(depth, int) and depth > DFS_MAX_CLICK_DEPTH:
            out.append(Finding("dataforseo", "dfs.click_depth", path,
                               detail=f"depth={depth} (max {DFS_MAX_CLICK_DEPTH})"))
        for check, fired in (page.get("checks") or {}).items():
            if fired and check in DFS_CHECK_CODES:
                out.append(Finding("dataforseo", DFS_CHECK_CODES[check], path))
    return out


def dataforseo_findings(domain: str, max_pages: int = 100, poll_seconds: int = 15,
                        max_polls: int = 20) -> tuple:
    """(findings, status). Posts a crawl, polls the summary, reads the pages.

    Run live for the first time 2026-08-14 against a real domain with real
    DataForSEO credentials: the request/response shapes documented here match
    the vendor. That one run is not exhaustive coverage of every response
    shape the API can return — the automated test suite still only covers the
    pure parser (`parse_dataforseo_pages`), which is the honest boundary; read
    the status string, not just the finding count, on every run.
    """
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not (login and password):
        return [], "skipped: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD unset"

    auth = base64.b64encode(f"{login}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}"}
    base = "https://api.dataforseo.com/v3/on_page"

    posted, err = _request(f"{base}/task_post",
                           [{"target": domain, "max_crawl_pages": max_pages,
                             "load_resources": False, "enable_javascript": False}],
                           headers)
    if err:
        return [], f"failed: {err}"
    try:
        task_id = posted["tasks"][0]["id"]
    except (KeyError, IndexError, TypeError):
        return [], "failed: no task id in the task_post response"

    for _ in range(max_polls):
        time.sleep(poll_seconds)
        summary, err = _request(f"{base}/summary/{task_id}", None, headers)
        if err:
            return [], f"failed: {err}"
        try:
            result = summary["tasks"][0]["result"][0]
        except (KeyError, IndexError, TypeError):
            continue
        if result.get("crawl_progress") == "finished":
            break
    else:
        return [], (f"timed out: the crawl of {domain} did not finish within "
                    f"{max_polls * poll_seconds}s — nothing was measured")

    pages, err = _request(f"{base}/pages", [{"id": task_id, "limit": max_pages}], headers)
    if err:
        return [], f"failed: {err}"
    try:
        items = pages["tasks"][0]["result"][0]["items"]
    except (KeyError, IndexError, TypeError):
        return [], "failed: no items in the pages response"
    return assign_ordinals(parse_dataforseo_pages(items)), f"ok: {len(items)} page(s) crawled"


# ── Bright Data SERP — rank and absence over the config's seed_queries ───────

def _serp_host(url_or_domain: str) -> str:
    """Comparable host for either a full URL or a bare domain. Substring
    matching would let notacme.com satisfy a check for acme.com."""
    s = url_or_domain if "//" in url_or_domain else "//" + url_or_domain
    return urllib.parse.urlsplit(s).netloc.lower().removeprefix("www.")


def parse_serp(payload: dict, domain: str, query: str) -> list:
    """Findings from one `brd_json=1` Google response for one seed query.

    `context` is the query and nothing else. Rank and the ranking URL are both
    volatile, so they live in `detail`, which the fingerprint excludes — without
    that, ordinary rank movement would read as RESOLVED plus NEW every cycle.
    The query is also the ONLY discriminator between two SERP findings, because
    `location` is always "/" — for the same reason CrUX measures at origin level:
    which page ranks is Google's choice and moves without the site changing.

    Collect every hit, then band the best one. Banding inside the scan would make
    the verdict depend on the order `organic[]` happens to arrive in — an
    assumption this module has no way to check and the vendor never promises.
    """
    organic = (payload or {}).get("organic") or []
    if not organic:
        # A missing or empty result set is a broken response, not a site that
        # ranks for nothing. Inventing serp.absent here would be invention.
        return []

    want, hits = _serp_host(domain), []
    for item in organic:
        link = item.get("link") or ""
        # `rank` is the position among organic results; `global_rank` counts ads
        # and SERP features above it — a #1 organic result came back rank=1,
        # global_rank=4 on the first live run. The bands below are organic
        # positions, so preferring global_rank would trip page_two on a site
        # that ranks first. .get default rather than `or`, so rank 0 survives.
        rank = item.get("rank", item.get("global_rank"))
        if _serp_host(link) == want and isinstance(rank, int):
            hits.append((rank, link))

    if not hits:
        return [Finding("serp", "serp.absent", "/", context=query,
                        detail=f"not in the top {len(organic)} organic results")]

    rank, link = min(hits)                       # tuples compare on rank first
    if rank <= SERP_TOP_PAGE:
        return []
    if rank <= SERP_REACHABLE_MAX:
        return [Finding("serp", "serp.page_two", "/", context=query,
                        detail=f"rank={rank} url={link}")]
    return [Finding("serp", "serp.absent", "/", context=query,
                    detail=f"rank={rank}, past the top {SERP_REACHABLE_MAX}")]


def serp_findings(domain: str, queries=None) -> tuple:
    """(findings, status). One Google SERP request per seed query.

    Run live for the first time 2026-08-14 against a real domain with real
    Bright Data credentials: Bright Data's documented request shape matches
    what the vendor actually accepts. That one run is not exhaustive coverage
    of every response shape the API can return — the automated test suite
    still only covers the pure parser (`parse_serp`), which is the honest
    boundary; read the status string, not just the finding count, on every run.
    """
    api_key = os.environ.get("BRIGHTDATA_API_KEY")
    zone = os.environ.get("BRIGHTDATA_SERP_ZONE")
    if not (api_key and zone):
        return [], "skipped: BRIGHTDATA_API_KEY / BRIGHTDATA_SERP_ZONE unset"

    queries = [q.strip() for q in (queries or []) if q and q.strip()]
    if not queries:
        return [], ("skipped: no seed_queries in docs/client-config.yml — there "
                    "is nothing to look up. Run wf-seed-queries to generate a "
                    "list, review it, and commit it to the client repo")

    headers = {"Authorization": f"Bearer {api_key}"}
    findings, measured, failed, last_err = [], 0, [], ""
    for query in queries:
        target = ("https://www.google.com/search?q="
                  + urllib.parse.quote_plus(query) + "&brd_json=1")
        payload, err = _request("https://api.brightdata.com/request",
                                {"zone": zone, "url": target, "format": "raw"},
                                headers)
        if err:
            failed.append(query)
            last_err = err
            continue
        findings.extend(parse_serp(payload, domain, query))
        measured += 1

    if not measured:
        # Carry the error itself. "all queries failed" without the reason sends
        # the operator to the dashboard to find out what a status line was for.
        return [], f"failed: none of the {len(queries)} queries returned — {last_err}"

    # `partial:` rather than `ok:` when anything failed, matching crux_findings —
    # "ok: 1/50 queries measured" leads with ok for a run that measured 2%.
    if failed:
        return assign_ordinals(findings), (
            f"partial: {measured}/{len(queries)} queries measured "
            f"({len(failed)} failed: {', '.join(failed[:3])})")
    return assign_ordinals(findings), f"ok: {measured}/{len(queries)} queries measured"
