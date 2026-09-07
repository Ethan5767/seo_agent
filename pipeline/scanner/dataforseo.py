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


def _tool(path: str, payload: list, parse, call=call, status: str = "ok") -> tuple:
    """The one caller shape shared by every DataForSEO tool: POST, and on success
    return (parse(doc), status, cost_of(doc)); on error ([], error, 0.0). Kills
    the per-tool call/err/cost boilerplate. `parse(doc) -> rows`."""
    doc, err = call(path, payload)
    if err:
        return [], err, 0.0
    return parse(doc), status, cost_of(doc)


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
    return _tool("/v3/dataforseo_labs/google/domain_rank_overview/live",
                 [{"target": domain, "location_code": LOCATION_CODE, "language_code": LANGUAGE_CODE}],
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
                 [{"keyword": keyword, "location_code": LOCATION_CODE,
                   "language_code": LANGUAGE_CODE, "depth": 20}],
                 lambda d: parse_serp_rank(d, domain, keyword), call=call)


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


def parse_search_volume(doc: dict, top: int = 15) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw, vol = _kw_vol(it)
        if kw:
            rows.append(_kw_row("dfs.keyword_volume", kw, vol, "info",
                                "Real monthly search demand for this term.",
                                "prioritise terms with demand you can realistically rank for"))
    return rows


def parse_keyword_ideas(doc: dict, top: int = 15) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw, vol = _kw_vol(it)
        if kw:
            rows.append(_kw_row("dfs.keyword_idea", kw, vol, "info",
                                "A related keyword you could target with new/expanded content.",
                                "consider a page or section for this term"))
    return rows


def parse_keyword_gap(doc: dict, competitor: str, top: int = 15) -> list[dict]:
    rows = []
    for it in result_items(doc)[:top]:
        kw, vol = _kw_vol(it)
        if kw:
            rows.append(_kw_row("dfs.keyword_gap", kw, vol, "warn",
                                f"{competitor} ranks for this term and you do not — a gap you're losing.",
                                "create content targeting this term to close the gap"))
    return rows


def parse_competitors(doc: dict, top: int = 10) -> list[dict]:
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
                 [{"keywords": keywords, "location_code": LOCATION_CODE, "language_code": LANGUAGE_CODE}],
                 parse_search_volume, call=call)


def keyword_ideas(seeds: list, call=call) -> tuple:
    if not seeds:
        return [], "skipped: no seed keywords", 0.0
    return _tool("/v3/dataforseo_labs/google/keyword_ideas/live",
                 [{"keywords": seeds, "location_code": LOCATION_CODE,
                   "language_code": LANGUAGE_CODE, "limit": 50}],
                 parse_keyword_ideas, call=call)


def keyword_gap(you: str, competitor: str, call=call) -> tuple:
    if not competitor:
        return [], "skipped: no competitor", 0.0
    return _tool("/v3/dataforseo_labs/google/domain_intersection/live",
                 [{"target1": competitor, "target2": you, "intersections": False,
                   "location_code": LOCATION_CODE, "language_code": LANGUAGE_CODE, "limit": 100}],
                 lambda d: parse_keyword_gap(d, competitor), call=call)


def competitors(domain: str, call=call) -> tuple:
    return _tool("/v3/dataforseo_labs/google/competitors_domain/live",
                 [{"target": domain, "location_code": LOCATION_CODE,
                   "language_code": LANGUAGE_CODE, "limit": 10}],
                 parse_competitors, call=call)


def keywords_card(domain: str, keywords=None, competitor_list=None, call=call) -> tuple:
    """(rows, status, cost) — the Keywords card: competitors + keyword-gap vs the
    top competitor + search volume for the client's terms + fresh ideas. The
    competitor for the gap comes from the onboard list, else auto-discovered."""
    keywords = keywords or []
    rows: list[dict] = []
    cost = 0.0
    comp_rows, _s, c = competitors(domain, call=call); rows += comp_rows; cost += c
    competitor = (competitor_list or [None])[0]
    if not competitor and comp_rows:
        competitor = comp_rows[0]["what"]
    if competitor:
        r, _s, c = keyword_gap(domain, competitor, call=call); rows += r; cost += c
    if keywords:
        r, _s, c = search_volume(keywords, call=call); rows += r; cost += c
        r, _s, c = keyword_ideas(keywords, call=call); rows += r; cost += c
    cost = round(cost, 4)
    return rows, f"keywords: {len(rows)} row(s) · ${cost:.4f}", cost


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
                 [{"target": target, "location_code": LOCATION_CODE,
                   "language_code": LANGUAGE_CODE, "limit": 100}],
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
             "detail": f"authority rank {rank}" if rank is not None else ""}]
    broken = r0.get("broken_backlinks") or 0
    if broken:
        rows.append({"code": "dfs.broken_backlinks", "what": f"{broken} broken backlink(s)",
                     "why": "Links pointing at dead pages on your site waste the authority they'd pass.",
                     "fix": "restore or 301-redirect those target URLs so the link equity isn't lost",
                     "severity": "warn", "detail": f"{broken} broken"})
    return rows


def backlinks(domain: str, call=call) -> tuple:
    """(rows, status, cost) — backlink profile summary. Input = domain only."""
    return _tool("/v3/backlinks/summary/live",
                 [{"target": domain, "internal_list_limit": 10, "backlinks_status_type": "live"}],
                 parse_backlinks, call=call)
