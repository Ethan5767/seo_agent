"use client";

import React, { useState, useEffect } from "react";
import type {
  MonitorWidget,
  WidgetTemplate,
  DataSource,
  ChartType,
  WidgetWidth,
  DatePreset,
} from "@/lib/monitor/types";
import { WIDGET_TEMPLATES } from "@/lib/monitor/types";

interface MonitorWidgetModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSaveWidget: (widget: MonitorWidget) => void;
  initialWidget?: MonitorWidget | null;
}

const GSC_METRICS = [
  { value: "clicks", label: "Clicks" },
  { value: "impressions", label: "Impressions" },
  { value: "ctr", label: "Average CTR (%)" },
  { value: "position", label: "Average Position" },
];

const GA4_METRICS = [
  { value: "sessions", label: "Sessions" },
  { value: "totalUsers", label: "Total Users" },
  { value: "engagedSessions", label: "Engaged Sessions" },
  { value: "engagementRate", label: "Engagement Rate (%)" },
  { value: "averageSessionDuration", label: "Avg Session Duration" },
  { value: "conversions", label: "Conversions" },
  { value: "eventCount", label: "Event Count" },
  { value: "screenPageViews", label: "Page Views" },
];

const GSC_DIMENSIONS = [
  { value: "date", label: "Date (Time Series)" },
  { value: "query", label: "Search Query" },
  { value: "page", label: "Landing Page" },
  { value: "country", label: "Country" },
  { value: "device", label: "Device" },
  { value: "searchAppearance", label: "Search Appearance" },
];

const GA4_DIMENSIONS = [
  { value: "date", label: "Date (Time Series)" },
  { value: "sessionDefaultChannelGroup", label: "Channel Group" },
  { value: "pagePath", label: "Page Path" },
  { value: "deviceCategory", label: "Device Category" },
  { value: "country", label: "Country" },
  { value: "sessionSourceMedium", label: "Source / Medium" },
  { value: "eventName", label: "Event Name" },
];

export function MonitorWidgetModal({
  isOpen,
  onClose,
  onSaveWidget,
  initialWidget,
}: MonitorWidgetModalProps) {
  const isEditing = Boolean(initialWidget);
  const [activeTab, setActiveTab] = useState<"library" | "custom">(isEditing ? "custom" : "library");

  const [title, setTitle] = useState("");
  const [source, setSource] = useState<DataSource>("gsc");
  const [chartType, setChartType] = useState<ChartType>("line");
  const [metric, setMetric] = useState("clicks");
  const [secondaryMetric, setSecondaryMetric] = useState<string>("");
  const [dimension, setDimension] = useState("date");
  const [width, setWidth] = useState<WidgetWidth>("half");
  const [dateOverridePreset, setDateOverridePreset] = useState<DatePreset | "none">("none");

  const [templateCategory, setTemplateCategory] = useState<string>("All");

  useEffect(() => {
    if (initialWidget) {
      setTitle(initialWidget.title);
      setSource(initialWidget.source);
      setChartType(initialWidget.chartType);
      setMetric(initialWidget.metric);
      setSecondaryMetric(initialWidget.secondaryMetric || "");
      setDimension(initialWidget.dimension || (initialWidget.source === "gsc" ? "query" : "sessionDefaultChannelGroup"));
      setWidth(initialWidget.width);
      setDateOverridePreset(initialWidget.dateRangeOverride?.preset || "none");
      setActiveTab("custom");
    } else {
      setTitle("New Custom Widget");
      setSource("gsc");
      setChartType("line");
      setMetric("clicks");
      setSecondaryMetric("impressions");
      setDimension("date");
      setWidth("half");
      setDateOverridePreset("none");
      setActiveTab("library");
    }
  }, [initialWidget, isOpen]);

  if (!isOpen) return null;

  const handleSelectTemplate = (template: WidgetTemplate) => {
    const newWidget: MonitorWidget = {
      id: `widget-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      title: template.title,
      description: template.description,
      source: template.source,
      chartType: template.chartType,
      metric: template.metric,
      secondaryMetric: template.secondaryMetric,
      dimension: template.dimension,
      width: template.width,
    };
    onSaveWidget(newWidget);
    onClose();
  };

  const handleSaveCustom = (e: React.FormEvent) => {
    e.preventDefault();
    const finalWidget: MonitorWidget = {
      id: initialWidget?.id || `widget-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      title: title.trim() || (source === "gsc" ? "Search Analytics" : "GA4 Traffic"),
      source,
      chartType,
      metric,
      secondaryMetric: secondaryMetric && secondaryMetric !== "none" ? secondaryMetric : undefined,
      dimension: chartType === "stat" ? undefined : dimension,
      width,
      dateRangeOverride: dateOverridePreset !== "none" ? { preset: dateOverridePreset } : undefined,
    };
    onSaveWidget(finalWidget);
    onClose();
  };

  const availableMetrics = source === "gsc" ? GSC_METRICS : GA4_METRICS;
  const availableDimensions = source === "gsc" ? GSC_DIMENSIONS : GA4_DIMENSIONS;

  const categories = ["All", "KPI Cards", "GSC Search", "GA4 Traffic", "Conversions"];
  const filteredTemplates = templateCategory === "All"
    ? WIDGET_TEMPLATES
    : WIDGET_TEMPLATES.filter((t) => t.category === templateCategory);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(15, 23, 42, 0.6)",
        backdropFilter: "blur(2px)",
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: "#ffffff",
          borderRadius: 12,
          maxWidth: 680,
          width: "100%",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
          border: "1px solid #e2e8f0",
          overflow: "hidden",
        }}
      >
        {/* Modal Header */}
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "#0f172a" }}>
              {isEditing ? "Edit Analytics Widget" : "Add Analytics Widget"}
            </h2>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--ink-muted)" }}>
              Custom dashboard analytics from verified Google Search Console and GA4
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: "transparent",
              border: 0,
              fontSize: 18,
              color: "#64748b",
              cursor: "pointer",
              padding: "4px 8px",
            }}
          >
            ✕
          </button>
        </div>

        {/* Modal Subtabs */}
        {!isEditing && (
          <div style={{ display: "flex", borderBottom: "1px solid #e2e8f0", background: "#f8fafc", padding: "0 20px" }}>
            <button
              type="button"
              onClick={() => setActiveTab("library")}
              style={{
                padding: "10px 14px",
                fontSize: 13,
                fontWeight: 600,
                color: activeTab === "library" ? "#0284c7" : "#64748b",
                borderBottom: `2px solid ${activeTab === "library" ? "#0284c7" : "transparent"}`,
                background: "transparent",
                border: "none",
                cursor: "pointer",
              }}
            >
              📚 Pre-Configured Templates
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("custom")}
              style={{
                padding: "10px 14px",
                fontSize: 13,
                fontWeight: 600,
                color: activeTab === "custom" ? "#0284c7" : "#64748b",
                borderBottom: `2px solid ${activeTab === "custom" ? "#0284c7" : "transparent"}`,
                background: "transparent",
                border: "none",
                cursor: "pointer",
              }}
            >
              🛠️ Custom Widget Builder
            </button>
          </div>
        )}

        {/* Modal Body */}
        <div style={{ padding: "18px 20px", overflowY: "auto", flex: 1 }}>
          {activeTab === "library" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {categories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => setTemplateCategory(cat)}
                    style={{
                      background: templateCategory === cat ? "#0284c7" : "#f1f5f9",
                      color: templateCategory === cat ? "#ffffff" : "#475569",
                      border: `1px solid ${templateCategory === cat ? "#0284c7" : "#e2e8f0"}`,
                      borderRadius: 6,
                      padding: "4px 10px",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {cat}
                  </button>
                ))}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                {filteredTemplates.map((tmpl) => (
                  <div
                    key={tmpl.id}
                    onClick={() => handleSelectTemplate(tmpl)}
                    style={{
                      border: "1px solid #e2e8f0",
                      borderRadius: 8,
                      padding: "12px 14px",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      transition: "all 0.15s ease",
                      background: "#ffffff",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "#0284c7";
                      e.currentTarget.style.boxShadow = "0 2px 8px rgba(2,132,199,0.1)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "#e2e8f0";
                      e.currentTarget.style.boxShadow = "none";
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 700,
                            textTransform: "uppercase",
                            padding: "1px 5px",
                            borderRadius: 4,
                            background: tmpl.source === "gsc" ? "#eff6ff" : "#f5f3ff",
                            color: tmpl.source === "gsc" ? "#1d4ed8" : "#7c3aed",
                          }}
                        >
                          {tmpl.source === "gsc" ? "GSC" : "GA4"}
                        </span>
                        <span style={{ fontSize: 11, color: "var(--ink-muted)", textTransform: "capitalize" }}>
                          {tmpl.chartType} chart
                        </span>
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>{tmpl.title}</div>
                      <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 4, lineHeight: 1.35 }}>
                        {tmpl.description}
                      </div>
                    </div>
                    <div style={{ marginTop: 10, fontSize: 11.5, fontWeight: 600, color: "#0284c7" }}>
                      + Add to dashboard
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <form onSubmit={handleSaveCustom} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                  Widget Title
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Organic Clicks by Country"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    borderRadius: 6,
                    border: "1px solid #cbd5e1",
                    fontSize: 13,
                  }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                    Data Source
                  </label>
                  <select
                    value={source}
                    onChange={(e) => {
                      const next = e.target.value as DataSource;
                      setSource(next);
                      setMetric(next === "gsc" ? "clicks" : "sessions");
                      setDimension(next === "gsc" ? "query" : "sessionDefaultChannelGroup");
                    }}
                    style={{
                      width: "100%",
                      padding: "7px 10px",
                      borderRadius: 6,
                      border: "1px solid #cbd5e1",
                      fontSize: 13,
                      background: "#ffffff",
                    }}
                  >
                    <option value="gsc">Google Search Console (GSC)</option>
                    <option value="ga4">Google Analytics 4 (GA4)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                    Visualization Type
                  </label>
                  <select
                    value={chartType}
                    onChange={(e) => setChartType(e.target.value as ChartType)}
                    style={{
                      width: "100%",
                      padding: "7px 10px",
                      borderRadius: 6,
                      border: "1px solid #cbd5e1",
                      fontSize: 13,
                      background: "#ffffff",
                    }}
                  >
                    <option value="line">Line Chart (Trend over time)</option>
                    <option value="bar">Bar Chart (Categorical)</option>
                    <option value="donut">Donut Chart (Distribution)</option>
                    <option value="table">Table View (Detailed rows)</option>
                    <option value="stat">Single-Stat KPI Card</option>
                    <option value="funnel">Conversion Funnel</option>
                  </select>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                    Primary Metric
                  </label>
                  <select
                    value={metric}
                    onChange={(e) => setMetric(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "7px 10px",
                      borderRadius: 6,
                      border: "1px solid #cbd5e1",
                      fontSize: 13,
                      background: "#ffffff",
                    }}
                  >
                    {availableMetrics.map((m) => (
                      <option key={m.value} value={m.value}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>

                {chartType !== "stat" && chartType !== "funnel" && (
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                      Dimension (Group By)
                    </label>
                    <select
                      value={dimension}
                      onChange={(e) => setDimension(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "7px 10px",
                        borderRadius: 6,
                        border: "1px solid #cbd5e1",
                        fontSize: 13,
                        background: "#ffffff",
                      }}
                    >
                      {availableDimensions.map((d) => (
                        <option key={d.value} value={d.value}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                {chartType === "line" && (
                  <div>
                    <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                      Secondary Metric (Optional)
                    </label>
                    <select
                      value={secondaryMetric}
                      onChange={(e) => setSecondaryMetric(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "7px 10px",
                        borderRadius: 6,
                        border: "1px solid #cbd5e1",
                        fontSize: 13,
                        background: "#ffffff",
                      }}
                    >
                      <option value="none">None</option>
                      {availableMetrics.map((m) => (
                        <option key={m.value} value={m.value}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                    Widget Width
                  </label>
                  <select
                    value={width}
                    onChange={(e) => setWidth(e.target.value as WidgetWidth)}
                    style={{
                      width: "100%",
                      padding: "7px 10px",
                      borderRadius: 6,
                      border: "1px solid #cbd5e1",
                      fontSize: 13,
                      background: "#ffffff",
                    }}
                  >
                    <option value="full">Full Width (100% / 12 cols)</option>
                    <option value="half">Half Width (50% / 6 cols)</option>
                    <option value="third">One-Third Width (33% / 4 cols)</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#334155", marginBottom: 4 }}>
                    Date Range Override (Optional)
                  </label>
                  <select
                    value={dateOverridePreset}
                    onChange={(e) => setDateOverridePreset(e.target.value as any)}
                    style={{
                      width: "100%",
                      padding: "7px 10px",
                      borderRadius: 6,
                      border: "1px solid #cbd5e1",
                      fontSize: 13,
                      background: "#ffffff",
                    }}
                  >
                    <option value="none">Use Global Filter Bar</option>
                    <option value="7d">Last 7 Days</option>
                    <option value="28d">Last 28 Days</option>
                    <option value="90d">Last 90 Days</option>
                    <option value="last_month">Last Month</option>
                  </select>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 10, borderTop: "1px solid #f1f5f9", paddingTop: 14 }}>
                <button
                  type="button"
                  onClick={onClose}
                  style={{
                    background: "#f1f5f9",
                    color: "#475569",
                    border: "1px solid #cbd5e1",
                    borderRadius: 6,
                    padding: "7px 14px",
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    background: "#0284c7",
                    color: "#ffffff",
                    border: 0,
                    borderRadius: 6,
                    padding: "7px 18px",
                    fontSize: 13,
                    fontWeight: 700,
                    cursor: "pointer",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.12)",
                  }}
                >
                  {isEditing ? "Save Changes" : "Create Widget"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
