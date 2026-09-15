/**
 * The on-page audit, read from a report: its score, why the score is what it
 * is, the issues ranked by impact, and the pages the crawl read.
 *
 * The score is the scanner's (pipeline/scanner/audit.py, version 3):
 * `ok / (ok + warn + error)` over the audit's groups only. Every graded row
 * weighs the same, so every failing row costs exactly `100 / graded` points.
 * That is the whole breakdown: no weight is invented here, and the category
 * losses add back to the score.
 *
 * Pure. Tested in tests/auditBreakdown.test.mjs.
 */

/** The tools the on-page audit runs. Pinned to `server.ONPAGE_AUDIT_TOOLS`
 *  by tests/test_onpage_audit.py. */
export const ONPAGE_AUDIT_TOOLS = ["seo", "onpage", "tech", "schema", "validate", "internal"] as const;

/** The groups Site Health counts: the audit's tools plus the crawl's `site`
 *  rows. Pinned to `audit.SCORED_GROUPS`. */
export const SCORED_GROUPS = ["seo", "onpage", "tech", "schema", "validate", "internal", "site"] as const;

/** Page depths offered for the audit's crawl. The scanner caps at 25. */
export const AUDIT_CRAWL_OPTIONS = [5, 10, 25] as const;

export const SCORE_VERSION = 3;

export type Report = Record<string, unknown> | null | undefined;

type RawRow = {
  code?: string; what?: string; why?: string; fix?: string; detail?: string;
  severity?: string; pages?: string[];
};

export type CategoryId = "titles" | "content" | "links" | "images" | "schema" | "indexing" | "technical" | "social";

export const CATEGORIES: ReadonlyArray<{ id: CategoryId; label: string }> = [
  { id: "titles", label: "Titles and descriptions" },
  { id: "content", label: "Headings and content" },
  { id: "links", label: "Links" },
  { id: "images", label: "Images" },
  { id: "schema", label: "Structured data" },
  { id: "indexing", label: "Crawling and indexing" },
  { id: "technical", label: "Technical and mobile" },
  { id: "social", label: "Social sharing" },
];

/** First match wins. Anything unmatched is a technical check. */
const RULES: ReadonlyArray<[RegExp, CategoryId]> = [
  [/^health\.(title|desc)|^onpage\.(single_title|single_meta_description|legacy_meta_keywords)|^site\.duplicate_|^dfs\.op\..*(title|description)/, "titles"],
  [/^health\.og_image|^tech\.(open_graph|twitter)/, "social"],
  [/^health\.schema|^schema\.|^tech\.structured_data|^dfs\.op\..*(schema|microdata)/, "schema"],
  [/^health\.img|^onpage\.image|^dfs\.op\..*(image|alt)/, "images"],
  [/^tech\.(internal_links|anchor)|^site\.(broken_internal_link|orphan)|^onpage\.(empty_links|link_volume|external_link_safety)|^dfs\.op\..*link/, "links"],
  [/^health\.(canonical|noindex)|^onpage\.(single_canonical|meta_refresh|hreflang|url_)|^valid\.|^tech\.(xml_sitemap|rendering)|^site\.pages_crawled|^dfs\.op\..*(canonical|noindex|redirect|4xx|5xx|sitemap|robots)/, "indexing"],
  [/^health\.(h1|thin_content)|^onpage\.(heading_order|subheadings|semantic_main|placeholder_text)|^dfs\.op\..*(h1|content|word)/, "content"],
];

export function categoryOf(code: string): CategoryId {
  for (const [re, id] of RULES) if (re.test(code)) return id;
  return "technical";
}

type Graded = RawRow & { group: string; code: string; severity: "ok" | "warn" | "error" };

function auditRows(report: Report): Array<RawRow & { group: string }> {
  if (!report || typeof report !== "object") return [];
  const out: Array<RawRow & { group: string }> = [];
  for (const g of SCORED_GROUPS) {
    const rows = (report as Record<string, unknown>)[g];
    if (Array.isArray(rows)) for (const row of rows as RawRow[]) out.push({ ...row, group: g });
  }
  return out;
}

function graded(report: Report): Graded[] {
  return auditRows(report).filter(
    (r): r is Graded => r.severity === "ok" || r.severity === "warn" || r.severity === "error",
  ).map((r) => ({ ...r, code: String(r.code ?? "") }));
}

export function auditScore(report: Report) {
  const rows = graded(report);
  const ok = rows.filter((r) => r.severity === "ok").length;
  const warn = rows.filter((r) => r.severity === "warn").length;
  const error = rows.filter((r) => r.severity === "error").length;
  const info = auditRows(report).filter((r) => r.severity === "info").length;
  const n = rows.length;
  const exact = n ? (100 * ok) / n : null;
  const saved = typeof (report as any)?.score === "number" ? ((report as any).score as number) : null;
  const version = typeof (report as any)?.score_version === "number" ? ((report as any).score_version as number) : null;
  return {
    score: exact === null ? null : Math.round(exact),
    exact,
    graded: n, ok, warn, error, info,
    /** What one failing check costs, in points. */
    perCheck: n ? 100 / n : null,
    savedScore: saved,
    /** The saved score came from older rules, so the audit score is recomputed. */
    recomputed: version !== null && version < SCORE_VERSION,
  };
}

export function scoreBreakdown(report: Report) {
  const s = auditScore(report);
  const rows = graded(report);
  const categories = CATEGORIES.map((c) => {
    const mine = rows.filter((r) => categoryOf(r.code) === c.id);
    const failing = mine.filter((r) => r.severity !== "ok").length;
    return {
      ...c,
      graded: mine.length,
      ok: mine.length - failing,
      failing,
      errors: mine.filter((r) => r.severity === "error").length,
      warnings: mine.filter((r) => r.severity === "warn").length,
      passRate: mine.length ? Math.round((100 * (mine.length - failing)) / mine.length) : null,
      pointsLost: s.perCheck ? failing * s.perCheck : 0,
    };
  })
    .filter((c) => c.graded > 0)
    .sort((a, b) => b.pointsLost - a.pointsLost || a.label.localeCompare(b.label));
  return { ...s, categories };
}

export type AuditIssue = {
  code: string; what: string; why: string; fix: string; detail: string;
  severity: "warn" | "error"; group: string; category: CategoryId;
  pages: string[]; pageCount: number | null; points: number;
};

export function rankedIssues(report: Report): AuditIssue[] {
  const s = auditScore(report);
  return graded(report)
    .filter((r) => r.severity !== "ok")
    .map((r) => {
      const pages = Array.isArray(r.pages) ? r.pages : [];
      return {
        code: r.code, what: String(r.what || r.code), why: String(r.why ?? ""), fix: String(r.fix ?? ""),
        detail: String(r.detail ?? ""), severity: r.severity as "warn" | "error", group: r.group,
        category: categoryOf(r.code), pages, pageCount: pages.length ? pages.length : null,
        points: s.perCheck ?? 0,
      };
    })
    .sort((a, b) =>
      (a.severity === b.severity ? 0 : a.severity === "error" ? -1 : 1)
      || (b.pageCount ?? 0) - (a.pageCount ?? 0)
      || a.what.localeCompare(b.what));
}

export type CrawledPage = {
  url: string; status: number; title: string | null; has_description: boolean; h1_count: number;
  words: number; links_out: number; links_in: number; errors: number; warnings: number;
  issues: Record<string, "warn" | "error">;
};

/** The crawl's page summary, worst page first; null for a scan saved before it existed. */
export function crawledPages(report: Report): CrawledPage[] | null {
  const pages = (report as any)?.crawl?.pages;
  if (!Array.isArray(pages)) return null;
  return [...(pages as CrawledPage[])].sort((a, b) => b.errors - a.errors || b.warnings - a.warnings || a.url.localeCompare(b.url));
}

export function labelOf(id: CategoryId): string {
  return CATEGORIES.find((c) => c.id === id)?.label ?? id;
}
