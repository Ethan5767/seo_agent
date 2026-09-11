/**
 * Report views: the screens behind the SEO section.
 *
 * The scanner already emits 25 distinct row codes on every run, but almost all
 * of them collapsed into one "Keywords" card, which is why the SEO menu had a
 * handful of destinations where Semrush has eighteen. Nothing new is fetched
 * here. Each view is a named slice of rows the report already contains, so
 * adding a screen costs no API call and no money.
 *
 * A view earns a nav entry only when its codes are rows the scanner really
 * produces (`pipeline/scanner/dataforseo.py`, `audit.py`). A screen with no
 * backing code would be the alias problem again, one layer down.
 */

import type { ReportRow, ScanReport } from "./priorities";

export interface ReportColumn {
  key: "what" | "detail" | "why" | "fix" | "severity";
  label: string;
  /** Right-aligned and tabular; used for columns that hold figures. */
  numeric?: boolean;
  width?: string;
}

export interface ReportView {
  id: string;
  label: string;
  /** Row codes this view shows. A prefix ending in "." matches any suffix. */
  codes: string[];
  /** Shown above the table; says what the screen is for in plain words. */
  blurb: string;
  columns: ReportColumn[];
  /** What to say when the report has none of these rows. */
  emptyHint: string;
}

/*
 * The scanner writes rows as prose, not as metrics. A real row looks like:
 *
 *   what:   "18168 backlinks from 48 referring domains"
 *   why:    "Backlinks are a top Google ranking factor..."
 *   fix:    "keep earning links from relevant, trusted sites"
 *   detail: "authority rank 268"
 *
 * So the columns are named for what the fields actually hold. An earlier
 * version labelled them "Metric" and "Value" and right-aligned `detail` as a
 * figure, which no row is. `detail` is also optional: `dfs.competitor` leaves
 * it empty, and the table renders an em dash rather than a blank cell.
 */
const KEYWORD_COLUMNS: ReportColumn[] = [
  { key: "what", label: "What we found", width: "36%" },
  { key: "detail", label: "Detail", width: "22%" },
  { key: "why", label: "Why it matters" },
];

const FINDING_COLUMNS: ReportColumn[] = [
  { key: "what", label: "What we found", width: "36%" },
  { key: "detail", label: "Detail", width: "22%" },
  { key: "fix", label: "What to do" },
];

export const REPORT_VIEWS: ReportView[] = [
  {
    id: "position-tracking",
    label: "Position Tracking",
    codes: ["dfs.rank_trend"],
    blurb: "How this domain's ranking positions have moved over time.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Rankings trend tool enabled to populate this.",
  },
  {
    id: "domain-overview",
    label: "Domain Overview",
    codes: ["dfs.domain_overview"],
    blurb: "Headline organic figures for the domain, as reported by DataForSEO.",
    columns: FINDING_COLUMNS,
    emptyHint: "The Domain Overview tool is not part of the scan yet.",
  },
  {
    id: "organic-rankings",
    label: "Organic Rankings",
    codes: ["dfs.ranked_keyword"],
    blurb: "Keywords this domain already ranks for, best positions first.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Rankings tool enabled to populate this.",
  },
  {
    id: "compare-domains",
    label: "Compare Domains",
    codes: ["dfs.competitor"],
    blurb: "Domains competing for the same organic terms, discovered from the SERP.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled; competitors come with it.",
  },
  {
    id: "keyword-gap",
    label: "Keyword Gap",
    codes: ["dfs.keyword_gap"],
    blurb: "Terms a competitor ranks for and this domain does not.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled; the gap comes with it.",
  },
  {
    id: "keyword-overview",
    label: "Keyword Overview",
    codes: ["dfs.keyword_volume", "dfs.keyword_difficulty"],
    blurb: "Search volume and difficulty for the terms tracked on this project.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Add keywords to the project, then run a scan with the Keywords tool.",
  },
  {
    id: "keyword-ideas",
    label: "Keyword Ideas",
    codes: ["dfs.keyword_idea", "dfs.keyword_suggestion"],
    blurb: "Related terms and suggestions to expand the keyword set.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled to populate this.",
  },
  {
    id: "search-intent",
    label: "Search Intent",
    codes: ["dfs.search_intent"],
    blurb: "What searchers want from each term: informational, commercial, navigational or transactional.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled to populate this.",
  },
  {
    id: "backlinks",
    label: "Backlinks",
    codes: ["dfs.backlinks"],
    blurb: "Referring domains and total backlinks for this site.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan with the Backlinks tool enabled to populate this.",
  },
  {
    id: "backlink-audit",
    label: "Backlink Audit",
    codes: ["dfs.broken_backlinks", "dfs.broken_links", "dfs.broken_page"],
    blurb: "Links pointing at pages that no longer resolve, inbound and internal.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan with the Backlinks tool enabled to populate this.",
  },
  {
    id: "site-crawl",
    label: "Crawl Issues",
    codes: [
      "dfs.duplicate_content",
      "dfs.duplicate_title",
      "dfs.duplicate_description",
      "dfs.click_depth",
      "dfs.orphan_page",
      "dfs.large_page_size",
      "dfs.redirect",
      "dfs.canonical_chain",
      "dfs.image_alt_missing",
    ],
    blurb: "Structural problems found crawling the site: duplicates, depth, orphans, redirects.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan with the Site Health tool enabled to populate this.",
  },
  {
    id: "serp-positions",
    label: "SERP Positions",
    codes: ["dfs.serp_rank"],
    blurb: "Live SERP position for each tracked term.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Rankings tool enabled to populate this.",
  },
  {
    id: "ai-mentions",
    label: "AI Mentions",
    codes: ["dfs.llm_mentions"],
    blurb: "Where this brand is mentioned in answers from large language models.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the AI citations tool enabled to populate this.",
  },
  {
    id: "aeo-answers",
    label: "Answer Readiness",
    codes: ["aeo.no_answer_structure", "aeo.statistics", "aeo.data_tables"],
    blurb:
      "Whether pages are written so an answer engine can lift a direct answer: question-and-answer blocks, stated statistics, and data in tables.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan. The AI visibility check is free and runs by default.",
  },
  {
    id: "aeo-crawlers",
    label: "Crawler Findings",
    // "aeo.robots" is not a real code: it was a prefix match on
    // "aeo.robots_missing". The scanner emits only these two.
    codes: ["aeo.crawler_blocked", "aeo.robots_missing"],
    blurb:
      "What robots.txt allows at the edge for GPTBot, ClaudeBot, PerplexityBot and Google-Extended. A blocked crawler cannot cite the site at all.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan. The AI visibility check is free and runs by default.",
  },
  {
    id: "aeo-citations",
    label: "Citation Signals",
    codes: ["aeo.citations"],
    blurb:
      "Quoted experts, cited studies and named sources on the page: the material answer engines reuse when they attribute.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan. The AI visibility check is free and runs by default.",
  },
  {
    id: "core-web-vitals",
    label: "Core Web Vitals",
    codes: ["crux.", "lh."],
    blurb:
      "Field data from real Chrome users (CrUX) alongside the lab run from Lighthouse. Field data is what Google ranks on; the lab run explains why it looks the way it does.",
    columns: FINDING_COLUMNS,
    emptyHint:
      "Run a scan. CrUX and all four Lighthouse categories are free and run by default.",
  },
  {
    id: "source-code",
    label: "Source Code",
    codes: ["src."],
    blurb:
      "What the repository says that the live page cannot: route existence, next.config redirects and headers, rendering posture, analytics wiring, llms.txt. No external SEO tool can see any of this.",
    columns: FINDING_COLUMNS,
    emptyHint:
      "Add this project's repository at onboarding, then run a scan. The source lane is free but needs a checkout.",
  },
  {
    id: "on-page",
    label: "On-Page Checks",
    codes: ["health."],
    blurb: "Per-page checks the crawler ran: titles, descriptions, headings, canonicals.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan to populate this. The on-page checks are free.",
  },
];

export interface RowTally {
  total: number;
  error: number;
  warn: number;
  info: number;
  ok: number;
}

/**
 * Counts for the strip above a report view.
 *
 * Always returns numbers, never nulls: an unscanned screen reports zeroes,
 * which is a reading, rather than rendering nothing at all. Rows with an
 * unrecognised severity are still counted in `total`, so the total can exceed
 * the sum of the four buckets and never silently loses a row.
 */
export function tallyRows(rows: ReportRow[] | null | undefined): RowTally {
  const t: RowTally = { total: 0, error: 0, warn: 0, info: 0, ok: 0 };
  if (!Array.isArray(rows)) return t;
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    t.total += 1;
    const s = row.severity;
    if (s === "error" || s === "warn" || s === "info" || s === "ok") t[s] += 1;
  }
  return t;
}

/**
 * The Site Audit screen's combined list: every finding from every tool.
 *
 * Deliberately NOT in REPORT_VIEWS. It claims no codes (the nav views slice
 * those) and has no nav entry of its own - it is the "everything" list on the
 * audit screen, which the sectioned views then cut up.
 */
export const ALL_FINDINGS_VIEW: ReportView = {
  id: "all-findings",
  label: "Audited Findings",
  codes: [],
  blurb: "Every finding from every tool that ran, newest scan first.",
  columns: FINDING_COLUMNS,
  emptyHint: "Run an audit to populate this. The on-page, technical and AI checks are free.",
};

export function viewById(id: string): ReportView | undefined {
  return REPORT_VIEWS.find((v) => v.id === id);
}

function matchesCode(rowCode: string, pattern: string): boolean {
  // A pattern ending in "." is a family: "health." matches "health.title_missing".
  return pattern.endsWith(".") ? rowCode.startsWith(pattern) : rowCode === pattern;
}

/** Keys in a report that are not groups of rows. */
const NON_GROUP_KEYS = new Set(["score", "counts", "cost", "log", "cycle", "url", "site_url"]);

/**
 * The rows a view shows, gathered from every group in the report.
 *
 * A code can appear in more than one group (the multipage merge re-emits rows),
 * so rows are de-duplicated on code plus `what`.
 */
export function rowsForView(
  report: ScanReport | null | undefined,
  view: ReportView,
): ReportRow[] {
  if (!report || typeof report !== "object") return [];

  const seen = new Set<string>();
  const out: ReportRow[] = [];

  for (const [key, value] of Object.entries(report)) {
    if (NON_GROUP_KEYS.has(key) || !Array.isArray(value)) continue;
    for (const row of value as ReportRow[]) {
      if (!row || typeof row !== "object") continue;
      const code = typeof row.code === "string" ? row.code : "";
      if (!code || !view.codes.some((p) => matchesCode(code, p))) continue;
      const dedupe = `${code}::${row.what ?? ""}`;
      if (seen.has(dedupe)) continue;
      seen.add(dedupe);
      out.push(row);
    }
  }
  return out;
}

/** How many rows each view would show, for badging the nav. */
export function viewCounts(report: ScanReport | null | undefined): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const view of REPORT_VIEWS) counts[view.id] = rowsForView(report, view).length;
  return counts;
}
