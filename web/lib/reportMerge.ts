/**
 * Merge a scoped scan's report over the report already open.
 *
 * `{ ...base, ...next }` replaced whole groups. That is right for a group only
 * one tool fills, and wrong for `site`, which two fill: the free multi-page
 * crawl (`site.*`, run on every web scan) and paid Site Health (`dfs.op.*`,
 * `unavailable.site`). A Backlinks test returned `site = [site.pages_crawled]`
 * and erased the Site Health rows that Crawl Issues, Technical Checks and
 * On-Page Checks show by default, then saved the result as the latest scan
 * (review, 2026-09-14).
 *
 * Rule: a row is replaced only by a run of the check that produces it.
 */

type Row = { code?: unknown };
type Report = Record<string, unknown>;

const SITE_HEALTH = (code: string) => code.startsWith("dfs.op.") || code === "unavailable.site";

export function mergeScanReport(base: Report, next: Report, ranTools: readonly string[]): Report {
  const merged: Report = { ...base, ...next };
  const baseSite = Array.isArray(base.site) ? (base.site as Row[]) : [];
  const nextSite = Array.isArray(next.site) ? (next.site as Row[]) : null;
  if (nextSite) {
    const code = (r: Row) => (typeof r?.code === "string" ? r.code : "");
    const siteHealthRan = ranTools.includes("site");
    const crawlRan = nextSite.some((r) => code(r).startsWith("site."));
    const kept = baseSite.filter((r) => {
      const c = code(r);
      if (SITE_HEALTH(c)) return !siteHealthRan;
      if (c.startsWith("site.")) return !crawlRan;
      return false;
    });
    merged.site = [...nextSite, ...kept];
  }
  return merged;
}

/**
 * A client-side merge combines results from different scanner invocations. It
 * has no complete, trustworthy denominator, so it must never invent a health
 * score. Only a complete backend report may carry one.
 */
export function invalidateMergedScore(report: Report): Report {
  const stale: Report = { ...report, score: null, score_version: null, score_breakdown: null };
  delete stale.counts;
  delete stale.counts_all;
  delete stale.graded;
  return stale;
}
