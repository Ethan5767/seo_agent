"""Per-tool check catalog — the named checks each Measure tool runs, so the UI
can show every individual check as its own row (pending → checking → result),
not just one card per tool.

Two kinds of tool:
  • Deterministic (free, on-page): the labels are FIXED and known up-front. These
    are harvested from the real row-producers and guarded by
    tests/test_scanner_checks.py so the catalog can't drift from what runs.
  • Dynamic (DataForSEO / Lighthouse): the exact findings vary per site, so the
    catalog lists the representative checks the tool covers; the real rows replace
    them when the tool finishes.

The UI never reconciles a catalog label 1:1 with a result row (pass and fail rows
can carry different labels) — it shows catalog labels while a tool is pending/
running, then swaps in the tool's actual rows on completion.
"""
from __future__ import annotations

# Fixed-label tools — asserted against live producer output by the drift test.
STATIC_CHECKS: dict[str, list[str]] = {
    "seo": [
        "Page title", "Meta description", "Single main heading (H1)", "Canonical tag",
        "Indexable (not noindexed)", "Social preview image", "LocalBusiness schema",
        "Breadcrumb schema", "Image alt text", "Content depth",
    ],
    "aeo": [
        # "Business schema" was "LocalBusiness schema": the check now accepts any
        # schema.org business type, so a dentist or clinic using the correct
        # subtype is no longer reported as having none.
        "AI crawlers allowed", "AI training crawlers allowed", "Business schema",
        "Answer-engine schema", "Answer-first structure",
        "Statistics and data", "Quotes and citations", "Data tables",
    ],
    "content": [
        "Content depth", "Original data", "Comprehensiveness", "Freshness", "Scannable structure",
    ],
    "eeat": [
        "Author / expertise", "Contact / trust", "Policy links", "Social proof",
        "Authoritativeness", "Citation-ready formatting",
    ],
    "tech": [
        "HTTPS", "Mobile viewport", "Language declared", "Open Graph tags", "Twitter/X card",
        "Favicon", "Rendering (crawler-visible content)", "XML sitemap", "Structured data found",
    ],
    "internal": [
        "Internal link count", "Anchor text quality", "Contextual links", "Descriptive anchors",
        "Over-optimization", "Nofollow usage", "Self-referential links", "Outbound links",
        "Image links",
    ],
    "perf": ["LCP (Largest Contentful Paint)", "INP (Interaction to Next Paint)", "CLS (Cumulative Layout Shift)"],
}

# Dynamic tools — representative coverage; real rows replace these on completion.
DYNAMIC_CHECKS: dict[str, list[str]] = {
    "site": ["Crawlability", "Broken links", "Duplicate titles/descriptions", "Redirect chains", "Indexation"],
    "schema": ["JSON-LD present", "Valid schema types", "Required fields", "Rich-result eligibility"],
    "validate": ["Sitemap reachable", "URLs valid", "hreflang pairs", "hreflang return-links"],
    "video": ["VideoObject schema", "Video metadata", "Thumbnail", "Transcript signals"],
    "ai": ["Brand cited by AI engines", "Citation share", "Answer presence"],
    "lh_perf": ["LCP", "Total Blocking Time", "CLS", "Speed Index", "Render-blocking resources"],
    "lh_seo": ["Crawlable", "Document title", "Meta description", "Tap targets", "Legible font sizes"],
    "lh_a11y": ["Colour contrast", "Image alt text", "ARIA roles", "Labels", "Focus order"],
    "lh_bp": ["HTTPS", "No console errors", "Image aspect ratios", "Vulnerable libraries"],
    "backlinks": ["Referring domains", "Backlink count", "Anchor profile", "Toxic links"],
    "keywords": ["Ranked keywords", "Search volume", "Keyword gaps"],
    "rankings": ["Position tracking", "SERP features"],
    "rank_trend": ["Rank movement", "Trend direction"],
    "gbp": ["GBP profile", "Reviews", "Categories", "NAP consistency"],
    "mentions": ["Web mentions", "Sentiment", "Unlinked mentions"],
    "source": [
        "Framework", "robots.txt", "sitemap.xml", "llms.txt", "Metadata API", "next.config",
        "SSR / SSG", "Image optimization", "Structured data", "Canonical strategy",
    ],
}


def checks_for(tool_key: str) -> list[str]:
    """The catalog checks for a tool key (static first, then dynamic), or []."""
    return STATIC_CHECKS.get(tool_key) or DYNAMIC_CHECKS.get(tool_key) or []
