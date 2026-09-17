"""Whole-site crawl — the site-wide half of the audit, from just a URL.

Single-page checks (audit.py) can't see problems that only exist ACROSS pages:
duplicate titles/descriptions, orphan pages, broken internal links. This walks
the site (breadth-first from the entry URL, seeded by sitemap.xml when present),
bounded by a page cap, and reports those site-wide issues.

Pure + injectable: `crawl_site` takes a `fetch(url) -> (html, status)` callable,
so the whole thing is unit-tested offline with a fake site. The server passes a
real fetcher built on measure.curl.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urldefrag, urljoin, urlsplit

from pipeline.lib.common import visible_text_ratio
from pipeline.lib.html import page_title, sitemap_locs

_DESC = re.compile(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)', re.IGNORECASE)
_HREF = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\']', re.IGNORECASE)


def _norm(url: str) -> str:
    """Canonical form for comparison: drop the fragment, ensure a trailing slash
    on a path-less/dir-like URL so `/a` and `/a/` are one page."""
    url, _ = urldefrag(url)
    parts = urlsplit(url)
    path = parts.path or "/"
    if "." not in path.rsplit("/", 1)[-1] and not path.endswith("/"):
        path += "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower().removeprefix("www.")


def title_of(html: str) -> str:
    return page_title(html) or ""


def desc_of(html: str) -> str:
    m = _DESC.search(html or "")
    return m.group(1).strip() if m else ""


def links_in(base_url: str, html: str) -> set[str]:
    """Same-site page links (absolute, normalized). Skips mailto/tel/js and
    non-HTML assets."""
    out: set[str] = set()
    host = _host(base_url)
    for href in _HREF.findall(html or ""):
        href = href.strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        absolute = _norm(urljoin(base_url, href))
        if not absolute.startswith(("http://", "https://")):
            continue
        if _host(absolute) != host:
            continue
        if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js|pdf|zip|ico|xml|json)$",
                     urlsplit(absolute).path, re.IGNORECASE):
            continue
        out.add(absolute)
    return out


def raw_links_in(base_url: str, html: str) -> set[str]:
    """Same-site navigational URLs, retaining query strings for trap analysis."""
    out: set[str] = set()
    host = _host(base_url)
    for href in _HREF.findall(html or ""):
        href = href.strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
            continue
        absolute = urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")) or _host(absolute) != host:
            continue
        if re.search(r"\.(png|jpe?g|gif|svg|webp|css|js|pdf|zip|ico|xml|json)$",
                     urlsplit(absolute).path, re.IGNORECASE):
            continue
        out.add(absolute)
    return out


def crawl_site(entry_url: str, fetch, sitemap_text: str | None = None,
               max_pages: int = 25, on_page=None, seed=None) -> dict:
    """Walk the site from entry_url. `fetch(url)->(html,status)`.

    `on_page(n, total, url)` is called before each page fetch, for live progress.

    `seed` is `(html, status)` for entry_url when the caller has already read it,
    so the entry is not fetched a second time.

    Returns {pages, reachable, sitemap_urls, capped}: `pages` is a list of
    {url,status,title,desc,links,html}; `reachable` is the set of URLs found by
    following links from the entry (used for orphan detection); `sitemap_urls`
    is every <loc> in the sitemap; `capped` is True if the cap was hit.
    """
    def _tick(url):
        if on_page:
            on_page(len(fetched) + 1, max_pages, url)
    entry = _norm(entry_url)
    # Same rule for the sitemap: compare on the canonical form, fetch the URL the
    # sitemap actually published. A <loc> of /a must be requested as /a.
    _sitemap_real: dict[str, str] = {}
    for u in sitemap_locs(sitemap_text):
        if _host(u) == _host(entry):
            _sitemap_real.setdefault(_norm(u), u.strip())
    sitemap_urls = set(_sitemap_real)

    reachable: set[str] = {entry}          # discovered by following links
    queue: list[tuple[str, int]] = [(entry, 0)]
    fetched: dict[str, dict] = {}
    depths: dict[str, int] = {entry: 0}
    capped = False

    # `_norm` is a CANONICAL form for comparison - it appends a trailing slash so
    # `/a` and `/a/` count as one page. It is not a fetchable URL: asking a
    # server for `/a/` when it publishes `/a` gets a redirect at best and a 404
    # at worst, and the crawl would then report a broken page that works fine.
    # So the normalised string is the dedup KEY and the URL as written is what
    # gets fetched and reported. Nothing caught this because, until the scan
    # wired this crawler in, nothing called it outside its own tests, whose
    # fixtures happened to use trailing slashes throughout.
    real: dict[str, str] = dict(_sitemap_real)
    real[entry] = entry_url.split("#")[0] or entry

    # BFS over links from the entry.
    while queue:
        if len(fetched) >= max_pages:
            capped = True
            break
        url, depth = queue.pop(0)
        if url in fetched:
            continue
        target = real.get(url, url)
        # The tick is progress, not a fetch: the entry still counts as page 1 of
        # the walk even when the caller already read it.
        _tick(target)
        if url == entry and seed is not None:
            html, status = seed[0] or "", seed[1]
        else:
            html, status = fetch(target)
        links = links_in(target, html) if status == 200 else set()
        raw_links = raw_links_in(target, html) if status == 200 else set()
        fetched[url] = {"url": target, "status": status, "title": title_of(html),
                        "desc": desc_of(html), "links": sorted(_norm(l) for l in links),
                        "raw_links": sorted(raw_links),
                        # The body, kept so the caller's per-page tools can read
                        # the page this crawl already fetched. Dropping it made
                        # every multi-page scan fetch the whole site twice.
                        "html": html or "",
                        "depth": depth}
        for l in links:
            key = _norm(l)
            reachable.add(key)
            real.setdefault(key, l)
            if key not in depths:
                depths[key] = depth + 1
                if key not in fetched:
                    queue.append((key, depth + 1))

    # Also fetch sitemap URLs we never reached by link (needed to SEE orphans and
    # to compare titles), within the remaining budget.
    for url in sorted(sitemap_urls):
        if len(fetched) >= max_pages:
            capped = True
            break
        if url in fetched:
            continue
        target = real.get(url, url)
        _tick(target)
        html, status = fetch(target)
        fetched[url] = {"url": target, "status": status, "title": title_of(html),
                        "desc": desc_of(html),
                        "links": sorted(_norm(l) for l in links_in(target, html)) if status == 200 else [],
                        "raw_links": sorted(raw_links_in(target, html)) if status == 200 else [],
                        "html": html or "",
                        "depth": -1}

    return {"pages": list(fetched.values()), "reachable": reachable,
            "sitemap_urls": sitemap_urls, "capped": capped}


def _row(what: str, severity: str, why: str, fix: str, detail: str = "") -> dict:
    return {"code": f"site.{what.lower().replace(' ', '_')}", "what": what,
            "why": why, "fix": fix, "detail": detail, "severity": severity}


def site_rows(crawl: dict) -> list[dict]:
    """Site-wide findings from a crawl result — duplicate titles/descriptions,
    orphan pages, broken internal links, plus a pages-crawled summary."""
    pages = crawl["pages"]
    ok = [p for p in pages if p["status"] == 200]
    by_url = {p["url"]: p for p in pages}
    rows: list[dict] = []

    # Summary (always shown, so the operator sees the scope).
    rows.append(_row("Pages crawled", "ok" if len(ok) > 1 else "info",
                     f"Walked {len(ok)} page(s) of the site"
                     + (" (page cap reached — a bigger site would need a higher cap)" if crawl["capped"] else "") + ".",
                     "passing", detail=f"{len(ok)} pages"))

    # Duplicate titles.
    rows += _dup_rows(ok, "title", "Duplicate page titles",
                      "Multiple pages share the same <title>, so they compete for the same search and dilute each other.",
                      "Give each page a unique, descriptive title.")
    # Duplicate descriptions.
    rows += _dup_rows(ok, "desc", "Duplicate meta descriptions",
                      "Multiple pages share the same meta description — a thin, templated signal to Google.",
                      "Write a unique meta description per page.")

    # Broken internal links: a link that points at a page we fetched with a
    # non-200 status.
    broken: dict[str, list[str]] = {}
    for p in pages:
        for l in p["links"]:
            tgt = by_url.get(l)
            if tgt and tgt["status"] not in (200, 0):
                broken.setdefault(l, []).append(p["url"])
    for target, sources in sorted(broken.items()):
        row = _row("Broken internal link", "error",
                   f"A link points to {target}, which returns {by_url[target]['status']}.",
                   f"Fix or remove the link (found on {len(sources)} page(s)).",
                   detail=f"{by_url[target]['status']} — from {sources[0]}")
        # The pages that carry the link, the same field merge_by_code sets, so
        # the per-page summary can attribute a site-wide finding to a page.
        row["pages"] = sources[:25]
        rows.append(row)

    # Orphan pages: in the sitemap but never reached by following links.
    # ONLY trustworthy on a COMPLETE crawl. If the crawl was capped, "unreached"
    # just means "we didn't get that far" — not orphaned — so reporting it would
    # be a false positive (the common case on a big site). Same if links are
    # JavaScript-rendered: our HTML crawler can't see them. So gate on capped,
    # and word the real finding to admit the JS caveat.
    sitemap_n = len(crawl["sitemap_urls"])
    orphans = sorted(u for u in crawl["sitemap_urls"] if u not in crawl["reachable"])
    orphan_share = (len(orphans) / sitemap_n) if sitemap_n else 0.0

    if crawl["capped"]:
        rows.append(_row("Orphan check", "info",
                         f"Only crawled {len(ok)} pages of a larger site, so we can't tell which sitemap "
                         f"pages are truly unlinked ({len(orphans)} unreached — likely just the crawl limit). "
                         f"Raise the page cap for a full orphan audit.",
                         "raise the crawl page cap", detail=f"{len(orphans)} unreached"))
    elif sitemap_n and orphan_share > 0.5:
        # Most of the sitemap "unreached" isn't a site with hundreds of orphans —
        # it's a navigation our HTML crawler couldn't follow (almost always a
        # JavaScript-rendered menu). Report that honestly instead of a false list.
        rows.append(_row("Orphan check", "info",
                         f"Our crawler could only follow links to {len(ok)} of {sitemap_n} sitemap pages. "
                         f"That usually means the site's menu is JavaScript-rendered — the links are there "
                         f"for people, but not in the raw HTML that search/AI crawlers read. Worth checking: "
                         f"a JS-only menu also makes these pages hard for AI crawlers to find.",
                         "make the main navigation real <a href> links in the HTML (not JS-only)",
                         detail=f"{len(orphans)} of {sitemap_n} unreached"))
    else:
        for u in orphans:
            rows.append(_row("Orphan page", "warn",
                             f"{u} is in the sitemap but our crawl found no internal link to it. "
                             f"(If it's linked only from a JavaScript menu, verify manually.)",
                             "Add an internal link to this page from a relevant page.",
                             detail=u))

    # Click depth: flag pages at depth > 3 as warning.
    for p in pages:
        d = p.get("depth", 0)
        if d > 3:
            row = _row("Click depth", "warn",
                       f"{p['url']} is {d} clicks away from the entry page (depth {d}). "
                       f"Pages deeper than 3 clicks are harder for search engines to crawl and users to find.",
                       "Add internal links from higher-level category or navigation pages to reduce click depth.",
                       detail=f"depth {d} — {p['url']}")
            row["pages"] = [p["url"]]
            rows.append(row)

    rows += crawl_behavior_rows(crawl)
    from pipeline.scanner.validate import hreflang_cluster_rows
    rows += hreflang_cluster_rows(pages)
    return rows


def crawl_trap_rows(crawl: dict) -> list[dict]:
    """Detect URL patterns that can expand a crawl without discovering new
    content. Pure analysis of the crawl graph; no extra requests."""
    pages = crawl.get("pages") or []
    urls = [str(p.get("url") or "") for p in pages]
    if len(urls) < 2:
        return [{"code": "crawl.traps_not_measured", "what": "Crawl traps",
                 "why": "A trap needs multiple crawled URLs to establish a pattern.",
                 "fix": "Run a multi-page crawl.", "detail": "needs at least 2 pages",
                 "severity": "info"}]
    findings: list[dict] = []
    query_keys: dict[str, set[str]] = {}
    for u in urls:
        q = dict(parse_qsl(urlsplit(u).query, keep_blank_values=True))
        for key in q:
            query_keys.setdefault(key.lower(), set()).add(u)
    trap_names = {
        "page": "pagination",
        "paged": "pagination",
        "p": "pagination",
        "page_num": "pagination",
        "session": "session IDs",
        "sid": "session IDs",
        "jsessionid": "session IDs",
        "sort": "faceted sorting",
        "filter": "faceted filtering",
        "facet": "faceted filtering",
        "calendar": "calendar navigation",
        "date": "calendar navigation",
    }
    for key, affected in sorted(query_keys.items()):
        if key in trap_names and len(affected) >= 2:
            findings.append({"code": f"crawl.trap_{trap_names[key].replace(' ', '_')}",
                             "what": f"Crawl trap: {trap_names[key]}", "severity": "warn",
                             "why": f"The crawl found {len(affected)} URLs varying the '{key}' parameter; this can create unbounded crawl paths.",
                             "fix": "Constrain or canonicalize the parameter and prevent crawl-only permutations.",
                             "detail": f"parameter {key}: {len(affected)} URLs", "pages": sorted(affected)[:100]})
    paths = [urlsplit(u).path.lower() for u in urls]
    if len(paths) >= 4 and len(set(paths)) < len(paths) * 0.75:
        findings.append({"code": "crawl.trap_path_permutation", "what": "Path permutation growth",
                         "severity": "warn",
                         "why": "Many crawled URLs collapse to a small set of repeated path shapes, indicating URL permutations.",
                         "fix": "Limit generated permutations and expose one canonical URL per content item.",
                         "detail": f"{len(urls)} URLs, {len(set(paths))} path shapes", "pages": urls[:100]})
    return findings or [{"code": "crawl.traps", "what": "Crawl traps", "severity": "ok",
                         "why": "No pagination, session, calendar, or faceted URL expansion pattern was detected in the crawled sample.",
                         "fix": "passing", "detail": f"{len(urls)} URLs sampled"}]


def crawl_depth_rows(crawl: dict) -> list[dict]:
    """Report click-depth distribution and pages not reached by links."""
    pages = crawl.get("pages") or []
    if not pages:
        return [{"code": "crawl.depth_not_measured", "what": "Crawl depth",
                 "severity": "info", "why": "No pages were crawled.",
                 "fix": "Run a multi-page crawl.", "detail": "no pages"}]
    depths = [int(p.get("depth", -1)) for p in pages if int(p.get("depth", -1)) >= 0]
    if not depths:
        return [{"code": "crawl.depth_not_measured", "what": "Crawl depth",
                 "severity": "info", "why": "The crawl did not record click depth.",
                 "fix": "Run the current crawler.", "detail": "depth unavailable"}]
    rows = [{"code": "crawl.depth_distribution", "what": "Click-depth distribution",
             "severity": "ok", "why": "Click depth shows how many links a crawler needs to reach each page.",
             "fix": "passing", "detail": ", ".join(f"depth {d}: {depths.count(d)}" for d in sorted(set(depths)))}]
    orphan = [p.get("url") for p in pages if p.get("depth") == -1 and p.get("url")]
    if orphan:
        rows.append({"code": "crawl.orphan_pages", "what": "Orphan pages",
                     "severity": "warn", "why": "These sitemap pages were not reached by following internal links from the entry page.",
                     "fix": "Add relevant internal links or remove stale sitemap URLs.",
                     "detail": f"{len(orphan)} page(s)", "pages": orphan[:100]})
    return rows


def crawl_behavior_rows(crawl: dict) -> list[dict]:
    """Detect URL patterns that can consume crawl budget without new content."""
    pages = crawl.get("pages", [])
    raw_urls = [u for p in pages for u in p.get("raw_links", [])]
    if not raw_urls:
        return []
    rows: list[dict] = []
    param_urls = [u for u in raw_urls if urlsplit(u).query]
    param_keys: dict[str, set[str]] = {}
    for url in param_urls:
        keys = tuple(sorted(k.lower() for k, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True)))
        if keys:
            param_keys.setdefault("&".join(keys), set()).add(url)
    trap_urls = [u for u in param_urls if re.search(r"(?:^|[&?])(?:sid|session|phpsessid|jsessionid|token)=|(?:^|[&?])(?:utm_|fbclid|gclid)", u, re.I)]
    if trap_urls:
        rows.append(_row("Crawl trap — session/tracking URLs", "warn",
                         f"The crawl found {len(trap_urls)} same-site URLs carrying session or tracking parameters. "
                         "These can create many duplicate URLs without new content.",
                         "Strip tracking/session parameters from internal links and disallow only the useless variants.",
                         detail=", ".join(sorted(trap_urls)[:5])))
    facets = [u for u in param_urls if len(parse_qsl(urlsplit(u).query, keep_blank_values=True)) >= 2]
    if len(facets) >= 3 or len(param_keys) >= 4:
        rows.append(_row("Crawl trap — faceted parameters", "warn",
                         f"The crawl found {len(param_keys)} parameter combinations ({len(facets)} multi-parameter URLs). "
                         "Facets can multiply crawlable URLs faster than content is created.",
                         "Choose a canonical facet strategy: allow useful combinations, canonicalize, or noindex the rest.",
                         detail=f"{len(param_keys)} combinations"))
    sequence_urls = [u for u in raw_urls if re.search(r"(?:/page(?:/|=)|[?&]page=|/calendar/|/(?:20\d\d)(?:/\d{1,2})?)", u, re.I)]
    if len(sequence_urls) >= 5:
        rows.append(_row("Crawl trap — pagination/calendar", "warn",
                         f"The crawl found {len(sequence_urls)} pagination or calendar-like URLs. "
                         "Unbounded sequences can consume crawl budget.",
                         "Bound pagination, link only useful pages, and keep calendar archives out of the crawl path unless they earn indexing.",
                         detail=", ".join(sorted(sequence_urls)[:5])))
    return rows


def _dup_rows(pages: list[dict], field: str, what: str, why: str, fix: str) -> list[dict]:
    groups: dict[str, list[str]] = {}
    for p in pages:
        val = (p.get(field) or "").strip()
        if val:
            groups.setdefault(val, []).append(p["url"])
    out = []
    for val, urls in sorted(groups.items()):
        if len(urls) > 1:
            row = _row(what, "warn", why, fix, detail=f'"{val[:50]}" on {len(urls)} pages')
            row["pages"] = urls[:25]
            out.append(row)
    return out
