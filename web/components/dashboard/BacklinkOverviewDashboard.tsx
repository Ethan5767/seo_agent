"use client";

import React from "react";
import { ChartCard, Metric, TrendChart, StackedBars, Donut, DistributionBars, Empty } from "@/components/dashboard/Charts";
import { backlinkOverview } from "@/lib/backlinkOverview";

/**
 * Backlink Overview: the link profile as DataForSEO reports it. Headline counts,
 * referring-domain growth by month, new vs lost, follow vs nofollow, link types,
 * TLDs, countries, and the top referring domains and anchors.
 */

const fmt = (v: number | null | undefined) => (typeof v === "number" ? v.toLocaleString() : "—");
const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];
const grid: React.CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "stretch", gap: "var(--space-4)", marginBottom: "var(--space-5)" };
const th: React.CSSProperties = { padding: "4px 0", fontWeight: 600, color: "var(--ink-muted)" };
const td: React.CSSProperties = { padding: "6px 0", borderTop: "1px solid var(--border)", fontVariantNumeric: "tabular-nums" };

export function BacklinkOverviewDashboard({ rows }: { rows: any[] }) {
  const o = backlinkOverview(rows);

  if (!o.measured) {
    return (
      <div style={grid}>
        <ChartCard title="Backlink Overview" span={3}>
          <Empty height={160}>No backlink data yet. Press Look up Backlink Overview above.</Empty>
        </ChartCard>
      </div>
    );
  }

  const hist = o.history;
  return (
    <div style={grid}>
      <ChartCard title="Link profile" span={3}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", gap: "var(--space-4)" }}>
          <Metric label="Referring domains" value={fmt(o.referringDomains)} sub={o.newLast ? `+${o.newLast.newDomains} / −${o.newLast.lostDomains} in ${o.newLast.month}` : undefined} />
          <Metric label="Backlinks" value={fmt(o.backlinks)} />
          <Metric label="DataForSEO rank" value={fmt(o.rank)} tone="var(--ink)" />
          <Metric label="Spam score" value={fmt(o.spamScore)} tone={typeof o.spamScore === "number" && o.spamScore >= 60 ? "var(--bad)" : "var(--ink)"} sub="0 to 100, lower is better" />
          <Metric label="Broken backlinks" value={fmt(o.brokenBacklinks)} tone="var(--bad)" />
          <Metric label="Referring IPs / subnets" value={`${fmt(o.referringIps)} / ${fmt(o.referringSubnets)}`} tone="var(--ink)" />
        </div>
      </ChartCard>

      <ChartCard title="Referring domains over time" subtitle={hist.length ? `${hist[0].date} to ${hist[hist.length - 1].date}` : undefined} span={2}>
        <TrendChart points={hist.map((p) => ({ label: p.date, value: p.referring_domains }))} height={150} empty="No monthly history reported." />
      </ChartCard>

      <ChartCard title="Follow vs nofollow" subtitle="referring domains">
        {o.follow.length ? (
          <Donut segments={o.follow.map((s, i) => ({ ...s, color: i ? "var(--chart-1-soft)" : "var(--chart-1)" }))} center={<b style={{ color: "var(--ink)" }}>{fmt(o.referringDomains)}</b>} />
        ) : <Empty>Not reported for this scan. Run Look up again.</Empty>}
      </ChartCard>

      <ChartCard title="New vs lost referring domains" subtitle="per month" span={2}>
        <StackedBars
          bars={hist.map((p) => ({ label: p.date, gained: p.new_referring_domains, lost: p.lost_referring_domains }))}
          keys={[{ key: "gained", label: "New", color: "var(--ok-fill)" }, { key: "lost", label: "Lost", color: "var(--bad-fill)" }]}
          height={120}
          empty="No monthly history reported."
        />
      </ChartCard>

      <ChartCard title="Backlinks over time">
        <TrendChart points={hist.map((p) => ({ label: p.date, value: p.backlinks }))} height={150} color="var(--chart-1)" empty="No monthly history reported." />
      </ChartCard>

      <ChartCard title="Link types">
        {o.types.length ? <Donut segments={o.types.slice(0, 6).map((t, i) => ({ ...t, color: PALETTE[i] }))} /> : <Empty>Not reported for this scan.</Empty>}
      </ChartCard>
      <ChartCard title="Top TLDs" subtitle="links by top-level domain">
        <DistributionBars items={o.tld} empty="Not reported for this scan." />
      </ChartCard>
      <ChartCard title="Top countries" subtitle="links by referring site country">
        <DistributionBars items={o.countries} color="var(--chart-1)" empty="Not reported for this scan." />
      </ChartCard>

      <ChartCard title="Top referring domains" span={2}>
        {o.referringDomains10.length ? (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead><tr style={{ textAlign: "left" }}><th style={th}>Domain</th><th style={{ ...th, textAlign: "right" }}>Rank</th><th style={{ ...th, textAlign: "right" }}>Backlinks</th><th style={{ ...th, textAlign: "right" }}>Spam</th><th style={{ ...th, textAlign: "right" }}>First seen</th></tr></thead>
              <tbody>
                {o.referringDomains10.map((d) => (
                  <tr key={d.domain}>
                    <td style={{ ...td, color: "var(--ink-body)", wordBreak: "break-all" }}>{d.domain}</td>
                    <td style={{ ...td, textAlign: "right" }}>{fmt(d.rank)}</td>
                    <td style={{ ...td, textAlign: "right" }}>{fmt(d.backlinks)}</td>
                    <td style={{ ...td, textAlign: "right", color: typeof d.spam === "number" && d.spam >= 60 ? "var(--bad)" : undefined }}>{fmt(d.spam)}</td>
                    <td style={{ ...td, textAlign: "right", color: "var(--ink-muted)" }}>{d.firstSeen ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty>No referring domains reported.</Empty>}
      </ChartCard>

      <ChartCard title="Top anchors">
        {o.anchors10.length ? (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr style={{ textAlign: "left" }}><th style={th}>Anchor</th><th style={{ ...th, textAlign: "right" }}>Domains</th><th style={{ ...th, textAlign: "right" }}>Links</th></tr></thead>
            <tbody>
              {o.anchors10.map((a, i) => (
                <tr key={`${a.anchor}-${i}`}>
                  <td style={{ ...td, maxWidth: 0, width: "60%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.anchor}>{a.anchor}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmt(a.domains)}</td>
                  <td style={{ ...td, textAlign: "right" }}>{fmt(a.backlinks)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty>No anchors reported.</Empty>}
      </ChartCard>
    </div>
  );
}
