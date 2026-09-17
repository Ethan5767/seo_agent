"use client";

import React, { useState } from "react";
import { formatMetricValue, formatDelta, lookupCountry } from "@/lib/monitor/types";

export interface BarCategoryItem {
  label: string;
  value: number;
  compareValue?: number;
  secondaryValue?: number;
}

interface MonitorBarChartProps {
  data: BarCategoryItem[];
  metric: string;
  dimension?: string;
  maxItems?: number;
  height?: number;
}

export function MonitorBarChart({
  data = [],
  metric,
  dimension = "category",
  maxItems = 8,
  height = 240,
}: MonitorBarChartProps) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const displayed = data.slice(0, maxItems);
  const totalVal = displayed.reduce((acc, d) => acc + d.value, 0);
  const maxVal = Math.max(...displayed.map((d) => d.value), 1);

  if (displayed.length === 0) {
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
        No breakdown data available for this selection
      </div>
    );
  }

  const isCountry = dimension === "country";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "4px 0", minHeight: height }}>
      {displayed.map((item, idx) => {
        const pctOfMax = Math.max(4, Math.min(100, (item.value / maxVal) * 100));
        const pctOfTotal = totalVal > 0 ? ((item.value / totalVal) * 100).toFixed(1) : "0.0";
        const isHovered = hoverIdx === idx;

        let displayLabel = item.label;
        let prefixEmoji = "";
        if (isCountry) {
          const info = lookupCountry(item.label);
          displayLabel = info.name;
          prefixEmoji = info.flag + " ";
        }

        return (
          <div
            key={item.label + idx}
            onMouseEnter={() => setHoverIdx(idx)}
            onMouseLeave={() => setHoverIdx(null)}
            style={{
              padding: "4px 8px",
              borderRadius: 6,
              background: isHovered ? "#f1f5f9" : "transparent",
              transition: "background 0.15s ease",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4, fontSize: 12 }}>
              <span
                style={{
                  fontWeight: 600,
                  color: "#1e293b",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                  maxWidth: "65%",
                }}
                title={item.label}
              >
                {prefixEmoji}{displayLabel}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontWeight: 700, color: "#0f172a" }}>
                  {formatMetricValue(item.value, metric)}
                </span>
                <span style={{ fontSize: 11, color: "var(--ink-muted)", width: 44, textAlign: "right" }}>
                  {pctOfTotal}%
                </span>
                {item.compareValue !== undefined && (
                  (() => {
                    const { label, positive } = formatDelta(item.value, item.compareValue, metric);
                    return (
                      <span
                        style={{
                          fontSize: 10.5,
                          fontWeight: 700,
                          color: positive ? "#166534" : "#dc2626",
                          background: positive ? "#dcfce7" : "#fee2e2",
                          padding: "1px 4px",
                          borderRadius: 3,
                        }}
                      >
                        {label}
                      </span>
                    );
                  })()
                )}
              </div>
            </div>

            {/* Progress Bar */}
            <div style={{ height: 7, background: "#e2e8f0", borderRadius: 4, overflow: "hidden" }}>
              <div
                style={{
                  width: `${pctOfMax}%`,
                  height: "100%",
                  background: isHovered ? "#0284c7" : "#3b82f6",
                  borderRadius: 4,
                  transition: "width 0.3s ease, background 0.15s ease",
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
