/**
 * The Backlink Overview page's numbers, from the rows the backlink_overview tool
 * saves: the summary row's link profile, the top referring domains, the top
 * anchors and the monthly history. Pure; nothing is estimated.
 */

type Row = { code?: string; what?: string; detail?: string; metrics?: any; competitor?: string };
export type Count = { label: string; value: number };
export type HistoryPoint = {
  date: string; backlinks: number; referring_domains: number;
  new_referring_domains: number; lost_referring_domains: number; new_backlinks: number; lost_backlinks: number;
};

const n = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function backlinkOverview(rows: Row[]) {
  const own = rows.filter((r) => !r.competitor);
  const summary = own.find((r) => r.code === "dfs.backlinks");
  const m = summary?.metrics ?? {};
  const refDomains = n(m.referring_domains);
  const nofollowDomains = n(m.referring_domains_nofollow);
  const history: HistoryPoint[] = own.find((r) => r.code === "dfs.backlink_history")?.metrics?.points ?? [];
  const last = history[history.length - 1];
  return {
    measured: Boolean(summary || history.length || own.some((r) => r.code === "dfs.referring_domain")),
    // Older saved scans carry only the text row; its two counts are still real.
    backlinks: n(m.backlinks) ?? (summary ? Number(String(summary.what).match(/(\d+)\s+backlinks/)?.[1] ?? NaN) || null : null),
    referringDomains: refDomains ?? (summary ? Number(String(summary.what).match(/(\d+)\s+referring/)?.[1] ?? NaN) || null : null),
    rank: n(m.rank),
    spamScore: n(m.backlinks_spam_score),
    brokenBacklinks: n(m.broken_backlinks),
    referringIps: n(m.referring_ips),
    referringSubnets: n(m.referring_subnets),
    follow: refDomains !== null && nofollowDomains !== null
      ? [{ label: "Follow", value: Math.max(0, refDomains - nofollowDomains) }, { label: "Nofollow", value: nofollowDomains }]
      : [],
    types: (m.types ?? []) as Count[],
    tld: (m.tld ?? []) as Count[],
    countries: (m.countries ?? []) as Count[],
    history,
    newLast: last ? { newDomains: last.new_referring_domains, lostDomains: last.lost_referring_domains, month: last.date } : null,
    referringDomains10: own.filter((r) => r.code === "dfs.referring_domain").map((r) => ({
      domain: String(r.what ?? ""), rank: n(r.metrics?.rank), backlinks: n(r.metrics?.backlinks), spam: n(r.metrics?.spam), firstSeen: r.metrics?.first_seen ?? null,
    })),
    anchors10: own.filter((r) => r.code === "dfs.anchor").map((r) => ({
      anchor: String(r.what ?? "").replace(/^"|"$/g, ""), backlinks: n(r.metrics?.backlinks), domains: n(r.metrics?.referring_domains),
    })),
  };
}
