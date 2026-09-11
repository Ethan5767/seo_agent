"use client";

import React, { useEffect } from "react";
import type { ReaiTab, NavSubTab } from "./types";

interface SidebarProps {
  activeTab: ReaiTab;
  onSelectTab: (tab: ReaiTab, subTab?: NavSubTab) => void;
  activeSubTab?: NavSubTab;
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
  totalToolsCount?: number;
}

export function Sidebar({
  activeTab,
  onSelectTab,
  activeSubTab,
  isMobileOpen = false,
  onCloseMobile,
  totalToolsCount = 160,
}: SidebarProps) {
  // Close mobile drawer on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isMobileOpen && onCloseMobile) {
        onCloseMobile();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isMobileOpen, onCloseMobile]);

  const handleItemClick = (tab: ReaiTab, subTab?: NavSubTab) => {
    onSelectTab(tab, subTab);
    if (onCloseMobile) onCloseMobile();
  };

  const [activeBigNav, setActiveBigNav] = React.useState<"Home" | "SEO" | "AI" | "Traffic" | "Local" | "Content" | "Reports" | "Tools">("SEO");
  const [isSmallCollapsed, setIsSmallCollapsed] = React.useState<boolean>(false);

  return (
    <>
      {/* Mobile Backdrop */}
      {isMobileOpen && (
        <div
          role="presentation"
          onClick={onCloseMobile}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.4)",
            backdropFilter: "blur(2px)",
            zIndex: 40,
            display: "block",
          }}
        />
      )}

      {/* Main Dual Sidebar Container */}
      <div
        style={{
          display: "flex",
          height: "100%",
          flexShrink: 0,
          position: isMobileOpen ? "fixed" : "relative",
          left: isMobileOpen ? 0 : "auto",
          top: isMobileOpen ? 0 : "auto",
          bottom: isMobileOpen ? 0 : "auto",
          zIndex: isMobileOpen ? 50 : 10,
          boxShadow: isMobileOpen ? "4px 0 24px rgba(0,0,0,0.15)" : "none",
        }}
      >
        {/* ── BIG SIDEBAR (PRIMARY RAIL - SEMRUSH STYLE) ── */}
        <aside
          aria-label="Primary Navigation Rail"
          style={{
            width: 64,
            background: "#ffffff",
            borderRight: "1px solid #e2e8f0",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "12px 4px",
            flexShrink: 0,
            boxSizing: "border-box",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%", alignItems: "center" }}>
            {[
              { id: "Home" as const, label: "Home", icon: "🏠", action: () => { setActiveBigNav("SEO"); handleItemClick("Overview"); } },
              { id: "SEO" as const, label: "SEO", icon: "🔍", action: () => { setActiveBigNav("SEO"); handleItemClick("Overview"); } },
              { id: "AI" as const, label: "AI", icon: "✨", action: () => { setActiveBigNav("AI"); handleItemClick("AI & AEO Lab", "AI Readiness"); } },
              { id: "Traffic" as const, label: "Traffic", icon: "📊", action: () => { setActiveBigNav("Traffic"); handleItemClick("Traffic Analytics"); } },
              { id: "Local" as const, label: "Local", icon: "📍", action: () => { setActiveBigNav("Local"); handleItemClick("Local SEO & GBP"); } },
              { id: "Content" as const, label: "Content", icon: "📄", action: () => { setActiveBigNav("Content"); handleItemClick("SERP Optimizer"); } },
              { id: "Reports" as const, label: "Reports", icon: "📈", action: () => { setActiveBigNav("Reports"); handleItemClick("Traffic Analytics", "Reports"); } },
              { id: "Tools" as const, label: "Apps", icon: "🗂️", action: () => { setActiveBigNav("Tools"); handleItemClick("All Tools Directory"); } },
            ].map((rail) => {
              const isSelected = activeBigNav === rail.id;
              return (
                <button
                  key={rail.id}
                  type="button"
                  onClick={() => {
                    rail.action();
                    setIsSmallCollapsed(false);
                  }}
                  title={rail.label}
                  style={{
                    width: 52,
                    height: 48,
                    borderRadius: 8,
                    border: 0,
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 2,
                    background: isSelected ? "#f1f5f9" : "transparent",
                    color: isSelected ? "#0f172a" : "var(--ink-muted)",
                    transition: "all 0.15s ease",
                  }}
                >
                  <span style={{ fontSize: 16 }}>{rail.icon}</span>
                  <span style={{ fontSize: 12, fontWeight: isSelected ? 700 : 500 }}>{rail.label}</span>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={() => setIsSmallCollapsed(!isSmallCollapsed)}
            style={{
              width: 38,
              height: 30,
              borderRadius: 6,
              border: "1px solid #e2e8f0",
              background: "#ffffff",
              color: "var(--ink-muted)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 13,
              fontWeight: 700,
            }}
          >
            {isSmallCollapsed ? "»" : "«"}
          </button>
        </aside>

        {/* ── SMALL SIDEBAR (CONTEXTUAL DRAWER - SEMRUSH STYLE) ── */}
        {!isSmallCollapsed && (
          <aside
            aria-label="Main Navigation"
            style={{
              width: 210,
              background: "#ffffff",
              borderRight: "1px solid #e2e8f0",
              display: "flex",
              flexDirection: "column",
              flexShrink: 0,
              height: "100%",
            }}
          >
        {/* Brand / Logo */}
        <div
          style={{
            padding: "16px 18px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div
              style={{
                width: 26,
                height: 26,
                borderRadius: 6,
                background: "linear-gradient(135deg, #2563eb, #7c3aed)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#ffffff",
                fontWeight: 800,
                fontSize: 13,
              }}
            >
              R
            </div>
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: "#0f172a", lineHeight: 1.2 }}>
                REAI Dashboard
              </div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                SEO & AI Search Visibility
              </div>
            </div>
          </div>

          {/* Close button on mobile */}
          {isMobileOpen && (
            <button
              type="button"
              onClick={onCloseMobile}
              aria-label="Close navigation menu"
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: 4,
                color: "var(--ink-muted)",
                fontSize: 18,
                lineHeight: 1,
              }}
            >
              ✕
            </button>
          )}
        </div>

        {/* Navigation Items (Scrollable) */}
        <nav style={{ flex: 1, overflowY: "auto", padding: "12px 10px" }}>
          {/* 1. SEO & DASHBOARD (SEMRUSH STYLE) */}
          <div style={{ marginBottom: 14 }}>
            <div
              style={{
                fontSize: 14,
                fontWeight: 800,
                color: "#0f172a",
                padding: "4px 8px 6px",
              }}
            >
              SEO
            </div>
            <button
              type="button"
              onClick={() => handleItemClick("Overview")}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "8px 12px",
                borderRadius: 6,
                border: "none",
                background: activeTab === "Overview" ? "#f1f5f9" : "transparent",
                color: activeTab === "Overview" ? "#1e293b" : "#475569",
                fontWeight: activeTab === "Overview" ? 700 : 500,
                fontSize: 13,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span>Dashboard</span>
            </button>
          </div>

          {/* Site Performance */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", padding: "4px 8px" }}>
              Site Performance
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Site Audit", tab: "Site Health & Audit" as ReaiTab },
                { label: "Position Tracking", tab: "Keyword Data Lab" as ReaiTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "5px 8px 5px 12px",
                      borderRadius: 5,
                      border: "none",
                      background: isSelected ? "#eff6ff" : "transparent",
                      color: isSelected ? "#1d4ed8" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Competitive Analysis */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", padding: "4px 8px" }}>
              Competitive Analysis
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Domain Overview", tab: "Overview" as ReaiTab },
                { label: "Organic Rankings", tab: "Keyword Data Lab" as ReaiTab },
                { label: "Top Pages", tab: "Keyword Data Lab" as ReaiTab },
                { label: "Compare Domains", tab: "Keyword Gap" as ReaiTab },
                { label: "Keyword Gap", tab: "Keyword Gap" as ReaiTab },
                { label: "Backlink Gap", tab: "Data Lab & Backlinks" as ReaiTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab && item.label !== "Domain Overview";
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "5px 8px 5px 12px",
                      borderRadius: 5,
                      border: "none",
                      background: isSelected ? "#eff6ff" : "transparent",
                      color: isSelected ? "#1d4ed8" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Keyword Research */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", padding: "4px 8px" }}>
              Keyword Research
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Keyword Overview", tab: "Keyword Data Lab" as ReaiTab },
                { label: "Keyword Magic Tool", tab: "Keyword Magic Tool" as ReaiTab },
                { label: "Keyword Strategy Builder", tab: "Keyword Data Lab" as ReaiTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab && item.label === "Keyword Magic Tool";
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "5px 8px 5px 12px",
                      borderRadius: 5,
                      border: "none",
                      background: isSelected ? "#eff6ff" : "transparent",
                      color: isSelected ? "#1d4ed8" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Content Ideas */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", padding: "4px 8px" }}>
              Content Ideas
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "SEO Writing Assistant", tab: "SERP Optimizer" as ReaiTab },
                { label: "Topic Research", tab: "On-Page SEO" as ReaiTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "5px 8px 5px 12px",
                      borderRadius: 5,
                      border: "none",
                      background: isSelected ? "#eff6ff" : "transparent",
                      color: isSelected ? "#1d4ed8" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Link Building */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", padding: "4px 8px" }}>
              Link Building
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Backlinks", tab: "Data Lab & Backlinks" as ReaiTab },
                { label: "Referring Domains", tab: "Data Lab & Backlinks" as ReaiTab },
                { label: "Backlink Audit", tab: "Data Lab & Backlinks" as ReaiTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "5px 8px 5px 12px",
                      borderRadius: 5,
                      border: "none",
                      background: isSelected ? "#eff6ff" : "transparent",
                      color: isSelected ? "#1d4ed8" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Extras */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", padding: "4px 8px" }}>
              Extras
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Sensor", tab: "Site Health & Audit" as ReaiTab },
                { label: "SEOquake", tab: "All Tools Directory" as ReaiTab },
                { label: "Semrush Rank", tab: "Keyword Data Lab" as ReaiTab },
              ].map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => handleItemClick(item.tab)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    padding: "5px 8px 5px 12px",
                    borderRadius: 5,
                    border: "none",
                    background: "transparent",
                    color: "#475569",
                    fontWeight: 400,
                    fontSize: 12,
                    cursor: "pointer",
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          {/* Other */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", padding: "4px 8px" }}>
              Other
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "On Page SEO Checker", tab: "On-Page SEO" as ReaiTab },
                { label: "Organic Traffic Insights", tab: "Traffic Analytics" as ReaiTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "5px 8px 5px 12px",
                      borderRadius: 5,
                      border: "none",
                      background: isSelected ? "#eff6ff" : "transparent",
                      color: isSelected ? "#1d4ed8" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>


          {/* 2. SEO FOUNDATIONS */}
          <div style={{ marginBottom: 14 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--ink-muted)",
                padding: "4px 10px",
              }}
            >
              SEO Foundations
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Technical SEO", tab: "Site Health & Audit" as ReaiTab },
                { label: "On-Page SEO", tab: "On-Page SEO" as ReaiTab },
                { label: "Content", tab: "SERP Optimizer" as ReaiTab },
                { label: "Keywords & Rankings", tab: "Keyword Data Lab" as ReaiTab },
                { label: "Links", tab: "Data Lab & Backlinks" as ReaiTab },
                { label: "Local SEO", tab: "Local SEO & GBP" as ReaiTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab, item.label as NavSubTab)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 10px 6px 16px",
                      borderRadius: 6,
                      border: "none",
                      background: isSelected ? "#eff6ff" : "transparent",
                      color: isSelected ? "#1d4ed8" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12.5,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 3. AI SEARCH VISIBILITY (AEO) */}
          <div style={{ marginBottom: 14 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--ink-muted)",
                padding: "4px 10px",
              }}
            >
              AI Search Visibility (AEO)
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "AI Readiness", sub: "AI Readiness" as NavSubTab },
                { label: "AI Citations", sub: "AI Citations" as NavSubTab },
                { label: "Schema & Entities", sub: "Schema & Entities" as NavSubTab },
                { label: "Answer Content", sub: "Answer Content" as NavSubTab },
                { label: "AI Crawler Access", sub: "AI Crawler Access" as NavSubTab },
              ].map((item) => {
                const effectiveSub = activeSubTab || "AI Readiness";
                const isSelected = activeTab === "AI & AEO Lab" && effectiveSub === item.sub;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick("AI & AEO Lab", item.sub)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 10px 6px 16px",
                      borderRadius: 6,
                      border: "none",
                      background: isSelected ? "#f5f3ff" : "transparent",
                      color: isSelected ? "#6d28d9" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12.5,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 4. FIX & IMPROVE */}
          <div style={{ marginBottom: 14 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--ink-muted)",
                padding: "4px 10px",
              }}
            >
              Fix & Improve
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Priority Actions", tab: "Overview" as ReaiTab, sub: "Priority Actions" as NavSubTab },
                { label: "Auto-Fix Review", tab: "Auto-Fix Engine" as ReaiTab, sub: "Auto-Fix Review" as NavSubTab },
                { label: "Content Opportunities", tab: "On-Page SEO" as ReaiTab, sub: "Content Opportunities" as NavSubTab },
                { label: "Change History", tab: "Auto-Fix Engine" as ReaiTab, sub: "Change History" as NavSubTab },
              ].map((item) => {
                const isSelected = activeTab === item.tab && activeSubTab === item.sub;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => handleItemClick(item.tab, item.sub)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 10px 6px 16px",
                      borderRadius: 6,
                      border: "none",
                      background: isSelected ? "#ecfdf5" : "transparent",
                      color: isSelected ? "#047857" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12.5,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 5. REPORTS & SETTINGS */}
          <div style={{ marginBottom: 14 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                color: "var(--ink-muted)",
                padding: "4px 10px",
              }}
            >
              Reports & Settings
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {[
                { label: "Reports", tab: "Traffic Analytics" as ReaiTab, sub: "Reports" as NavSubTab },
                { label: "Google Search Console", tab: "Traffic Analytics" as ReaiTab, sub: "Google Search Console" as NavSubTab },
                { label: "Integrations", tab: "Overview" as ReaiTab, sub: "Integrations" as NavSubTab },
                { label: "Project Settings", tab: "Overview" as ReaiTab, sub: "Project Settings" as NavSubTab },
                { label: "Profile & Account", href: "/profile" },
              ].map((item: any) => {
                const isSelected = item.tab ? (activeTab === item.tab && activeSubTab === item.sub) : false;
                return (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => {
                      if (item.href) {
                        if (typeof window !== "undefined") window.location.href = item.href;
                      } else {
                        handleItemClick(item.tab, item.sub);
                      }
                    }}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 10px 6px 16px",
                      borderRadius: 6,
                      border: "none",
                      background: isSelected ? "#f8fafc" : "transparent",
                      color: isSelected ? "#1e293b" : "#475569",
                      fontWeight: isSelected ? 600 : 400,
                      fontSize: 12.5,
                      cursor: "pointer",
                    }}
                  >
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
        </nav>

        {/* 6. ALL TOOLS DIRECTORY (PINNED BOTTOM) */}
        <div style={{ padding: "10px", borderTop: "1px solid #e2e8f0", background: "#f8fafc" }}>
          <button
            type="button"
            onClick={() => handleItemClick("All Tools Directory")}
            style={{
              width: "100%",
              padding: "9px 12px",
              borderRadius: 6,
              background: activeTab === "All Tools Directory" ? "#2563eb" : "#ffffff",
              color: activeTab === "All Tools Directory" ? "#ffffff" : "#1e293b",
              border: "1px solid #cbd5e1",
              fontSize: 12.5,
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span>🛠️</span>
              <span>All Tools Directory</span>
            </span>
            <span
              style={{
                fontSize: 12,
                padding: "2px 6px",
                borderRadius: 10,
                background: activeTab === "All Tools Directory" ? "rgba(255,255,255,0.2)" : "#f1f5f9",
                color: activeTab === "All Tools Directory" ? "#ffffff" : "var(--ink-muted)",
                fontWeight: 700,
              }}
            >
              {totalToolsCount}
            </span>
          </button>
        </div>
      </aside>
    )}
  </div>
</>
  );
}
