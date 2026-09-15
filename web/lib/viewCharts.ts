/**
 * Chart data for a tool page, read from that page's rows (the same rows its
 * table lists). Pure, so every page's charts are tested against the row text the
 * scanner writes. Nothing here estimates: a number that is not in a row is not
 * charted.
 */

export type ChartRow = { code?: string; what?: string; detail?: string; severity?: string; metrics?: any; domain?: string; competitor?: string; pages?: unknown };
export type Bar = { label: string; value: number };

const num = (s: string | undefined) => (s === undefined ? null : Number(s.replace(/,/g, "")));

export type KeywordFact = { keyword: string; rank: number | null; volume: number | null; kd: number | null; intent: string | null };

/** What a keyword row states: rank, monthly volume, difficulty, intent. */
export function keywordFact(r: ChartRow): KeywordFact | null {
  const text = `${r.what ?? ""} ${r.detail ?? ""}`;
  const keyword = String(r.what ?? "").match(/"([^"]+)"/)?.[1] ?? null;
  if (!keyword) return null;
  return {
    keyword,
    rank: num(text.match(/rank #(\d+)/)?.[1] ?? text.match(/position (\d+)/)?.[1]),
    volume: num(text.match(/(\d[\d,]*)\/mo/)?.[1]),
    kd: num(text.match(/difficulty (\d+)\/100/)?.[1] ?? text.match(/\bKD (\d+)/)?.[1]),
    intent: text.match(/— (\w+) intent/)?.[1]?.toLowerCase() ?? null,
  };
}

export function keywordCharts(rows: ChartRow[]) {
  const facts = rows.map(keywordFact).filter((f): f is KeywordFact => Boolean(f));
  const ranked = facts.filter((f) => f.rank !== null) as Array<KeywordFact & { rank: number }>;
  const buckets: Array<[string, number, number]> = [["Top 3", 1, 3], ["4-10", 4, 10], ["11-20", 11, 20], ["21-50", 21, 50], ["51-100", 51, 100]];
  const byVolume = new Map<string, number>();
  for (const f of facts) if (f.volume !== null) byVolume.set(f.keyword, Math.max(byVolume.get(f.keyword) ?? 0, f.volume));
  const kds = facts.filter((f) => f.kd !== null).map((f) => f.kd as number);
  const kdBands: Array<[string, number, number]> = [["Easy 0-29", 0, 29], ["Medium 30-49", 30, 49], ["Hard 50-69", 50, 69], ["Very hard 70+", 70, 100]];
  const intents = new Map<string, number>();
  for (const f of facts) if (f.intent) intents.set(f.intent, (intents.get(f.intent) ?? 0) + 1);
  return {
    keywords: new Set(facts.map((f) => f.keyword)).size,
    positions: ranked.length ? buckets.map(([label, lo, hi]) => ({ label, value: ranked.filter((f) => f.rank >= lo && f.rank <= hi).length })) : [],
    topVolume: [...byVolume.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value })),
    difficulty: kds.length ? kdBands.map(([label, lo, hi]) => ({ label, value: kds.filter((k) => k >= lo && k <= hi).length })) : [],
    intent: [...intents.entries()].map(([label, value]) => ({ label: label[0].toUpperCase() + label.slice(1), value })),
    totalVolume: [...byVolume.values()].reduce((a, b) => a + b, 0),
  };
}

/** Compare Domains: one bar per domain for organic keywords and estimated traffic. */
export function compareCharts(rows: ChartRow[]) {
  const domains = rows.filter((r) => r.code === "dfs.compare_domain");
  const keywords: Bar[] = [];
  const traffic: Bar[] = [];
  for (const r of domains) {
    const label = r.domain ?? String(r.what ?? "").split(":")[0];
    const count = r.metrics?.organic?.count ?? num(String(r.what ?? "").match(/(\d[\d,]*) keywords/)?.[1]);
    const etv = r.metrics?.organic?.etv;
    if (typeof count === "number") keywords.push({ label, value: count });
    if (typeof etv === "number") traffic.push({ label, value: Math.round(etv) });
  }
  return { keywords, traffic };
}

/** Backlink Gap: the gap domains' link counts and spam scores, as stated per row. */
export function backlinkGapCharts(rows: ChartRow[]) {
  const gaps = rows.filter((r) => r.code === "dfs.backlink_gap").map((r) => ({
    domain: String(r.what ?? ""),
    links: num(String(r.detail ?? "").match(/(\d[\d,]*) links/)?.[1]),
    spam: num(String(r.detail ?? "").match(/spam (\d+)/)?.[1]),
  }));
  const spam = gaps.filter((g) => g.spam !== null).map((g) => g.spam as number);
  return {
    topLinks: gaps.filter((g) => g.links !== null).sort((a, b) => (b.links as number) - (a.links as number)).slice(0, 8).map((g) => ({ label: g.domain, value: g.links as number })),
    spam: spam.length ? [["Low 0-29", 0, 29], ["Medium 30-59", 30, 59], ["High 60+", 60, 100]].map(([label, lo, hi]) => ({ label: label as string, value: spam.filter((s) => s >= (lo as number) && s <= (hi as number)).length })) : [],
  };
}

/** Any findings page: the severity mix and the checks that fail most. */
export function findingCharts(rows: ChartRow[]) {
  const sev = (s: string) => rows.filter((r) => r.severity === s).length;
  const failing = rows.filter((r) => r.severity === "error" || r.severity === "warn");
  const counts = new Map<string, number>();
  for (const r of failing) {
    const label = String(r.what ?? r.code ?? "").slice(0, 60);
    // A per-page check states how many pages it hit; otherwise each row counts once.
    const pages = num(String(r.detail ?? "").match(/^(\d[\d,]*) page\(s\)/)?.[1]);
    counts.set(label, (counts.get(label) ?? 0) + (pages ?? 1));
  }
  return {
    severity: [
      { label: "Errors", value: sev("error") },
      { label: "Warnings", value: sev("warn") },
      { label: "Passed", value: sev("ok") },
      { label: "Notices", value: sev("info") },
    ],
    topIssues: [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([label, value]) => ({ label, value })),
    graded: sev("error") + sev("warn") + sev("ok"),
  };
}

/** Which chart family a view uses. */
export function chartKind(viewId: string): "keywords" | "compare" | "backlinks" | "backlink-gap" | "performance" | "none" | "findings" {
  if (["organic-rankings", "serp-positions", "keyword-gap", "keyword-overview", "keyword-ideas", "search-intent", "keyword-clusters", "position-tracking"].includes(viewId)) return "keywords";
  if (viewId === "compare-domains") return "compare";
  if (viewId === "backlinks" || viewId === "backlink-audit") return "backlinks";
  if (viewId === "backlink-gap") return "backlink-gap";
  if (viewId === "core-web-vitals") return "performance";
  if (viewId === "domain-overview" || viewId === "backlink-overview") return "none"; // their dashboards draw their own
  return "findings";
}
