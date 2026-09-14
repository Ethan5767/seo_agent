/**
 * Report views: the screens behind the SEO section.
 *
 * The scanner already emits 25 distinct row codes on every run, but almost all
 * of them collapsed into one "Keywords" card, which is why the SEO menu had a
 * handful of destinations where a big-suite tool has eighteen. Nothing new is fetched
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
  /**
   * The nav section this view belongs to, so a screen can scan ITS OWN concern
   * instead of running all 25 tools. Declared here rather than derived from the
   * id prefix: `trust` and `local` share no prefix with their section, and a
   * guess that works today breaks on the next view added.
   *
   * Absent on the two "everything" views (ALL_FINDINGS_VIEW, CHECKS_VIEW),
   * which deliberately belong to no section - they show the whole scan, so
   * scoping a scan from them would be a contradiction. Optional rather than a
   * sentinel value, because "this view has no section" is the real shape.
   */
  section?: "SEO" | "AI" | "Content" | "Local";
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
    section: "SEO",
    label: "Position Tracking",
    codes: ["dfs.rank_trend"],
    blurb: "How this domain's ranking positions have moved over time.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Rankings trend tool enabled to populate this.",
  },
  {
    id: "domain-overview",
    section: "SEO",
    label: "Domain Overview",
    codes: ["dfs.domain_overview"],
    blurb: "Headline organic figures for the domain, as reported by DataForSEO.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled; the domain overview comes with it.",
  },
  {
    id: "organic-rankings",
    section: "SEO",
    label: "Organic Rankings",
    codes: ["dfs.ranked_keyword"],
    blurb: "Keywords this domain already ranks for, best positions first.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Rankings tool enabled to populate this.",
  },
  {
    id: "compare-domains",
    section: "SEO",
    label: "Compare Domains",
    codes: ["dfs.competitor"],
    blurb: "Domains competing for the same organic terms, discovered from the SERP.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled; competitors come with it.",
  },
  {
    id: "keyword-gap",
    section: "SEO",
    label: "Keyword Gap",
    codes: ["dfs.keyword_gap"],
    blurb: "Terms a competitor ranks for and this domain does not.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled; the gap comes with it.",
  },
  {
    id: "keyword-overview",
    section: "SEO",
    label: "Keyword Overview",
    codes: ["dfs.keyword_volume", "dfs.keyword_difficulty"],
    blurb: "Search volume and difficulty for the terms tracked on this project.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Add keywords to the project, then run a scan with the Keywords tool.",
  },
  {
    // The big suites call the equivalent a Keyword Strategy Builder. Derived from the
    // keyword rows the scan already paid for, so it adds no API call.
    id: "keyword-clusters",
    section: "SEO",
    label: "Keyword Clusters",
    codes: ["cluster."],
    blurb:
      "The measured keywords grouped into the pages they want to become. A cluster usually wants one page covering all of it rather than a page per keyword, which competes with itself.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled; the clusters come with it.",
  },
  {
    id: "keyword-ideas",
    section: "SEO",
    label: "Keyword Ideas",
    codes: ["dfs.keyword_idea", "dfs.keyword_suggestion"],
    blurb: "Related terms and suggestions to expand the keyword set.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled to populate this.",
  },
  {
    id: "search-intent",
    section: "SEO",
    label: "Search Intent",
    codes: ["dfs.search_intent"],
    blurb: "What searchers want from each term: informational, commercial, navigational or transactional.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Keywords tool enabled to populate this.",
  },
  {
    id: "backlinks",
    section: "SEO",
    label: "Backlinks",
    codes: ["dfs.backlinks"],
    blurb: "Referring domains and total backlinks for this site.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan with the Backlinks tool enabled to populate this.",
  },
  {
    id: "backlink-audit",
    section: "SEO",
    label: "Backlink Audit",
    codes: ["dfs.broken_backlinks", "dfs.broken_links", "dfs.broken_page"],
    blurb: "Links pointing at pages that no longer resolve, inbound and internal.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan with the Backlinks tool enabled to populate this.",
  },
  {
    id: "site-crawl",
    section: "SEO",
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
      // The DataForSEO per-page flags, one row per check with a page count
      // (onpage_audit.aggregate_checks). Emitted on every Site Health run and
      // reachable from no screen until now.
      "dfs.op.",
      // The free multi-page crawl's own site-wide rows (crawl.site_rows):
      // duplicate titles/descriptions, orphans, broken internal links, and the
      // pages-crawled summary. Free, on by default, and likewise unscreened.
      "site.",
    ],
    blurb:
      "Structural problems found crawling the site: duplicates, depth, orphans, redirects and broken internal links. Both crawls report here - the free multi-page walk and the paid Site Health audit.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan. The multi-page crawl is free; the Site Health tool adds the paid rows.",
  },
  {
    id: "serp-positions",
    section: "SEO",
    label: "SERP Positions",
    codes: ["dfs.serp_rank"],
    blurb: "Live SERP position for each tracked term.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the Rankings tool enabled to populate this.",
  },
  {
    id: "ai-mentions",
    section: "AI",
    label: "AI Mentions",
    codes: ["dfs.llm_mentions"],
    blurb: "Where this brand is mentioned in answers from large language models.",
    columns: KEYWORD_COLUMNS,
    emptyHint: "Run a scan with the AI citations tool enabled to populate this.",
  },
  {
    id: "aeo-answers",
    section: "AI",
    label: "Answer Readiness",
    codes: [
      "aeo.no_answer_structure",
      "aeo.statistics",
      "aeo.data_tables",
      // FAQPage/QAPage/HowTo/Article is what tells an engine what kind of
      // answer the page holds, so it belongs with answer readiness.
      "aeo.answer_schema_missing",
    ],
    blurb:
      "Whether pages are written so an answer engine can lift a direct answer: question-and-answer blocks, stated statistics, and data in tables.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan. The AI visibility check is free and runs by default.",
  },
  {
    id: "aeo-crawlers",
    section: "AI",
    label: "Crawler Findings",
    // "aeo.robots" is not a real code: it was a prefix match on
    // "aeo.robots_missing". The scanner emits only these two.
    codes: [
      "aeo.crawler_blocked",
      "aeo.robots_missing",
      // Reported as info, never as a defect: blocking training crawlers is a
      // business decision and does not affect citation. The screen that covers
      // robots.txt is still the only honest place for it.
      "aeo.training_crawler_blocked",
    ],
    blurb:
      "What robots.txt allows at the edge for GPTBot, ClaudeBot, PerplexityBot and Google-Extended. A blocked crawler cannot cite the site at all.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan. The AI visibility check is free and runs by default.",
  },
  {
    id: "aeo-citations",
    section: "AI",
    label: "Citation Signals",
    // Authorship is a citation signal, not an answer-structure one: engines
    // weigh who wrote a thing when deciding what to attribute.
    codes: ["aeo.citations", "aeo.article_author_missing"],
    blurb:
      "Quoted experts, cited studies and named sources on the page: the material answer engines reuse when they attribute.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan. The AI visibility check is free and runs by default.",
  },
  {
    id: "core-web-vitals",
    section: "SEO",
    label: "Core Web Vitals",
    codes: ["crux.", "lh."],
    blurb:
      "Field data from real Chrome users (CrUX) alongside the lab run from Lighthouse. Field data is what Google ranks on; the lab run explains why it looks the way it does.",
    columns: FINDING_COLUMNS,
    emptyHint:
      "Run a scan. CrUX and all four Lighthouse categories are free and run by default.",
  },
  {
    id: "on-page",
    section: "SEO",
    label: "On-Page Checks",
    // `health.` is the universal checklist (title, description, H1, canonical,
    // indexability). `onpage.` is the deep pass over the same page: URL shape,
    // DOM weight, mixed content, heading order, filler text left in. Two
    // families, one screen, because an operator fixing a page wants both at
    // once and neither is a separate job.
    codes: ["health.", "onpage."],
    blurb:
      "Everything measurable in one page and its URL: titles, descriptions and canonicals, plus URL shape, DOM weight, mixed content, heading order, and filler text that reached production.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan to populate this. The on-page checks are free.",
  },
  {
    // Three free tools - Technical, Schema validation, Sitemap & hreflang - run
    // on every scan and had no sectioned screen of their own. Their rows landed
    // only on the combined audit list, so the whole technical lane was
    // unreachable from the menu while being measured every time.
    id: "technical",
    section: "SEO",
    label: "Technical Checks",
    codes: ["tech.", "schema.", "valid."],
    blurb:
      "Crawlability and markup: HTTPS, robots.txt, sitemap, hreflang, structured-data validity. Free, and every one of them runs by default.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan to populate this. The technical checks are free.",
  },
  /*
   * The content lane, three screens rather than one.
   *
   * These began as a single "Content & Trust" view parked under SEO, which was
   * enough to stop the rows being invisible but wrong as a home: the Content
   * section of the menu held five drafting tools and not one finding, so the
   * part of the product that MEASURES content lived under SEO while the part
   * that WRITES it lived under Content. They are three different questions and
   * they answer to three different people, so they get three entries, all in
   * Content, next to the tools that act on them.
   */
  {
    id: "content-quality",
    section: "Content",
    label: "Content Quality",
    codes: ["content."],
    blurb:
      "Depth and information gain: how much substance the page carries, whether it offers original data, how broadly it covers the topic, whether it is dated, and whether it can be skimmed.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan to populate this. The content checks are free.",
  },
  {
    id: "video",
    section: "Content",
    label: "Video",
    codes: ["video."],
    blurb:
      "Embedded video and how well it is described: VideoObject schema, plus live title/description/duration/thumbnail metadata read from the YouTube Data API for every video found on the page.",
    columns: FINDING_COLUMNS,
    emptyHint:
      "Run a scan. The schema check is free; the metadata rows need YOUTUBE_API_KEY. A page with no video reports that, which is a pass, not a gap.",
  },
  {
    id: "local",
    section: "Local",
    label: "Local Signals",
    codes: ["local."],
    blurb:
      "What a local searcher looks for, read from the page itself: a Google Maps embed, a tappable phone number, and a structured address, geo coordinates and opening hours. Free with every scan, and true of the page we fetched - unlike a directory listing, which only the directory can confirm.",
    columns: FINDING_COLUMNS,
    emptyHint:
      "Run a scan. These five checks are free and need no credential. They cover the site's own local signals; the Google Business Profile itself is a separate, paid tool.",
  },
  {
    id: "trust",
    section: "Content",
    label: "Trust & E-E-A-T",
    codes: ["eeat."],
    blurb:
      "Who stands behind the page: named authorship and credentials, reachable contact details, policy links, social proof, external validation, and whether facts are formatted so an answer engine can lift and attribute them.",
    columns: FINDING_COLUMNS,
    emptyHint: "Run a scan to populate this. The trust checks are free.",
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

/**
 * The "All Checks" sub-tab: every row the scan produced, passes included.
 *
 * Distinct from ALL_FINDINGS_VIEW, which shows only problems. This one keeps
 * "ok" rows so an operator can see what was checked and passed, which is the
 * whole point of the sub-tab. Like ALL_FINDINGS_VIEW it is not in
 * REPORT_VIEWS: it claims no codes and has no nav entry of its own.
 */
export const CHECKS_VIEW: ReportView = {
  id: "all-checks",
  label: "All Checks",
  codes: [],
  blurb: "Every check that ran on this scan, passes included.",
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
/**
 * A row that says a check did not run (`unavailable.<tool>` from the scanner's
 * run loop, `<group>.not_measured` when the page could not be fetched). It is a
 * reason, not a measurement.
 */
export function isNotRun(row: { code?: unknown } | null | undefined): boolean {
  const code = typeof row?.code === "string" ? row.code : "";
  return code.startsWith("unavailable.") || code.endsWith(".not_measured");
}

/**
 * The rows of a group that were actually measured. Every screen that reads a
 * report group directly (the Overview's rankings table, competitors, backlink
 * authority, Local, AI) must go through this: a "Rankings did not run" row read
 * as a ranking became a keyword at #1 with 240 searches a month (review,
 * 2026-09-14).
 */
export function measured<T extends { code?: unknown }>(rows: T[] | null | undefined): T[] {
  return Array.isArray(rows) ? rows.filter((r) => r && !isNotRun(r)) : [];
}

export function rowsForView(
  report: ScanReport | null | undefined,
  view: ReportView,
  /**
   * The page's chosen data source (`lib/toolSources.ts`): which codes to show
   * and which tools back it. Absent, the view shows everything it lists, which
   * is what the combined audit screens want.
   */
  source?: { codes: string[]; tools: string[] },
): ReportRow[] {
  if (!report || typeof report !== "object") return [];

  const seen = new Set<string>();
  const out: ReportRow[] = [];
  const codes = source?.codes ?? view.codes;
  // A tool that could not run files one `unavailable.<tool>` row naming why
  // (no credentials, paused, no repo). The tool page shows it for the tools its
  // chosen source runs, or the page reads "nothing found" with the reason
  // hidden. Only with an explicit source: callers that pass none (the
  // Executive Report's keyword list) want measurements, and listed "Rankings
  // did not run" as a tracked keyword, twice.
  const unavailable = new Set((source?.tools ?? []).map((k) => `unavailable.${k}`));

  for (const [key, value] of Object.entries(report)) {
    if (NON_GROUP_KEYS.has(key) || !Array.isArray(value)) continue;
    for (const row of value as ReportRow[]) {
      if (!row || typeof row !== "object") continue;
      const code = typeof row.code === "string" ? row.code : "";
      if (!code || !(unavailable.has(code) || codes.some((p) => matchesCode(code, p)))) continue;
      // A card can file several reasons under one code and label; key on the
      // reason too, or only the first survives ("needs a competitor" hid "no
      // target keywords" on every keyword page).
      const dedupe = `${code}::${row.what ?? ""}${isNotRun(row) ? `::${row.why ?? ""}` : ""}`;
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
