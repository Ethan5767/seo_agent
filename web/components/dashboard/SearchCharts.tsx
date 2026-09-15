"use client";

import React from "react";
import type { ReportRow } from "@/lib/priorities";

/**
 * Charts for any search view, above its data table.
 *
 * Search tools return keyword-shaped rows — a term, a SERP rank, a monthly
 * volume — carried as text ("\"roof repair\" — rank #3", detail "position 3,
 * ~5,500/mo searches"). This reads those two figures back out and, when enough
 * rows carry them, draws a position distribution and a top-by-volume bar chart.
 * When a view's rows carry neither (e.g. a referring-domains list), it renders
 * nothing and the table stands alone — no invented chart.
 */

interface Point { label: string; rank?: number; vol?: number }

function parsePoints(rows: ReportRow[]): Point[] {
  return rows.map((r) => {
    const label = kwOf(r.what);
    const rankM = (r.detail || r.what || "").match(/(?:position|rank)\D*(\d+)/i);
    const volM = (r.detail || "").match(/~?([\d,]+)\s*\/\s*mo/i);
    return {
      label,
      rank: rankM ? Number(rankM[1]) : undefined,
      vol: volM ? Number(volM[1].replace(/,/g, "")) : undefined,
    };
  });
}

export function SearchCharts({ rows }: { rows: ReportRow[] }) {
  const points = parsePoints(rows);
  const ranked = points.filter((p) => p.rank != null);
  const withVol = points.filter((p) => p.vol != null && p.vol > 0);

  // Position distribution: keywords bucketed by where they rank.
  const buckets = [
    { label: "#1", test: (r: number) => r === 1 },
    { label: "2-3", test: (r: number) => r >= 2 && r <= 3 },
    { label: "4-10", test: (r: number) => r >= 4 && r <= 10 },
    { label: "11-20", test: (r: number) => r >= 11 && r <= 20 },
    { label: "21-50", test: (r: number) => r >= 21 && r <= 50 },
    { label: "51+", test: (r: number) => r >= 51 },
  ].map((b) => ({ label: b.label, value: ranked.filter((p) => b.test(p.rank!)).length }));

  const topByVol = [...withVol].sort((a, b) => (b.vol! - a.vol!)).slice(0, 8);

  // Nothing to chart — let the table speak for itself.
  if (ranked.length < 2 && topByVol.length < 2) return null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(20rem, 1fr))", gap: "var(--space-4)", marginBottom: "var(--space-4)" }}>
      {ranked.length >= 2 && buckets.some((b) => b.value > 0) && (
        <section style={panel}>
          <h2 style={panelTitle}>Position Distribution <span style={{ color: "var(--ink-faint)", fontWeight: 500 }}>({ranked.length})</span></h2>
          <Bars data={buckets.map((b) => ({ label: b.label, value: b.value }))} format={(v) => String(v)} />
        </section>
      )}
      {topByVol.length >= 2 && (
        <section style={panel}>
          <h2 style={panelTitle}>Top Keywords by Search Volume</h2>
          <Bars data={topByVol.map((p) => ({ label: p.label, value: p.vol! }))} format={(v) => `${v.toLocaleString()}/mo`} wideLabel />
        </section>
      )}
    </div>
  );
}

/** Horizontal bars, each relative to the largest, tokens throughout. */
function Bars({ data, format, wideLabel }: { data: { label: string; value: number }[]; format: (v: number) => string; wideLabel?: boolean }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
      {data.map((d, i) => (
        <div key={`${d.label}-${i}`} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
          <span title={d.label} style={{ width: wideLabel ? "9rem" : "3.5rem", fontSize: "var(--text-xs)", color: "var(--ink-muted)", fontWeight: 600, textAlign: wideLabel ? "left" : "right", flexShrink: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{d.label}</span>
          <div style={{ flex: 1, height: 10, background: "var(--surface-3)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
            <div style={{ width: `${(d.value / max) * 100}%`, height: "100%", background: "var(--accent)", borderRadius: "var(--radius-full)", transition: "width var(--dur) var(--ease)" }} />
          </div>
          <span style={{ width: "5rem", fontSize: "var(--text-sm)", color: "var(--ink)", fontWeight: 600, textAlign: "right", flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>{format(d.value)}</span>
        </div>
      ))}
    </div>
  );
}

function kwOf(what: string | undefined): string {
  if (!what) return "—";
  const m = what.match(/^"([^"]+)"/);
  return m ? m[1] : what.replace(/\s*—.*$/, "");
}

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
