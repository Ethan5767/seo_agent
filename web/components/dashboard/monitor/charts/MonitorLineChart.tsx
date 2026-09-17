"use client";

import React, { useState, useRef, useId } from "react";
import { formatMetricValue, formatDelta } from "@/lib/monitor/types";

export interface LineSeriesPoint {
  date: string;
  value: number;
  secondaryValue?: number;
  compareValue?: number;
}

interface MonitorLineChartProps {
  data: LineSeriesPoint[];
  metric: string;
  secondaryMetric?: string;
  metricLabel?: string;
  secondaryLabel?: string;
  hasComparison?: boolean;
  comparisonLabel?: string;
  height?: number;
}

export function MonitorLineChart({
  data = [],
  metric,
  secondaryMetric,
  metricLabel,
  secondaryLabel,
  hasComparison = false,
  comparisonLabel = "Previous period",
  height = 240,
}: MonitorLineChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const gradId = useId().replace(/:/g, "");

  if (!data || data.length === 0) {
    return (
      <div
        style={{
          height,
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
        No time-series data available for this range
      </div>
    );
  }

  const primaryValues = data.map((d) => d.value);
  const secondaryValues = secondaryMetric ? data.map((d) => d.secondaryValue ?? 0) : [];
  const compValues = hasComparison ? data.map((d) => d.compareValue ?? 0) : [];

  const maxVal = Math.max(...primaryValues, ...(hasComparison ? compValues : [0]), 1);
  const minVal = Math.min(0, ...primaryValues);
  const rangeVal = maxVal - minVal || 1;

  const maxSec = secondaryMetric ? Math.max(...secondaryValues, 1) : 1;
  const minSec = 0;
  const rangeSec = maxSec - minSec || 1;

  // Layout boundaries
  const padLeft = 46;
  const padRight = secondaryMetric ? 46 : 16;
  const padTop = 18;
  const padBottom = 28;
  const svgWidth = 800;
  const chartWidth = svgWidth - padLeft - padRight;
  const chartHeight = height - padTop - padBottom;

  // Calculate coordinates
  const pts = data.map((d, i) => {
    const x = padLeft + (i / Math.max(1, data.length - 1)) * chartWidth;
    const y = padTop + chartHeight - ((d.value - minVal) / rangeVal) * chartHeight;
    const ySec = secondaryMetric && d.secondaryValue !== undefined
      ? padTop + chartHeight - ((d.secondaryValue - minSec) / rangeSec) * chartHeight
      : undefined;
    const yComp = hasComparison && d.compareValue !== undefined
      ? padTop + chartHeight - ((d.compareValue - minVal) / rangeVal) * chartHeight
      : undefined;
    return { x, y, ySec, yComp, data: d };
  });

  const linePath = pts.reduce((acc, p, idx) => `${acc} ${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`, "");
  const areaPath = `${linePath} L ${pts[pts.length - 1].x.toFixed(1)} ${padTop + chartHeight} L ${pts[0].x.toFixed(1)} ${padTop + chartHeight} Z`;

  let secLinePath = "";
  if (secondaryMetric) {
    secLinePath = pts.reduce((acc, p, idx) => `${acc} ${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${(p.ySec ?? p.y).toFixed(1)}`, "");
  }

  let compLinePath = "";
  if (hasComparison) {
    compLinePath = pts.reduce((acc, p, idx) => `${acc} ${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${(p.yComp ?? p.y).toFixed(1)}`, "");
  }

  const yTicks = [0, 0.33, 0.66, 1];
  const stepIdx = Math.max(1, Math.floor(data.length / 6));

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const relativeX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, (relativeX - (padLeft * rect.width) / svgWidth) / ((chartWidth * rect.width) / svgWidth)));
    const targetIdx = Math.round(pct * (data.length - 1));
    setHoverIndex(Math.max(0, Math.min(data.length - 1, targetIdx)));
  };

  const activePoint = hoverIndex !== null ? pts[hoverIndex] : null;

  return (
    <div style={{ position: "relative", width: "100%" }}>
      {/* Legend & Summary Info */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, fontSize: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 10, height: 3, background: "#0284c7", borderRadius: 2 }} />
            <span style={{ fontWeight: 600, color: "#1e293b" }}>{metricLabel || metric}</span>
          </div>
          {secondaryMetric && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 10, height: 3, background: "#8b5cf6", borderRadius: 2 }} />
              <span style={{ fontWeight: 600, color: "#6d28d9" }}>{secondaryLabel || secondaryMetric} (right axis)</span>
            </div>
          )}
          {hasComparison && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 12, height: 2, background: "#94a3b8", borderTop: "2px dashed #94a3b8" }} />
              <span style={{ color: "var(--ink-muted)" }}>{comparisonLabel}</span>
            </div>
          )}
        </div>
      </div>

      {/* Responsive SVG Chart */}
      <div ref={containerRef} style={{ width: "100%", height }}>
        <svg
          viewBox={`0 0 ${svgWidth} ${height}`}
          style={{ width: "100%", height: "100%", overflow: "visible", cursor: "crosshair" }}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id={`grad-${gradId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0284c7" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#0284c7" stopOpacity="0.01" />
            </linearGradient>
          </defs>

          {/* Horizontal Gridlines & Y-Axis Labels */}
          {yTicks.map((t) => {
            const yPos = padTop + chartHeight - t * chartHeight;
            const val = minVal + t * rangeVal;
            const secVal = minSec + t * rangeSec;
            return (
              <g key={t}>
                <line
                  x1={padLeft}
                  y1={yPos}
                  x2={svgWidth - padRight}
                  y2={yPos}
                  stroke="#f1f5f9"
                  strokeWidth="1"
                />
                <text
                  x={padLeft - 8}
                  y={yPos + 3.5}
                  textAnchor="end"
                  fontSize="10"
                  fill="#94a3b8"
                  fontFamily="sans-serif"
                >
                  {formatMetricValue(val, metric)}
                </text>
                {secondaryMetric && (
                  <text
                    x={svgWidth - padRight + 8}
                    y={yPos + 3.5}
                    textAnchor="start"
                    fontSize="10"
                    fill="#8b5cf6"
                    fontFamily="sans-serif"
                  >
                    {formatMetricValue(secVal, secondaryMetric)}
                  </text>
                )}
              </g>
            );
          })}

          {/* Area & Curves */}
          <path d={areaPath} fill={`url(#grad-${gradId})`} />

          {/* Comparison Line (Dashed) */}
          {hasComparison && compLinePath && (
            <path
              d={compLinePath}
              fill="none"
              stroke="#94a3b8"
              strokeWidth="2"
              strokeDasharray="4 4"
              strokeLinecap="round"
            />
          )}

          {/* Primary Trend Line */}
          <path
            d={linePath}
            fill="none"
            stroke="#0284c7"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Secondary Metric Line */}
          {secondaryMetric && secLinePath && (
            <path
              d={secLinePath}
              fill="none"
              stroke="#8b5cf6"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* X-Axis Date Ticks */}
          {data.map((d, i) => {
            if (i % stepIdx !== 0 && i !== data.length - 1) return null;
            const x = padLeft + (i / Math.max(1, data.length - 1)) * chartWidth;
            const label = d.date.length >= 10 ? d.date.slice(5) : d.date;
            return (
              <text
                key={d.date + i}
                x={x}
                y={height - 8}
                textAnchor="middle"
                fontSize="10"
                fill="#64748b"
                fontFamily="sans-serif"
              >
                {label}
              </text>
            );
          })}

          {/* Active Hover Crosshair Line & Points */}
          {activePoint && (
            <g>
              <line
                x1={activePoint.x}
                y1={padTop}
                x2={activePoint.x}
                y2={padTop + chartHeight}
                stroke="#64748b"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <circle cx={activePoint.x} cy={activePoint.y} r="4.5" fill="#0284c7" stroke="#ffffff" strokeWidth="2" />
              {activePoint.ySec !== undefined && (
                <circle cx={activePoint.x} cy={activePoint.ySec} r="4" fill="#8b5cf6" stroke="#ffffff" strokeWidth="2" />
              )}
              {activePoint.yComp !== undefined && (
                <circle cx={activePoint.x} cy={activePoint.yComp} r="4" fill="#94a3b8" stroke="#ffffff" strokeWidth="2" />
              )}
            </g>
          )}
        </svg>
      </div>

      {/* Floating Hover Tooltip */}
      {activePoint && (
        <div
          style={{
            position: "absolute",
            left: `${Math.min(85, Math.max(15, (activePoint.x / svgWidth) * 100))}%`,
            top: 24,
            transform: "translateX(-50%)",
            background: "#0f172a",
            color: "#ffffff",
            padding: "8px 12px",
            borderRadius: 6,
            fontSize: 12,
            boxShadow: "0 4px 12px rgba(0,0,0,0.25)",
            pointerEvents: "none",
            zIndex: 10,
            minWidth: 140,
          }}
        >
          <div style={{ fontWeight: 700, color: "#94a3b8", marginBottom: 4, borderBottom: "1px solid #334155", paddingBottom: 2 }}>
            📅 {activePoint.data.date}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 3 }}>
            <span style={{ color: "#38bdf8" }}>{metricLabel || metric}:</span>
            <strong>{formatMetricValue(activePoint.data.value, metric)}</strong>
          </div>
          {secondaryMetric && activePoint.data.secondaryValue !== undefined && (
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 2 }}>
              <span style={{ color: "#c084fc" }}>{secondaryLabel || secondaryMetric}:</span>
              <strong>{formatMetricValue(activePoint.data.secondaryValue, secondaryMetric)}</strong>
            </div>
          )}
          {hasComparison && activePoint.data.compareValue !== undefined && (
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginTop: 4, borderTop: "1px dashed #334155", paddingTop: 3 }}>
              <span style={{ color: "#94a3b8" }}>Prev:</span>
              <span>{formatMetricValue(activePoint.data.compareValue, metric)}</span>
            </div>
          )}
          {hasComparison && activePoint.data.compareValue !== undefined && (
            <div style={{ marginTop: 2, textAlign: "right", fontSize: 11, fontWeight: 700 }}>
              {(() => {
                const { label, positive } = formatDelta(activePoint.data.value, activePoint.data.compareValue, metric);
                return (
                  <span style={{ color: positive ? "#4ade80" : "#f87171" }}>
                    {positive ? "▲ " : "▼ "}{label}
                  </span>
                );
              })()}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
