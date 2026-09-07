"""DataForSEO tools for the scanner — the paid "deep scan" layer.

Ported from the dfs-test proving ground (INPUTS-17-TOOLS.md). Each tool is a
pure parser + a thin caller; `call` is injectable so parsers are unit-tested
offline with canned responses (the live API costs money and can't run in CI).

This module starts with the URL-only tools (input = the domain, nothing else).
Everything degrades honestly: no creds -> a "skipped" status, never faked data.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

BASE = "https://api.dataforseo.com"
LOCATION_CODE = 2116          # Cambodia (dfs-test default for this client)
LANGUAGE_CODE = "en"


def _auth() -> str | None:
    login = os.environ.get("DATAFORSEO_LOGIN")
    pw = os.environ.get("DATAFORSEO_PASSWORD")
    if not (login and pw):
        return None
    return "Basic " + base64.b64encode(f"{login}:{pw}".encode()).decode()


def call(path: str, payload: list, timeout: int = 60) -> tuple:
    """(json, error). POST to DataForSEO with Basic auth. Never raises — a
    provider that is down or unauthorized is a skip, not a crash."""
    auth = _auth()
    if not auth:
        return None, "skipped: DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD unset"
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": auth},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), None
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code} from DataForSEO"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


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


def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": "dfs.ranked_keyword", "what": what, "why": why,
            "fix": fix, "detail": detail, "severity": severity}


def parse_ranked_keywords(doc: dict, top: int = 15) -> list[dict]:
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


# DataForSEO on-page site-audit finding codes -> (why, fix, severity). This is
# DataForSEO's OWN crawler (it renders the site), so unlike our free crawler it
# sees JS-rendered menus — the fix for the false-orphan problem.
DFS_RECS = {
    "dfs.broken_page":       ("A crawled page returns an error status, not 200.", "Fix or redirect the broken URL.", "error"),
    "dfs.broken_links":      ("The page links to a URL that is broken.", "Fix or remove the broken link.", "error"),
    "dfs.click_depth":       ("The page is too many clicks from the homepage, so it gets little authority.", "Link it closer to the homepage.", "warn"),
    "dfs.duplicate_title":   ("Another page shares this exact <title>.", "Make each title unique.", "warn"),
    "dfs.duplicate_description": ("Another page shares this meta description.", "Make each description unique.", "warn"),
    "dfs.duplicate_content": ("This page's body largely duplicates another page.", "Consolidate or differentiate the pages.", "warn"),
    "dfs.redirect":          ("This URL redirects — a chain wastes crawl budget and link equity.", "Point links straight at the final URL.", "warn"),
    "dfs.canonical_chain":   ("The canonical tag points through a chain rather than at the final URL.", "Canonicalize directly to the final URL.", "warn"),
    "dfs.orphan_page":       ("DataForSEO's crawler found no internal link to this page (it renders JS, so this is reliable).", "Add an internal link from a relevant page.", "warn"),
    "dfs.large_page_size":   ("The page's HTML payload is large, slowing load.", "Trim the markup / inline bloat.", "warn"),
    "dfs.image_alt_missing": ("An image on this page has no alt text.", "Add descriptive alt text.", "warn"),
}


def site_audit(domain: str, max_pages: int = 25, run=None) -> tuple:
    """(rows, status, cost) — DataForSEO's on-page site audit mapped to report
    rows. Uses the proven providers.dataforseo_findings crawl (task_post -> poll
    -> pages). `run` is injectable for tests. Cost is a per-page estimate — the
    on-page crawl bills ~$0.0003/page (exact figure isn't surfaced by the crawl
    summary; ranked_keywords reports its exact cost)."""
    if run is None:
        from pipeline.audit.providers import dataforseo_findings as run
    findings, status = run(domain, max_pages)
    rows = []
    for f in findings:
        j = f.to_json() if hasattr(f, "to_json") else f
        code = j.get("code")
        why, fix, sev = DFS_RECS.get(code, ("A site-audit issue.", "Review and fix.", "warn"))
        rows.append({"code": code, "what": code.replace("dfs.", "").replace("_", " "),
                     "why": why, "fix": fix, "severity": sev,
                     "detail": (j.get("location") or "") + (f" — {j.get('detail')}" if j.get("detail") else "")})
    cost = round(0.0003 * max_pages, 4)
    return rows, f"{status} · ~${cost:.4f} est ({max_pages}pg crawl)", cost


def ranked_keywords(domain: str, call=call, top: int = 15) -> tuple:
    """(rows, status, cost_usd) — keywords `domain` ranks for. Input = domain."""
    doc, err = call("/v3/dataforseo_labs/google/ranked_keywords/live",
                    [{"target": domain, "location_code": LOCATION_CODE,
                      "language_code": LANGUAGE_CODE, "limit": 100}])
    if err:
        return [], err, 0.0
    rows = parse_ranked_keywords(doc, top=top)
    cost = cost_of(doc)
    return rows, f"ok: {len(rows)} ranked keyword(s) · ${cost:.4f}", cost


# ── Rankings (tools 8-11): domain overview + SERP position ───────────────────

def parse_domain_overview(doc: dict) -> list[dict]:
    """One visibility row from domain_rank_overview: how many keywords the
    domain ranks for, its estimated traffic value, and #1 positions."""
    items = result_items(doc)
    if not items:
        return []
    org = (items[0].get("metrics") or {}).get("organic") or {}
    count = org.get("count")
    if count is None:
        return []
    etv = round(float(org.get("etv") or 0))
    pos1 = org.get("pos_1") or 0
    return [{"code": "dfs.domain_overview", "what": f"Ranks for {count} keywords on Google",
             "why": "The domain's total organic footprint — how many searches it shows up for.",
             "fix": f"est. traffic value ${etv}/mo · {pos1} keyword(s) at position #1",
             "severity": "ok" if count else "info", "detail": f"{count} keywords"}]


def domain_overview(domain: str, call=call) -> tuple:
    """(rows, status, cost) — the domain's organic visibility overview."""
    doc, err = call("/v3/dataforseo_labs/google/domain_rank_overview/live",
                    [{"target": domain, "location_code": LOCATION_CODE,
                      "language_code": LANGUAGE_CODE}])
    if err:
        return [], err, 0.0
    return parse_domain_overview(doc), "ok", cost_of(doc)


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
    doc, err = call("/v3/serp/google/organic/live/advanced",
                    [{"keyword": keyword, "location_code": LOCATION_CODE,
                      "language_code": LANGUAGE_CODE, "depth": 20}])
    if err:
        return [], err, 0.0
    return parse_serp_rank(doc, domain, keyword), "ok", cost_of(doc)


def rankings(domain: str, keywords=None, call=call, max_serp: int = 5) -> tuple:
    """(rows, status, cost) — the Rankings card: ranked keywords + domain
    overview + a SERP position check for up to `max_serp` of the client's
    target keywords. Cost is the exact sum of every call's reported cost."""
    keywords = keywords or []
    rows: list[dict] = []
    cost = 0.0
    r, _s, c = ranked_keywords(domain, call=call); rows += r; cost += c
    r, _s, c = domain_overview(domain, call=call); rows += r; cost += c
    for kw in keywords[:max_serp]:
        r, _s, c = serp_rank(kw, domain, call=call); rows += r; cost += c
    cost = round(cost, 4)
    return rows, f"rankings: {len(rows)} row(s) · ${cost:.4f}", cost
