/**
 * The verb a tool's Test button and scope caption should use.
 *
 * Not every tool audits. "Audit Domain Overview" is wrong: Domain Overview is a
 * lookup, Compare Domains is a comparison, Keyword Ideas is a search. The button
 * and the one-line caption both read from here, so the word always fits the
 * action instead of a blanket "Test" / "Audits".
 *
 * `verb` is the imperative for the button, `gerund` the -s form for the caption,
 * and `object` the noun both act on (kept short and natural, e.g. "Domains" not
 * "Compare Domains", so the verb never doubles the label). Keyed by the report
 * view id in `lib/reportViews.ts`; anything unlisted falls back to "Run".
 */
export interface ToolVerb {
  verb: string;
  gerund: string;
  object: string;
}

const VERBS: Record<string, ToolVerb> = {
  "position-tracking": { verb: "Track", gerund: "Tracks", object: "Positions" },
  "domain-overview": { verb: "Look up", gerund: "Looks up", object: "Domain Overview" },
  "organic-rankings": { verb: "Look up", gerund: "Looks up", object: "Organic Rankings" },
  "compare-domains": { verb: "Compare", gerund: "Compares", object: "Domains" },
  "keyword-gap": { verb: "Find", gerund: "Finds", object: "Keyword Gaps" },
  "keyword-overview": { verb: "Look up", gerund: "Looks up", object: "Keyword Metrics" },
  "keyword-clusters": { verb: "Build", gerund: "Builds", object: "Keyword Clusters" },
  "keyword-ideas": { verb: "Find", gerund: "Finds", object: "Keyword Ideas" },
  "search-intent": { verb: "Analyze", gerund: "Analyzes", object: "Search Intent" },
  "backlinks": { verb: "Look up", gerund: "Looks up", object: "Backlinks" },
  "backlink-audit": { verb: "Audit", gerund: "Audits", object: "Backlinks" },
  "backlink-gap": { verb: "Find", gerund: "Finds", object: "Backlink Gaps" },
  "site-crawl": { verb: "Crawl", gerund: "Crawls", object: "the Site" },
  "serp-positions": { verb: "Check", gerund: "Checks", object: "SERP Positions" },
  "ai-mentions": { verb: "Check", gerund: "Checks", object: "AI Mentions" },
  "aeo-answers": { verb: "Check", gerund: "Checks", object: "Answer Readiness" },
  "aeo-crawlers": { verb: "Check", gerund: "Checks", object: "Crawler Access" },
  "aeo-citations": { verb: "Check", gerund: "Checks", object: "Citation Signals" },
  "core-web-vitals": { verb: "Measure", gerund: "Measures", object: "Core Web Vitals" },
  "on-page": { verb: "Check", gerund: "Checks", object: "On-Page SEO" },
  "technical": { verb: "Check", gerund: "Checks", object: "Technical SEO" },
  "content-quality": { verb: "Review", gerund: "Reviews", object: "Content Quality" },
  "video": { verb: "Check", gerund: "Checks", object: "Video SEO" },
  "local": { verb: "Check", gerund: "Checks", object: "Local Signals" },
  "trust": { verb: "Check", gerund: "Checks", object: "Trust Signals" },
  "all-findings": { verb: "Audit", gerund: "Audits", object: "Everything" },
  "all-checks": { verb: "Run", gerund: "Runs", object: "All Checks" },
};

/** The verb for a view, or a plain "Run <label>" fallback for anything unlisted. */
export function toolVerb(viewId: string | undefined, viewLabel: string | undefined): ToolVerb {
  return (viewId && VERBS[viewId]) || { verb: "Run", gerund: "Runs", object: viewLabel || "Tool" };
}
