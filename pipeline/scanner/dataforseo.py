"""DataForSEO tools for the scanner — the paid "deep scan" layer.

Ported from the dfs-test proving ground (INPUTS-17-TOOLS.md). Each tool is a
pure parser + a thin caller; `call` is injectable so parsers are unit-tested
offline with canned responses (the live API costs money and can't run in CI).

This module starts with the URL-only tools (input = the domain, nothing else).
Everything degrades honestly: no creds -> a "skipped" status, never faked data.
"""
from __future__ import annotations

import base64
import re
import http.client
import json
import os
import time
import urllib.error
import urllib.request

from pipeline.scanner import progress

BASE = "https://api.dataforseo.com"
# The market every paid lookup is measured against: keyword volume, SERP
# position, GBP lookup, mention search.
#
# B-076. This was hardcoded to 2116 — Cambodia — with a comment conceding it was
# "dfs-test default for this client". Every other client was therefore measured
# against Cambodian SERPs and shown the numbers as their own, which is not a
# wrong setting so much as a wrong answer delivered confidently.
#
# 2840 (United States) is the deliberate default; override per client. A value
# that will not parse is refused loudly rather than silently falling back, since
# a silently wrong market is exactly the failure being fixed.
def _location_default() -> int:
    raw = os.environ.get("DFS_LOCATION_CODE", "2840").strip()
    try:
        return int(raw)
    except ValueError:
        # `from None`: this is an operator's typo in an env var, and a chained
        # int() traceback in front of the fix instruction only buries it.
        raise SystemExit(f"DFS_LOCATION_CODE must be a DataForSEO location code, got {raw!r}") from None


def _language_default() -> str:
    return os.environ.get("DFS_LANGUAGE_CODE", "en").strip() or "en"


# Read when each request is built, not once at import. `wf-scan-web` imports this
# module before `main()` loads the repo-root .env, so constants captured at
# import silently ignored a market set there and sent 2840/en (B-076's failure,
# reached by a different road). The constants stay for callers that only want
# the default; every payload calls the functions.
from contextlib import contextmanager
from contextvars import ContextVar

#: The market for the scan in progress: (location_code, language_code), set per
#: request from the project's domain (a .kh site is measured on Google Cambodia).
#: Falls back to DFS_LOCATION_CODE / DFS_LANGUAGE_CODE, then 2840/en.
_MARKET: ContextVar[tuple | None] = ContextVar("dfs_market", default=None)


def location_code() -> int:
    m = _MARKET.get()
    return m[0] if m else _location_default()


def language_code() -> str:
    m = _MARKET.get()
    return m[1] if m else _language_default()


@contextmanager
def market(location: int | None, language: str | None):
    """Measure every DataForSEO call inside this block against one market."""
    token = _MARKET.set((int(location), (language or "en").strip() or "en")) if location else None
    try:
        yield
    finally:
        if token is not None:
            _MARKET.reset(token)
LOCATION_CODE = _location_default()
LANGUAGE_CODE = _language_default()


def _auth() -> str | None:
    login = os.environ.get("DATAFORSEO_LOGIN")
    pw = os.environ.get("DATAFORSEO_PASSWORD")
    if not (login and pw):
        return None
    return "Basic " + base64.b64encode(f"{login}:{pw}".encode()).decode()


def availability() -> tuple[bool, str]:
    """(can a paid call be made right now, why not). No network, no spend.

    The one gate both `call` and the tool catalog read, so the checkbox the UI
    greys out and the refusal a scan reports can never disagree.

    It replaces two latches (d64662d) that kept every paid tool dark in a live
    scan: `call` refused any login except the test fixture's literal `x`, and
    `server._wanted` admitted a paid tool only under pytest. Both were silent,
    so 13 screens read as "nothing found" for a week. Spend is now governed by
    the operator's own switch and the web tier's daily budget, and every refusal
    says which one.
    """
    if not (os.environ.get("DATAFORSEO_LOGIN") and os.environ.get("DATAFORSEO_PASSWORD")):
        return False, "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD unset"
    # Fail closed on anything that reads as "on". The shared .env loader keeps
    # inline comments, so `DATAFORSEO_PAUSE_SPEND=1  # keep paused` arrives as
    # "1  # keep paused", and an exact == "1" left paid calls live.
    pause = os.environ.get("DATAFORSEO_PAUSE_SPEND", "").split("#", 1)[0].strip().lower()
    if pause in {"1", "true", "yes", "on"}:
        return False, "paused by DATAFORSEO_PAUSE_SPEND=1"
    return True, ""


#: Plain names for the requests an operator watches in the live panel.
_LABELS = {
    "on_page/task_post": "start the site crawl",
    "on_page/pages": "the crawled page results",
    "backlinks/summary": "the backlink summary",
    "backlinks/domain_intersection": "the backlink gap",
    "dataforseo_labs/google/ranked_keywords": "the keywords this site ranks for",
    "dataforseo_labs/google/domain_rank_overview": "the domain overview",
    "dataforseo_labs/google/competitors_domain": "competing domains",
    "dataforseo_labs/google/domain_intersection": "the keyword gap",
    "dataforseo_labs/google/historical_rank_overview": "the ranking history",
    "dataforseo_labs/google/bulk_keyword_difficulty": "keyword difficulty",
    "dataforseo_labs/google/search_intent": "search intent",
    "dataforseo_labs/google/keyword_suggestions": "keyword suggestions",
    "dataforseo_labs/google/keyword_ideas": "keyword ideas",
    "serp/google/organic/live/advanced": "a live Google results page",
    "ai_optimization/llm_mentions/search_mentions": "AI engine mentions",
    "business_data/google/my_business_info": "the Google Business Profile",
    "content_analysis/search": "web mentions",
}


def _label(path: str) -> str:
    """'/v3/dataforseo_labs/google/ranked_keywords/live' -> 'the keywords this site ranks for'."""
    key = path.split("?")[0].removeprefix("/v3/").removesuffix("/live")
    for known, name in _LABELS.items():
        if key == known or key.startswith(known):
            return name
    p = key
    for noise in ("dataforseo_labs/google/", "google/", "/advanced", "/regular"):
        p = p.replace(noise, "")
    parts = [seg for seg in p.split("/") if seg and not any(ch.isdigit() for ch in seg[-6:])]
    return " ".join(parts).replace("_", " ").strip() or path


def call(path: str, payload=None, timeout: int = 60, retries: int = 3, sleep=time.sleep,
         quiet: bool = False) -> tuple:
    """(json, error), reporting start and finish to the live activity panel
    (`progress`) unless `quiet` (the crawl's own summary polls report pages
    crawled instead)."""
    if quiet:
        return _call(path, payload, timeout, retries, sleep)
    label = _label(path)
    progress.emit(f"Requesting {label} from DataForSEO", step="request", phase="start", path=path)
    started = time.monotonic()
    doc, err = _call(path, payload, timeout, retries, sleep)
    ms = int((time.monotonic() - started) * 1000)
    if err:
        if not err.startswith("skipped:"):
            progress.emit(f"{label}: {err}", step="request", phase="error", path=path, ms=ms)
    else:
        progress.emit(f"{label} answered", step="request", phase="done", path=path, ms=ms, cost=cost_of(doc))
    return doc, err


def _call(path: str, payload=None, timeout: int = 60, retries: int = 3, sleep=time.sleep) -> tuple:
    """(json, error). POST to DataForSEO with Basic auth (GET when payload is
    None — e.g. the on-page summary poll). Never raises — a provider that is down
    or unauthorized is a skip, not a crash."""
    ok, reason = availability()
    if not ok:
        return None, f"skipped: {reason}"
    auth = _auth()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json", "Authorization": auth},
        method="POST" if data is not None else "GET")
    last = "no attempt made"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                doc = json.loads(r.read().decode())
            refusal = _body_refusal(doc)
            return (None, refusal) if refusal else (doc, None)
        except urllib.error.HTTPError as exc:
            # 5xx is transient (DataForSEO hiccup) — retry; 4xx (auth/bad
            # request) won't fix itself, so return immediately.
            last = f"HTTP {exc.code} from DataForSEO"
            if exc.code >= 500 and attempt < retries - 1:
                sleep(1.5 * (attempt + 1))
                continue
            return None, last
        except (json.JSONDecodeError, UnicodeDecodeError, http.client.HTTPException) as exc:
            # A body cut short in transfer (IncompleteRead), not UTF-8, or not
            # JSON. None of these is an OSError, so they escaped the "never
            # raises" promise and aborted the whole scan. Not retried: the POST
            # was delivered, and a retry can buy the same task twice.
            return None, f"{type(exc).__name__}: {exc}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt < retries - 1:
                sleep(1.5 * (attempt + 1))
    return None, last


def _body_refusal(doc) -> str | None:
    """DataForSEO's in-body refusal, or None when the request succeeded.

    It answers HTTP 200 and reports failure in `status_code` at the top level
    or per task (20000-20199 is success: 20000 Ok, 20100 Task Created). Read as
    success, a refusal became an empty result and the parsers made findings of
    it: '"roofing" - not in top 20', 'not cited by AI engines'. This account hit
    exactly that in August: 40104 on every billable endpoint.
    """
    if not isinstance(doc, dict):
        return None

    def bad(code) -> bool:
        return isinstance(code, int) and not 20000 <= code < 20200

    if bad(doc.get("status_code")):
        return f"DataForSEO {doc['status_code']}: {doc.get('status_message') or 'refused'}"
    for task in doc.get("tasks") or []:
        if isinstance(task, dict) and bad(task.get("status_code")):
            return f"DataForSEO {task['status_code']}: {task.get('status_message') or 'task refused'}"
    return None


def result_items(doc: dict) -> list:
    """DataForSEO nests everything under tasks[0].result[0].items[]. Shared by
    every tool parser."""
    try:
        return (doc["tasks"][0]["result"][0] or {}).get("items") or []
    except (KeyError, IndexError, TypeError):
        return []


def cost_of(doc: dict) -> float:
    """The exact money DataForSEO billed for a request (top-level `cost`, USD).
    Read it so the UI shows the real charge, never a guess. Shared by every tool."""
    try:
        return round(float((doc or {}).get("cost") or 0.0), 4)
    except (TypeError, ValueError):
        return 0.0


def _tool(path: str, payload: list, parse, call=call, status: str = "ok") -> tuple:
    """The one caller shape shared by every DataForSEO tool: POST, and on success
    return (parse(doc), status, cost_of(doc)); on error ([], error, 0.0). Kills
    the per-tool call/err/cost boilerplate. `parse(doc) -> rows`."""
    doc, err = call(path, payload)
    if err:
        return [], err, 0.0
    return parse(doc), status, cost_of(doc)


def _problem(status: str) -> list[str]:
    """A sub-call's status as a list of problems: empty when it ran.

    Success statuses all start with "ok" (`_tool`'s default, or a caller's
    "ok (verify live)"); anything else is a refusal or an error string. The
    composite cards used to bind this to `_s` and drop it, so a card whose every
    call was refused reported "0 row(s)", indistinguishable from a clean site.
    """
    return [] if (status or "").startswith("ok") else [status.removeprefix("skipped: ")]


def _unavailable_rows(tool_key: str, label: str, problems: list[str]) -> list[dict]:
    """One named, ungraded row per distinct reason a card's sub-calls did not run."""
    from pipeline.scanner.rows import unavailable_row
    return [unavailable_row(tool_key, p, label) for p in dict.fromkeys(problems)]


def _card_status(tool_key: str, rows: list, cost: float, problems: list[str]) -> str:
    real = sum(1 for r in rows if not r.get("code", "").startswith("unavailable."))
    line = f"{tool_key}: {real} row(s) · ${cost:.4f}"
    return line + (" · not run: " + "; ".join(dict.fromkeys(problems)) if problems else "")


def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": "dfs.ranked_keyword", "what": what, "why": why,
            "fix": fix, "detail": detail, "severity": severity}


#: How many rows a keyword/ranking parser keeps.
#:
#: It was 15 while the requests below ask DataForSEO for 50 or 100, so every
#: paid call fetched depth we billed for and then discarded - 85 of 100 ranked
#: keywords, 85 of 100 gap rows, 35 of 50 ideas. The rows are already bought by
#: the time a parser sees them; slicing them off saves nothing and is the whole
#: reason the keyword screens looked thin next to a competitor's.
#:
#: Named once so the ask and the keep cannot drift again. Override per call
#: where a screen genuinely wants a shortlist.
TOP_ROWS = 100

#: Competitor lists are a shortlist by nature: past the first handful they are
#: long-tail domains nobody acts on.
TOP_COMPETITORS = 25
# Backlink Overview lists: the Backlinks API bills per row, so ask for the top
# ten referring domains and anchors and keep exactly those.
TOP_LINK_ROWS = 10


def parse_ranked_keywords(doc: dict, top: int = TOP_ROWS) -> list[dict]:
    """Rows for the keywords a domain already ranks for, best positions first.
    Pure — takes the raw DataForSEO response, returns report rows."""
    rows = []
    entries = []
    for it in result_items(doc):
        kw = ((it.get("keyword_data") or {}).get("keyword"))
        rank = (((it.get("ranked_serp_element") or {}).get("serp_item") or {})
                .get("rank_absolute"))
        vol = (((it.get("keyword_data") or {}).get("keyword_info") or {})
               .get("search_volume"))
        if kw and isinstance(rank, int):
            entries.append((rank, kw, vol))
    entries.sort(key=lambda e: e[0])
    for rank, kw, vol in entries[:top]:
        sev = "ok" if rank <= 10 else "warn" if rank <= 30 else "info"
        vol_txt = f", ~{vol}/mo searches" if vol else ""
        rows.append(_row(
            f'"{kw}" — rank #{rank}',
            sev,
            "A keyword this site already ranks for on Google."
            + (" On page one." if rank <= 10 else " On page 2-3 — a copy push can move it up." if rank <= 30 else " Beyond page 3."),
            "hold" if rank <= 10 else "improve the page targeting this term",
            detail=f"position {rank}{vol_txt}",
        ))
    return rows


# `site_audit` / `DFS_RECS` (the providers.dataforseo_findings mapping) were
# removed 2026-09-14: nothing called them outside their own tests, the live Site
# Health tool is `onpage_audit.site_audit_full`, and their codes made Backlink
# Audit and Crawl Issues wait for rows no scan emits (B-115).


def ranked_keywords(domain: str, call=call, top: int = TOP_ROWS) -> tuple:
    """(rows, status, cost_usd) — keywords `domain` ranks for. Input = domain."""
    doc, err = call("/v3/dataforseo_labs/google/ranked_keywords/live",
                    [{"target": domain, "location_code": location_code(),
                      "language_code": language_code(), "limit": TOP_ROWS}])
    if err:
        return [], err, 0.0
    rows = parse_ranked_keywords(doc, top=top)
    cost = cost_of(doc)
    return rows, f"ok: {len(rows)} ranked keyword(s) · ${cost:.4f}", cost


# ── Rankings (tools 8-11): domain overview + SERP position ───────────────────

def parse_domain_overview(doc: dict) -> list[dict]:
    """One visibility row from domain_rank_overview, carrying the full metrics the
    endpoint returns — not just the headline three. The row stays readable as
    text (`what`/`fix`) for any list view, and its `metrics` block feeds the
    Domain Overview dashboard: position distribution, keyword movement, and paid
    figures the old parser discarded."""
    items = result_items(doc)
    if not items:
        return []
    m = items[0].get("metrics") or {}
    org = m.get("organic") or {}
    paid = m.get("paid") or {}
    count = org.get("count")
    if count is None:
        return []

    def n(d: dict, k: str) -> int:
        try:
            return int(d.get(k) or 0)
        except (TypeError, ValueError):
            return 0

    etv = round(float(org.get("etv") or 0))
    pos1 = n(org, "pos_1")
    # The SERP position buckets DataForSEO reports, folded to the six a reader
    # scans at a glance. The fine buckets (21-30 … 91-100) collapse into two.
    distribution = [
        {"label": "#1", "value": pos1},
        {"label": "2-3", "value": n(org, "pos_2_3")},
        {"label": "4-10", "value": n(org, "pos_4_10")},
        {"label": "11-20", "value": n(org, "pos_11_20")},
        {"label": "21-50", "value": n(org, "pos_21_30") + n(org, "pos_31_40") + n(org, "pos_41_50")},
        {"label": "51-100", "value": (n(org, "pos_51_60") + n(org, "pos_61_70") + n(org, "pos_71_80")
                                      + n(org, "pos_81_90") + n(org, "pos_91_100"))},
    ]
    metrics = {
        "keywords": int(count),
        "etv": etv,
        "pos_1": pos1,
        "distribution": distribution,
        "movement": {
            "new": n(org, "is_new"), "up": n(org, "is_up"),
            "down": n(org, "is_down"), "lost": n(org, "is_lost"),
        },
        "paid": {"keywords": n(paid, "count"), "etv": round(float(paid.get("etv") or 0))},
    }
    return [{"code": "dfs.domain_overview", "what": f"Ranks for {count} keywords on Google",
             "why": "The domain's total organic footprint — how many searches it shows up for.",
             "fix": f"est. traffic value ${etv}/mo · {pos1} keyword(s) at position #1",
             "severity": "ok" if count else "info", "detail": f"{count} keywords",
             "metrics": metrics}]


def parse_historical_overview(doc: dict) -> list[dict]:
    """A month-by-month organic trend from historical_rank_overview: one point
    per month with its keyword count and estimated traffic value. Pure."""
    trend = []
    for it in result_items(doc):
        org = (it.get("metrics") or {}).get("organic") or {}
        year, month = it.get("year"), it.get("month")
        if year and month and org:
            try:
                trend.append({"month": f"{int(year):04d}-{int(month):02d}",
                              "keywords": int(org.get("count") or 0),
                              "etv": round(float(org.get("etv") or 0))})
            except (TypeError, ValueError):
                continue
    trend.sort(key=lambda p: p["month"])
    return trend


def historical_overview(domain: str, call=call) -> tuple:
    """(trend, status, cost) — the monthly organic trend for the domain. Returns
    an empty trend on any failure rather than inventing a line."""
    doc, err = call("/v3/dataforseo_labs/google/historical_rank_overview/live",
                    [{"target": domain, "location_code": location_code(),
                      "language_code": language_code()}])
    if err:
        return [], err, 0.0
    trend = parse_historical_overview(doc)
    return trend, f"ok: {len(trend)} month(s)", cost_of(doc)


def domain_overview(domain: str, call=call) -> tuple:
    """(rows, status, cost) — the domain's organic visibility overview."""
    return _tool("/v3/dataforseo_labs/google/domain_rank_overview/live",
                 [{"target": domain, "location_code": location_code(), "language_code": language_code()}],
                 parse_domain_overview, call=call)


def parse_serp_rank(doc: dict, domain: str, keyword: str) -> list[dict]:
    """Where `domain` sits in the live Google results for `keyword` (or absent)."""
    for it in result_items(doc):
        if it.get("type") == "organic" and domain in (it.get("domain") or ""):
            r = it.get("rank_absolute")
            sev = "ok" if isinstance(r, int) and r <= 10 else "warn" if isinstance(r, int) and r <= 30 else "info"
            return [{"code": "dfs.serp_rank", "what": f'"{keyword}" — rank #{r}',
                     "why": f"Where {domain} ranks on Google for this exact term.",
                     "fix": "holding page one" if sev == "ok" else "improve the page targeting this term",
                     "severity": sev, "detail": f"position {r}"}]
    return [{"code": "dfs.serp_rank", "what": f'"{keyword}" — not in top 20',
             "why": f"{domain} does not appear in the first 20 Google results for this term.",
             "fix": "create or optimise a page targeting this keyword",
             "severity": "warn", "detail": "not ranking"}]


def serp_rank(keyword: str, domain: str, call=call) -> tuple:
    """(rows, status, cost) — the client's Google position for one keyword."""
    return _tool("/v3/serp/google/organic/live/advanced",
                 [{"keyword": keyword, "location_code": location_code(),
                   "language_code": language_code(), "depth": 20}],
                 lambda d: parse_serp_rank(d, domain, keyword), call=call)


def _tag_competitor(rows: list[dict], domain: str) -> list[dict]:
    """Mark rows as a competitor's, not yours, so one table reads you-vs-them.
    Prefixes the label with the domain and carries it in `competitor` for the
    UI to group on. Pure; never mutates the input rows."""
    out = []
    for r in rows:
        r = dict(r)
        r["what"] = f"{domain}: {r.get('what', '')}"
        r["competitor"] = domain
        out.append(r)
    return out


def rankings(domain: str, keywords=None, call=call, max_serp: int = 5,
             competitors=None) -> tuple:
    """(rows, status, cost) — the Rankings card: ranked keywords + domain
    overview + a SERP position check for up to `max_serp` of the client's
    target keywords. Cost is the exact sum of every call's reported cost.

    When `competitors` are named, each one's overview and top keywords are
    fetched too and tagged with its domain, so Domain Overview and Organic
    Rankings read as a you-vs-them comparison. No competitors means the exact
    single-domain behaviour as before — the competitor side is purely additive."""
    keywords = keywords or []
    rows: list[dict] = []
    cost = 0.0
    problems: list[str] = []
    r, s, c = ranked_keywords(domain, call=call); rows += r; cost += c; problems += _problem(s)
    ov, s, c = domain_overview(domain, call=call); cost += c; problems += _problem(s)
    # Fold the monthly trend into the overview row's metrics, so the dashboard
    # reads one object. A failed or empty trend simply leaves the chart out.
    if ov:
        trend, ts, tc = historical_overview(domain, call=call); cost += tc; problems += _problem(ts)
        if trend:
            ov[0].setdefault("metrics", {})["trend"] = trend
    rows += ov
    for kw in keywords[:max_serp]:
        r, s, c = serp_rank(kw, domain, call=call); rows += r; cost += c; problems += _problem(s)
    # The competitor side: one overview row plus a shortlist of their ranked
    # keywords, per named competitor. Capped at three domains and a short
    # keyword list so a comparison never balloons the table or the bill.
    for comp in (competitors or [])[:3]:
        if not comp:
            continue
        r, s, c = domain_overview(comp, call=call); rows += _tag_competitor(r, comp); cost += c; problems += _problem(s)
        r, s, c = ranked_keywords(comp, call=call, top=25); rows += _tag_competitor(r, comp); cost += c; problems += _problem(s)
    cost = round(cost, 4)
    rows += _unavailable_rows("rankings", "Rankings", problems)
    return rows, _card_status("rankings", rows, cost, problems), cost


def compare_domains(domain: str, competitor_list=None, call=call, max_competitors: int = 3) -> tuple:
    """(rows, status, cost) — Compare Domains: the domain's overview next to up
    to `max_competitors` competitors' overviews, one `dfs.compare_domain` row per
    domain. The competitors the operator names are the ones compared; with none
    named, the top domains DataForSEO finds competing for the same terms are used.

    This is the only tool that reads the competitor input as a comparison. The
    Compare Domains page used to run the whole Keywords card and show the
    discovered competitor list, ignoring the competitors it made the operator type."""
    you = bare_domain(domain)
    rows: list[dict] = []
    cost = 0.0
    problems: list[str] = []
    named = [d for d in dict.fromkeys(bare_domain(c) for c in (competitor_list or [])) if d and d != you]
    others = named[:max_competitors]
    if not others:
        found, s, c = competitors(domain, call=call); cost += c; problems += _problem(s)
        others = [d for d in dict.fromkeys(bare_domain(r.get("what", "")) for r in found) if d and d != you][:max_competitors]
        if not others and not problems:
            problems.append("no competitors named, and DataForSEO found none for this domain")
    for target, is_you in [(you, True)] + [(d, False) for d in others]:
        r, s, c = domain_overview(target, call=call); cost += c; problems += _problem(s)
        for row in r:
            row = {**row, "code": "dfs.compare_domain", "domain": target}
            if not is_you:
                row["competitor"] = target
            row["what"] = f"{target}{' (you)' if is_you else ''}: {row.get('what', '')}"
            rows.append(row)
    cost = round(cost, 4)
    rows += _unavailable_rows("compare", "Compare Domains", problems)
    return rows, _card_status("compare", rows, cost, problems), cost


# ── Keywords (tools 12-16): volume, ideas, gap, competitors ──────────────────

def _kw_vol(it: dict) -> tuple:
    """(keyword, search_volume) from either a google_ads item (flat) or a Labs
    item (nested under keyword_info / keyword_data)."""
    kw = it.get("keyword") or (it.get("keyword_data") or {}).get("keyword")
    vol = it.get("search_volume")
    if vol is None:
        info = it.get("keyword_info") or (it.get("keyword_data") or {}).get("keyword_info") or {}
        vol = info.get("search_volume")
    return kw, vol


def _kw_row(code: str, kw: str, vol, sev: str, why: str, fix: str) -> dict:
    return {"code": code, "what": f'"{kw}"' + (f" — {vol}/mo searches" if vol else ""),
            "why": why, "fix": fix, "severity": sev, "detail": f"{vol}/mo" if vol else ""}


def parse_search_volume(doc: dict, top: int = TOP_ROWS) -> list[dict]:
    """keywords_data/google_ads/search_volume returns one object PER KEYWORD
    directly in `tasks[0].result` (no `items`). Reading `result[0].items` only
    returned nothing while each call was billed (~$0.09); verified live
    2026-09-14: "hospital phnom penh" 720/mo, location 2116."""
    try:
        direct = [r for r in (doc["tasks"][0]["result"] or []) if isinstance(r, dict) and "keyword" in r]
    except (KeyError, IndexError, TypeError):
        direct = []
    rows = []
    for it in (direct or result_items(doc))[:top]:
        kw, vol = _kw_vol(it)
        if kw:
            rows.append(_kw_row("dfs.keyword_volume", kw, vol, "info",
                                "Real monthly search demand for this term.",
                                "prioritise terms with demand you can realistically rank for"))
    return rows


def parse_keyword_ideas(doc: dict, top: int = TOP_ROWS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw, vol = _kw_vol(it)
        if kw:
            rows.append(_kw_row("dfs.keyword_idea", kw, vol, "info",
                                "A related keyword you could target with new/expanded content.",
                                "consider a page or section for this term"))
    return rows


def parse_keyword_gap(doc: dict, competitor: str, top: int = TOP_ROWS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw, vol = _kw_vol(it)
        if kw:
            rows.append(_kw_row("dfs.keyword_gap", kw, vol, "warn",
                                f"{competitor} ranks for this term and you do not — a gap you're losing.",
                                "create content targeting this term to close the gap"))
    return rows


def parse_competitors(doc: dict, top: int = TOP_COMPETITORS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        dom = it.get("domain") or it.get("target")
        if dom:
            rows.append({"code": "dfs.competitor", "what": dom,
                         "why": "A domain competing for your keywords on Google.",
                         "fix": "study their pages for the terms you're missing",
                         "severity": "info", "detail": ""})
    return rows


def search_volume(keywords: list, call=call) -> tuple:
    if not keywords:
        return [], "skipped: no keywords", 0.0
    return _tool("/v3/keywords_data/google_ads/search_volume/live",
                 [{"keywords": keywords, "location_code": location_code(), "language_code": language_code()}],
                 parse_search_volume, call=call)


def keyword_ideas(seeds: list, call=call) -> tuple:
    if not seeds:
        return [], "skipped: no seed keywords", 0.0
    return _tool("/v3/dataforseo_labs/google/keyword_ideas/live",
                 [{"keywords": seeds, "location_code": location_code(),
                   "language_code": language_code(), "limit": TOP_ROWS}],
                 parse_keyword_ideas, call=call)


def parse_keyword_suggestions(doc: dict, top: int = TOP_ROWS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw, vol = _kw_vol(it)
        if kw:
            rows.append(_kw_row("dfs.keyword_suggestion", kw, vol, "info",
                                "A long-tail variant of your seed term — often easier to rank for.",
                                "consider a page/section for high-intent long-tails"))
    return rows


def keyword_suggestions(seed: str, call=call) -> tuple:
    if not seed:
        return [], "skipped: no seed keyword", 0.0
    return _tool("/v3/dataforseo_labs/google/keyword_suggestions/live",
                 [{"keyword": seed, "location_code": location_code(),
                   "language_code": language_code(), "limit": TOP_ROWS}],
                 parse_keyword_suggestions, call=call)


def keyword_gap(you: str, competitor: str, call=call) -> tuple:
    if not competitor:
        return [], "skipped: no competitor", 0.0
    return _tool("/v3/dataforseo_labs/google/domain_intersection/live",
                 [{"target1": competitor, "target2": you, "intersections": False,
                   "location_code": location_code(), "language_code": language_code(), "limit": TOP_ROWS}],
                 lambda d: parse_keyword_gap(d, competitor), call=call)


def competitors(domain: str, call=call) -> tuple:
    return _tool("/v3/dataforseo_labs/google/competitors_domain/live",
                 [{"target": domain, "location_code": location_code(),
                   "language_code": language_code(), "limit": TOP_COMPETITORS}],
                 parse_competitors, call=call)


def bare_domain(value: str) -> str:
    """'https://www.Rival.com/en?x=1' -> 'rival.com'. DataForSEO's backlinks and
    Labs endpoints want targets without scheme or www; projects store competitors
    however they were typed (the hospital's is 'https://royalphnompenhhospital.com/')."""
    v = str(value or "").strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = re.split(r"[/?#]", v, maxsplit=1)[0]
    return v.split(":")[0].removeprefix("www.")


#: Referring domains with a DataForSEO spam score at or above this are shown
#: with a warning rather than as an opportunity.
SPAM_WARN = 50


def parse_backlink_gap(doc: dict, competitors: list[str], top: int = TOP_ROWS) -> list[dict]:
    """Rows from backlinks/domain_intersection: each item's `target` is a domain
    linking to the competitor(s) and not to you."""
    try:
        result = doc["tasks"][0]["result"][0] or {}
    except (KeyError, IndexError, TypeError):
        return []
    items = result.get("items") or []
    total = result.get("total_count") or len(items)
    names = ", ".join(competitors)
    rows = [{"code": "dfs.backlink_gap_summary",
             "what": f"{total} domains link to {names} but not to you",
             "why": "Sites already linking to a competitor are the likeliest to link to you.",
             "fix": "work the list from the highest rank down", "severity": "info",
             "detail": f"showing the top {min(len(items), top)}"}]
    entries = []
    for it in items:
        hits = [v for v in (it.get("domain_intersection") or {}).values() if isinstance(v, dict)]
        if not hits:
            continue
        dom = hits[0].get("target")
        if not dom:
            continue
        rank = max(int(h.get("rank") or 0) for h in hits)
        links = sum(int(h.get("backlinks") or 0) for h in hits)
        spam = max(int(h.get("backlinks_spam_score") or 0) for h in hits)
        count = (it.get("summary") or {}).get("intersections_count") or len(hits)
        entries.append((rank, dom, links, spam, count, hits[0].get("first_seen") or ""))
    entries.sort(key=lambda e: (-e[0], e[3]))
    for rank, dom, links, spam, count, first in entries[:top]:
        of = f"{count} of {len(competitors)} competitors" if len(competitors) > 1 else names
        rows.append({
            "code": "dfs.backlink_gap", "what": dom,
            "why": f"Links to {of}, not to you.",
            "fix": ("check this site before outreach: high spam score" if spam >= SPAM_WARN
                    else "reach out with a page worth linking to"),
            "severity": "warn" if spam >= SPAM_WARN else "info",
            "detail": f"rank {rank} · {links} links · spam {spam}" + (f" · since {first[:10]}" if first else ""),
        })
    return rows


def backlink_gap(domain: str, competitor_list=None, call=call, discover: bool = True, max_competitors: int = 3) -> tuple:
    """(rows, status, cost) — referring domains your competitors have and you do
    not. Competitors come from the project; with none, DataForSEO's own
    competitor list for the domain is used (one extra Labs call)."""
    you = bare_domain(domain)
    rivals = [bare_domain(c) for c in (competitor_list or []) if bare_domain(c) and bare_domain(c) != you]
    cost = 0.0
    if not rivals and discover:
        comp_rows, s, c = competitors(you, call=call)
        cost += c
        if not s.startswith("ok"):
            from pipeline.scanner.rows import unavailable_row
            return [unavailable_row("backlink_gap", f"could not find competitors: {s}", "Backlink Gap")], f"not run: {s}", round(cost, 4)
        rivals = [bare_domain(r["what"]) for r in comp_rows if bare_domain(r["what"]) not in ("", you)]
    rivals = list(dict.fromkeys(rivals))[:max_competitors]
    if not rivals:
        from pipeline.scanner.rows import unavailable_row
        reason = "needs a competitor: add one to the project"
        return [unavailable_row("backlink_gap", reason, "Backlink Gap")], f"not run: {reason}", round(cost, 4)
    doc, err = call("/v3/backlinks/domain_intersection/live",
                    [{"targets": {str(i + 1): r for i, r in enumerate(rivals)},
                      "exclude_targets": [you], "limit": TOP_ROWS, "intersection_mode": "all"}])
    if err:
        from pipeline.scanner.rows import unavailable_row
        return [unavailable_row("backlink_gap", err, "Backlink Gap")], err, round(cost, 4)
    cost += cost_of(doc)
    rows = parse_backlink_gap(doc, rivals)
    total = rows[0]["what"].split(" ")[0] if rows else "0"
    return rows, f"backlink gap vs {', '.join(rivals)}: {total} domains · ${cost:.4f}", round(cost, 4)


def keywords_card(domain: str, keywords=None, competitor_list=None, call=call) -> tuple:
    """(rows, status, cost) — the Keywords card: competitors + keyword-gap vs the
    top competitor + search volume for the client's terms + fresh ideas. The
    competitor for the gap comes from the onboard list, else auto-discovered."""
    keywords = keywords or []
    rows: list[dict] = []
    cost = 0.0
    problems: list[str] = []
    comp_rows, s, c = competitors(domain, call=call); rows += comp_rows; cost += c; problems += _problem(s)
    competitor = bare_domain((competitor_list or [""])[0]) or None
    if not competitor and comp_rows:
        competitor = comp_rows[0]["what"]
    if competitor:
        r, s, c = keyword_gap(domain, competitor, call=call); rows += r; cost += c; problems += _problem(s)
    elif not problems:
        problems.append("keyword gap needs a competitor: add one to the project, "
                        "or DataForSEO found none for this domain")
    seeded = ""
    if not keywords:
        # No target keywords on the project: seed from what the site already
        # ranks for, a real DataForSEO answer, rather than refusing five tools.
        ranked, s, c = ranked_keywords(domain, call=call); cost += c
        if s.startswith("ok"):
            keywords = [m.group(1) for r in ranked
                        if (m := re.match(r'^"(.+)" — rank #\d+', r.get("what", "")))][:5]
            if keywords:
                seeded = f" · seeds: {len(keywords)} keywords the site ranks for (project has none)"
        else:
            problems += _problem(s)
    if keywords:
        for fn, arg in ((search_volume, keywords), (keyword_ideas, keywords),
                        (keyword_difficulty, keywords), (search_intent, keywords),
                        (keyword_suggestions, keywords[0])):
            r, s, c = fn(arg, call=call); rows += r; cost += c; problems += _problem(s)
    else:
        problems.append("no target keywords on this project: volume, ideas, difficulty, "
                        "intent and suggestions need at least one")

    # Clustering is derived, not fetched: it groups the keyword rows above into
    # candidate pages, so the plan costs nothing beyond the calls already made.
    # Imported here rather than at module scope so `clusters` can import nothing
    # from this module and stay independently testable.
    from pipeline.scanner.clusters import cluster_rows
    keyword_codes = ("dfs.keyword_idea", "dfs.keyword_suggestion",
                     "dfs.keyword_gap", "dfs.keyword_volume")
    rows += cluster_rows([r for r in rows if r.get("code") in keyword_codes])

    cost = round(cost, 4)
    rows += _unavailable_rows("keywords", "Keywords", problems)
    return rows, _card_status("keywords", rows, cost, problems) + seeded, cost


# ── AI visibility (tool 17): LLM mentions ────────────────────────────────────

def parse_llm_mentions(doc: dict, brand: str) -> list[dict]:
    """One summary row: is the brand cited by AI answer engines, and how often."""
    items = result_items(doc)
    if not items:
        return [{"code": "dfs.llm_mentions", "what": f"{brand}: not cited by AI engines",
                 "why": "AI answer engines (ChatGPT, Perplexity, Google AI) don't reference the brand yet — the AEO gap.",
                 "fix": "publish citable, factual content (clear answers, stats, entity schema) so AI engines cite you",
                 "severity": "warn", "detail": "0 mentions"}]
    models = sorted({str(it.get("ai_provider") or it.get("model") or it.get("llm_model") or "AI")
                     for it in items})
    return [{"code": "dfs.llm_mentions", "what": f"{brand}: cited {len(items)} time(s) by AI",
             "why": "AI answer engines already reference the brand — solid AEO footing.",
             "fix": "keep and expand the citable content that's earning the mentions",
             "severity": "ok", "detail": ", ".join(models)[:80]}]


def llm_mentions(brand: str, domain: str, call=call) -> tuple:
    """(rows, status, cost) — is `brand`/`domain` cited across AI answer engines."""
    target = [
        {"keyword": brand, "search_filter": "include",
         "search_scope": ["answer"], "match_type": "partial_match"},
        {"domain": domain, "search_filter": "include", "search_scope": ["sources"]},
    ]
    return _tool("/v3/ai_optimization/llm_mentions/search_mentions/live",
                 [{"target": target, "location_code": location_code(),
                   "language_code": language_code(), "limit": TOP_ROWS}],
                 lambda d: parse_llm_mentions(d, brand), call=call)


# ── Backlinks (SOP Measure: backlink analysis) ───────────────────────────────
# NOTE: endpoint not in the tested INPUTS-17 doc — parser built to DataForSEO's
# documented Backlinks Summary shape; verify against a live response.

def parse_backlinks(doc: dict) -> list[dict]:
    res = (doc.get("tasks") or [{}])[0].get("result") if doc else None
    r0 = (res or [{}])[0] or {}
    if not r0:
        return []
    bl = r0.get("backlinks") or 0
    rd = r0.get("referring_domains") or 0
    rank = r0.get("rank")
    rows = [{"code": "dfs.backlinks",
             "what": f"{bl} backlinks from {rd} referring domains",
             "why": "Backlinks are a top Google ranking factor — other sites vouching for yours.",
             "fix": "keep earning links from relevant, trusted sites" if bl else "no links yet — start earning quality backlinks",
             "severity": "ok" if bl else "warn",
             "detail": f"authority rank {rank}" if rank is not None else "",
             "metrics": _link_profile(r0)}]
    broken = r0.get("broken_backlinks") or 0
    if broken:
        rows.append({"code": "dfs.broken_backlinks", "what": f"{broken} broken backlink(s)",
                     "why": "Links pointing at dead pages on your site waste the authority they'd pass.",
                     "fix": "restore or 301-redirect those target URLs so the link equity isn't lost",
                     "severity": "warn", "detail": f"{broken} broken"})
    return rows


def _top_counts(d, n: int = 8) -> list[dict]:
    """{"com": 5322, "": 9, ...} -> [{"label": "com", "value": 5322}, ...], largest
    first, blank keys (unknown country / TLD) dropped rather than labelled."""
    if not isinstance(d, dict):
        return []
    pairs = [(str(k), int(v)) for k, v in d.items() if k and isinstance(v, (int, float))]
    return [{"label": k, "value": v} for k, v in sorted(pairs, key=lambda kv: -kv[1])[:n]]


def _link_profile(r: dict) -> dict:
    """The Backlinks Summary figures the Backlink Overview charts, as DataForSEO
    reports them (field names verified against sandbox.dataforseo.com, 2026-09-15)."""
    keys = ("rank", "backlinks", "backlinks_spam_score", "referring_domains", "referring_domains_nofollow",
            "referring_main_domains", "referring_ips", "referring_subnets", "referring_pages",
            "referring_pages_nofollow", "broken_backlinks", "broken_pages", "first_seen")
    out = {k: r.get(k) for k in keys if r.get(k) is not None}
    out.update({
        "tld": _top_counts(r.get("referring_links_tld")),
        "types": _top_counts(r.get("referring_links_types")),
        "attributes": _top_counts(r.get("referring_links_attributes")),
        "countries": _top_counts(r.get("referring_links_countries")),
        "platforms": _top_counts(r.get("referring_links_platform_types")),
    })
    return out


def parse_referring_domains(doc: dict, top: int = TOP_LINK_ROWS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        dom = it.get("domain")
        if not dom:
            continue
        since = str(it.get("first_seen") or "")[:10]
        rows.append({"code": "dfs.referring_domain", "what": dom,
                     "why": "A site linking to this domain.",
                     "fix": "keep the relationship; ask for links to your key pages",
                     "severity": "info",
                     "detail": f"rank {it.get('rank')} · {it.get('backlinks') or 0} backlinks · spam {it.get('backlinks_spam_score') or 0}"
                               + (f" · since {since}" if since else ""),
                     "metrics": {"rank": it.get("rank"), "backlinks": it.get("backlinks"),
                                 "spam": it.get("backlinks_spam_score"), "first_seen": since or None,
                                 "nofollow": bool(it.get("referring_pages") and it.get("referring_pages_nofollow") == it.get("referring_pages"))}})
    return rows


def parse_anchors(doc: dict, top: int = TOP_LINK_ROWS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        # A null or blank anchor is real: image links and bare URLs carry no text.
        label = str(it.get("anchor") or "").strip() or "(no anchor text)"
        rows.append({"code": "dfs.anchor", "what": f'"{label}"',
                     "why": "Link text other sites use when they link here.",
                     "fix": "a natural mix of brand, URL and topic anchors is healthy",
                     "severity": "info",
                     "detail": f"{it.get('backlinks') or 0} backlinks from {it.get('referring_domains') or 0} domains",
                     "metrics": {"backlinks": it.get("backlinks"), "referring_domains": it.get("referring_domains")}})
    return rows


def parse_backlink_history(doc: dict) -> list[dict]:
    """One row carrying the monthly series: backlinks, referring domains, new/lost."""
    pts = []
    for it in result_items(doc):
        date = str(it.get("date") or "")[:7]
        if not date:
            continue
        pts.append({"date": date, "backlinks": it.get("backlinks") or 0,
                    "referring_domains": it.get("referring_domains") or 0,
                    "new_referring_domains": it.get("new_referring_domains") or 0,
                    "lost_referring_domains": it.get("lost_referring_domains") or 0,
                    "new_backlinks": it.get("new_backlinks") or 0,
                    "lost_backlinks": it.get("lost_backlinks") or 0})
    if not pts:
        return []
    pts.sort(key=lambda p: p["date"])
    first, last = pts[0], pts[-1]
    return [{"code": "dfs.backlink_history",
             "what": f"Referring domains {first['referring_domains']} → {last['referring_domains']} ({first['date']} to {last['date']})",
             "why": "How the link profile has grown or shrunk month by month.",
             "fix": "a steady gain in referring domains is the healthy shape",
             "severity": "info", "detail": f"{len(pts)} months",
             "metrics": {"points": pts}}]


def backlink_overview(domain: str, call=call, months: int = 12, today=None) -> tuple:
    """(rows, status, cost) — Backlink Overview: the summary with its full link
    profile, the top referring domains, the top anchors, and a monthly history.
    Four Backlinks API calls; the cost is the sum of what each reports."""
    import datetime as _dt
    target = bare_domain(domain) or domain
    rows: list[dict] = []
    cost = 0.0
    problems: list[str] = []
    today = today or _dt.date.today()
    y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
    start = _dt.date(y, m + 1, 1).isoformat()  # the same month, `months` back
    for path, payload, parser in (
        ("/v3/backlinks/summary/live", {"target": target, "internal_list_limit": 10, "backlinks_status_type": "live"}, parse_backlinks),
        ("/v3/backlinks/referring_domains/live", {"target": target, "limit": TOP_LINK_ROWS, "order_by": ["rank,desc"], "backlinks_status_type": "live"}, parse_referring_domains),
        ("/v3/backlinks/anchors/live", {"target": target, "limit": TOP_LINK_ROWS, "order_by": ["backlinks,desc"], "backlinks_status_type": "live"}, parse_anchors),
        ("/v3/backlinks/history/live", {"target": target, "date_from": start}, parse_backlink_history),
    ):
        r, s, c = _tool(path, [payload], parser, call=call); rows += r; cost += c; problems += _problem(s)
    cost = round(cost, 4)
    rows += _unavailable_rows("backlink_overview", "Backlink Overview", problems)
    return rows, _card_status("backlink_overview", rows, cost, problems), cost


def backlinks(domain: str, call=call) -> tuple:
    """(rows, status, cost) — backlink profile summary. Input = domain only."""
    return _tool("/v3/backlinks/summary/live",
                 [{"target": domain, "internal_list_limit": 10, "backlinks_status_type": "live"}],
                 parse_backlinks, call=call)


# ── Historical rank overview (#11): visibility trend over time ───────────────

def parse_historical_rank(doc: dict) -> list[dict]:
    """One trend row: is the domain's organic keyword count rising or falling?"""
    pts = []
    for it in result_items(doc):
        org = (it.get("metrics") or {}).get("organic") or {}
        cnt = org.get("count")
        if isinstance(cnt, (int, float)):
            pts.append((it.get("year"), it.get("month"), int(cnt)))
    if not pts:
        return []
    first, last = pts[0][2], pts[-1][2]
    delta = last - first
    sev = "ok" if delta > 0 else "warn" if delta < 0 else "info"
    arrow = "up" if delta > 0 else "down" if delta < 0 else "flat"
    return [{"code": "dfs.rank_trend",
             "what": f"Visibility trend: {last} keywords ({arrow} {abs(delta)} vs earliest sampled)",
             "why": "Whether the site is gaining or losing organic footprint over time.",
             "fix": "keep the momentum" if delta > 0 else "reverse the decline — refresh decaying pages" if delta < 0 else "push for growth",
             "severity": sev, "detail": f"{first} → {last}"}]


def historical_rank(domain: str, call=call) -> tuple:
    """(rows, status, cost) — organic visibility trend. Input = domain only."""
    return _tool("/v3/dataforseo_labs/google/historical_rank_overview/live",
                 [{"target": domain, "location_code": location_code(), "language_code": language_code()}],
                 parse_historical_rank, call=call)


# ── Keyword difficulty (Labs): how hard each term is to rank for ─────────────

def parse_keyword_difficulty(doc: dict, top: int = TOP_ROWS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw = it.get("keyword") or (it.get("keyword_data") or {}).get("keyword")
        kd = it.get("keyword_difficulty")
        if kd is None:
            kd = (it.get("keyword_properties") or {}).get("keyword_difficulty")
        if kw and isinstance(kd, (int, float)):
            sev = "ok" if kd <= 30 else "warn" if kd <= 60 else "info"
            rows.append({"code": "dfs.keyword_difficulty", "what": f'"{kw}" — difficulty {int(kd)}/100',
                         "why": "How hard it is to rank for this term (0 easy, 100 brutal).",
                         "fix": "target low-difficulty terms first for quick wins" if kd <= 30 else "hard — needs strong content + links",
                         "severity": sev, "detail": f"KD {int(kd)}"})
    return rows


def keyword_difficulty(keywords: list, call=call) -> tuple:
    if not keywords:
        return [], "skipped: no keywords", 0.0
    return _tool("/v3/dataforseo_labs/google/bulk_keyword_difficulty/live",
                 [{"keywords": keywords, "location_code": location_code(), "language_code": language_code()}],
                 parse_keyword_difficulty, call=call)


# ── Search intent (Labs): what the searcher wants per keyword ────────────────

def parse_search_intent(doc: dict, top: int = TOP_ROWS) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw = it.get("keyword") or (it.get("keyword_data") or {}).get("keyword")
        intent = (it.get("keyword_intent") or {}).get("label") or it.get("main_intent")
        if kw and intent:
            rows.append({"code": "dfs.search_intent", "what": f'"{kw}" — {intent} intent',
                         "why": "What the searcher wants (informational / commercial / transactional) — decides the page type to build.",
                         "fix": "match the page type to the intent (guide vs comparison vs booking)",
                         "severity": "info", "detail": str(intent)})
    return rows


def search_intent(keywords: list, call=call) -> tuple:
    if not keywords:
        return [], "skipped: no keywords", 0.0
    return _tool("/v3/dataforseo_labs/google/search_intent/live",
                 [{"keywords": keywords, "location_code": location_code(), "language_code": language_code()}],
                 parse_search_intent, call=call)
