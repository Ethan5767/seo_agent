"use client";

import React from "react";
import type { ReportRow } from "@/lib/priorities";

/**
 * Domain Overview, rendered as a dashboard rather than a single audit row.
 *
 * Reads the structured `metrics` the scanner now attaches to the
 * `dfs.domain_overview` row (position distribution, keyword movement, monthly
 * trend, paid figures) and the `dfs.ranked_keyword` rows for the top-terms
 * table. Every block degrades on absence: no trend → no chart, no keywords → no
 * table, so a thin scan still renders cleanly.
 */

interface DistBucket { label: string; value: number }
interface TrendPoint { month: string; keywords: number; etv: number }
interface Movement { new: number; up: number; down: number; lost: number }
interface DomainMetrics {
  keywords?: number;
  etv?: number;
  pos_1?: number;
  distribution?: DistBucket[];
  movement?: Movement;
  paid?: { keywords: number; etv: number };
  trend?: TrendPoint[];
}

export function DomainOverviewDashboard({ rows }: { rows: ReportRow[] }) {
  const overview = rows.find((r) => r.code === "dfs.domain_overview");
  // A scan run before the enriched parser has no `metrics`, only the text
  // row. Recover the three headline figures from that text so a cached scan
  // still shows its cards; the richer panels simply wait for a re-scan.
  const m = withTextFallback((overview?.metrics as DomainMetrics | undefined) ?? {}, overview);
  const keywords = rows.filter((r) => r.code === "dfs.ranked_keyword");

  const cards = [
    { label: "Keywords", value: fmt(m.keywords), sub: "ranking on Google" },
    { label: "Est. traffic value", value: m.etv != null ? `$${fmt(m.etv)}` : "—", sub: "per month" },
    { label: "Top positions", value: fmt(m.pos_1), sub: "keywords at #1" },
    { label: "Paid keywords", value: fmt(m.paid?.keywords), sub: m.paid?.etv ? `$${fmt(m.paid.etv)}/mo ads` : "no paid presence" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
      {/* Headline figures. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "var(--space-3)" }}>
        {cards.map((c) => (
          <div key={c.label} style={card}>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)", fontWeight: 600 }}>{c.label}</div>
            <div style={{ fontSize: "var(--text-2xl)", fontWeight: 750, color: "var(--ink)", lineHeight: 1.1, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{c.value}</div>
            <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-faint)", marginTop: 2 }}>{c.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(20rem, 1fr))", gap: "var(--space-4)" }}>
        {/* Position distribution. */}
        {m.distribution && m.distribution.some((d) => d.value > 0) && (
          <section style={panel}>
            <h2 style={panelTitle}>Position Distribution</h2>
            <DistributionBars buckets={m.distribution} />
          </section>
        )}

        {/* Keyword movement since last measure. */}
        {m.movement && (m.movement.new + m.movement.up + m.movement.down + m.movement.lost > 0) && (
          <section style={panel}>
            <h2 style={panelTitle}>Keyword Movement</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
              <MoveChip label="New" value={m.movement.new} tone="var(--ok)" />
              <MoveChip label="Up" value={m.movement.up} tone="var(--info)" />
              <MoveChip label="Down" value={m.movement.down} tone="var(--warn)" />
              <MoveChip label="Lost" value={m.movement.lost} tone="var(--bad)" />
            </div>
          </section>
        )}
      </div>

      {/* Organic trend, when the historical endpoint returned one. */}
      {m.trend && m.trend.length >= 2 && (
        <section style={panel}>
          <h2 style={panelTitle}>Estimated Traffic Value Trend</h2>
          <TrendChart points={m.trend} />
        </section>
      )}

      {/* Top ranked terms. */}
      {keywords.length > 0 && (
        <section style={panel}>
          <h2 style={panelTitle}>Top Keywords <span style={{ color: "var(--ink-faint)", fontWeight: 500 }}>({keywords.length})</span></h2>
          <div style={{ overflowX: "auto", marginTop: "var(--space-3)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "var(--text-sm)" }}>
              <thead>
                <tr>
                  <th style={th}>Keyword</th>
                  <th style={{ ...th, textAlign: "right", width: "7rem" }}>Position</th>
                  <th style={{ ...th, textAlign: "right", width: "9rem" }}>Volume</th>
                </tr>
              </thead>
              <tbody>
                {keywords.slice(0, 25).map((k, i) => (
                  <tr key={i}>
                    <td style={td}>{cleanKw(k.what)}</td>
                    <td style={{ ...td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{rankOf(k.detail)}</td>
                    <td style={{ ...td, textAlign: "right", color: "var(--ink-muted)", fontVariantNumeric: "tabular-nums" }}>{volOf(k.detail)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!overview && (
        <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)" }}>
          No overview yet. Run Domain Overview above to populate this.
        </p>
      )}
    </div>
  );
}

/** Horizontal bars, each bucket relative to the largest, so the shape reads at a glance. */
function DistributionBars({ buckets }: { buckets: DistBucket[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
      {buckets.map((b) => (
        <div key={b.label} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <span style={{ width: "3.5rem", fontSize: "var(--text-xs)", color: "var(--ink-muted)", fontWeight: 600, textAlign: "right", flexShrink: 0 }}>{b.label}</span>
          <div style={{ flex: 1, height: 10, background: "var(--surface-3)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
            <div style={{ width: `${(b.value / max) * 100}%`, height: "100%", background: "var(--accent)", borderRadius: "var(--radius-full)", transition: "width var(--dur) var(--ease)" }} />
          </div>
          <span style={{ width: "2.5rem", fontSize: "var(--text-sm)", color: "var(--ink)", fontWeight: 600, textAlign: "right", flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>{b.value}</span>
        </div>
      ))}
    </div>
  );
}

function MoveChip({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div style={{ textAlign: "center", padding: "var(--space-3) var(--space-2)", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)" }}>
      <div style={{ fontSize: "var(--text-xl)", fontWeight: 700, color: tone, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

/** A small inline SVG line of estimated traffic value over time. */
function TrendChart({ points }: { points: TrendPoint[] }) {
  const W = 640, H = 120, pad = 6;
  const vals = points.map((p) => p.etv);
  const max = Math.max(1, ...vals), min = Math.min(...vals);
  const span = max - min || 1;
  const x = (i: number) => pad + (i * (W - pad * 2)) / Math.max(1, points.length - 1);
  const y = (v: number) => H - pad - ((v - min) / span) * (H - pad * 2);
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(p.etv).toFixed(1)}`).join(" ");
  const area = `${line} L ${x(points.length - 1).toFixed(1)} ${H - pad} L ${x(0).toFixed(1)} ${H - pad} Z`;
  return (
    <div style={{ marginTop: "var(--space-3)" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="Estimated traffic value over time" preserveAspectRatio="none">
        <path d={area} fill="var(--accent-tint)" />
        <path d={line} fill="none" stroke="var(--accent)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: "var(--text-xs)", color: "var(--ink-faint)" }}>
        <span>{points[0].month}</span>
        <span>${fmt(max)}/mo peak</span>
        <span>{points[points.length - 1].month}</span>
      </div>
    </div>
  );
}

const card: React.CSSProperties = {
  padding: "var(--space-4)",
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
};

const panel: React.CSSProperties = {
  padding: "var(--space-4) var(--space-5)",
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
};

const panelTitle: React.CSSProperties = {
  fontSize: "var(--text-base)",
  fontWeight: 700,
  color: "var(--ink)",
  margin: 0,
};

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--text-xs)",
  fontWeight: 600,
  color: "var(--ink-muted)",
  borderBottom: "1px solid var(--border)",
};

const td: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--surface-3)",
  color: "var(--ink)",
};

/** Fill the three headline figures from the row's text when a pre-enrichment
 *  scan left no metrics object, so a cached Domain Overview still reads. */
function withTextFallback(m: DomainMetrics, row: ReportRow | undefined): DomainMetrics {
  if (m.keywords != null || !row) return m;
  const kw = (row.what || "").match(/Ranks for ([\d,]+) keywords/i);
  const etv = (row.fix || "").match(/\$([\d,]+)\/mo/i);
  const pos1 = (row.fix || "").match(/([\d,]+) keyword\(s\) at position #1/i);
  const num = (s: string | undefined) => (s ? Number(s.replace(/,/g, "")) : undefined);
  return {
    ...m,
    keywords: num(kw?.[1]),
    etv: num(etv?.[1]),
    pos_1: num(pos1?.[1]),
  };
}

function fmt(n: number | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

// The ranked-keyword row is text: what = '"keyword" — rank #3', detail =
// 'position 3, ~5,500/mo searches'. Pull the parts back out for the columns.
function cleanKw(what: string | undefined): string {
  if (!what) return "—";
  const m = what.match(/^"([^"]+)"/);
  return m ? m[1] : what.replace(/\s*—.*$/, "");
}
function rankOf(detail: string | undefined): string {
  const m = (detail || "").match(/position\s+(\d+)/i);
  return m ? `#${m[1]}` : "—";
}
function volOf(detail: string | undefined): string {
  const m = (detail || "").match(/~([\d,]+)\s*\/mo/i);
  return m ? `${m[1]}/mo` : "—";
}
