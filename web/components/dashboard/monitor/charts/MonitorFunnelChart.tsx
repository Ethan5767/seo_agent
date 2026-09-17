"use client";

import React from "react";
import { formatMetricValue } from "@/lib/monitor/types";

export interface FunnelStage {
  name: string;
  count: number;
  description: string;
  color?: string;
}

interface MonitorFunnelChartProps {
  stages: FunnelStage[];
  height?: number;
}

const DEFAULT_STAGE_COLORS = ["#0284c7", "#6366f1", "#10b981"];

export function MonitorFunnelChart({
  stages = [],
  height = 240,
}: MonitorFunnelChartProps) {
  if (stages.length === 0) {
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
        No funnel data available
      </div>
    );
  }

  const baseCount = Math.max(stages[0]?.count || 1, 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, padding: "8px 4px", minHeight: height, justifyContent: "center" }}>
      {stages.map((stage, idx) => {
        const pctOfBase = ((stage.count / baseCount) * 100).toFixed(1);
        const prevStage = idx > 0 ? stages[idx - 1] : null;
        const dropoffPct = prevStage && prevStage.count > 0
          ? (((prevStage.count - stage.count) / prevStage.count) * 100).toFixed(1)
          : null;

        const color = stage.color || DEFAULT_STAGE_COLORS[idx % DEFAULT_STAGE_COLORS.length];
        const barWidthPct = Math.max(12, Math.min(100, (stage.count / baseCount) * 100));

        return (
          <div key={stage.name} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", fontSize: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontWeight: 700, color: "#1e293b" }}>{idx + 1}. {stage.name}</span>
                <span style={{ fontSize: 11, color: "var(--ink-muted)" }}>{stage.description}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontWeight: 800, fontSize: 13, color: "#0f172a" }}>
                  {formatMetricValue(stage.count, "sessions")}
                </span>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#475569" }}>
                  {pctOfBase}%
                </span>
                {dropoffPct !== null && (
                  <span style={{ fontSize: 10.5, color: "#dc2626", background: "#fef2f2", padding: "1px 5px", borderRadius: 3 }}>
                    -{dropoffPct}%
                  </span>
                )}
              </div>
            </div>

            {/* Funnel Step Bar */}
            <div style={{ height: 26, background: "#f1f5f9", borderRadius: 6, overflow: "hidden", display: "flex", alignItems: "center", padding: "0 6px" }}>
              <div
                style={{
                  width: `${barWidthPct}%`,
                  height: "100%",
                  background: `linear-gradient(90deg, ${color}dd 0%, ${color} 100%)`,
                  borderRadius: 5,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "flex-end",
                  paddingRight: 8,
                  color: "#ffffff",
                  fontSize: 11,
                  fontWeight: 700,
                  transition: "width 0.4s ease",
                  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.2)",
                }}
              >
                {barWidthPct > 20 && `${pctOfBase}%`}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
