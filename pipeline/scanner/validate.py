"""Sitemap + hreflang validation (ours — DataForSEO has no direct tool).

Goes beyond "does a sitemap exist" (Technical already flags presence): is it a
valid urlset/index, how many URLs, any insecure http URLs; and for multi-region
sites, are the hreflang alternates well-formed with an x-default. Pure. Emits
rows only when there's something to say (no noise for a single-region site with
no sitemap — Technical already covered presence).
"""
from __future__ import annotations

import re

from pipeline.scanner.rows import make_row

from pipeline.lib.html import sitemap_locs

_row = make_row("valid")


def sitemap_validation_rows(sitemap: str | None) -> list[dict]:
    if not sitemap or not sitemap.strip():
        return []  # presence already flagged by the Technical card
    low = sitemap.lower()
    if "<sitemapindex" in low:
        n = len(re.findall(r"<sitemap>", low))
        return [_row("Sitemap index", "ok", f"A sitemap index with {n} child sitemap(s) — good for large sites.",
                     "passing", detail=f"{n} child sitemaps")]
    locs = sitemap_locs(sitemap)
    if not locs:
        return [_row("Sitemap valid", "error", "sitemap.xml has no <loc> entries — it isn't a valid sitemap.",
                     "fix the sitemap to list <url><loc> entries")]
    rows = [_row("Sitemap valid", "ok", f"Valid sitemap with {len(locs)} URL(s).", "passing", detail=f"{len(locs)} URLs")]
    http = [u for u in locs if u.startswith("http://")]
    if http:
        rows.append(_row("Sitemap URL scheme", "warn", f"{len(http)} sitemap URL(s) use http:// — should be https.",
                         "list https URLs only", detail=f"{len(http)}"))
    if len(locs) > 50000:
        rows.append(_row("Sitemap size", "warn", "Over 50,000 URLs — exceeds the per-file limit.",
                         "split into a sitemap index"))
    return rows


def hreflang_rows(html: str) -> list[dict]:
    tags = re.findall(r"<link[^>]*hreflang=[^>]*>", (html or "").lower())
    if not tags:
        return []  # single-region site — nothing to validate
    rows: list[dict] = []
    missing_href = [t for t in tags if "href=" not in t]
    if missing_href:
        rows.append(_row("hreflang href", "warn", f"{len(missing_href)} hreflang tag(s) missing an href.",
                         "every hreflang link needs an href", detail=f"{len(missing_href)}"))
    if not any("x-default" in t for t in tags):
        rows.append(_row("hreflang x-default", "warn", "No x-default hreflang — set the fallback for unmatched locales.",
                         'add <link rel="alternate" hreflang="x-default" ...>'))
    else:
        rows.append(_row("hreflang set", "ok", f"{len(tags)} hreflang alternate(s) with an x-default.",
                         "passing", detail=f"{len(tags)} alternates"))
    return rows


def validate_rows(html: str, sitemap: str | None) -> list[dict]:
    return sitemap_validation_rows(sitemap) + hreflang_rows(html)


def hreflang_cluster_rows(pages: list[dict]) -> list[dict]:
    """Validate return tags and targets across every crawled page."""
    tag_map: dict[str, dict[str, str]] = {}
    statuses = {p.get("url"): p.get("status") for p in pages}
    pattern = re.compile(r"<link[^>]*rel=[\"'][^\"']*alternate[^\"']*[\"'][^>]*>", re.I)
    for page in pages:
        links: dict[str, str] = {}
        for tag in pattern.findall(page.get("html", "") or ""):
            lang = re.search(r"hreflang=[\"']([^\"']+)", tag, re.I)
            href = re.search(r"href=[\"']([^\"']+)", tag, re.I)
            if lang and href:
                links[lang.group(1).lower()] = href.group(1)
        if links:
            tag_map[page.get("url", "")] = links
    if not tag_map:
        return []
    rows: list[dict] = []
    missing_return: list[str] = []
    broken: list[str] = []
    for source, links in tag_map.items():
        for lang, target in links.items():
            if statuses.get(target) not in (None, 200):
                broken.append(f"{source} → {target} ({statuses[target]})")
            target_links = tag_map.get(target, {})
            if target not in (source,) and source not in target_links.values():
                missing_return.append(f"{source} → {target} ({lang})")
    if missing_return:
        rows.append({"code": "valid.hreflang_return_cluster", "what": "Hreflang return links", "severity": "warn",
                     "why": "Google may ignore an hreflang cluster when alternate pages do not link back to the source.",
                     "fix": "Add matching bidirectional hreflang links across the language/region cluster.",
                     "detail": f"{len(missing_return)} missing return link(s)", "pages": missing_return[:100]})
    if broken:
        rows.append({"code": "valid.hreflang_broken_target", "what": "Hreflang targets reachable", "severity": "error",
                     "why": "An hreflang target that errors or redirects cannot serve the intended locale.",
                     "fix": "Point hreflang at a canonical 200 URL that is indexable.",
                     "detail": f"{len(broken)} broken target(s)", "pages": broken[:100]})
    return rows
