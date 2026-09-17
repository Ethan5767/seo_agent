"use client";

import React, { useState } from "react";
import type { MonitorWidget as MonitorWidgetType } from "@/lib/monitor/types";
import { formatMetricValue, formatDelta } from "@/lib/monitor/types";
import {
  MonitorLineChart,
  MonitorBarChart,
  MonitorDonutChart,
  MonitorFunnelChart,
} from "./charts";
import { IconGoogle } from "@/components/dashboard/icons";

function MiniSparkline({
  data = [2.8, 3.2, 3.7, 4.1, 5.2, 6.2],
  color = "var(--ok)",
  width = 72,
  height = 28,
}: {
  data?: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (!data || data.length === 0) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 3;
  const pts = data.map((d, i) => {
    const x = pad + (i / Math.max(1, data.length - 1)) * (width - pad * 2);
    const y = height - pad - ((d - min) / range) * (height - pad * 2);
    return { x, y };
  });
  const pointsStr = pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={pointsStr}
      />
    </svg>
  );
}

interface MonitorWidgetProps {
  widget: MonitorWidgetType;
  index: number;
  totalWidgets: number;
  onMove: (index: number, direction: "left" | "right") => void;
  onEdit: (widget: MonitorWidgetType) => void;
  onDelete: (id: string) => void;
  // Connection states
  gscConnected: boolean;
  ga4Connected: boolean;
  onConnectGsc: () => void;
  onConnectGa4: () => void;
  // Data
  isLoading: boolean;
  data: any;
  hasComparison: boolean;
  comparisonLabel?: string;
}

export function MonitorWidget({
  widget,
  index,
  totalWidgets,
  onMove,
  onEdit,
  onDelete,
  gscConnected,
  ga4Connected,
  onConnectGsc,
  onConnectGa4,
  isLoading,
  data,
  hasComparison,
  comparisonLabel,
}: MonitorWidgetProps) {
  const isGsc = widget.source === "gsc";
  const isConnected = isGsc ? gscConnected : ga4Connected;

  const gridSpan = widget.width === "full" ? "span 12" : widget.width === "half" ? "span 6" : "span 4";

  return (
    <div
      style={{
        gridColumn: gridSpan,
        background: "#ffffff",
        border: "1px solid #e2e8f0",
        borderRadius: 10,
        padding: "16px 18px",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
        position: "relative",
        minHeight: widget.chartType === "stat" ? 110 : 280,
      }}
    >
      {/* ── Widget Header ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12, gap: 8 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span
              style={{
                fontSize: 10.5,
                fontWeight: 700,
                textTransform: "uppercase",
                padding: "2px 6px",
                borderRadius: 4,
                background: isGsc ? "#eff6ff" : "#f5f3ff",
                color: isGsc ? "#1d4ed8" : "#7c3aed",
                border: `1px solid ${isGsc ? "#bfdbfe" : "#ddd6fe"}`,
              }}
            >
              {isGsc ? "Search Console" : "Google Analytics 4"}
            </span>
            {widget.dateRangeOverride && (
              <span style={{ fontSize: 11, color: "#d97706", fontWeight: 600, background: "#fef3c7", padding: "1px 5px", borderRadius: 3 }}>
                Override
              </span>
            )}
          </div>
          <h3 style={{ margin: "5px 0 0", fontSize: widget.chartType === "stat" ? 13 : 15, fontWeight: 700, color: "#0f172a" }}>
            {widget.title}
          </h3>
        </div>

        {/* Action Controls: Move Left, Move Right, Edit, Delete */}
        <div style={{ display: "flex", alignItems: "center", gap: 3, opacity: 0.85 }}>
          {index > 0 && (
            <button
              type="button"
              onClick={() => onMove(index, "left")}
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 4,
                padding: "2px 5px",
                fontSize: 11,
                cursor: "pointer",
                color: "#64748b",
              }}
              title="Move left/up"
            >
              ←
            </button>
          )}
          {index < totalWidgets - 1 && (
            <button
              type="button"
              onClick={() => onMove(index, "right")}
              style={{
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 4,
                padding: "2px 5px",
                fontSize: 11,
                cursor: "pointer",
                color: "#64748b",
              }}
              title="Move right/down"
            >
              →
            </button>
          )}
          <button
            type="button"
            onClick={() => onEdit(widget)}
            style={{
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 4,
              padding: "2px 6px",
              fontSize: 11,
              cursor: "pointer",
              color: "#475569",
              fontWeight: 600,
            }}
            title="Edit widget configuration"
          >
            ✎
          </button>
          <button
            type="button"
            onClick={() => onDelete(widget.id)}
            style={{
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 4,
              padding: "2px 6px",
              fontSize: 11,
              cursor: "pointer",
              color: "#ef4444",
              fontWeight: 700,
            }}
            title="Remove widget"
          >
            ✕
          </button>
        </div>
      </div>

      {/* ── Widget Body Content ── */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        {!isConnected ? (
          /* Disconnected Data Source State */
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              background: "#f8fafc",
              borderRadius: 8,
              border: "1px dashed #cbd5e1",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 10,
            }}
          >
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                background: isGsc ? "#eff6ff" : "#f5f3ff",
                border: `1px solid ${isGsc ? "#bfdbfe" : "#ddd6fe"}`,
                display: "grid",
                placeItems: "center",
              }}
            >
              <IconGoogle size={20} />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                Connect {isGsc ? "Google Search Console" : "Google Analytics 4"}
              </div>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ink-muted)", maxWidth: 300, lineHeight: 1.4 }}>
                {isGsc
                  ? "Connect Search Console to display organic search clicks, impressions, and query rankings."
                  : "Connect GA4 to view verified sessions, engaged time, channels, and conversion events."}
              </p>
            </div>
            <button
              type="button"
              onClick={isGsc ? onConnectGsc : onConnectGa4}
              style={{
                background: isGsc ? "#1d4ed8" : "#7c3aed",
                color: "#ffffff",
                border: 0,
                borderRadius: 6,
                padding: "6px 14px",
                fontSize: 12,
                fontWeight: 700,
                cursor: "pointer",
                boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
              }}
            >
              Connect {isGsc ? "GSC" : "GA4"} →
            </button>
          </div>
        ) : isLoading ? (
          /* Loading Skeleton */
          <div style={{ padding: "20px 0", display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ height: 24, background: "#f1f5f9", borderRadius: 4, width: "40%" }} />
            <div style={{ height: 140, background: "#f8fafc", borderRadius: 6 }} />
          </div>
        ) : data?.error ? (
          /* Query Error */
          <div style={{ padding: 18, background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, fontSize: 12, color: "#991b1b" }}>
            <strong>Unable to load widget data:</strong> {data.error}
          </div>
        ) : (
          /* Render Specific Chart Type */
          (() => {
            switch (widget.chartType) {
              case "stat":
                return <WidgetStatView widget={widget} data={data} hasComparison={hasComparison} />;
              case "line":
                return (
                  <MonitorLineChart
                    data={data?.lineSeries || []}
                    metric={widget.metric}
                    secondaryMetric={widget.secondaryMetric}
                    hasComparison={hasComparison}
                    comparisonLabel={comparisonLabel}
                  />
                );
              case "bar":
                return (
                  <MonitorBarChart
                    data={data?.barSeries || []}
                    metric={widget.metric}
                    dimension={widget.dimension}
                  />
                );
              case "donut":
                return (
                  <MonitorDonutChart
                    slices={data?.donutSeries || []}
                    metric={widget.metric}
                  />
                );
              case "funnel":
                return <MonitorFunnelChart stages={data?.funnelStages || []} />;
              case "table":
                return <WidgetTableView widget={widget} data={data} />;
              default:
                return <div>Unsupported chart type</div>;
            }
          })()
        )}
      </div>

      {/* ── Widget Footer Note ── */}
      <div style={{ marginTop: 8, paddingTop: 6, borderTop: "1px solid #f8fafc", fontSize: 11, color: "var(--ink-muted)", display: "flex", justifyContent: "space-between" }}>
        <span>
          {isGsc
            ? "Data delay: ~2-3 days (Google SERP aggregation)"
            : "Data thresholding: GA4 Data API standard"}
        </span>
      </div>
    </div>
  );
}

/** KPI Stat Card View */
function WidgetStatView({
  widget,
  data,
  hasComparison,
}: {
  widget: MonitorWidgetType;
  data: any;
  hasComparison: boolean;
}) {
  const currentVal = data?.statCurrent ?? 0;
  const previousVal = data?.statPrevious ?? 0;
  const trend = data?.statTrend || [];

  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", paddingTop: 4 }}>
      <div>
        <div style={{ fontSize: 26, fontWeight: 800, color: "#0f172a", lineHeight: 1.1 }}>
          {formatMetricValue(currentVal, widget.metric)}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: 12 }}>
          {hasComparison && previousVal > 0 && (
            (() => {
              const { label, positive } = formatDelta(currentVal, previousVal, widget.metric);
              return (
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: positive ? "#166534" : "#dc2626",
                    background: positive ? "#dcfce7" : "#fee2e2",
                    padding: "2px 6px",
                    borderRadius: 4,
                  }}
                >
                  {positive ? "▲ " : "▼ "}{label}
                </span>
              );
            })()
          )}
          <span style={{ color: "var(--ink-muted)" }}>
            {widget.metric === "ctr" ? "Click-through rate" : widget.metric === "position" ? "Avg SERP rank" : "Total volume"}
          </span>
        </div>
      </div>

      {trend.length > 0 && (
        <div style={{ paddingBottom: 2 }}>
          <MiniSparkline
            data={trend}
            color={widget.source === "gsc" ? "#0284c7" : "#8b5cf6"}
            width={64}
            height={26}
          />
        </div>
      )}
    </div>
  );
}

/** Table Widget View */
function WidgetTableView({
  widget,
  data,
}: {
  widget: MonitorWidgetType;
  data: any;
}) {
  const rows: any[] = data?.tableRows || [];
  const [sortKey, setSortKey] = useState<string>(widget.metric);
  const [sortAsc, setSortAsc] = useState<boolean>(false);

  if (rows.length === 0) {
    return (
      <div style={{ padding: 24, textAlign: "center", color: "var(--ink-muted)", fontSize: 12 }}>
        No table entries recorded for this date range
      </div>
    );
  }

  const sorted = [...rows].sort((a, b) => {
    const valA = a[sortKey] ?? 0;
    const valB = b[sortKey] ?? 0;
    return sortAsc ? (valA > valB ? 1 : -1) : valA < valB ? 1 : -1;
  });

  const handleHeaderClick = (key: string) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const isGsc = widget.source === "gsc";

  return (
    <div style={{ overflowX: "auto", maxHeight: 250, overflowY: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #e2e8f0", color: "#64748b", fontSize: 11, textTransform: "uppercase" }}>
            <th style={{ padding: "6px 8px", fontWeight: 700 }}>{widget.dimension || "Name"}</th>
            {isGsc ? (
              <>
                <th
                  onClick={() => handleHeaderClick("clicks")}
                  style={{ padding: "6px 8px", fontWeight: 700, textAlign: "right", cursor: "pointer" }}
                >
                  Clicks {sortKey === "clicks" ? (sortAsc ? "▲" : "▼") : ""}
                </th>
                <th
                  onClick={() => handleHeaderClick("impressions")}
                  style={{ padding: "6px 8px", fontWeight: 700, textAlign: "right", cursor: "pointer" }}
                >
                  Imp {sortKey === "impressions" ? (sortAsc ? "▲" : "▼") : ""}
                </th>
                <th
                  onClick={() => handleHeaderClick("ctr")}
                  style={{ padding: "6px 8px", fontWeight: 700, textAlign: "right", cursor: "pointer" }}
                >
                  CTR {sortKey === "ctr" ? (sortAsc ? "▲" : "▼") : ""}
                </th>
                <th
                  onClick={() => handleHeaderClick("position")}
                  style={{ padding: "6px 8px", fontWeight: 700, textAlign: "right", cursor: "pointer" }}
                >
                  Position {sortKey === "position" ? (sortAsc ? "▲" : "▼") : ""}
                </th>
              </>
            ) : (
              <>
                <th
                  onClick={() => handleHeaderClick("sessions")}
                  style={{ padding: "6px 8px", fontWeight: 700, textAlign: "right", cursor: "pointer" }}
                >
                  Sessions {sortKey === "sessions" ? (sortAsc ? "▲" : "▼") : ""}
                </th>
                <th
                  onClick={() => handleHeaderClick("engagementRate")}
                  style={{ padding: "6px 8px", fontWeight: 700, textAlign: "right", cursor: "pointer" }}
                >
                  Engaged {sortKey === "engagementRate" ? (sortAsc ? "▲" : "▼") : ""}
                </th>
                <th
                  onClick={() => handleHeaderClick("conversions")}
                  style={{ padding: "6px 8px", fontWeight: 700, textAlign: "right", cursor: "pointer" }}
                >
                  Conv {sortKey === "conversions" ? (sortAsc ? "▲" : "▼") : ""}
                </th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, 50).map((r, i) => (
            <tr key={r.key + i} style={{ borderBottom: "1px solid #f1f5f9" }}>
              <td
                style={{
                  padding: "6px 8px",
                  fontWeight: 600,
                  color: "#0f172a",
                  maxWidth: 240,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={r.key}
              >
                {r.key}
              </td>
              {isGsc ? (
                <>
                  <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700, color: "#0284c7" }}>
                    {formatMetricValue(r.clicks, "clicks")}
                  </td>
                  <td style={{ padding: "6px 8px", textAlign: "right", color: "var(--ink-muted)" }}>
                    {formatMetricValue(r.impressions, "impressions")}
                  </td>
                  <td style={{ padding: "6px 8px", textAlign: "right" }}>
                    {formatMetricValue(r.ctr, "ctr")}
                  </td>
                  <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 600 }}>
                    {formatMetricValue(r.position, "position")}
                  </td>
                </>
              ) : (
                <>
                  <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700, color: "#7c3aed" }}>
                    {formatMetricValue(r.sessions, "sessions")}
                  </td>
                  <td style={{ padding: "6px 8px", textAlign: "right" }}>
                    {formatMetricValue(r.engagementRate, "engagementRate")}
                  </td>
                  <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 700, color: "#059669" }}>
                    {formatMetricValue(r.conversions, "conversions")}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
