"""Reconcile owned crawl/sitemap URLs with Search Console index states."""

from __future__ import annotations


def reconcile_index(crawl_urls: set[str], sitemap_urls: set[str], inspections: list[dict] | None) -> list[dict]:
    """Return measured index buckets, or an honest OAuth-required finding."""
    if not inspections:
        return [{"code": "index.gsc_connection_required", "what": "Search Console index data not connected",
                 "severity": "info", "why": "A crawl can see what the site publishes, not what Google indexed.",
                 "fix": "Connect Google Search Console to reconcile submitted, indexed, discovered, and crawled URLs.",
                 "confidence": "low"}]
    submitted = set(sitemap_urls)
    crawled = set(crawl_urls)
    buckets: dict[str, list[str]] = {"indexed": [], "submitted_not_indexed": [],
                                    "discovered_not_indexed": [], "crawled_not_indexed": []}
    for item in inspections:
        url = str(item.get("url") or item.get("inspectionUrl") or "")
        if not url:
            continue
        state = str(item.get("coverageState") or "").lower()
        indexed = bool(item.get("indexed")) or state.startswith(("indexed", "submitted and indexed"))
        if indexed:
            buckets["indexed"].append(url)
        elif "crawled" in state:
            buckets["crawled_not_indexed"].append(url)
        elif "discovered" in state:
            buckets["discovered_not_indexed"].append(url)
        elif url in submitted:
            buckets["submitted_not_indexed"].append(url)
    labels = {
        "indexed": ("Indexed URLs", "ok", "Google reports these URLs as indexed."),
        "submitted_not_indexed": ("Submitted but not indexed", "warn", "The sitemap submits these URLs, but Google does not report them indexed."),
        "discovered_not_indexed": ("Discovered but not indexed", "warn", "Google knows these URLs but has not indexed them."),
        "crawled_not_indexed": ("Crawled but not indexed", "error", "Google crawled these URLs but did not include them in the index."),
    }
    rows: list[dict] = []
    for key, urls in buckets.items():
        label, severity, why = labels[key]
        rows.append({"code": f"index.{key}", "what": label, "severity": severity if urls else "info",
                     "why": why, "fix": "Inspect affected URLs and improve indexability signals before requesting another crawl.",
                     "detail": f"{len(urls)} URL(s)", "pages": sorted(urls), "confidence": "high"})
    all_seen = {u for values in buckets.values() for u in values}
    not_inspected = sorted((submitted | crawled) - all_seen)
    if not_inspected:
        rows.append({"code": "index.not_inspected", "what": "Crawl URLs without an inspection result", "severity": "info",
                     "why": "The reconciliation is incomplete for URLs without a Search Console inspection.",
                     "fix": "Run URL Inspection for the remaining URLs.", "detail": f"{len(not_inspected)} URL(s)",
                     "pages": not_inspected[:100], "confidence": "medium"})
    return rows
