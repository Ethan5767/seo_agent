"use client";

import React, { useState } from "react";
import { formatMetricValue } from "@/lib/monitor/types";

export interface DonutSlice {
  label: string;
  value: number;
  color?: string;
}

const PALETTE = ["#0284c7", "#10b981", "#8b5cf6", "#f59e0b", "#ec4899", "#64748b"];

interface MonitorDonutChartProps {
  slices: DonutSlice[];
  metric: string;
  size?: number;
  strokeWidth?: number;
}

export function MonitorDonutChart({
  slices = [],
  metric,
  size = 140,
  strokeWidth = 18,
}: MonitorDonutChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const total = slices.reduce((acc, s) => acc + s.value, 0);

  if (slices.length === 0 || total === 0) {
    return (
      <div
        style={{
          height: size + 40,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--ink-muted)",
          fontSize: 13,
          background: "#f8fafc",
          borderRadius: 8,
          border: "1px dashed #e2e8f0",
        }}
      >
        No distribution data available
      </div>
    );
  }

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;

  let accumulatedPct = 0;

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-around", flexWrap: "wrap", gap: 16, padding: "8px 0" }}>
      {/* SVG Donut Circle */}
      <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {slices.map((slice, i) => {
            const pct = slice.value / total;
            const strokeDasharray = `${pct * circumference} ${circumference}`;
            const strokeDashoffset = -accumulatedPct * circumference;
            accumulatedPct += pct;
            const color = slice.color || PALETTE[i % PALETTE.length];
            const isHovered = hoverIdx === i;

            return (
              <circle
                key={slice.label + i}
                cx={center}
                cy={center}
                r={radius}
                fill="transparent"
                stroke={color}
                strokeWidth={isHovered ? strokeWidth + 3 : strokeWidth}
                strokeDasharray={strokeDasharray}
                strokeDashoffset={strokeDashoffset}
                transform={`rotate(-90 ${center} ${center})`}
                onMouseEnter={() => setHoverIdx(i)}
                onMouseLeave={() => setHoverIdx(null)}
                style={{
                  transition: "stroke-width 0.2s ease, opacity 0.2s ease",
                  opacity: hoverIdx !== null && !isHovered ? 0.45 : 1,
                  cursor: "pointer",
                }}
              />
            );
          })}
        </svg>

        {/* Center Label */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <div style={{ fontSize: 16, fontWeight: 800, color: "#0f172a" }}>
            {hoverIdx !== null ? formatMetricValue(slices[hoverIdx].value, metric) : formatMetricValue(total, metric)}
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            {hoverIdx !== null ? slices[hoverIdx].label : "Total"}
          </div>
        </div>
      </div>

      {/* Legend Column */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1, minWidth: 140 }}>
        {slices.map((slice, i) => {
          const color = slice.color || PALETTE[i % PALETTE.length];
          const pct = ((slice.value / total) * 100).toFixed(1);
          const isHovered = hoverIdx === i;

          return (
            <div
              key={slice.label + i}
              onMouseEnter={() => setHoverIdx(i)}
              onMouseLeave={() => setHoverIdx(null)}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "3px 6px",
                borderRadius: 4,
                background: isHovered ? "#f1f5f9" : "transparent",
                cursor: "pointer",
                fontSize: 12,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 7, overflow: "hidden" }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: color, flexShrink: 0 }} />
                <span style={{ fontWeight: 600, color: "#334155", textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
                  {slice.label}
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontWeight: 700, color: "#0f172a" }}>{formatMetricValue(slice.value, metric)}</span>
                <span style={{ color: "var(--ink-muted)", width: 40, textAlign: "right" }}>{pct}%</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
