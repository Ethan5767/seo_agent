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
  score = 41,
  size = 34,
  strokeWidth = 3.5,
  color = "#10b981",
  bgColor = "#edf2f7",
}: {
  score?: number;
  size?: number;
  strokeWidth?: number;
  color?: string;
  bgColor?: string;
}) {
  const r = (size - strokeWidth) / 2;
  const circ = 2 * Math.PI * r;
  const strokeDash = Math.min(circ, Math.max(0, (score / 100) * circ));
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
      <span style={{ position: "absolute", fontSize, fontWeight: 700, color: "#1e293b", letterSpacing: "-0.02em" }}>{score}</span>
    </div>
  );
}

export function SiteHealthDonut({ score = 82, size = 110 }: { score?: number; size?: number }) {
  const stroke = size <= 80 ? 7 : 11;
  const radius = (size - stroke) / 2;
  const circ = 2 * Math.PI * radius;
  const offset = circ - (Math.max(0, Math.min(100, score)) / 100) * circ;
  const color = score >= 80 ? "#10b981" : score >= 50 ? "#f59e0b" : "#ef4444";
  const valFontSize = size <= 80 ? 17 : 24;
  const labelFontSize = size <= 80 ? 8.5 : 10;

  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#f1f3f7" strokeWidth={stroke} />
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
        <span style={{ fontSize: valFontSize, fontWeight: 800, color: "#0f172a", lineHeight: 1 }}>
          {score}%
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
      <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", background: "#f1f3f7", gap: 1 }}>
        <div style={{ width: `${pOk}%`, background: "#10b981" }} title={`Passing: ${ok}`} />
        <div style={{ width: `${pErr}%`, background: "#ef4444" }} title={`Errors: ${error}`} />
        <div style={{ width: `${pWarn}%`, background: "#f59e0b" }} title={`Warnings: ${warn}`} />
        <div style={{ width: `${pInfo}%`, background: "#0ea5e9" }} title={`Notices: ${info}`} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-muted)", marginTop: 8, flexWrap: "wrap", gap: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#10b981" }} /> Healthy ({ok})
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#ef4444" }} /> Errors ({error})
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#f59e0b" }} /> Warnings ({warn})
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#0ea5e9" }} /> Notices ({info})
        </span>
      </div>
    </div>
  );
}
