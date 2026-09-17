"use client";

/**
 * Small presentational primitives shared between ReaiDashboard and the
 * screens extracted out of it.
 *
 * They lived in ReaiDashboard.tsx and are used by both it and MeasureScreen.
 * Keeping them here is what lets MeasureScreen import them without a cycle
 * back into the 13,000-line file it was carved out of. A move: the markup is
 * unchanged.
 */

import React from "react";

export function IconTerminal({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  );
}

export function MiniRadialGauge({
  score,
  size = 34,
  strokeWidth = 3.5,
  color = "var(--ok)",
  bgColor = "var(--border)",
}: {
  score?: number | null;
  size?: number;
  strokeWidth?: number;
  color?: string;
  bgColor?: string;
}) {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const measured = typeof score === "number" && Number.isFinite(score);
  const strokeDash = measured ? Math.min(circ, Math.max(0, (score! / 100) * circ)) : 0;
  const fontSize = size >= 60 ? 15 : size >= 44 ? 12 : 9.5;

  return (
    <div style={{ position: "relative", width: size, height: size, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} stroke={bgColor} strokeWidth={strokeWidth} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={strokeWidth}
          fill="none"
          strokeDasharray={`${strokeDash} ${circ}`}
          strokeLinecap="round"
          style={{ transition: "stroke-dasharray 0.4s ease" }}
        />
      </svg>
      <span style={{ position: "absolute", fontSize, fontWeight: 700, color: "var(--ink-body)", letterSpacing: "-0.02em" }}>{measured ? score : "—"}</span>
    </div>
  );
}

export function SiteHealthDonut({ score, size = 110 }: { score?: number | null; size?: number }) {
  const stroke = size <= 80 ? 7 : 11;
  const radius = (size - stroke) / 2;
  const circ = 2 * Math.PI * radius;
  const measured = typeof score === "number" && Number.isFinite(score);
  const offset = measured ? circ - (Math.max(0, Math.min(100, score!)) / 100) * circ : circ;
  const color = !measured ? "var(--border-strong)" : score! >= 80 ? "var(--ok)" : score! >= 50 ? "var(--warn)" : "var(--bad)";
  const valFontSize = size <= 80 ? 17 : 24;
  const labelFontSize = size <= 80 ? 8.5 : 10;

  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: "stroke-dashoffset 0.6s ease" }}
        />
      </svg>
      <div style={{
        position: "absolute", inset: 0, display: "flex", flexDirection: "column",
        alignItems: "center", justifyContent: "center", pointerEvents: "none",
      }}>
        <span style={{ fontSize: valFontSize, fontWeight: 800, color: "var(--ink)", lineHeight: 1 }}>
          {measured ? `${score}%` : "—"}
        </span>
        <span style={{ fontSize: labelFontSize, color: "var(--ink-muted)", marginTop: 2, fontWeight: 600 }}>
          Health
        </span>
      </div>
    </div>
  );
}

export function CrawledPagesBar({
  ok = 52,
  warn = 21,
  error = 7,
  info = 14,
}: { ok?: number; warn?: number; error?: number; info?: number }) {
  const total = ok + warn + error + info || 100;
  const pOk = (ok / total) * 100;
  const pWarn = (warn / total) * 100;
  const pErr = (error / total) * 100;
  const pInfo = (info / total) * 100;

  return (
    <div style={{ width: "100%", marginTop: 8 }}>
      <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", background: "var(--surface-3)", gap: 1 }}>
        <div style={{ width: `${pOk}%`, background: "var(--ok)" }} title={`Passing: ${ok}`} />
        <div style={{ width: `${pErr}%`, background: "var(--bad)" }} title={`Errors: ${error}`} />
        <div style={{ width: `${pWarn}%`, background: "var(--warn)" }} title={`Warnings: ${warn}`} />
        <div style={{ width: `${pInfo}%`, background: "var(--info)" }} title={`Notices: ${info}`} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-muted)", marginTop: 8, flexWrap: "wrap", gap: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--ok)" }} /> Healthy ({ok})
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--bad)" }} /> Errors ({error})
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--warn)" }} /> Warnings ({warn})
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--info)" }} /> Notices ({info})
        </span>
      </div>
    </div>
  );
}
