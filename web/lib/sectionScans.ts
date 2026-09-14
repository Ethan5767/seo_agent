/**
 * What each section audits when you press Scan inside it.
 *
 * The operator's ask, and it is the right shape: *"if SEO, when audit only audit
 * about SEO."* Until now every scan ran all 25 tools and every screen filtered
 * the same pile afterwards, so pressing Scan on the Local page spent money on
 * backlinks and rank tracking and then showed you five local rows.
 *
 * Nothing new was needed to support this. `build_report(..., selected=...)` has
 * always taken a set of tool keys, and every tool already declares a `category`.
 * The missing piece was a map from the SECTION a person is looking at to the
 * CATEGORIES that answer it - which is product knowledge, so it lives here
 * rather than being re-derived in a component.
 *
 * Two rules this follows:
 *
 *   A section's scan must be a strict subset of the full scan. No section gets a
 *   tool the full scan would not run, so "scan this section" can never produce a
 *   finding "scan everything" would miss.
 *
 *   Paid tools are named, per section, in the cost line. A scoped scan is mostly
 *   an argument about money: the operator should see what this one will spend
 *   before pressing it, not after.
 */

/** Tool categories, exactly as `pipeline/scanner/server.py` declares them. */
export type ToolCategory =
  | "On-page" | "Technical" | "Content" | "Trust & E-E-A-T"
  | "AEO (AI search)" | "Keywords & Rankings" | "Links"
  | "Local" | "Local SEO" | "Reputation"
  | "Performance" | "Lighthouse (Google)" | "Source code";

export type SectionScan = {
  /** Matches NAV_SECTIONS id. */
  id: "SEO" | "AI" | "Local" | "Content" | "Traffic";
  label: string;
  /** One line: what pressing Scan here actually looks at. */
  scope: string;
  categories: ToolCategory[];
};

export const SECTION_SCANS: SectionScan[] = [
  {
    id: "SEO",
    label: "SEO",
    scope: "The page and the site: titles, meta, headings, schema, sitemap, internal links and speed.",
    categories: ["On-page", "Technical", "Performance", "Lighthouse (Google)", "Links"],
  },
  {
    id: "AI",
    label: "AI Search (AEO)",
    scope: "Whether answer engines can reach, read and quote the page.",
    categories: ["AEO (AI search)"],
  },
  {
    id: "Local",
    label: "Local",
    scope: "The Google Business Profile, and the local signals on the page itself.",
    categories: ["Local", "Local SEO", "Reputation"],
  },
  {
    id: "Content",
    label: "Content",
    scope: "Depth, information gain, video, and the trust signals a reader looks for.",
    categories: ["Content", "Trust & E-E-A-T"],
  },
  {
    id: "Traffic",
    label: "Keywords & Rankings",
    scope: "Where the site ranks and for what. Every tool here is paid.",
    categories: ["Keywords & Rankings"],
  },
];

export type ToolLike = { key: string; category: string; label?: string; group?: string; cost?: string };

export function sectionById(id: string): SectionScan | undefined {
  return SECTION_SCANS.find((s) => s.id === id);
}

/**
 * The tool keys a section's scan should run.
 *
 * Returns `null` when the tool list has not loaded - NOT an empty set. An empty
 * set would read to `build_report` as "run nothing", and a scan that ran nothing
 * must never look like a scan that found nothing.
 */
export function toolsForSection(
  id: string, tools: ToolLike[] | null | undefined,
): string[] | null {
  const section = sectionById(id);
  if (!section || !Array.isArray(tools) || tools.length === 0) return null;
  const wanted = new Set<string>(section.categories);
  const keys = tools.filter((t) => t && wanted.has(t.category)).map((t) => t.key);
  return keys.length ? keys : null;
}

/** What this section's scan will spend, named rather than totalled silently. */
export function sectionCost(
  id: string, tools: ToolLike[] | null | undefined,
): { free: number; paid: ToolLike[] } | null {
  const keys = toolsForSection(id, tools);
  if (!keys) return null;
  const chosen = (tools ?? []).filter((t) => keys.includes(t.key));
  return {
    free: chosen.filter((t) => t.group === "free").length,
    paid: chosen.filter((t) => t.group && t.group !== "free"),
  };
}

/** Tool keys that back a specific report view, so an operator can test THAT SPECIFIC TOOL directly. */
export const VIEW_TOOLS: Record<string, string[]> = {
  "site-crawl": ["internal", "site"],
  "technical": ["tech", "schema", "validate"],
  "position-tracking": ["rank_trend"],
  "domain-overview": ["keywords"],
  "organic-rankings": ["rankings"],
  "compare-domains": ["keywords"],
  "keyword-gap": ["keywords"],
  "keyword-overview": ["keywords"],
  "keyword-clusters": ["keywords"],
  "keyword-ideas": ["keywords"],
  "search-intent": ["keywords"],
  "serp-positions": ["rankings"],
  "backlinks": ["backlinks"],
  "backlink-audit": ["backlinks"],
  "core-web-vitals": ["perf", "lh_perf", "lh_seo"],
  "source-code": ["source"],
  "on-page": ["seo", "onpage"],
  "content-quality": ["content", "eeat"],
  "video": ["video"],
  "local": ["local"],
  "aeo-answers": ["aeo"],
  "aeo-crawlers": ["aeo"],
  "aeo-citations": ["aeo"],
  "ai-mentions": ["ai", "mentions"],
};

export function toolsForView(
  viewId: string, tools: ToolLike[] | null | undefined,
): string[] | null {
  if (!Array.isArray(tools) || tools.length === 0) return null;
  const wanted = VIEW_TOOLS[viewId];
  if (!wanted) return null;
  const available = new Set(tools.map((t) => t.key));
  const keys = wanted.filter((k) => available.has(k));
  return keys.length ? keys : null;
}

export function viewCost(
  viewId: string, tools: ToolLike[] | null | undefined,
): { free: number; paid: ToolLike[] } | null {
  const keys = toolsForView(viewId, tools);
  if (!keys) return null;
  const chosen = (tools ?? []).filter((t) => keys.includes(t.key));
  return {
    free: chosen.filter((t) => t.group === "free").length,
    paid: chosen.filter((t) => t.group && t.group !== "free"),
  };
}

