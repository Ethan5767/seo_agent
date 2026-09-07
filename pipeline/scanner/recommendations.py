"""Plain-English 'why it matters / how to fix' per finding code.

Keyed by the finding.code that measure.check_page / providers emit. Purely
advisory copy for the audit UI — the machine-checkable acceptance still lives
in plan.ACTIONS. Kept as data so it reads and reviews as a table.
"""
from __future__ import annotations

RECOMMENDATIONS: dict[str, dict] = {
    "health.title_missing": {
        "why": "The <title> is the headline Google shows in results and the strongest on-page ranking signal. A missing title means Google invents one.",
        "fix": "Add a unique <title> of 30-60 characters that names the page's topic and location.",
    },
    "health.title_length": {
        "why": "Titles outside 30-60 characters get truncated or padded by Google, weakening the click.",
        "fix": "Rewrite the <title> to 30-60 characters, front-loading the primary term.",
    },
    "health.desc_missing": {
        "why": "With no meta description Google auto-generates the results snippet, often pulling unhelpful text and lowering click-through.",
        "fix": "Add a <meta name=\"description\"> of 120-160 characters that summarises the page and invites the click.",
    },
    "health.desc_length": {
        "why": "Descriptions outside 120-160 characters get cut off or look thin in results.",
        "fix": "Rewrite the meta description to 120-160 characters.",
    },
    "health.h1_count": {
        "why": "Exactly one <h1> tells search engines and screen readers the page's single main topic. Zero or many blurs it.",
        "fix": "Keep exactly one <h1> as the page's main heading; demote the rest to <h2>/<h3>.",
    },
    "health.canonical_mismatch": {
        "why": "A missing or wrong canonical lets duplicate URLs compete and splits ranking signals.",
        "fix": "Add <link rel=\"canonical\"> pointing to this page's own preferred URL.",
    },
    "health.noindex_present": {
        "why": "A noindex tag tells Google to drop the page from search entirely — often left in by accident.",
        "fix": "Remove the noindex directive unless the page is genuinely meant to be hidden.",
    },
    "health.og_image_missing": {
        "why": "Without og:image the page shows no preview thumbnail when shared on social or chat, cutting clicks.",
        "fix": "Add <meta property=\"og:image\"> pointing at a representative image.",
    },
    "health.schema_business_missing": {
        "why": "LocalBusiness structured data is how Google and AI engines reliably read the business's name, address and phone. Without it they guess.",
        "fix": "Add LocalBusiness JSON-LD with name, address, phone and URL.",
    },
    "health.schema_breadcrumb_missing": {
        "why": "BreadcrumbList structured data gives search results a clear path and can show breadcrumb rich snippets.",
        "fix": "Add BreadcrumbList JSON-LD reflecting the page's position in the site.",
    },
    "health.img_alt_missing": {
        "why": "Images with no alt attribute are invisible to search image indexing and to screen readers.",
        "fix": "Add a descriptive alt attribute to each content image (empty alt only for decorative images).",
    },
    "health.thin_content": {
        "why": "Very short pages rarely satisfy a search intent, so they struggle to rank and are seldom cited by AI answers.",
        "fix": "Expand the copy to genuinely answer the page's question (aim for 500+ words of substance, not padding).",
    },
    # AEO
    "aeo.robots_missing": {
        "why": "With no robots.txt, AI citation crawlers have no explicit allow and some treat the site as off-limits.",
        "fix": "Ship a robots.txt that Allows the citation crawlers (OAI-SearchBot, ClaudeBot, PerplexityBot, Bingbot, Googlebot) at root.",
    },
    "aeo.crawler_blocked": {
        "why": "If an AI citation crawler is Disallowed, the site cannot be cited in that engine's answers at all.",
        "fix": "Update robots.txt to Allow the blocked citation crawler at root.",
    },
    # Performance (CrUX)
    "crux.lcp_above_good": {
        "why": "Largest Contentful Paint over 2.5s is the moment users decide a page is slow; Google penalises it and AI engines cite it less.",
        "fix": "Optimise the largest element: compress/serve the hero image well, remove render-blocking resources, and speed up the server response.",
    },
    "crux.inp_above_good": {
        "why": "Interaction to Next Paint over 200ms makes taps and clicks feel frozen, driving users away.",
        "fix": "Break up long JavaScript tasks, defer non-critical scripts, and reduce main-thread work.",
    },
    "crux.cls_above_good": {
        "why": "Cumulative Layout Shift over 0.1 means the page jumps while loading, causing misclicks and frustration.",
        "fix": "Set width/height on images and embeds, and reserve space for anything that loads late.",
    },
    "crux.disabled": {
        "why": "Real field performance (LCP/INP/CLS) comes from Google's CrUX dataset and needs an API key.",
        "fix": "Set CRUX_API_KEY (free from Google) to enable Core Web Vitals in the audit.",
    },
}

_GENERIC = {
    "why": "This issue affects how search engines or AI answer engines read the page.",
    "fix": "Review the finding detail and correct the underlying markup or content.",
}


def recommend(code: str, detail: str = "") -> dict:
    """Return {'why','fix'} for a finding code, or a safe generic fallback."""
    return RECOMMENDATIONS.get(code, _GENERIC)
