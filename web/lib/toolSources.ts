/**
 * Which data source a tool page reads: DataForSEO, or our own tools.
 *
 * Operator decision, 2026-09-14: every tool page carries a Data source dropdown,
 * DataForSEO is the default wherever it can serve the page, and our own tools
 * stay selectable. A source that cannot serve a page is still listed, disabled,
 * with the reason, so the choice is never hidden.
 *
 * A source is two lists: the scanner tool keys its Test button runs, and the
 * row codes the page shows. Keeping both here is what makes "I picked
 * DataForSEO" mean the same thing to the button and to the table.
 */

import { REPORT_VIEWS } from "./reportViews.ts";

export type SourceId = "dataforseo" | "ours";

export type SourceOption =
  | { tools: string[]; codes: string[] }
  | { disabled: string };

export type ToolSources = { dataforseo: SourceOption; ours: SourceOption };

export const SOURCE_LABEL: Record<SourceId, string> = {
  dataforseo: "DataForSEO (paid)",
  ours: "Our tools (free)",
};

/**
 * DataForSEO's on-page crawl flags (`pipeline/scanner/onpage_audit.py` CHECKS),
 * split by the page that should show them. One Site Health run ($0.006 for 25
 * pages) feeds all three; `toolSources.test.mjs` fails if a flag is added there
 * and not placed here.
 */
export const DFS_FLAGS = {
  crawl: [
    "is_4xx_code", "is_5xx_code", "is_broken", "broken_links", "broken_resources",
    "is_orphan_page", "duplicate_content", "duplicate_title", "duplicate_description",
    "links_relation_conflict",
  ],
  technical: [
    "is_https", "is_http", "https_to_http_links", "no_doctype", "has_html_doctype",
    "no_encoding_meta_tag", "meta_charset_consistency", "has_micromarkup",
    "has_micromarkup_errors", "no_content_encoding", "frame", "flash", "deprecated_html_tags",
    "no_favicon", "is_redirect", "redirect_loop", "meta_refresh_redirect", "canonical",
    "canonical_chain", "canonical_to_broken", "canonical_to_redirect", "recursive_canonical",
    "seo_friendly_url", "high_loading_time", "high_waiting_time", "size_greater_than_3mb",
    "has_render_blocking_resources",
  ],
  onPage: [
    "no_title", "title_too_long", "title_too_short", "title_too_many_words", "irrelevant_title",
    "duplicate_title_tag", "duplicate_meta_tags",
    "no_description", "irrelevant_description", "irrelevant_meta_keywords", "no_h1_tag", "no_h2",
    "no_image_alt", "no_image_title", "low_content_rate", "high_content_rate",
    "low_readability_rate", "lorem_ipsum", "small_page_size",
  ],
} as const;

const op = (flags: readonly string[]) => flags.map((f) => `dfs.op.${f}`);

function viewCodes(id: string): string[] {
  return REPORT_VIEWS.find((v) => v.id === id)?.codes ?? [];
}

const NO_OTHER_SITES =
  "No free source has data about other sites. Only a paid index like DataForSEO does.";
const NO_LINK_INDEX = "No free backlink index exists. Only a paid index like DataForSEO has one.";
const GSC_NOT_YET =
  "Free option (Google Search Console, your own verified site) is not built yet.";

const dfs = (id: string, tools: string[]): SourceOption => ({ tools, codes: viewCodes(id) });
const ours = (id: string, tools: string[]): SourceOption => ({ tools, codes: viewCodes(id) });

export const TOOL_SOURCES: Record<string, ToolSources> = {
  // ── SEO ──
  "site-crawl": {
    dataforseo: { tools: ["site"], codes: op(DFS_FLAGS.crawl) },
    ours: { tools: ["internal"], codes: ["site."] },
  },
  technical: {
    dataforseo: { tools: ["site"], codes: op(DFS_FLAGS.technical) },
    ours: ours("technical", ["tech", "headers", "schema", "validate", "render", "media", "security", "url", "index_reality", "logs", "migration"]),
  },
  "position-tracking": { dataforseo: dfs("position-tracking", ["rank_trend"]), ours: { disabled: GSC_NOT_YET } },
  "live-monitor": {
    dataforseo: { disabled: "The monitor reads the live site directly, which costs nothing." },
    ours: ours("live-monitor", ["monitor"]),
  },
  "core-web-vitals": {
    dataforseo: { disabled: "DataForSEO has no real-user field data. Google's CrUX and Lighthouse are the source, and free." },
    ours: ours("core-web-vitals", ["perf", "lh_perf", "lh_seo", "lh_a11y", "lh_bp", "lh_pages"]),
  },
  // ── Competitive ──
  "domain-overview": { dataforseo: dfs("domain-overview", ["rankings"]), ours: { disabled: GSC_NOT_YET } },
  "organic-rankings": { dataforseo: dfs("organic-rankings", ["rankings"]), ours: { disabled: GSC_NOT_YET } },
  "compare-domains": { dataforseo: dfs("compare-domains", ["compare"]), ours: { disabled: NO_OTHER_SITES } },
  "keyword-gap": { dataforseo: dfs("keyword-gap", ["keywords"]), ours: { disabled: NO_OTHER_SITES } },
  // ── Keywords ──
  "keyword-overview": { dataforseo: dfs("keyword-overview", ["keywords"]), ours: { disabled: GSC_NOT_YET } },
  "keyword-ideas": { dataforseo: dfs("keyword-ideas", ["keywords"]), ours: { disabled: NO_OTHER_SITES } },
  "keyword-clusters": { dataforseo: dfs("keyword-clusters", ["keywords"]), ours: { disabled: GSC_NOT_YET } },
  "search-intent": { dataforseo: dfs("search-intent", ["keywords"]), ours: { disabled: NO_OTHER_SITES } },
  "serp-positions": { dataforseo: dfs("serp-positions", ["rankings"]), ours: { disabled: GSC_NOT_YET } },
  // ── Links ──
  "backlink-overview": { dataforseo: dfs("backlink-overview", ["backlink_overview"]), ours: { disabled: NO_LINK_INDEX } },
  backlinks: { dataforseo: dfs("backlinks", ["backlinks"]), ours: { disabled: NO_LINK_INDEX } },
  "backlink-audit": { dataforseo: dfs("backlink-audit", ["backlinks"]), ours: { disabled: NO_LINK_INDEX } },
  "backlink-gap": { dataforseo: dfs("backlink-gap", ["backlink_gap"]), ours: { disabled: NO_LINK_INDEX } },
  // ── On-page ──
  "on-page": {
    dataforseo: { tools: ["site"], codes: op(DFS_FLAGS.onPage) },
    ours: ours("on-page", ["seo", "onpage"]),
  },
  // ── Content, AI, Local ──
  "content-quality": { dataforseo: { disabled: "DataForSEO has no content-quality or E-E-A-T checks." }, ours: ours("content-quality", ["content", "eeat"]) },
  trust: { dataforseo: { disabled: "DataForSEO has no E-E-A-T trust checks." }, ours: ours("trust", ["eeat"]) },
  video: { dataforseo: { disabled: "DataForSEO has no video checks." }, ours: ours("video", ["video"]) },
  local: { dataforseo: { disabled: "The Google Business Profile lookup shows in Local Presence." }, ours: ours("local", ["local"]) },
  "aeo-answers": { dataforseo: { disabled: "DataForSEO does not check answer-engine structure." }, ours: ours("aeo-answers", ["aeo"]) },
  "aeo-crawlers": { dataforseo: { disabled: "DataForSEO does not read your robots.txt rules for AI crawlers." }, ours: ours("aeo-crawlers", ["aeo"]) },
  "aeo-citations": { dataforseo: { disabled: "Use AI Mentions for DataForSEO's LLM citation data." }, ours: ours("aeo-citations", ["aeo"]) },
  // `ai` only: `mentions` (~$0.03) emits mention.* rows this page never shows.
  "ai-mentions": { dataforseo: dfs("ai-mentions", ["ai"]), ours: { disabled: "No free source records what AI engines say about a brand." } },
};

export function isEnabled(o: SourceOption | undefined): o is { tools: string[]; codes: string[] } {
  return Boolean(o && "tools" in o);
}

type CatalogLike = { key: string; available?: boolean; unavailable_reason?: string };

/**
 * Why a source cannot be picked right now, or "" when it can. Static reasons
 * come from the table; a live one (no DataForSEO credentials, paused spend)
 * comes from the scanner catalog, so the dropdown and the scan agree. While
 * the catalog is loading, the scan endpoint remains the availability check.
 */
export function sourceBlocker(
  viewId: string, source: SourceId, catalog: CatalogLike[] | null | undefined,
): string {
  const opt = TOOL_SOURCES[viewId]?.[source];
  if (!opt) return "Not configured for this page.";
  if (!isEnabled(opt)) return opt.disabled;
  const down = (catalog ?? []).filter((t) => opt.tools.includes(t.key) && t.available === false);
  return down.length ? down[0].unavailable_reason || "Unavailable right now." : "";
}

/**
 * The source a page opens on: the saved choice if it can still be used, else
 * DataForSEO, else our tools.
 */
export function effectiveSource(
  viewId: string, saved: SourceId | null | undefined, catalog: CatalogLike[] | null | undefined,
): SourceId | null {
  const order: SourceId[] = [saved, "dataforseo", "ours"].filter(Boolean) as SourceId[];
  for (const s of order) if (!sourceBlocker(viewId, s, catalog)) return s;
  return null;
}

/**
 * Did the last scan run this source's tools? Distinguishes "never scanned"
 * from "scanned and found nothing of this kind". Crawl Issues on DataForSEO read
 * "No data here yet / Run a scan" right after a 25-page Site Health run whose 12
 * flags were all on-page and technical (operator, 2026-09-14).
 *
 * `site` is shared with the free crawl, so it counts as run only when a Site
 * Health row (or its refusal) is present.
 */
export function sourceRan(
  report: Record<string, unknown> | null | undefined,
  opt: { tools: string[] } | undefined,
): boolean {
  if (!report || !opt) return false;
  return opt.tools.some((tool) => {
    const rows = report[tool];
    if (!Array.isArray(rows) || rows.length === 0) return false;
    if (tool !== "site") return true;
    return rows.some((r: any) => typeof r?.code === "string" && (r.code.startsWith("dfs.op.") || r.code === "unavailable.site"));
  });
}
