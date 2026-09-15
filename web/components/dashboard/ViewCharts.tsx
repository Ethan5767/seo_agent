"use client";

import React from "react";
import { ChartCard, Metric, Gauge, Donut, DistributionBars, Empty } from "@/components/dashboard/Charts";
import { chartKind, keywordCharts, compareCharts, backlinkGapCharts, findingCharts, type ChartRow } from "@/lib/viewCharts";
import { backlinks as backlinkMetrics, lighthouse } from "@/lib/dashboardMetrics";

/**
 * The charts at the top of every tool page, drawn from the page's own rows (and,
 * for Backlinks and Core Web Vitals, the report rows those pages summarise).
 * No rows yet: one card that says which button above fills it.
 */

const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];
const SEVERITY_COLORS: Record<string, string> = { Errors: "var(--bad-fill)", Warnings: "var(--warn-fill)", Passed: "var(--ok-fill)", Notices: "var(--ink-faint)" };

const grid: React.CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: "var(--space-4)", marginBottom: "var(--space-5)" };
const fmt = (n: number | null | undefined) => (typeof n === "number" ? n.toLocaleString() : "—");

export function ViewCharts({ viewId, label, rows, report }: { viewId: string; label: string; rows: ChartRow[]; report?: Record<string, unknown> | null }) {
  const kind = chartKind(viewId);
  if (kind === "none") return null;

  const measured = rows.filter((r) => !String(r.code ?? "").startsWith("unavailable.") && !String(r.code ?? "").endsWith(".not_measured"));
  if (measured.length === 0) {
    return (
      <div style={grid}>
        <ChartCard title={`${label} charts`} span={3}>
          <Empty height={120}>No data on this page yet. Run it with the button above and its charts appear here.</Empty>
        </ChartCard>
      </div>
    );
  }

  if (kind === "keywords") {
    const k = keywordCharts(measured);
    return (
      <div style={grid}>
        <ChartCard title="Summary">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
            <Metric label="Keywords" value={fmt(k.keywords)} />
            <Metric label="Total volume / mo" value={k.totalVolume ? fmt(k.totalVolume) : "—"} sub={k.totalVolume ? undefined : "not reported"} />
            {k.positions.length > 0 && <Metric label="In top 10" value={fmt(k.positions[0].value + k.positions[1].value)} tone="var(--ink)" />}
            {k.difficulty.length > 0 && <Metric label="Easy to rank" value={fmt(k.difficulty[0].value)} tone="var(--ok)" sub="difficulty under 30" />}
          </div>
        </ChartCard>
        {k.positions.length > 0 && (
          <ChartCard title="Position distribution"><DistributionBars items={k.positions} empty="No positions reported." /></ChartCard>
        )}
        {k.topVolume.length > 0 && (
          <ChartCard title="Top search volume" subtitle="monthly searches"><DistributionBars items={k.topVolume} color="var(--chart-1)" empty="No volume reported." /></ChartCard>
        )}
        {k.difficulty.length > 0 && (
          <ChartCard title="Keyword difficulty"><DistributionBars items={k.difficulty} color="var(--chart-1)" empty="No difficulty reported." /></ChartCard>
        )}
        {k.intent.length > 0 && (
          <ChartCard title="Search intent">
            <Donut segments={k.intent.map((s, i) => ({ ...s, color: PALETTE[i % PALETTE.length] }))} center={<b style={{ color: "var(--ink)" }}>{k.intent.reduce((a, b) => a + b.value, 0)}</b>} />
          </ChartCard>
        )}
      </div>
    );
  }

  if (kind === "compare") {
    const c = compareCharts(measured);
    return (
      <div style={grid}>
        <ChartCard title="Organic keywords by domain">
          <DistributionBars items={c.keywords} empty="No keyword counts reported for these domains." />
        </ChartCard>
        <ChartCard title="Estimated traffic by domain" subtitle="monthly, DataForSEO estimate">
          <DistributionBars items={c.traffic} color="var(--chart-1)" empty="No traffic estimate reported for these domains." />
        </ChartCard>
      </div>
    );
  }

  if (kind === "backlinks") {
    const b = backlinkMetrics(report ?? { rows: measured });
    return (
      <div style={grid}>
        <ChartCard title="Link profile">
          {b ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
              <Metric label="Referring domains" value={fmt(b.referringDomains)} />
              <Metric label="Backlinks" value={fmt(b.backlinks)} />
              <Metric label="Broken backlinks" value={fmt(b.broken)} tone="var(--bad)" />
              <Metric label="DataForSEO rank" value={fmt(b.rank)} tone="var(--ink)" />
            </div>
          ) : <Empty>Run Backlinks to count the link profile.</Empty>}
        </ChartCard>
        {b && typeof b.backlinks === "number" && typeof b.broken === "number" && (
          <ChartCard title="Working vs broken">
            <Donut
              segments={[
                { label: "Working", value: Math.max(0, b.backlinks - b.broken), color: "var(--ok-fill)" },
                { label: "Broken", value: b.broken, color: "var(--bad-fill)" },
              ]}
              center={<span><b style={{ color: "var(--ink)" }}>{b.backlinks ? Math.round((b.broken / b.backlinks) * 1000) / 10 : 0}%</b><br />broken</span>}
            />
          </ChartCard>
        )}
      </div>
    );
  }

  if (kind === "backlink-gap") {
    const g = backlinkGapCharts(measured);
    return (
      <div style={grid}>
        <ChartCard title="Gap domains with the most links"><DistributionBars items={g.topLinks} empty="No link counts reported." /></ChartCard>
        <ChartCard title="Spam score of gap domains"><DistributionBars items={g.spam} color="var(--chart-1)" empty="No spam scores reported." /></ChartCard>
      </div>
    );
  }

  if (kind === "performance") {
    const lh = lighthouse(report ?? { rows: measured });
    const f = findingCharts(measured);
    return (
      <div style={grid}>
        <ChartCard title="Lighthouse scores" span={2}>
          {lh.some((c) => c.score !== null) ? (
            <div style={{ display: "flex", justifyContent: "space-around", flexWrap: "wrap", gap: "var(--space-3)" }}>
              {lh.map((c) => <Gauge key={c.label} value={c.score} label={c.label} size={130} />)}
            </div>
          ) : <Empty>No Lighthouse scores in this scan.</Empty>}
        </ChartCard>
        <ChartCard title="Checks">
          <Donut segments={f.severity.map((s) => ({ ...s, color: SEVERITY_COLORS[s.label] }))} center={<b style={{ color: "var(--ink)" }}>{f.graded}</b>} />
        </ChartCard>
      </div>
    );
  }

  const f = findingCharts(measured);
  return (
    <div style={grid}>
      <ChartCard title="Check results">
        <Donut segments={f.severity.map((s) => ({ ...s, color: SEVERITY_COLORS[s.label] }))} center={<span><b style={{ color: "var(--ink)", fontSize: 15 }}>{f.graded ? Math.round((f.severity[2].value / f.graded) * 100) : 0}%</b><br />passed</span>} />
      </ChartCard>
      <ChartCard title="Most frequent issues" subtitle="pages affected, or findings" span={2}>
        <DistributionBars items={f.topIssues} color="var(--chart-1)" empty="Nothing failing on this page." />
      </ChartCard>
    </div>
  );
}
