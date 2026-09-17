"use client";

import React, { useState, useEffect, useCallback } from "react";
import type {
  MonitorGlobalFilters,
  MonitorWidget as MonitorWidgetType,
} from "@/lib/monitor/types";
import {
  computeDateRange,
  loadMonitorLayout,
  saveMonitorLayout,
  resetMonitorLayout,
} from "@/lib/monitor/types";
import { fetchWidgetGscData, fetchWidgetGa4Data } from "@/lib/monitor/fetcher";
import { deleteWidget, moveWidget, saveWidget } from "@/lib/monitor/layout";
import { MonitorFilterBar } from "./MonitorFilterBar";
import { MonitorWidget } from "./MonitorWidget";
import { MonitorWidgetModal } from "./MonitorWidgetModal";
import { authedFetch } from "@/lib/authedFetch";
import { IconGoogle } from "@/components/dashboard/icons";

export interface MonitorScreenProps {
  currentDomain: string;
  currentBusiness?: string;
  googleConnected: boolean;
  googleAccount?: string | null;
  handleConnectGoogle: () => void;
  googleConnecting?: boolean;
  verifiedGscProperties?: string[];
  selectedGscProperty?: string;
  setSelectedGscProperty?: (prop: string) => void;
}

export function MonitorScreen({
  currentDomain,
  currentBusiness = "this project",
  googleConnected,
  googleAccount,
  handleConnectGoogle,
  googleConnecting = false,
  verifiedGscProperties = [],
  selectedGscProperty = "",
  setSelectedGscProperty,
}: MonitorScreenProps) {
  // GSC & GA4 Connection state
  const [gscConnected, setGscConnected] = useState<boolean>(googleConnected);
  const [ga4Connected, setGa4Connected] = useState<boolean>(googleConnected);
  const [ga4Properties, setGa4Properties] = useState<Array<{ id: string; property: string; displayName: string }>>([]);
  const [selectedGa4Prop, setSelectedGa4Prop] = useState<string>("");

  // Global filters
  const initialDates = computeDateRange("28d", "none");
  const [filters, setFilters] = useState<MonitorGlobalFilters>({
    datePreset: "28d",
    startDate: initialDates.startDate,
    endDate: initialDates.endDate,
    compareMode: "none",
    compareStartDate: initialDates.compareStartDate,
    compareEndDate: initialDates.compareEndDate,
    deviceFilter: "all",
    countryFilter: "all",
    pageFilter: "",
    searchAppearanceFilter: "all",
    channelFilter: "all",
  });

  // Custom Widgets Layout
  const [widgets, setWidgets] = useState<MonitorWidgetType[]>([]);
  const [widgetData, setWidgetData] = useState<Record<string, { isLoading: boolean; data: any }>>({});

  // Auto Refresh
  const [autoRefreshInterval, setAutoRefreshInterval] = useState<"30s" | "60s" | "5m" | "off">("off");
  const [syncCountdown, setSyncCountdown] = useState<number>(30);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);

  // Modals
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [editingWidget, setEditingWidget] = useState<MonitorWidgetType | null>(null);

  // Active GSC property fallback
  const activeGscProp = selectedGscProperty || (verifiedGscProperties[0] ?? `sc-domain:${currentDomain}`);

  // Fetch GA4 Properties
  const fetchGa4Properties = useCallback(async () => {
    try {
      const res = await authedFetch("/api/ga4/properties");
      if (res.ok) {
        const json = await res.json();
        if (Array.isArray(json?.properties) && json.properties.length > 0) {
          setGa4Properties(json.properties);
          const savedProp = typeof window !== "undefined" ? localStorage.getItem(`reai_ga4_prop_${currentDomain}`) : null;
          const chosen = savedProp && json.properties.some((p: any) => p.property === savedProp)
            ? savedProp
            : json.properties[0].property;
          setSelectedGa4Prop(chosen);
        }
      }
    } catch {
      // Non-critical
    }
  }, [currentDomain]);

  // Check Google services connection status
  const refreshGoogleStatus = useCallback(async () => {
    try {
      const res = await authedFetch("/api/auth/google/status");
      if (res.ok) {
        const json = await res.json();
        setGscConnected(Boolean(json?.services?.searchConsole?.connected));
        setGa4Connected(Boolean(json?.services?.analytics?.connected));
        if (json?.services?.analytics?.connected) {
          fetchGa4Properties();
        }
      }
    } catch {
      setGscConnected(googleConnected);
      setGa4Connected(googleConnected);
    }
  }, [googleConnected, fetchGa4Properties]);

  useEffect(() => {
    refreshGoogleStatus();
  }, [refreshGoogleStatus]);

  // Load custom layout from localStorage
  useEffect(() => {
    const loaded = loadMonitorLayout(currentDomain);
    setWidgets(loaded);
  }, [currentDomain]);

  // Fetch data for a single widget
  const fetchSingleWidget = useCallback(
    async (w: MonitorWidgetType) => {
      setWidgetData((prev) => ({
        ...prev,
        [w.id]: { isLoading: true, data: prev[w.id]?.data || null },
      }));

      try {
        if (w.source === "gsc") {
          const res = await fetchWidgetGscData(activeGscProp, w, filters);
          if (!res.ok) {
            setWidgetData((prev) => ({
              ...prev,
              [w.id]: { isLoading: false, data: { error: res.error } },
            }));
            return;
          }

          const mappedData: any = { source: "gsc" };

          if (w.chartType === "stat") {
            const m = w.metric;
            mappedData.statCurrent = res.totals[m as keyof typeof res.totals] ?? 0;
            mappedData.statPrevious = res.comparisonTotals ? res.comparisonTotals[m as keyof typeof res.totals] ?? 0 : 0;
            mappedData.statTrend = res.rows.slice(0, 15).map((r) => r[m as keyof typeof r] ?? 0);
          } else if (w.chartType === "line") {
            mappedData.lineSeries = res.rows.map((r, idx) => ({
              date: r.key,
              value: r[w.metric as keyof typeof r] as number ?? 0,
              secondaryValue: w.secondaryMetric ? (r[w.secondaryMetric as keyof typeof r] as number ?? 0) : undefined,
              compareValue: res.comparisonRows?.[idx]
                ? (res.comparisonRows[idx][w.metric as keyof typeof r] as number ?? 0)
                : undefined,
            }));
          } else if (w.chartType === "bar") {
            mappedData.barSeries = res.rows.map((r, idx) => ({
              label: r.key,
              value: r[w.metric as keyof typeof r] as number ?? 0,
              compareValue: res.comparisonRows?.[idx]
                ? (res.comparisonRows[idx][w.metric as keyof typeof r] as number ?? 0)
                : undefined,
            }));
          } else if (w.chartType === "donut") {
            mappedData.donutSeries = res.rows.map((r) => ({
              label: r.key,
              value: r[w.metric as keyof typeof r] as number ?? 0,
            }));
          } else if (w.chartType === "table") {
            mappedData.tableRows = res.rows;
          }

          setWidgetData((prev) => ({
            ...prev,
            [w.id]: { isLoading: false, data: mappedData },
          }));
        } else {
          // GA4
          const res = await fetchWidgetGa4Data(selectedGa4Prop, w, filters);
          if (!res.ok) {
            setWidgetData((prev) => ({
              ...prev,
              [w.id]: { isLoading: false, data: { error: res.error } },
            }));
            return;
          }

          const mappedData: any = { source: "ga4" };
          const m = w.metric;

          if (w.chartType === "stat") {
            mappedData.statCurrent = res.totals[m] ?? 0;
            mappedData.statPrevious = res.comparisonTotals?.[m] ?? 0;
            mappedData.statTrend = res.rows.slice(0, 15).map((r) => r.metrics[m] ?? 0);
          } else if (w.chartType === "line") {
            mappedData.lineSeries = res.rows.map((r, idx) => ({
              date: r.key,
              value: r.metrics[m] ?? 0,
              secondaryValue: w.secondaryMetric ? r.metrics[w.secondaryMetric] ?? 0 : undefined,
              compareValue: res.comparisonRows?.[idx] ? res.comparisonRows[idx].metrics[m] ?? 0 : undefined,
            }));
          } else if (w.chartType === "bar") {
            mappedData.barSeries = res.rows.map((r, idx) => ({
              label: r.key,
              value: r.metrics[m] ?? 0,
              compareValue: res.comparisonRows?.[idx] ? res.comparisonRows[idx].metrics[m] ?? 0 : undefined,
            }));
          } else if (w.chartType === "donut") {
            mappedData.donutSeries = res.rows.map((r) => ({
              label: r.key,
              value: r.metrics[m] ?? 0,
            }));
          } else if (w.chartType === "funnel") {
            // A funnel is useful only when every stage came from GA4.  Do not
            // turn a zero or absent metric into a plausible-looking estimate.
            const reportedTotal = (name: string) => {
              const value = res.totals[name];
              return typeof value === "number" && Number.isFinite(value) ? value : 0;
            };
            mappedData.funnelStages = [
              { name: "Total Sessions", count: reportedTotal("sessions"), description: "GA4-reported sessions" },
              { name: "Engaged Sessions", count: reportedTotal("engagedSessions"), description: "GA4-reported engaged sessions" },
              { name: "Conversions", count: reportedTotal("conversions"), description: "GA4-reported conversion events" },
            ];
          } else if (w.chartType === "table") {
            mappedData.tableRows = res.rows.map((r) => ({
              key: r.key,
              sessions: r.metrics["sessions"] ?? 0,
              engagementRate: r.metrics["engagementRate"] ?? 0,
              conversions: r.metrics["conversions"] ?? 0,
            }));
          }

          setWidgetData((prev) => ({
            ...prev,
            [w.id]: { isLoading: false, data: mappedData },
          }));
        }
      } catch (err: any) {
        setWidgetData((prev) => ({
          ...prev,
          [w.id]: { isLoading: false, data: { error: err?.message || "Failed to load data" } },
        }));
      }
    },
    [activeGscProp, selectedGa4Prop, filters],
  );

  // Refetch all widgets when filters, GSC property, or GA4 property change
  const refreshAllWidgets = useCallback(async () => {
    if (widgets.length === 0) return;
    setIsSyncing(true);
    await Promise.all(widgets.map((w) => fetchSingleWidget(w)));
    setIsSyncing(false);
  }, [widgets, fetchSingleWidget]);

  useEffect(() => {
    refreshAllWidgets();
  }, [refreshAllWidgets]);

  const handleFilterChange = (updated: Partial<MonitorGlobalFilters>) => {
    const nextPreset = updated.datePreset || filters.datePreset;
    const nextCompare = updated.compareMode !== undefined ? updated.compareMode : filters.compareMode;
    const computed = computeDateRange(nextPreset, nextCompare, updated.startDate, updated.endDate);

    setFilters((prev) => ({
      ...prev,
      ...updated,
      startDate: computed.startDate,
      endDate: computed.endDate,
      compareStartDate: computed.compareStartDate,
      compareEndDate: computed.compareEndDate,
    }));
  };

  const handleMoveWidget = (index: number, direction: "left" | "right") => {
    const next = moveWidget(widgets, index, direction);
    if (next === widgets) return;
    setWidgets(next);
    saveMonitorLayout(currentDomain, next);
  };

  const handleSaveWidget = (savedWidget: MonitorWidgetType) => {
    const next = saveWidget(widgets, savedWidget);
    setWidgets(next);
    saveMonitorLayout(currentDomain, next);
    fetchSingleWidget(savedWidget);
  };

  const handleDeleteWidget = (id: string) => {
    const next = deleteWidget(widgets, id);
    setWidgets(next);
    saveMonitorLayout(currentDomain, next);
  };

  const handleResetLayout = () => {
    if (typeof window !== "undefined" && !window.confirm("Reset dashboard layout to default widgets?")) {
      return;
    }
    const def = resetMonitorLayout(currentDomain);
    setWidgets(def);
  };

  const handleToggleService = async (service: "gsc" | "analytics", enable: boolean) => {
    try {
      if (enable) {
        await authedFetch(`/api/auth/google/status?service=${service}`, { method: "POST" });
      } else {
        await authedFetch(`/api/auth/google/status?service=${service}`, { method: "DELETE" });
      }
      await refreshGoogleStatus();
    } catch {
      // Ignore
    }
  };

  useEffect(() => {
    if (autoRefreshInterval === "off") return;
    const intervalSec = autoRefreshInterval === "30s" ? 30 : autoRefreshInterval === "60s" ? 60 : 300;
    setSyncCountdown(intervalSec);

    const timer = setInterval(() => {
      setSyncCountdown((prev) => {
        if (prev <= 1) {
          refreshAllWidgets();
          return intervalSec;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [autoRefreshInterval, refreshAllWidgets]);

  const neitherConnected = !gscConnected && !ga4Connected;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* ── Top Workspace Header ── */}
      <div
        style={{
          background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
          borderRadius: 10,
          padding: "16px 20px",
          color: "#ffffff",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 14,
          boxShadow: "0 2px 8px rgba(15, 23, 42, 0.15)",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <h1 style={{ margin: 0, fontSize: 19, fontWeight: 800, letterSpacing: "-0.01em" }}>
              Monitor Stage: Verified GSC & GA4 Analytics
            </h1>
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                background: "#0369a1",
                color: "#e0f2fe",
                padding: "2px 7px",
                borderRadius: 4,
              }}
            >
              Stage 6
            </span>
          </div>
          <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "#94a3b8", maxWidth: 650, lineHeight: 1.4 }}>
            Direct first-party data from your connected Google Search Console and GA4 properties for <b>{currentDomain}</b>.
            No third-party estimations or mock metrics.
          </p>
        </div>

        {/* Header Action Buttons */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <button
            type="button"
            onClick={() => {
              setEditingWidget(null);
              setIsModalOpen(true);
            }}
            style={{
              background: "#0284c7",
              color: "#ffffff",
              border: 0,
              borderRadius: 6,
              padding: "8px 14px",
              fontSize: 12.5,
              fontWeight: 700,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
              boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
            }}
          >
            <span>+ Add Widget</span>
          </button>

          <button
            type="button"
            onClick={handleResetLayout}
            style={{
              background: "#334155",
              color: "#e2e8f0",
              border: "1px solid #475569",
              borderRadius: 6,
              padding: "8px 12px",
              fontSize: 12,
              fontWeight: 600,
              cursor: "pointer",
            }}
            title="Reset to default widget set"
          >
            Reset Layout
          </button>
        </div>
      </div>

      {/* ── Entry State when NEITHER GSC nor GA4 is connected ── */}
      {neitherConnected ? (
        <div
          style={{
            background: "#ffffff",
            borderRadius: 12,
            border: "1px solid #e2e8f0",
            padding: "48px 24px",
            textAlign: "center",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 16,
            boxShadow: "0 1px 3px rgba(0,0,0,0.02)",
          }}
        >
          <div
            style={{
              width: 58,
              height: 58,
              borderRadius: 16,
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              display: "grid",
              placeItems: "center",
            }}
          >
            <IconGoogle size={32} />
          </div>
          <div style={{ maxWidth: 580 }}>
            <h2 style={{ margin: "0 0 8px 0", fontSize: 18, fontWeight: 800, color: "#0f172a" }}>
              Unlock Verified First-Party Analytics for {currentDomain}
            </h2>
            <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-muted)", lineHeight: 1.6 }}>
              The Monitor stage is powered by Google Search Console and GA4 data only. Connecting your Google account unlocks exact organic search clicks, search appearance rankings, engaged session times, and conversion tracking — with zero estimated or synthetic data.
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, maxWidth: 580, textAlign: "left", width: "100%", marginTop: 8 }}>
            <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <strong style={{ fontSize: 13, color: "#0369a1" }}>✓ Google Search Console</strong>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                Exact organic search queries, impression share, click-through rates, and rich result appearances.
              </div>
            </div>
            <div style={{ background: "#f8fafc", padding: "12px 14px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <strong style={{ fontSize: 13, color: "#7c3aed" }}>✓ Google Analytics 4</strong>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                Real user session funnels, channel attribution, bounce and engagement rates, and custom conversion events.
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={handleConnectGoogle}
            disabled={googleConnecting}
            style={{
              marginTop: 10,
              background: "#0f172a",
              color: "#ffffff",
              border: 0,
              borderRadius: 8,
              padding: "11px 24px",
              fontSize: 13.5,
              fontWeight: 700,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 9,
              boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
            }}
          >
            <IconGoogle size={16} />
            <span>{googleConnecting ? "Connecting to Google..." : "Connect Google Account →"}</span>
          </button>
        </div>
      ) : (
        <>
          {/* ── Global Filter Bar ── */}
          <MonitorFilterBar
            filters={filters}
            onChange={handleFilterChange}
            gscConnected={gscConnected}
            ga4Connected={ga4Connected}
            googleAccount={googleAccount}
            gscProperties={verifiedGscProperties}
            selectedGscProperty={activeGscProp}
            onSelectGscProperty={(prop) => {
              if (setSelectedGscProperty) setSelectedGscProperty(prop);
              if (typeof window !== "undefined") localStorage.setItem("reai_gsc_property", prop);
            }}
            ga4Properties={ga4Properties}
            selectedGa4Property={selectedGa4Prop}
            onSelectGa4Property={(prop) => {
              setSelectedGa4Prop(prop);
              if (typeof window !== "undefined") localStorage.setItem(`reai_ga4_prop_${currentDomain}`, prop);
            }}
            autoRefreshInterval={autoRefreshInterval}
            onAutoRefreshChange={(inv) => setAutoRefreshInterval(inv)}
            syncCountdown={syncCountdown}
            onForceSync={refreshAllWidgets}
            isSyncing={isSyncing}
            onToggleService={handleToggleService}
          />

          {/* ── Responsive Customizable Widget Grid ── */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(12, 1fr)",
              gap: 14,
            }}
          >
            {widgets.map((widget, idx) => (
              <MonitorWidget
                key={widget.id}
                widget={widget}
                index={idx}
                totalWidgets={widgets.length}
                onMove={handleMoveWidget}
                onEdit={(w) => {
                  setEditingWidget(w);
                  setIsModalOpen(true);
                }}
                onDelete={handleDeleteWidget}
                gscConnected={gscConnected}
                ga4Connected={ga4Connected}
                onConnectGsc={handleConnectGoogle}
                onConnectGa4={handleConnectGoogle}
                isLoading={widgetData[widget.id]?.isLoading ?? true}
                data={widgetData[widget.id]?.data}
                hasComparison={filters.compareMode !== "none"}
                comparisonLabel={filters.compareMode === "previous_year" ? "Same period last year" : "Previous period"}
              />
            ))}
          </div>
        </>
      )}

      {/* ── Add / Edit Widget Modal ── */}
      <MonitorWidgetModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingWidget(null);
        }}
        onSaveWidget={handleSaveWidget}
        initialWidget={editingWidget}
      />
    </div>
  );
}
