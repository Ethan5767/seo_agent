"use client";

import React from "react";

/**
 * The dashboard chart kit: plain SVG, no chart library, theme tokens only.
 *
 * Every chart takes measured numbers. With too little to draw, a chart renders
 * its frame and an "empty" sentence instead of inventing a shape: a flat line
 * or a zero bar would read as a measurement.
 */

export type Point = { label: string; value: number };

const GRID = "var(--chart-grid)";

/** The mark colour for a 0-100 score: the status fills (DESIGN.md §2.4). */
export function fillFor(score: number | null | undefined): string {
  if (typeof score !== "number") return "var(--ink-faint)";
  return score >= 90 ? "var(--ok-fill)" : score >= 50 ? "var(--warn-fill)" : "var(--bad-fill)";
}

/** The text colour for a 0-100 score: the AA status shades. */
export function toneFor(score: number | null | undefined): string {
  if (typeof score !== "number") return "var(--ink-faint)";
  return score >= 90 ? "var(--ok)" : score >= 50 ? "var(--warn)" : "var(--bad)";
}

/* ── Card chrome ────────────────────────────────────────────────────────── */

export function ChartCard({
  title, subtitle, action, children, span = 1,
}: {
  title: string;
  subtitle?: React.ReactNode;
  action?: { label: string; onClick: () => void };
  children: React.ReactNode;
  span?: 1 | 2 | 3;
}) {
  // Flex, not a spanning grid cell: cards in a `.chart-flow` row grow to fill it,
  // so a row never ends in a dead column (see app/tokens.css).
  return (
    <section className={`seo-panel chart-card chart-card--${span}`}>
      <header className="seo-panel__head">
        <div style={{ minWidth: 0 }}>
          <h3 className="seo-panel__title">{title}</h3>
          {subtitle && <div className="seo-panel__sub">{subtitle}</div>}
        </div>
        {action && (
          <button type="button" className="seo-panel__link" onClick={action.onClick}>
            {action.label}
            <span aria-hidden="true">→</span>
          </button>
        )}
      </header>
      <div className="seo-panel__body">{children}</div>
    </section>
  );
}

export function Metric({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: string }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: "var(--text-h3)", fontWeight: 700, letterSpacing: "var(--tracking-heading)", color: tone ?? "var(--ink)", lineHeight: 1.15, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

export function Empty({ children, height = 120 }: { children: React.ReactNode; height?: number }) {
  return (
    <div
      style={{
        height, display: "grid", placeItems: "center", textAlign: "center", padding: "0 var(--space-4)",
        border: "1px dashed var(--border)", borderRadius: "var(--radius-md)", background: "var(--surface-2)",
        fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5,
      }}
    >
      <div>{children}</div>
    </div>
  );
}

/* ── Trend: area + line, gridlines, axis labels, hover readout ─────────── */

export function TrendChart({
  points, height = 180, color = "var(--chart-1)", unit = "", yMax, empty,
}: {
  points: Point[];
  height?: number;
  color?: string;
  unit?: string;
  /** Fixed top of the scale (100 for a percentage); else from the data. */
  yMax?: number;
  empty: React.ReactNode;
}) {
  const [hover, setHover] = React.useState<number | null>(null);
  const id = React.useId().replace(/:/g, "");
  if (points.length < 2) return <Empty height={height}>{points.length === 1 ? <>One measurement so far ({points[0].value}{unit}, {points[0].label}). A trend needs a second one.<br />{empty}</> : empty}</Empty>;

  const W = 600, H = Math.round(height * 1.6), padL = 36, padR = 12, padT = 12, padB = 24;
  const max = yMax ?? (Math.max(...points.map((p) => p.value)) * 1.1 || 1);
  const min = yMax !== undefined ? 0 : Math.min(0, ...points.map((p) => p.value));
  const x = (i: number) => padL + (i * (W - padL - padR)) / (points.length - 1);
  const y = (v: number) => padT + (1 - (v - min) / (max - min || 1)) * (H - padT - padB);
  const line = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${H - padB} L${x(0).toFixed(1)},${H - padB} Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => min + t * (max - min));
  const labelIdx = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
  const h = hover !== null ? points[hover] : null;

  return (
    <div style={{ position: "relative" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }} role="img"
        aria-label={`Trend from ${points[0].value}${unit} to ${points[points.length - 1].value}${unit}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          const i = Math.round(((px - padL) / (W - padL - padR)) * (points.length - 1));
          setHover(Math.max(0, Math.min(points.length - 1, i)));
        }}
      >
        <defs>
          <linearGradient id={`g${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.28" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke={GRID} strokeDasharray={i ? "3 4" : undefined} />
            <text x={padL - 6} y={y(t) + 4} textAnchor="end" fontSize="12" fill="var(--ink-muted)">{Math.round(t)}</text>
          </g>
        ))}
        <path d={area} fill={`url(#g${id})`} />
        <path d={line} fill="none" stroke={color} strokeWidth="2.25" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        {points.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.value)} r={hover === i ? 4.5 : 2.5} fill="var(--surface)" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        ))}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={padT} y2={H - padB} stroke={color} strokeOpacity="0.35" />}
        {labelIdx.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} fontSize="12" fill="var(--ink-muted)">{points[i].label}</text>
        ))}
      </svg>
      {h && (
        <div
          style={{
            position: "absolute", top: 4, left: `${(x(hover!) / W) * 100}%`, transform: "translateX(-50%)", pointerEvents: "none",
            background: "var(--ink)", color: "var(--surface)", fontSize: 11.5, fontWeight: 600, padding: "3px 8px", borderRadius: 6, whiteSpace: "nowrap",
          }}
        >
          {h.label}: {h.value}{unit}
        </div>
      )}
    </div>
  );
}

/* ── Stacked bars: one bar per scan ────────────────────────────────────── */

export function StackedBars({
  bars, keys, height = 150, empty,
}: {
  bars: Array<{ label: string } & Record<string, number | string>>;
  keys: Array<{ key: string; label: string; color: string }>;
  height?: number;
  empty: React.ReactNode;
}) {
  if (bars.length === 0) return <Empty height={height}>{empty}</Empty>;
  const totals = bars.map((b) => keys.reduce((s, k) => s + (Number(b[k.key]) || 0), 0));
  const max = Math.max(1, ...totals);
  // Few scans stretched a bar to full width, reading as a crude slab. Cap the
  // width and centre them, print each bar's total above it, and label every bar
  // below rather than only the ends. A dense history (>8) keeps the thin bars.
  const few = bars.length <= 8;
  const colStyle: React.CSSProperties = few
    ? { flex: "0 1 48px", maxWidth: 48, minWidth: 20 }
    : { flex: "1 1 0", minWidth: 4 };
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: few ? "space-around" : "space-between", gap: few ? 14 : 5, height }}>
        {bars.map((b, i) => (
          <div key={i} title={`${b.label}: ${keys.map((k) => `${k.label} ${b[k.key]}`).join(", ")}`}
            style={{ ...colStyle, height: "100%", display: "flex", flexDirection: "column", justifyContent: "flex-end", alignItems: "center" }}>
            {few && totals[i] > 0 && (
              <span style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-body)", marginBottom: 4, fontVariantNumeric: "tabular-nums" }}>{totals[i]}</span>
            )}
            <div style={{ width: "100%", flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end" }}>
              {keys.slice().reverse().map((k) => {
                const v = Number(b[k.key]) || 0;
                return v ? <div key={k.key} style={{ height: `${(v / max) * 100}%`, background: k.color, borderRadius: 2, marginTop: 1 }} /> : null;
              })}
            </div>
          </div>
        ))}
      </div>
      {few ? (
        <div style={{ display: "flex", justifyContent: "space-around", gap: 14, fontSize: 12, color: "var(--ink-muted)", marginTop: 6 }}>
          {bars.map((b, i) => (
            <span key={i} style={{ flex: "0 1 48px", maxWidth: 48, minWidth: 20, textAlign: "center", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{b.label}</span>
          ))}
        </div>
      ) : (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
          <span>{bars[0].label}</span>
          {bars.length > 1 && <span>{bars[bars.length - 1].label}</span>}
        </div>
      )}
      <Legend items={keys} />
    </div>
  );
}

export function Legend({ items }: { items: Array<{ label: string; color: string }> }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-3)", marginTop: "var(--space-2)" }}>
      {items.map((k) => (
        <span key={k.label} style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11.5, color: "var(--ink-muted)" }}>
          <span style={{ width: 9, height: 9, borderRadius: 2, background: k.color }} /> {k.label}
        </span>
      ))}
    </div>
  );
}

/* ── Gauge: semicircle, coloured by threshold ──────────────────────────── */

export function Gauge({ value, label, size = 150, caption }: { value: number | null; label?: string; size?: number; caption?: string }) {
  const r = 52, cx = 60, cy = 60, len = Math.PI * r;
  const v = typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  const color = fillFor(v);
  return (
    <div style={{ width: size, textAlign: "center" }}>
      <svg viewBox="0 0 120 70" width={size} height={size * (70 / 120)} role="img" aria-label={`${label ?? "Score"}: ${v === null ? "not measured" : `${v} of 100`}`}>
        <path d={`M8,60 A52,52 0 0 1 112,60`} fill="none" stroke="var(--surface-3)" strokeWidth="11" strokeLinecap="round" />
        {v !== null && (
          <path d={`M8,60 A52,52 0 0 1 112,60`} fill="none" stroke={color} strokeWidth="11" strokeLinecap="round" strokeDasharray={`${(v / 100) * len} ${len}`} />
        )}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize="22" fontWeight="800" fill={v === null ? "var(--ink-muted)" : "var(--ink)"}>{v === null ? "—" : `${v}`}</text>
        {v !== null && <text x={cx} y={cy + 8} textAnchor="middle" fontSize="12" fill="var(--ink-muted)">of 100</text>}
      </svg>
      {label && <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-body)", marginTop: -2 }}>{label}</div>}
      {caption && <div style={{ fontSize: 11, color: "var(--ink-muted)" }}>{caption}</div>}
    </div>
  );
}

/* ── Donut ─────────────────────────────────────────────────────────────── */

export function Donut({ segments, size = 120, center }: { segments: Array<{ label: string; value: number; color: string }>; size?: number; center?: React.ReactNode }) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const r = 42, c = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)", flexWrap: "wrap" }}>
      <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
        <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label={segments.map((s) => `${s.label} ${s.value}`).join(", ")}>
          <circle cx="50" cy="50" r={r} fill="none" stroke="var(--surface-3)" strokeWidth="12" />
          {total > 0 && segments.map((s) => {
            const dash = (s.value / total) * c;
            const el = <circle key={s.label} cx="50" cy="50" r={r} fill="none" stroke={s.color} strokeWidth="12" strokeDasharray={`${dash} ${c - dash}`} strokeDashoffset={-offset} transform="rotate(-90 50 50)" />;
            offset += dash;
            return el;
          })}
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center", fontSize: 12, color: "var(--ink-muted)" }}>{center}</div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {segments.map((s) => (
          <span key={s.label} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "var(--ink-body)" }}>
            <span style={{ width: 9, height: 9, borderRadius: 2, background: s.color }} /> {s.label}
            <b style={{ fontVariantNumeric: "tabular-nums" }}>{s.value}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ── Horizontal distribution bars ──────────────────────────────────────── */

export function DistributionBars({ items, color = "var(--chart-1)", empty }: { items: Point[]; color?: string; empty: React.ReactNode }) {
  const max = Math.max(0, ...items.map((i) => i.value));
  if (max === 0) return <Empty height={130}>{empty}</Empty>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {items.map((it) => (
        <div key={it.label} style={{ display: "grid", gridTemplateColumns: "minmax(56px, 38%) 1fr auto", alignItems: "center", gap: 8, fontSize: 12.5 }}>
          <span title={it.label} style={{ color: "var(--ink-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.label}</span>
          <span style={{ height: 10, background: "var(--surface-3)", borderRadius: 5, overflow: "hidden" }}>
            <span style={{ display: "block", height: "100%", width: `${(it.value / max) * 100}%`, background: color, borderRadius: 5 }} />
          </span>
          <b style={{ textAlign: "right", color: "var(--ink)", fontVariantNumeric: "tabular-nums" }}>{it.value}</b>
        </div>
      ))}
    </div>
  );
}

/* ── Segmented bar (crawled pages by status) ───────────────────────────── */

export function SegmentBar({ segments }: { segments: Array<{ label: string; value: number; color: string }> }) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  return (
    <div>
      <div style={{ display: "flex", height: 14, borderRadius: 4, overflow: "hidden", background: "var(--surface-3)" }}>
        {total > 0 && segments.map((s) => s.value > 0 && (
          <div key={s.label} title={`${s.label}: ${s.value}`} style={{ width: `${(s.value / total) * 100}%`, background: s.color }} />
        ))}
      </div>
      <Legend items={segments.map((s) => ({ label: `${s.label} ${s.value}`, color: s.color }))} />
    </div>
  );
}
