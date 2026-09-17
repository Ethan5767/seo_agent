"use client";

import React from "react";
import { ChartCard, Empty } from "@/components/dashboard/Charts";
import { TableSkeleton } from "@/components/dashboard/DashboardSkeletons";
import { keywordRankHistory, type KeywordSeries } from "@/lib/db";

/**
 * Real per-keyword rank tracking: position over time, one row per keyword.
 *
 * The `keywords` table already stores a position per keyword per scan; this reads
 * it back (`keywordRankHistory`) and draws each keyword's movement. It is the
 * difference between "you are #8 today" and "you were #14, now #8" — the thing
 * "rank tracking" is supposed to mean and the old snapshot never did.
 *
 * Rank sparklines are drawn INVERTED: position #1 sits at the top, because up
 * should mean better. A keyword with one reading shows the number and says a
 * trend needs a second scan, rather than a flat line that implies stability.
 */
export function KeywordTrend({
  clientId,
  title = "Position tracking over time",
  subtitle = "each keyword's Google position across scans (up = better)",
}: {
  clientId: string | null | undefined;
  title?: string;
  subtitle?: string;
}) {
  const [series, setSeries] = React.useState<KeywordSeries[] | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState("");

  React.useEffect(() => {
    if (!clientId) { setSeries([]); return; }
    let live = true;
    setLoading(true); setErr("");
    keywordRankHistory(clientId)
      .then((s) => { if (live) setSeries(s); })
      .catch((e) => { if (live) setErr(e?.message || "Could not load rank history."); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [clientId]);

  if (!clientId) return null;

  const withTrend = (series ?? []).filter((s) => s.points.filter((p) => p.position !== null).length >= 2);
  const oneReading = (series ?? []).length > 0 && withTrend.length === 0;

  return (
    <ChartCard title={title} subtitle={subtitle}>
      {loading ? (
        <TableSkeleton columns={6} rows={6} />
      ) : err ? (
        <Empty height={120}>{err}</Empty>
      ) : (series ?? []).length === 0 ? (
        <Empty height={120}>
          No ranked keywords stored yet. Positions are captured on every scan; run a scan with rankings to start the history.
        </Empty>
      ) : oneReading ? (
        <Empty height={120}>
          One scan on record, so there is no movement to show yet. Positions are saved each scan — run a second scan and the trend appears here.
        </Empty>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                {["Keyword", "Volume", "Movement", "First", "Latest", "Change"].map((h, i) => (
                  <th key={h} style={{ textAlign: i >= 3 ? "right" : "left", padding: "8px 10px",
                                       borderBottom: "1px solid var(--border)", color: "var(--ink-muted)",
                                       fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {withTrend.map((s) => (
                <TrendRow key={s.keyword} s={s} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </ChartCard>
  );
}

function TrendRow({ s }: { s: KeywordSeries }) {
  // Improvement is a smaller position, so a negative delta is good.
  const improved = s.delta !== null && s.delta < 0;
  const worse = s.delta !== null && s.delta > 0;
  const deltaColor = improved ? "var(--ok)" : worse ? "var(--bad)" : "var(--ink-muted)";
  const deltaText = s.delta === null || s.delta === 0 ? "—"
    : improved ? `▲ ${Math.abs(s.delta)}` : `▼ ${s.delta}`;
  return (
    <tr>
      <td style={cell}>{s.keyword}</td>
      <td style={{ ...cell, color: "var(--ink-muted)" }}>{s.volume ? `${s.volume.toLocaleString()}/mo` : "—"}</td>
      <td style={cell}><RankSpark points={s.points} /></td>
      <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{s.first !== null ? `#${s.first}` : "—"}</td>
      <td style={{ ...cell, textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>{s.latest !== null ? `#${s.latest}` : "—"}</td>
      <td style={{ ...cell, textAlign: "right", fontWeight: 700, color: deltaColor }}>{deltaText}</td>
    </tr>
  );
}

/** A small inverted rank sparkline: #1 at the top, higher numbers lower down. */
function RankSpark({ points }: { points: KeywordSeries["points"] }) {
  const measured = points.filter((p) => typeof p.position === "number") as Array<{ at: string; position: number }>;
  if (measured.length < 2) return <span style={{ color: "var(--ink-muted)", fontSize: 12 }}>one reading</span>;
  const W = 120, H = 28, pad = 3;
  const positions = measured.map((p) => p.position);
  const lo = Math.min(...positions), hi = Math.max(...positions);
  const span = hi - lo || 1;
  const x = (i: number) => pad + (i * (W - 2 * pad)) / (measured.length - 1);
  // Invert: the best (smallest) position sits at the top (small y).
  const y = (pos: number) => pad + ((pos - lo) / span) * (H - 2 * pad);
  const line = measured.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.position).toFixed(1)}`).join(" ");
  const last = measured[measured.length - 1];
  const improved = last.position <= measured[0].position;
  const color = improved ? "var(--ok)" : "var(--bad)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img"
         aria-label={`positions ${positions.map((p) => `#${p}`).join(", ")}`}>
      <path d={line} fill="none" stroke={color} strokeWidth="1.75" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      {measured.map((p, i) => (
        <circle key={i} cx={x(i)} cy={y(p.position)} r={i === measured.length - 1 ? 3 : 1.8}
                fill="var(--surface)" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      ))}
    </svg>
  );
}

const cell: React.CSSProperties = {
  padding: "8px 10px", borderBottom: "1px solid var(--border)", verticalAlign: "middle", color: "var(--ink-body)",
};
