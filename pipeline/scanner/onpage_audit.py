"""DataForSEO on-page full audit — the ~40-check, site-wide layer.

DataForSEO's on-page crawl returns a `checks` object of ~40 boolean flags per
page. This crawls the site (task_post -> poll summary -> pull /pages), then maps
every flag to a report row, aggregated across pages. Separate module so
dataforseo.py stays focused and under the split line.

`parse_onpage_checks(pages)` is pure (page dicts in, rows out) and unit-tested;
`crawl_onpage` does the async crawl (injectable `call`/`sleep` for tests).
"""
from __future__ import annotations

import time

from pipeline.scanner import progress
from pipeline.scanner.dataforseo import call as _call, cost_of

# DataForSEO on-page `checks` flag -> (label, why, fix, severity, bad_when).
# bad_when=True  → the flag being True is the problem (most).
# bad_when=False → the flag being False is the problem (good-signal flags).
CHECKS = {
    "is_4xx_code":            ("4xx pages", "Pages returning a 4xx (not found) error.", "fix or redirect them", "error", True),
    "is_5xx_code":            ("5xx pages", "Pages returning a 5xx server error.", "fix the server error", "error", True),
    "is_broken":              ("Broken pages", "Pages that don't load (broken).", "restore or remove", "error", True),
    "is_redirect":            ("Redirecting pages", "Pages that redirect — chains waste crawl budget.", "link to the final URL", "warn", True),
    "canonical_to_broken":    ("Canonical → broken", "Canonical points at a broken URL.", "canonicalize to a live URL", "error", True),
    "canonical_to_redirect":  ("Canonical → redirect", "Canonical points at a redirect, not the final URL.", "canonicalize directly", "warn", True),
    "recursive_canonical":    ("Recursive canonical", "Canonical loops back on itself.", "fix the canonical chain", "error", True),
    "redirect_loop":          ("Redirect loop", "A redirect loop traps crawlers.", "break the loop", "error", True),
    "no_title":               ("Missing title", "Page has no <title>.", "add a unique title", "error", True),
    "title_too_long":         ("Title too long", "Title exceeds the recommended length.", "trim to ~60 chars", "warn", True),
    "title_too_short":        ("Title too short", "Title is very short.", "make it 30-60 chars", "warn", True),
    # Labels below follow docs.dataforseo.com/v3/on_page-pages. `duplicate_title_tag`
    # is "page with more than one title tag" and was labelled "Duplicate titles"
    # (pages sharing a title), so the site-wide check was never read at all.
    "duplicate_title_tag":    ("Multiple title tags on a page", "The page has more than one <title> tag.", "keep a single <title>", "warn", True),
    "duplicate_title":        ("Duplicate page titles", "Other pages on the site use the same <title>.", "give each page a unique title", "warn", True),
    "duplicate_description":  ("Duplicate meta descriptions", "Other pages on the site use the same meta description.", "write a unique description per page", "warn", True),
    "no_description":         ("Missing meta description", "Page has no meta description.", "add one (120-160 chars)", "warn", True),
    "duplicate_meta_tags":    ("Repeated meta tags on a page", "The page has more than one meta tag of the same type.", "keep one of each", "warn", True),
    "irrelevant_description":  ("Irrelevant description", "Meta description doesn't match the page.", "rewrite to match content", "warn", True),
    "irrelevant_title":       ("Irrelevant title", "Title doesn't match the page content.", "align title with content", "warn", True),
    "no_h1_tag":              ("Missing H1", "Page has no <h1>.", "add one clear H1", "warn", True),
    "no_image_alt":           ("Images missing alt", "Images without alt text.", "add descriptive alt", "warn", True),
    "no_image_title":         ("Images missing title", "Images without a title attribute.", "optional: add image titles", "info", True),
    "no_favicon":             ("Missing favicon", "No favicon.", "add one", "info", True),
    "no_doctype":             ("Missing doctype", "No <!DOCTYPE html>.", "add it", "warn", True),
    "no_encoding_meta_tag":   ("Missing charset", "No charset meta tag.", "add <meta charset>", "warn", True),
    "high_loading_time":      ("Slow loading", "Page loads slowly.", "optimise assets/server", "warn", True),
    "high_waiting_time":      ("Slow server (TTFB)", "High time-to-first-byte.", "speed up the server", "warn", True),
    "size_greater_than_3mb":  ("Page over 3MB", "Page weighs more than 3MB.", "compress/trim assets", "warn", True),
    "has_render_blocking_resources": ("Render-blocking resources", "CSS/JS block first paint.", "defer/async them", "warn", True),
    "low_content_rate":       ("Low text ratio", "Little text relative to code.", "add substantive copy", "warn", True),
    "low_readability_rate":   ("Hard to read", "Low readability score.", "simplify the writing", "info", True),
    "lorem_ipsum":            ("Placeholder text", "'lorem ipsum' placeholder on the page.", "replace with real content", "error", True),
    "deprecated_html_tags":   ("Deprecated HTML", "Obsolete tags (font/center/…).", "use modern HTML/CSS", "warn", True),
    "flash":                  ("Flash content", "Flash — obsolete/unsupported.", "replace with HTML5", "warn", True),
    "frame":                  ("Frames", "Old-style frames.", "use modern layout", "warn", True),
    "broken_resources":       ("Broken resources", "The page references broken assets.", "fix/remove them", "error", True),
    "broken_links":           ("Broken links", "Links to dead URLs.", "fix or remove", "error", True),
    "links_relation_conflict": ("Link rel conflict", "Conflicting link relations.", "resolve the conflict", "warn", True),
    "is_orphan_page":         ("Orphan page", "No internal link points here.", "link it from a relevant page", "warn", True),
    "duplicate_content":      ("Duplicate content", "Body largely duplicates another page.", "consolidate/differentiate", "warn", True),
    "https_to_http_links":    ("HTTPS→HTTP links", "Secure page links to insecure URLs.", "link to https", "warn", True),
    "no_content_encoding":    ("No compression", "Response isn't gzip/br compressed.", "enable compression", "warn", True),
    "seo_friendly_url":       ("SEO-friendly URLs", "URLs are clean and readable.", "keep slugs clean", "ok", False),
    "is_https":               ("HTTPS", "Pages served over HTTPS.", "keep HTTPS", "ok", False),
    # ── more DataForSEO on-page flags ────────────────────────────────────────
    "is_http":                ("Served over HTTP", "Pages served over insecure http://.", "serve over https", "error", True),
    "has_micromarkup_errors": ("Structured-data errors", "Schema markup has errors — it may earn nothing.", "validate the JSON-LD", "warn", True),
    "title_too_many_words":   ("Title too many words", "Title has too many words — Google truncates it.", "tighten the title", "warn", True),
    "small_page_size":        ("Very small page", "Page is unusually small — often thin content.", "add substantive content", "info", True),
    "irrelevant_meta_keywords": ("Irrelevant meta keywords", "meta keywords don't match the page (and Google ignores them).", "drop the meta keywords tag", "info", True),
    "canonical_chain":        ("Canonical chain", "Canonical points through a chain, not the final URL.", "canonicalize directly", "warn", True),
    "no_h2":                  ("Missing H2s", "No H2 subheadings — weak structure.", "add descriptive H2s", "warn", True),
    "meta_refresh_redirect":  ("Meta refresh redirect", "Uses a meta-refresh redirect — bad for SEO.", "use a 301", "warn", True),
    "high_content_rate":      ("Very dense text", "Extremely high text density — may hurt readability.", "add whitespace/structure", "info", True),
    "canonical":              ("Canonical present", "Pages declare a canonical URL.", "keep canonicals", "ok", False),
    "has_html_doctype":       ("HTML5 doctype", "Pages declare a valid doctype.", "keep it", "ok", False),
    "meta_charset_consistency": ("Charset consistent", "Declared charset matches the response.", "keep consistent", "ok", False),
    "has_micromarkup":        ("Structured data present", "Pages carry schema.org markup.", "keep/expand schema", "ok", False),
}


def parse_onpage_checks(pages: list) -> list[dict]:
    """Aggregate the per-page `checks` across the crawl → one row per check,
    with the count of pages affected."""
    counts: dict[str, int] = {}
    seen: set[str] = set()           # flags DataForSEO actually reported
    ok_flags: dict[str, int] = {}
    affected: dict[str, list] = {}   # flag -> the actual URLs that failed it
    total = 0
    for p in pages:
        checks = (p or {}).get("checks") or {}
        if not checks:
            continue
        total += 1
        url = (p or {}).get("url") or (p or {}).get("resource") or ""
        for flag, val in checks.items():
            if flag not in CHECKS:
                continue
            seen.add(flag)
            _l, _w, _f, _sev, bad_when = CHECKS[flag]
            if bool(val) == bad_when and bad_when:
                counts[flag] = counts.get(flag, 0) + 1
                if url:
                    affected.setdefault(flag, []).append(url)
            elif not bad_when:
                ok_flags[flag] = ok_flags.get(flag, 0) + (1 if val else 0)
    rows = []
    for flag, (label, why, fix, sev, bad_when) in CHECKS.items():
        if bad_when:
            n = counts.get(flag, 0)
            if n:
                rows.append({"code": f"dfs.op.{flag}", "what": label, "why": why,
                             "fix": fix, "severity": sev, "detail": f"{n} page(s)",
                             "pages": affected.get(flag, [])[:25]})
            elif flag in seen and total:
                # Checked and clean is a result. Emitting nothing left Crawl
                # Issues blank after a 25-page crawl with 0 broken, 0 4xx, 0
                # orphan pages. Only for flags DataForSEO reported: a check it
                # never ran is not a pass.
                rows.append({"code": f"dfs.op.{flag}", "what": label, "why": why,
                             "fix": "passing", "severity": "ok", "detail": f"0 of {total} page(s)"})
        else:
            # good-signal flag: pass row when all crawled pages have it
            if total and ok_flags.get(flag, 0) == total:
                rows.append({"code": f"dfs.op.{flag}", "what": label, "why": why,
                             "fix": "passing", "severity": "ok", "detail": f"{total} page(s)"})
    return rows


def _poll(call, path):
    """A summary poll: quiet when `call` is the real client (the crawl reports
    page counts instead of a request line every 5 s); test doubles take no
    `quiet` keyword."""
    import inspect
    try:
        takes_quiet = "quiet" in inspect.signature(call).parameters
    except (TypeError, ValueError):
        takes_quiet = False
    return call(path, quiet=True) if takes_quiet else call(path)


def crawl_onpage(domain: str, max_pages: int = 20, call=_call,
                 sleep=time.sleep, poll_seconds: int = 5, max_polls: int = 48) -> tuple:
    """(pages, cost, err). task_post -> poll summary until finished -> /pages."""
    posted, err = call("/v3/on_page/task_post",
                       [{"target": domain, "max_crawl_pages": max_pages,
                         "load_resources": False, "enable_javascript": False}])
    if err:
        return [], 0.0, err
    cost = cost_of(posted)
    try:
        task_id = posted["tasks"][0]["id"]
    except (KeyError, IndexError, TypeError):
        return [], cost, "no task id from task_post"
    progress.emit(f"Crawl task posted to DataForSEO ({max_pages} pages max)", step="crawl",
                  phase="posted", cost=cost, max_crawl_pages=max_pages)
    # Summary polls are free ("charged only for posting a task", on_page/summary
    # docs), so poll every 5 s rather than 12: same 240 s ceiling, and the panel
    # moves instead of looking frozen.
    for _ in range(max_polls):
        sleep(poll_seconds)
        summary, err = _poll(call, f"/v3/on_page/summary/{task_id}")
        if err:
            return [], cost, err
        try:
            result = summary["tasks"][0]["result"][0]
        except (KeyError, IndexError, TypeError):
            continue
        status = result.get("crawl_status") or {}
        if isinstance(status.get("pages_crawled"), int):
            progress.emit(
                f"Crawling: {status['pages_crawled']} of {status.get('max_crawl_pages', max_pages)} pages",
                step="crawl", phase="progress",
                pages_crawled=status["pages_crawled"],
                pages_in_queue=status.get("pages_in_queue", 0),
                max_crawl_pages=status.get("max_crawl_pages", max_pages))
        if result.get("crawl_progress") == "finished":
            break
    else:
        return [], cost, f"crawl of {domain} did not finish in time"
    progress.emit("Crawl finished; fetching page results", step="crawl", phase="fetching")
    pages_doc, err = call("/v3/on_page/pages", [{"id": task_id, "limit": max_pages}])
    if err:
        return [], cost, err
    cost += cost_of(pages_doc)
    try:
        items = pages_doc["tasks"][0]["result"][0].get("items") or []
    except (KeyError, IndexError, TypeError):
        items = []
    return items, round(cost, 4), None


def site_audit_full(domain: str, max_pages: int = 20, crawl=crawl_onpage) -> tuple:
    """(rows, status, cost) — the full on-page audit as a Site Health card."""
    pages, cost, err = crawl(domain, max_pages)
    if err:
        return [], err, cost
    rows = parse_onpage_checks(pages)
    ok = sum(1 for p in pages if (p or {}).get("checks"))
    flagged = sum(1 for r in rows if r["severity"] != "ok")
    passed = len(rows) - flagged
    return rows, f"crawled {ok} page(s), {flagged} check(s) flagged, {passed} passed · ${cost:.4f}", cost
