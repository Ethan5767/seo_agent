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
from urllib.parse import urldefrag, urljoin, urlsplit

_TITLE = re.compile(r"<title[^>]*>([^<]*)</title>", re.IGNORECASE)
_DESC = re.compile(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']*)', re.IGNORECASE)
_HREF = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\']', re.IGNORECASE)
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


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
    m = _TITLE.search(html or "")
    return m.group(1).strip() if m else ""


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


def crawl_site(entry_url: str, fetch, sitemap_text: str | None = None,
               max_pages: int = 25, on_page=None) -> dict:
    """Walk the site from entry_url. `fetch(url)->(html,status)`.

    `on_page(n, total, url)` is called before each page fetch, for live progress.

    Returns {pages, reachable, sitemap_urls, capped}: `pages` is a list of
    {url,status,title,desc,links}; `reachable` is the set of URLs found by
    following links from the entry (used for orphan detection); `sitemap_urls`
    is every <loc> in the sitemap; `capped` is True if the cap was hit.
    """
    def _tick(url):
        if on_page:
            on_page(len(fetched) + 1, max_pages, url)
    entry = _norm(entry_url)
    sitemap_urls = {_norm(u) for u in _LOC.findall(sitemap_text or "")
                    if _host(u) == _host(entry)}

    reachable: set[str] = {entry}          # discovered by following links
    queue: list[str] = [entry]
    fetched: dict[str, dict] = {}
    capped = False

    # BFS over links from the entry.
    while queue:
        if len(fetched) >= max_pages:
            capped = True
            break
        url = queue.pop(0)
        if url in fetched:
            continue
        _tick(url)
        html, status = fetch(url)
        links = links_in(url, html) if status == 200 else set()
        fetched[url] = {"url": url, "status": status, "title": title_of(html),
                        "desc": desc_of(html), "links": sorted(links)}
        for l in links:
            reachable.add(l)
            if l not in fetched and l not in queue:
                queue.append(l)

    # Also fetch sitemap URLs we never reached by link (needed to SEE orphans and
    # to compare titles), within the remaining budget.
    for url in sorted(sitemap_urls):
        if len(fetched) >= max_pages:
            capped = True
            break
        if url in fetched:
            continue
        _tick(url)
        html, status = fetch(url)
        fetched[url] = {"url": url, "status": status, "title": title_of(html),
                        "desc": desc_of(html), "links": sorted(links_in(url, html) if status == 200 else set())}

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
        rows.append(_row("Broken internal link", "error",
                         f"A link points to {target}, which returns {by_url[target]['status']}.",
                         f"Fix or remove the link (found on {len(sources)} page(s)).",
                         detail=f"{by_url[target]['status']} — from {sources[0]}"))

    # Orphan pages: in the sitemap but never reached by following links.
    # ONLY trustworthy on a COMPLETE crawl. If the crawl was capped, "unreached"
    # just means "we didn't get that far" — not orphaned — so reporting it would
    # be a false positive (the common case on a big site). Same if links are
    # JavaScript-rendered: our HTML crawler can't see them. So gate on capped,
    # and word the real finding to admit the JS caveat.
    orphans = sorted(u for u in crawl["sitemap_urls"] if u not in crawl["reachable"])
    if crawl["capped"]:
        rows.append(_row("Orphan check", "info",
                         f"Only crawled {len(ok)} pages of a larger site, so we can't tell which sitemap "
                         f"pages are truly unlinked ({len(orphans)} were unreached, but that's likely just "
                         f"the crawl limit). Raise the page cap for a full orphan audit.",
                         "raise the crawl page cap", detail=f"{len(orphans)} unreached"))
    else:
        for u in orphans:
            rows.append(_row("Orphan page", "warn",
                             f"{u} is in the sitemap but our crawl found no internal link to it. "
                             f"(If it's linked only from a JavaScript menu, our crawler can't see that — verify manually.)",
                             "Add an internal link to this page from a relevant page.",
                             detail=u))

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
            out.append(_row(what, "warn", why, fix,
                            detail=f'"{val[:50]}" on {len(urls)} pages'))
    return out
