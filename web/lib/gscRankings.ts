/**
 * Google Search Console as a rankings source — free, first-party, real.
 *
 * The rankings screens (Top Keywords, Organic Rankings, Domain Overview,
 * Position Tracking, SERP Positions) are powered by DataForSEO's
 * `dfs.ranked_keyword` rows, which are paid and, in this repo, never run live.
 * GSC already gives the same shape for the operator's OWN site — the query, its
 * average position, and (better than DFS) real clicks and impressions — for
 * free, and the Google OAuth here is already scoped for it
 * (`webmasters.readonly`).
 *
 * This module is the data layer of that switch: convert GSC query rows into the
 * ranked-keyword row shape the rankings views already render, and resolve which
 * source to use (prefer Google when we have it, fall back to DataForSEO, else
 * nothing). The actual screen wiring and the provenance badge live in G3; this
 * is pure and unit-tested so the switch itself is trustworthy before it is
 * plumbed in.
 *
 * DIFFERENCE FROM DFS, stated honestly: GSC is the operator's own property only
 * (no competitor rankings), carries no search volume, and its position is a
 * 28-day average, not a single live SERP check. So a GSC-sourced row leaves
 * `volume` null and marks `metrics.source = "gsc"` so the UI can say so.
 */

import type { ReportRow } from "./priorities";
import type { GscRow } from "./gscViews";

export type RankingSource = "gsc" | "dataforseo" | "none";

/** A GSC query row in either shape this app produces: the raw API row
 *  (`keys: [query]`) or the flattened dashboard row (`query`, `ctr` as a
 *  percentage). Both are accepted so the converter has one entry point. */
export type GscQueryLike = GscRow & { query?: string };

/** One GSC query row -> a ranked-keyword report row. Position rounds to a whole
 *  rank for display; the exact average is kept in `metrics.position`. */
export function gscQueryToRankingRow(g: GscQueryLike): ReportRow | null {
  const keyword = ((g.keys && g.keys[0]) || g.query || "").toString().trim();
  if (!keyword) return null;
  const pos = typeof g.position === "number" ? g.position : null;
  const rank = pos !== null ? Math.round(pos) : null;
  const clicks = typeof g.clicks === "number" ? g.clicks : null;
  const impressions = typeof g.impressions === "number" ? g.impressions : null;
  const ctr = typeof g.ctr === "number" ? g.ctr : null;
  const what = `"${keyword}"` + (rank !== null ? ` — rank #${rank}` : "");
  const detailParts = [
    rank !== null ? `position ${pos!.toFixed(1)}` : null,
    clicks !== null ? `${clicks} clicks` : null,
    impressions !== null ? `${impressions} impressions` : null,
  ].filter(Boolean);
  return {
    code: "dfs.ranked_keyword",
    what,
    why: "A query this site already ranks for on Google, measured by Search Console.",
    fix: "hold and strengthen the page that earns this query",
    severity: "info",
    detail: detailParts.join(" · "),
    metrics: {
      source: "gsc",
      keyword,
      position: pos,
      rank,
      volume: null,       // GSC does not report search volume
      clicks,
      impressions,
      ctr,
    },
  };
}

/** Convert a page of GSC query rows into ranked-keyword rows, best position
 *  first, dropping rows with no usable keyword. */
export function gscQueriesToRankingRows(rows: GscQueryLike[] | null | undefined): ReportRow[] {
  if (!Array.isArray(rows)) return [];
  return rows
    .map(gscQueryToRankingRow)
    .filter((r): r is ReportRow => r !== null)
    .sort((a, b) => {
      const pa = (a.metrics?.position as number | null) ?? 999;
      const pb = (b.metrics?.position as number | null) ?? 999;
      return pa - pb;
    });
}

/**
 * Decide which rows the rankings views should show, and say which source they
 * came from. Prefers Google (free, real, first-party) when it returned
 * anything, falls back to the DataForSEO rows the scan produced, and reports
 * `none` when neither did — never an empty list dressed as a source.
 */
export function resolveRankingRows(opts: {
  gscRows?: GscQueryLike[] | null;
  dfsRows?: ReportRow[] | null;
}): { rows: ReportRow[]; source: RankingSource } {
  const gsc = gscQueriesToRankingRows(opts.gscRows);
  if (gsc.length > 0) return { rows: gsc, source: "gsc" };
  const dfs = Array.isArray(opts.dfsRows) ? opts.dfsRows : [];
  if (dfs.length > 0) return { rows: dfs, source: "dataforseo" };
  return { rows: [], source: "none" };
}

/** GSC query rows -> the `{keyword, position, volume}` shape the Dashboard's
 *  Top Keywords panel uses (`dashboardMetrics.RankedKeyword`). Volume is null
 *  (GSC has none); best position first. */
export function gscToRankedKeywords(
  rows: GscQueryLike[] | null | undefined,
): Array<{ keyword: string; position: number; volume: number | null }> {
  if (!Array.isArray(rows)) return [];
  return rows
    .map((g) => {
      const keyword = ((g.keys && g.keys[0]) || g.query || "").toString().trim();
      const position = typeof g.position === "number" ? Math.round(g.position) : NaN;
      return { keyword, position, volume: null as number | null };
    })
    .filter((k) => k.keyword && Number.isFinite(k.position))
    .sort((a, b) => a.position - b.position);
}

/** Human label for a source, for the provenance badge (G3). */
export function rankingSourceLabel(source: RankingSource): string {
  return source === "gsc" ? "Google Search Console"
    : source === "dataforseo" ? "DataForSEO"
    : "Not connected";
}
