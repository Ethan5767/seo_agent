"use client";

import React, { useState } from "react";
import type { MonitorGlobalFilters, DatePreset, CompareMode } from "@/lib/monitor/types";

interface MonitorFilterBarProps {
  filters: MonitorGlobalFilters;
  onChange: (updated: Partial<MonitorGlobalFilters>) => void;
  // Connection states
  gscConnected: boolean;
  ga4Connected: boolean;
  googleAccount?: string | null;
  // Property selections
  gscProperties: string[];
  selectedGscProperty: string;
  onSelectGscProperty: (prop: string) => void;
  ga4Properties: Array<{ id: string; property: string; displayName: string }>;
  selectedGa4Property: string;
  onSelectGa4Property: (prop: string) => void;
  // Auto refresh
  autoRefreshInterval: "30s" | "60s" | "5m" | "off";
  onAutoRefreshChange: (interval: "30s" | "60s" | "5m" | "off") => void;
  syncCountdown: number;
  onForceSync: () => void;
  isSyncing: boolean;
  onToggleService: (service: "gsc" | "analytics", enabled: boolean) => Promise<void>;
}

const COMMON_CHANNELS = [
  "all",
  "Organic Search",
  "Direct",
  "Referral",
  "Organic Social",
  "Paid Search",
  "Email",
];

const SEARCH_APPEARANCE_OPTIONS = [
  { value: "all", label: "All Appearances" },
  { value: "RICHLIST", label: "Rich Results" },
  { value: "AMP_ARTICLE", label: "AMP Articles" },
  { value: "PRODUCT_RESULTS", label: "Product Snippets" },
  { value: "VIDEO", label: "Video Results" },
  { value: "RECIPE", label: "Recipe Rich Cards" },
];

export function MonitorFilterBar({
  filters,
  onChange,
  gscConnected,
  ga4Connected,
  googleAccount,
  gscProperties,
  selectedGscProperty,
  onSelectGscProperty,
  ga4Properties,
  selectedGa4Property,
  onSelectGa4Property,
  autoRefreshInterval,
  onAutoRefreshChange,
  syncCountdown,
  onForceSync,
  isSyncing,
  onToggleService,
}: MonitorFilterBarProps) {
  const [showCustomDates, setShowCustomDates] = useState(filters.datePreset === "custom");
  const [customStart, setCustomStart] = useState(filters.startDate);
  const [customEnd, setCustomEnd] = useState(filters.endDate);

  const handlePresetClick = (preset: DatePreset) => {
    if (preset === "custom") {
      setShowCustomDates(true);
      onChange({ datePreset: "custom", startDate: customStart, endDate: customEnd });
    } else {
      setShowCustomDates(false);
      onChange({ datePreset: preset });
    }
  };

  const handleApplyCustomDates = () => {
    if (customStart && customEnd && customStart <= customEnd) {
      onChange({ datePreset: "custom", startDate: customStart, endDate: customEnd });
    }
  };

  const hasActiveFilters =
    filters.deviceFilter !== "all" ||
    filters.countryFilter !== "all" ||
    Boolean(filters.pageFilter.trim()) ||
    filters.searchAppearanceFilter !== "all" ||
    filters.channelFilter !== "all";

  const handleResetFilters = () => {
    onChange({
      deviceFilter: "all",
      countryFilter: "all",
      pageFilter: "",
      searchAppearanceFilter: "all",
      channelFilter: "all",
    });
  };

  return (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid #e2e8f0",
        borderRadius: 10,
        padding: "14px 18px",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
      }}
    >
      {/* ── Top Row: Connections & Property Pickers & Sync ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
        {/* Connection status badges */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {/* GSC Status Badge */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              padding: "4px 10px",
              borderRadius: 6,
              background: gscConnected ? "#f0fdf4" : "#fef2f2",
              border: `1px solid ${gscConnected ? "#bbf7d0" : "#fecaca"}`,
              color: gscConnected ? "#166534" : "#991b1b",
              fontWeight: 600,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: gscConnected ? "#10b981" : "#ef4444",
                boxShadow: gscConnected ? "0 0 5px #10b981" : "none",
              }}
            />
            <span>Search Console: {gscConnected ? "Active" : "Disconnected"}</span>
            <button
              type="button"
              onClick={() => onToggleService("gsc", !gscConnected)}
              style={{
                background: "transparent",
                border: 0,
                color: gscConnected ? "#dc2626" : "#0284c7",
                fontSize: 11,
                cursor: "pointer",
                textDecoration: "underline",
                padding: "0 2px",
                fontWeight: 600,
              }}
              title={gscConnected ? "Disconnect GSC to test degraded state" : "Reconnect GSC"}
            >
              ({gscConnected ? "Disconnect" : "Connect"})
            </button>
          </div>

          {/* GA4 Status Badge */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              padding: "4px 10px",
              borderRadius: 6,
              background: ga4Connected ? "#f0fdf4" : "#fef2f2",
              border: `1px solid ${ga4Connected ? "#bbf7d0" : "#fecaca"}`,
              color: ga4Connected ? "#166534" : "#991b1b",
              fontWeight: 600,
            }}
          >
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: ga4Connected ? "#10b981" : "#ef4444",
                boxShadow: ga4Connected ? "0 0 5px #10b981" : "none",
              }}
            />
            <span>GA4 Analytics: {ga4Connected ? "Active" : "Disconnected"}</span>
            <button
              type="button"
              onClick={() => onToggleService("analytics", !ga4Connected)}
              style={{
                background: "transparent",
                border: 0,
                color: ga4Connected ? "#dc2626" : "#0284c7",
                fontSize: 11,
                cursor: "pointer",
                textDecoration: "underline",
                padding: "0 2px",
                fontWeight: 600,
              }}
              title={ga4Connected ? "Disconnect GA4 to test degraded state" : "Reconnect GA4"}
            >
              ({ga4Connected ? "Disconnect" : "Connect"})
            </button>
          </div>

          {googleAccount && (
            <span style={{ fontSize: 12, color: "var(--ink-muted)", marginLeft: 2 }}>
              Account: <strong style={{ color: "#334155" }}>{googleAccount}</strong>
            </span>
          )}
        </div>

        {/* Sync and Interval Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              background: autoRefreshInterval !== "off" ? "#f0fdf4" : "#f8fafc",
              border: `1px solid ${autoRefreshInterval !== "off" ? "#bbf7d0" : "#e2e8f0"}`,
              padding: "3px 8px",
              borderRadius: 6,
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: autoRefreshInterval !== "off" ? "#10b981" : "#94a3b8",
              }}
            />
            <span style={{ color: autoRefreshInterval !== "off" ? "#166534" : "var(--ink-muted)", fontWeight: 600 }}>
              {autoRefreshInterval !== "off" ? `Syncing in ${syncCountdown}s` : "Auto-refresh off"}
            </span>
            <select
              value={autoRefreshInterval}
              onChange={(e) => onAutoRefreshChange(e.target.value as any)}
              style={{
                background: "#ffffff",
                border: "1px solid #cbd5e1",
                borderRadius: 4,
                padding: "1px 4px",
                fontSize: 11.5,
                fontWeight: 600,
                color: "#1e293b",
                cursor: "pointer",
              }}
            >
              <option value="30s">30s</option>
              <option value="60s">60s</option>
              <option value="5m">5m</option>
              <option value="off">Off</option>
            </select>
            <button
              type="button"
              onClick={onForceSync}
              disabled={isSyncing}
              style={{
                background: "transparent",
                border: 0,
                cursor: isSyncing ? "wait" : "pointer",
                fontSize: 12,
                color: "var(--ok)",
                padding: "0 2px",
                fontWeight: 700,
              }}
              title="Force sync now"
            >
              {isSyncing ? "⏳" : "🔄"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Middle Row: Properties & Date Presets & Comparison ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, borderTop: "1px solid #f1f5f9", paddingTop: 10 }}>
        {/* Property Selectors */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          {gscConnected && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>GSC Site:</span>
              <select
                value={selectedGscProperty}
                onChange={(e) => onSelectGscProperty(e.target.value)}
                style={{
                  background: "#f8fafc",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  padding: "4px 8px",
                  fontSize: 12,
                  fontWeight: 600,
                  color: "#0f172a",
                  maxWidth: 220,
                }}
              >
                {gscProperties.length > 0 ? (
                  gscProperties.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))
                ) : (
                  <option value={selectedGscProperty}>{selectedGscProperty || "No GSC Site"}</option>
                )}
              </select>
            </div>
          )}

          {ga4Connected && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>GA4 Property:</span>
              <select
                value={selectedGa4Property}
                onChange={(e) => onSelectGa4Property(e.target.value)}
                style={{
                  background: "#f8fafc",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  padding: "4px 8px",
                  fontSize: 12,
                  fontWeight: 600,
                  color: "#0f172a",
                  maxWidth: 220,
                }}
              >
                {ga4Properties.length > 0 ? (
                  ga4Properties.map((p) => (
                    <option key={p.id} value={p.property}>
                      {p.displayName} ({p.id})
                    </option>
                  ))
                ) : (
                  <option value={selectedGa4Property}>{selectedGa4Property || "Auto-detected GA4"}</option>
                )}
              </select>
            </div>
          )}
        </div>

        {/* Date Presets Pill Group */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Date Range:</span>
          {(["7d", "28d", "90d", "last_month", "custom"] as const).map((preset) => {
            const isSelected = filters.datePreset === preset;
            const labels: Record<string, string> = {
              "7d": "Last 7d",
              "28d": "Last 28d",
              "90d": "Last 90d",
              "last_month": "Last Month",
              "custom": "Custom",
            };
            return (
              <button
                key={preset}
                type="button"
                onClick={() => handlePresetClick(preset)}
                style={{
                  background: isSelected ? "#0284c7" : "#f1f5f9",
                  color: isSelected ? "#ffffff" : "#475569",
                  border: `1px solid ${isSelected ? "#0284c7" : "#e2e8f0"}`,
                  borderRadius: 5,
                  padding: "4px 9px",
                  fontSize: 11.5,
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                {labels[preset]}
              </button>
            );
          })}

          {/* Comparison Toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 8 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Compare:</span>
            <select
              value={filters.compareMode}
              onChange={(e) => onChange({ compareMode: e.target.value as CompareMode })}
              style={{
                background: "#f8fafc",
                border: "1px solid #cbd5e1",
                borderRadius: 5,
                padding: "3px 8px",
                fontSize: 12,
                fontWeight: 600,
                color: "#1e293b",
                cursor: "pointer",
              }}
            >
              <option value="none">No comparison</option>
              <option value="previous_period">vs Previous period</option>
              <option value="previous_year">vs Same period last year</option>
            </select>
          </div>
        </div>
      </div>

      {/* Custom Date Inputs (only when Custom preset is selected) */}
      {showCustomDates && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#f8fafc", padding: "8px 12px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
          <span style={{ fontSize: 12, color: "#475569", fontWeight: 600 }}>From:</span>
          <input
            type="date"
            value={customStart}
            onChange={(e) => setCustomStart(e.target.value)}
            style={{ padding: "3px 8px", fontSize: 12, borderRadius: 4, border: "1px solid #cbd5e1" }}
          />
          <span style={{ fontSize: 12, color: "#475569", fontWeight: 600 }}>To:</span>
          <input
            type="date"
            value={customEnd}
            onChange={(e) => setCustomEnd(e.target.value)}
            style={{ padding: "3px 8px", fontSize: 12, borderRadius: 4, border: "1px solid #cbd5e1" }}
          />
          <button
            type="button"
            onClick={handleApplyCustomDates}
            style={{
              background: "#0284c7",
              color: "#ffffff",
              border: 0,
              borderRadius: 4,
              padding: "4px 10px",
              fontSize: 11.5,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Apply Range
          </button>
        </div>
      )}

      {/* ── Bottom Row: Global Dimension Filters ── */}
      <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10, borderTop: "1px solid #f1f5f9", paddingTop: 10, fontSize: 12 }}>
        <span style={{ fontWeight: 700, color: "#64748b", textTransform: "uppercase", fontSize: 11, letterSpacing: "0.04em" }}>
          Global Filters:
        </span>

        {/* Device Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ color: "#64748b" }}>Device:</span>
          <select
            value={filters.deviceFilter}
            onChange={(e) => onChange({ deviceFilter: e.target.value as any })}
            style={{
              background: filters.deviceFilter !== "all" ? "#eff6ff" : "#f8fafc",
              border: `1px solid ${filters.deviceFilter !== "all" ? "#bfdbfe" : "#cbd5e1"}`,
              borderRadius: 5,
              padding: "3px 7px",
              fontSize: 11.5,
              fontWeight: 600,
              color: filters.deviceFilter !== "all" ? "#1d4ed8" : "#334155",
            }}
          >
            <option value="all">All Devices</option>
            <option value="desktop">Desktop</option>
            <option value="mobile">Mobile</option>
            <option value="tablet">Tablet</option>
          </select>
        </div>

        {/* Country Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ color: "#64748b" }}>Country:</span>
          <select
            value={filters.countryFilter}
            onChange={(e) => onChange({ countryFilter: e.target.value })}
            style={{
              background: filters.countryFilter !== "all" ? "#eff6ff" : "#f8fafc",
              border: `1px solid ${filters.countryFilter !== "all" ? "#bfdbfe" : "#cbd5e1"}`,
              borderRadius: 5,
              padding: "3px 7px",
              fontSize: 11.5,
              fontWeight: 600,
              color: filters.countryFilter !== "all" ? "#1d4ed8" : "#334155",
            }}
          >
            <option value="all">All Countries</option>
            <option value="usa">🇺🇸 United States</option>
            <option value="gbr">🇬🇧 United Kingdom</option>
            <option value="can">🇨🇦 Canada</option>
            <option value="aus">🇦🇺 Australia</option>
            <option value="deu">🇩🇪 Germany</option>
            <option value="fra">🇫🇷 France</option>
            <option value="ind">🇮🇳 India</option>
            <option value="idn">🇮🇩 Indonesia</option>
            <option value="bra">🇧🇷 Brazil</option>
            <option value="sgp">🇸🇬 Singapore</option>
          </select>
        </div>

        {/* Page / Segment URL Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ color: "#64748b" }}>URL / Page:</span>
          <input
            type="text"
            placeholder="e.g. /blog or pricing"
            value={filters.pageFilter}
            onChange={(e) => onChange({ pageFilter: e.target.value })}
            style={{
              background: filters.pageFilter.trim() ? "#eff6ff" : "#f8fafc",
              border: `1px solid ${filters.pageFilter.trim() ? "#bfdbfe" : "#cbd5e1"}`,
              borderRadius: 5,
              padding: "3px 7px",
              fontSize: 11.5,
              width: 140,
              color: "#0f172a",
            }}
          />
        </div>

        {/* GSC Search Appearance Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 4, opacity: gscConnected ? 1 : 0.45 }}>
          <span style={{ color: "#64748b" }}>Search Type:</span>
          <select
            disabled={!gscConnected}
            title={gscConnected ? "Filter by Search Appearance" : "Connect Search Console to filter by appearance"}
            value={filters.searchAppearanceFilter}
            onChange={(e) => onChange({ searchAppearanceFilter: e.target.value })}
            style={{
              background: !gscConnected ? "#f1f5f9" : filters.searchAppearanceFilter !== "all" ? "#eff6ff" : "#f8fafc",
              border: `1px solid ${filters.searchAppearanceFilter !== "all" && gscConnected ? "#bfdbfe" : "#cbd5e1"}`,
              borderRadius: 5,
              padding: "3px 7px",
              fontSize: 11.5,
              fontWeight: 600,
              color: filters.searchAppearanceFilter !== "all" && gscConnected ? "#1d4ed8" : "#334155",
              cursor: gscConnected ? "pointer" : "not-allowed",
            }}
          >
            {SEARCH_APPEARANCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* GA4 Channel Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 4, opacity: ga4Connected ? 1 : 0.45 }}>
          <span style={{ color: "#64748b" }}>GA4 Channel:</span>
          <select
            disabled={!ga4Connected}
            title={ga4Connected ? "Filter by Traffic Channel" : "Connect Google Analytics 4 to filter by channel"}
            value={filters.channelFilter}
            onChange={(e) => onChange({ channelFilter: e.target.value })}
            style={{
              background: !ga4Connected ? "#f1f5f9" : filters.channelFilter !== "all" ? "#eff6ff" : "#f8fafc",
              border: `1px solid ${filters.channelFilter !== "all" && ga4Connected ? "#bfdbfe" : "#cbd5e1"}`,
              borderRadius: 5,
              padding: "3px 7px",
              fontSize: 11.5,
              fontWeight: 600,
              color: filters.channelFilter !== "all" && ga4Connected ? "#1d4ed8" : "#334155",
              cursor: ga4Connected ? "pointer" : "not-allowed",
            }}
          >
            {COMMON_CHANNELS.map((ch) => (
              <option key={ch} value={ch}>
                {ch === "all" ? "All Channels" : ch}
              </option>
            ))}
          </select>
        </div>

        {/* Reset Filters button if any active */}
        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleResetFilters}
            style={{
              background: "#fee2e2",
              color: "#dc2626",
              border: "1px solid #fca5a5",
              borderRadius: 5,
              padding: "2px 7px",
              fontSize: 11,
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            ✕ Clear Filters
          </button>
        )}
      </div>
    </div>
  );
}
