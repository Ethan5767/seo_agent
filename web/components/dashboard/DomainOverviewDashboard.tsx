"use client";

import React from "react";
import type { ReportRow } from "@/lib/priorities";
import { Panel, StatStrip } from "@/components/dashboard/Panel";
import { TrendChart, DistributionBars } from "@/components/dashboard/Charts";

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
  const moved = m.movement && (m.movement.new + m.movement.up + m.movement.down + m.movement.lost > 0) ? m.movement : null;
  const dist = m.distribution && m.distribution.some((d) => d.value > 0) ? m.distribution : null;

  if (!overview && keywords.length === 0) {
    return (
      <div className="audit-empty">
        <p>No overview yet. Look up this domain above to see its organic keywords, traffic value, positions and trend.</p>
      </div>
    );
  }

  return (
    <div className="tool-sections">
      <StatStrip
        label="Headline figures"
        stats={[
          { label: "Organic keywords", value: fmt(m.keywords), sub: "ranking on Google" },
          { label: "Est. traffic value", value: m.etv != null ? `$${fmt(m.etv)}` : "—", sub: "per month, DataForSEO estimate" },
          { label: "Keywords at #1", value: fmt(m.pos_1), sub: "top position" },
          { label: "Paid keywords", value: fmt(m.paid?.keywords), sub: m.paid?.etv ? `$${fmt(m.paid.etv)}/mo in ads` : "no paid presence" },
        ]}
      />

      <div className="tool-grid">
        {m.trend && m.trend.length >= 2 ? (
          <Panel className="span-8" title="Traffic Value Trend" subtitle={`Estimated monthly organic traffic value, ${m.trend[0].month} to ${m.trend[m.trend.length - 1].month}`}>
            <TrendChart points={m.trend.map((p) => ({ label: p.month, value: p.etv }))} unit="" height={150} empty="" />
          </Panel>
        ) : null}
        {dist && (
          <Panel className={m.trend && m.trend.length >= 2 ? "span-4" : "span-6"} title="Position Distribution" subtitle={`${fmt(m.keywords)} keywords by Google position`}>
            <DistributionBars items={dist} empty="No positions reported." />
          </Panel>
        )}
        {moved && (
          <Panel className={m.trend && m.trend.length >= 2 ? "span-4" : "span-6"} title="Keyword Movement" subtitle="Since DataForSEO last measured this domain">
            <ul className="movement">
              <MoveCell glyph="+" label="New" value={moved.new} />
              <MoveCell glyph="▲" label="Moved up" value={moved.up} />
              <MoveCell glyph="▼" label="Moved down" value={moved.down} />
              <MoveCell glyph="−" label="Lost" value={moved.lost} />
            </ul>
          </Panel>
        )}
        {keywords.length > 0 && (
          <Panel className={moved ? "span-8" : "span-12"} title="Top Keywords" subtitle={`Best ${Math.min(25, keywords.length)} of ${keywords.length}, by position`}>
            <div className="table-scroll">
              <table className="data-table data-table--rows">
                <thead>
                  <tr>
                    <th scope="col">Keyword</th>
                    <th scope="col" className="num">Position</th>
                    <th scope="col" className="num">Volume / mo</th>
                  </tr>
                </thead>
                <tbody>
                  {keywords.slice(0, 25).map((k, i) => (
                    <tr key={i}>
                      <td>{cleanKw(k.what)}</td>
                      <td className="num"><span className="rank-pill">{rankOf(k.detail)}</span></td>
                      <td className="num muted">{volOf(k.detail)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}

/** One movement figure: a neutral number with a glyph and a word, never a colour alone. */
function MoveCell({ glyph, label, value }: { glyph: string; label: string; value: number }) {
  return (
    <li className="movement__cell">
      <span className="movement__glyph" aria-hidden="true">{glyph}</span>
      <span className="movement__value">{value.toLocaleString()}</span>
      <span className="movement__label">{label}</span>
    </li>
  );
}

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
  return m ? Number(m[1].replace(/,/g, "")).toLocaleString() : "—";
}
