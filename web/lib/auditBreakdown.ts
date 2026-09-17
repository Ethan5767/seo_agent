/**
 * The on-page audit, read from a report: its score, why the score is what it
 * is, the issues ranked by impact, and the pages the crawl read.
 *
 * The scanner owns the weighted formula, version, and category breakdown.
 * This module only displays those fields; it must never create a client-side
 * score from merged or partial report rows.
 *
 * Pure. Tested in tests/auditBreakdown.test.mjs.
 */

/** The tools the on-page audit runs. Pinned to `server.ONPAGE_AUDIT_TOOLS`
 *  by tests/test_onpage_audit.py. */
export const ONPAGE_AUDIT_TOOLS = ["seo", "site", "onpage", "tech", "headers", "monitor", "schema", "validate",
  "internal", "aeo", "perf", "lh_perf", "lh_seo", "lh_a11y", "lh_bp", "lh_pages", "render", "media", "security", "url"] as const;

/** The groups Site Health counts: the audit's tools plus the crawl's `site`
 *  rows. Pinned to `audit.SCORED_GROUPS`. */
export const SCORED_GROUPS = ["seo", "onpage", "tech", "headers", "schema", "validate",
  "internal", "site"] as const;

/**
 * Page depths offered for the audit's crawl, capped by MAX_CRAWL_PAGES in
 * pipeline/scanner/server.py. It stopped at 25 while every page was fetched
 * twice; the crawl now carries each page's body, so one read per page, and a
 * real site fits in one audit (operator, 2026-09-16: "one website is at least
 * 100 pages"). The walk is serial, so deeper is slower, not more expensive.
 */
export const AUDIT_CRAWL_OPTIONS = [5, 10, 25, 50, 100] as const;

export type Report = Record<string, unknown> | null | undefined;

type RawRow = {
  code?: string; what?: string; why?: string; fix?: string; detail?: string;
  severity?: string; pages?: string[]; score_weight?: number; score_category?: CategoryId;
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
  const raw = (report && typeof report === "object" ? report : {}) as Record<string, any>;
  const counts = raw.counts && typeof raw.counts === "object" ? raw.counts : {};
  const score = typeof raw.score === "number" ? raw.score : null;
  const weighted = raw.score_breakdown && typeof raw.score_breakdown === "object" ? raw.score_breakdown : null;
  return {
    score, weighted,
    graded: typeof raw.graded === "number" ? raw.graded : 0,
    ok: Number(counts.ok || 0), warn: Number(counts.warn || 0), error: Number(counts.error || 0), info: Number(counts.info || 0),
    version: typeof raw.score_version === "number" ? raw.score_version : null,
  };
}

export function scoreBreakdown(report: Report) {
  const s = auditScore(report);
  const categories = Array.isArray((s.weighted as any)?.categories)
    ? [...(s.weighted as any).categories].map((c: any) => ({
        id: c.id as CategoryId, label: String(c.label), graded: Number(c.graded || 0),
        ok: Number(c.ok || 0), errors: Number(c.error || 0), warnings: Number(c.warn || 0),
        failing: Number(c.warn || 0) + Number(c.error || 0),
        pointsLost: Number(c.lost_weight || 0),
        passRate: typeof c.pass_rate === "number" ? c.pass_rate : null,
      })).sort((a, b) => b.pointsLost - a.pointsLost || a.label.localeCompare(b.label))
    : [];
  return { ...s, categories };
}

export type AuditIssue = {
  code: string; what: string; why: string; fix: string; detail: string;
  severity: "warn" | "error"; group: string;
  pages: string[]; pageCount: number | null; points: number; category: CategoryId | null;
  // The remediation playbook the scanner attaches to failing findings. All
  // optional: absent on findings with no written playbook, so the renderer
  // falls back to why/fix.
  plain?: string; impact?: string; effort?: string;
  steps?: string[]; snippet?: string; verify?: string;
  timeline?: string; optional?: boolean;
};

export function rankedIssues(report: Report): AuditIssue[] {
  return graded(report)
    .filter((r) => r.severity !== "ok")
    .map((r) => {
      const pages = Array.isArray(r.pages) ? r.pages : [];
      // The scanner attaches the playbook as extra keys not in RawRow's type.
      const rr = r as Record<string, unknown>;
      return {
        code: r.code, what: String(r.what || r.code), why: String(r.why ?? ""), fix: String(r.fix ?? ""),
        detail: String(r.detail ?? ""), severity: r.severity as "warn" | "error", group: r.group,
        pages, pageCount: pages.length ? pages.length : null,
        points: typeof rr.score_weight === "number" ? rr.score_weight : 0,
        category: typeof rr.score_category === "string" ? rr.score_category as CategoryId : null,
        // Carry the playbook through when the scanner attached it.
        plain: rr.plain ? String(rr.plain) : undefined,
        impact: rr.impact ? String(rr.impact) : undefined,
        effort: rr.effort ? String(rr.effort) : undefined,
        steps: Array.isArray(rr.steps) ? rr.steps.map(String) : undefined,
        snippet: rr.snippet ? String(rr.snippet) : undefined,
        verify: rr.verify ? String(rr.verify) : undefined,
        timeline: rr.timeline ? String(rr.timeline) : undefined,
        optional: rr.optional === true,
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
