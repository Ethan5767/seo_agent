"use client";

import React from "react";
import {
  ChartCard, Metric, TrendChart, StackedBars, Gauge, Donut, DistributionBars, SegmentBar, Empty, toneFor,
} from "@/components/dashboard/Charts";
import {
  healthTrend, issueHistory, siteAudit, rankedKeywords, positionDistribution, organic, backlinks, lighthouse, aiSearch,
  type Report, type ScanLike,
} from "@/lib/dashboardMetrics";

/**
 * The SEO dashboard: one monitoring card per area, each drawn from the project's
 * saved scans and the open report. A card with nothing measured says which tool
 * fills it; nothing is estimated to fill the space.
 */
export type DashboardTarget = "site-audit" | "domain-overview" | "organic-rankings" | "backlinks" | "core-web-vitals" | "ai";

const COLORS = {
  error: "var(--bad)",
  warn: "var(--warn)",
  ok: "var(--ok)",
  info: "var(--ink-faint)",
};

const fmt = (n: number | null | undefined) => (typeof n === "number" ? n.toLocaleString() : "—");

export function SeoDashboard({
  report, scans, domain, onOpen,
}: {
  report: Report;
  scans: ScanLike[] | null | undefined;
  domain: string;
  onOpen: (target: DashboardTarget) => void;
}) {
  const audit = siteAudit(report);
  const trend = healthTrend(scans, domain);
  const issues = issueHistory(scans, domain);
  const keywords = rankedKeywords(report);
  const dist = positionDistribution(keywords);
  const org = organic(report);
  const links = backlinks(report);
  const lh = lighthouse(report);
  const ai = aiSearch(report);
  const top3 = dist[0].value;
  const top10 = dist[0].value + dist[1].value;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: "var(--space-4)", marginBottom: "var(--space-5)" }}>
      {/* Site Audit: the latest health, its issues, the crawl. */}
      <ChartCard title="Site Audit" subtitle={audit ? "Latest scan" : "Not scanned yet"} action={{ label: "View full report", onClick: () => onOpen("site-audit") }}>
        {audit ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-3)", flexWrap: "wrap" }}>
              <Gauge value={audit.score} label="Site Health" caption={audit.score === null ? "no graded checks" : undefined} />
              <div style={{ display: "grid", gap: "var(--space-3)" }}>
                <Metric label="Errors" value={fmt(audit.errors)} tone={COLORS.error} />
                <Metric label="Warnings" value={fmt(audit.warnings)} tone={COLORS.warn} />
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, marginBottom: 4 }}>
                Checks {audit.pagesCrawled !== null ? `· ${audit.pagesCrawled} pages crawled` : ""}
              </div>
              <SegmentBar segments={[
                { label: "Passed", value: audit.passed, color: COLORS.ok },
                { label: "Warnings", value: audit.warnings, color: COLORS.warn },
                { label: "Errors", value: audit.errors, color: COLORS.error },
                { label: "Notices", value: audit.notices, color: COLORS.info },
              ]} />
            </div>
          </div>
        ) : (
          <Empty height={180}>Run Site Audit to measure this site&apos;s health.</Empty>
        )}
      </ChartCard>

      {/* Health over time, from every graded scan of this domain. */}
      <ChartCard title="Site Health Trend" subtitle={trend.length ? `${trend.length} scan${trend.length === 1 ? "" : "s"} of ${domain}` : undefined} span={2}>
        <TrendChart points={trend} yMax={100} unit="%" color="var(--accent)" height={150} empty="Each Site Audit adds a point here." />
        <div style={{ marginTop: "var(--space-4)" }}>
          <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, marginBottom: 4 }}>Issues per scan</div>
          <StackedBars
            bars={issues}
            height={90}
            keys={[
              { key: "errors", label: "Errors", color: COLORS.error },
              { key: "warnings", label: "Warnings", color: COLORS.warn },
            ]}
            empty="No graded scans yet."
          />
        </div>
      </ChartCard>

      {/* Organic search: DataForSEO figures and the ranked keywords' spread. */}
      <ChartCard title="Organic Search" subtitle="DataForSEO" span={2} action={{ label: "View Domain Overview", onClick: () => onOpen("domain-overview") }}>
        {org || keywords.length ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "var(--space-5)" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
                <Metric label="Organic keywords" value={fmt(org?.keywordsTotal ?? keywords.length)} />
                <Metric label="Est. traffic / mo" value={fmt(org?.traffic)} sub={org?.traffic === null ? "not reported" : undefined} />
                <Metric label="Top 3" value={fmt(top3)} tone="var(--ink)" />
                <Metric label="Top 10" value={fmt(top10)} tone="var(--ink)" />
              </div>
              {org?.trend && org.trend.length > 1 && (
                <TrendChart points={org.trend} height={90} empty="" />
              )}
            </div>
            <div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600, marginBottom: 8 }}>Positions ({keywords.length} tracked keywords)</div>
              <DistributionBars items={dist} empty="No ranked keywords in the last scan." />
            </div>
          </div>
        ) : (
          <Empty height={180}>Run Domain Overview to see organic keywords, traffic and positions.</Empty>
        )}
      </ChartCard>

      {/* Top keywords, best position first. */}
      <ChartCard title="Top Keywords" subtitle={keywords.length ? `${Math.min(8, keywords.length)} of ${keywords.length}` : undefined} action={keywords.length ? { label: "View all", onClick: () => onOpen("organic-rankings") } : undefined}>
        {keywords.length ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ color: "var(--ink-muted)", textAlign: "left" }}>
                <th style={{ padding: "4px 0", fontWeight: 600 }}>Keyword</th>
                <th style={{ padding: "4px 0", fontWeight: 600, textAlign: "right" }}>Pos.</th>
                <th style={{ padding: "4px 0", fontWeight: 600, textAlign: "right" }}>Volume</th>
              </tr>
            </thead>
            <tbody>
              {keywords.slice(0, 8).map((k) => (
                <tr key={k.keyword} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "6px 8px 6px 0", color: "var(--accent)", maxWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", width: "60%" }} title={k.keyword}>{k.keyword}</td>
                  <td style={{ padding: "6px 0", textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>{k.position}</td>
                  <td style={{ padding: "6px 0", textAlign: "right", fontVariantNumeric: "tabular-nums", color: "var(--ink-muted)" }}>{fmt(k.volume)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty height={180}>Run Organic Rankings to list the keywords this site ranks for.</Empty>
        )}
      </ChartCard>

      {/* Backlinks. */}
      <ChartCard title="Backlinks" subtitle="DataForSEO" action={{ label: "View Backlinks", onClick: () => onOpen("backlinks") }}>
        {links ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
              <Metric label="Referring domains" value={fmt(links.referringDomains)} />
              <Metric label="Backlinks" value={fmt(links.backlinks)} />
            </div>
            {typeof links.backlinks === "number" && typeof links.broken === "number" ? (
              <Donut
                size={104}
                center={<span><b style={{ color: "var(--ink)", fontSize: 14 }}>{links.broken}</b><br />broken</span>}
                segments={[
                  { label: "Working", value: Math.max(0, links.backlinks - links.broken), color: COLORS.ok },
                  { label: "Broken", value: links.broken, color: COLORS.error },
                ]}
              />
            ) : null}
            {links.rank !== null && <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>DataForSEO rank {fmt(links.rank)}</div>}
          </div>
        ) : (
          <Empty height={180}>Run Backlinks to count referring domains and broken links.</Empty>
        )}
      </ChartCard>

      {/* Lighthouse. */}
      <ChartCard title="Page Performance" subtitle="Google Lighthouse, homepage" span={2} action={{ label: "View Core Web Vitals", onClick: () => onOpen("core-web-vitals") }}>
        {lh.some((c) => c.score !== null) ? (
          <div style={{ display: "flex", justifyContent: "space-around", flexWrap: "wrap", gap: "var(--space-3)" }}>
            {lh.map((c) => <Gauge key={c.label} value={c.score} label={c.label} size={130} />)}
          </div>
        ) : (
          <Empty height={140}>Run Core Web Vitals to score performance, SEO, accessibility and best practices.</Empty>
        )}
      </ChartCard>

      {/* AI search. */}
      <ChartCard title="AI Search" subtitle="Answer readiness and AI citations" action={{ label: "View AI Search", onClick: () => onOpen("ai") }}>
        {ai ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            <Donut
              size={104}
              center={<span><b style={{ color: "var(--ink)", fontSize: 14 }}>{ai.passed}</b><br />passed</span>}
              segments={[
                { label: "Passed", value: ai.passed, color: COLORS.ok },
                { label: "Needs work", value: ai.failing, color: COLORS.warn },
              ]}
            />
            <Metric label="AI engine mentions" value={fmt(ai.mentions)} tone={ai.mentions ? toneFor(90) : "var(--ink)"} sub={ai.mentions === null ? "not checked" : undefined} />
          </div>
        ) : (
          <Empty height={180}>Run the AI Search checks to see answer readiness and citations.</Empty>
        )}
      </ChartCard>
    </div>
  );
}
