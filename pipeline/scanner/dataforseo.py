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
