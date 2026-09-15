/**
 * Numbers for the dashboard charts, read from what was measured and nothing
 * else: the project's saved scans (health over time) and the open report's rows
 * (rankings, backlinks, Lighthouse, AI checks, the crawl).
 *
 * Every reader returns null (or an empty series) when the thing was not
 * measured, so a chart can say "Not measured yet" instead of drawing a shape.
 * Pure: tested with the row formats the scanner saves.
 */

export type Row = { code?: string; what?: string; detail?: string; severity?: string; [k: string]: unknown };
export type Report = Record<string, unknown> | null | undefined;
export type ScanLike = { created_at: string; url?: string | null; score: number | null; counts: Record<string, number> | null; cost?: number | null };

export type Point = { label: string; value: number };

const rowsOf = (report: Report, group?: string): Row[] => {
  if (!report || typeof report !== "object") return [];
  if (group) return Array.isArray((report as any)[group]) ? ((report as any)[group] as Row[]) : [];
  return Object.values(report).flatMap((v) => (Array.isArray(v) ? (v as Row[]) : []));
};
const firstInt = (s: unknown): number | null => {
  const m = String(s ?? "").replace(/,/g, "").match(/\d+/);
  return m ? Number(m[0]) : null;
};
const host = (u: string | null | undefined) =>
  String(u || "").toLowerCase().replace(/^[a-z]+:\/\//, "").replace(/[/?#:].*$/, "").replace(/^www\./, "");

export function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/* ── Site health, over time ─────────────────────────────────────────────── */

/**
 * The project's graded scans of ITS OWN domain, oldest first. A scan of another
 * site filed under the project (github.com, B-126) is left out, and so is a scan
 * with no grade.
 */
export function healthHistory(scans: ScanLike[] | null | undefined, domain: string): Array<ScanLike & { score: number }> {
  const want = host(domain);
  return (scans ?? [])
    .filter((s) => typeof s.score === "number" && (!want || !s.url || host(s.url) === want))
    .map((s) => s as ScanLike & { score: number })
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export function healthTrend(scans: ScanLike[] | null | undefined, domain: string): Point[] {
  return healthHistory(scans, domain).map((s) => ({ label: shortDate(s.created_at), value: s.score }));
}

export function issueHistory(scans: ScanLike[] | null | undefined, domain: string) {
  return healthHistory(scans, domain).map((s) => ({
    label: shortDate(s.created_at),
    errors: Number(s.counts?.error) || 0,
    warnings: Number(s.counts?.warn) || 0,
    passed: Number(s.counts?.ok) || 0,
  }));
}

/* ── The open report ────────────────────────────────────────────────────── */

export function siteAudit(report: Report) {
  const all = rowsOf(report);
  if (!all.length) return null;
  const count = (sev: string) => all.filter((r) => r.severity === sev).length;
  const crawled = rowsOf(report, "site").find((r) => r.code === "site.pages_crawled");
  const score = typeof (report as any)?.score === "number" ? ((report as any).score as number) : null;
  return {
    score,
    errors: count("error"),
    warnings: count("warn"),
    passed: count("ok"),
    notices: count("info"),
    pagesCrawled: crawled ? firstInt(crawled.detail) : null,
  };
}

export type RankedKeyword = { keyword: string; position: number; volume: number | null };

export function rankedKeywords(report: Report): RankedKeyword[] {
  return rowsOf(report)
    .filter((r) => r.code === "dfs.ranked_keyword" && !(r as any).competitor)
    .map((r) => {
      const kw = String(r.what ?? "").match(/^"(.+)"/)?.[1] ?? String(r.what ?? "");
      const pos = Number(String(r.what ?? "").match(/rank #(\d+)/)?.[1] ?? String(r.detail ?? "").match(/position (\d+)/)?.[1]);
      const vol = String(r.detail ?? "").replace(/,/g, "").match(/~?(\d+)\/mo/);
      return { keyword: kw, position: pos, volume: vol ? Number(vol[1]) : null };
    })
    .filter((k) => k.keyword && Number.isFinite(k.position))
    .sort((a, b) => a.position - b.position);
}

export const POSITION_BUCKETS = [
  { label: "Top 3", min: 1, max: 3 },
  { label: "4-10", min: 4, max: 10 },
  { label: "11-20", min: 11, max: 20 },
  { label: "21-50", min: 21, max: 50 },
  { label: "51-100", min: 51, max: 100 },
] as const;

export function positionDistribution(keywords: RankedKeyword[]) {
  return POSITION_BUCKETS.map((b) => ({ label: b.label, value: keywords.filter((k) => k.position >= b.min && k.position <= b.max).length }));
}

export function organic(report: Report) {
  const ov = rowsOf(report).find((r) => r.code === "dfs.domain_overview" && !(r as any).competitor);
  const metrics = (ov?.metrics ?? null) as any;
  const keywordsTotal = metrics?.organic?.count ?? metrics?.count ?? (ov ? firstInt(ov.detail ?? ov.what) : null);
  const trend: Point[] = Array.isArray(metrics?.trend)
    ? metrics.trend
        .map((t: any) => ({ label: String(t.label ?? t.date ?? t.month ?? ""), value: Number(t.value ?? t.count ?? t.keywords ?? 0) }))
        .filter((p: Point) => p.label && Number.isFinite(p.value))
    : [];
  const etv = metrics?.organic?.etv ?? metrics?.etv ?? null;
  return ov ? { keywordsTotal: typeof keywordsTotal === "number" ? keywordsTotal : null, traffic: typeof etv === "number" ? etv : null, trend } : null;
}

export function backlinks(report: Report) {
  const main = rowsOf(report).find((r) => r.code === "dfs.backlinks");
  if (!main) return null;
  const what = String(main.what ?? "").replace(/,/g, "");
  const broken = rowsOf(report).find((r) => r.code === "dfs.broken_backlinks");
  const num = (m: RegExpMatchArray | null) => (m ? Number(m[1]) : null);
  return {
    backlinks: num(what.match(/(\d+)\s+backlinks/)),
    referringDomains: num(what.match(/(\d+)\s+referring/)),
    rank: firstInt(String(main.detail ?? "").match(/rank\s+(\d+)/)?.[0]),
    broken: broken ? firstInt(broken.detail ?? broken.what) : null,
  };
}

const LH = [
  { code: "lh.lighthouse_performance", label: "Performance" },
  { code: "lh.lighthouse_seo", label: "SEO" },
  { code: "lh.lighthouse_accessibility", label: "Accessibility" },
  { code: "lh.lighthouse_best_practices", label: "Best practices" },
];

/** The four Lighthouse category scores; null where the category did not run. */
export function lighthouse(report: Report) {
  const all = rowsOf(report);
  return LH.map((c) => {
    const row = all.find((r) => r.code === c.code);
    const m = String(row?.detail ?? "").match(/(\d+)\s*\/\s*100/);
    return { label: c.label, score: m ? Number(m[1]) : null };
  });
}

/** AI search readiness: how many AEO checks pass, and whether AI engines cite the brand. */
export function aiSearch(report: Report) {
  const aeo = rowsOf(report, "aeo");
  const mention = rowsOf(report).find((r) => r.code === "dfs.llm_mentions");
  if (!aeo.length && !mention) return null;
  return {
    passed: aeo.filter((r) => r.severity === "ok").length,
    failing: aeo.filter((r) => r.severity === "warn" || r.severity === "error").length,
    mentions: mention ? firstInt(mention.detail) : null,
  };
}
