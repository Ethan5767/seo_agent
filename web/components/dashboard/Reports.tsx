"use client";

import React, { useState } from "react";
import type { NavSubTab } from "./types";

interface ReportsProps {
  subTab?: NavSubTab;
  onSelectSubTab?: (sub: NavSubTab) => void;
  gscConnected?: boolean;
}

export function Reports({
  subTab = "Reports",
  onSelectSubTab,
  gscConnected = false,
}: ReportsProps) {
  const [activeView, setActiveView] = useState<NavSubTab>(subTab);

  const handleTabChange = (tab: NavSubTab) => {
    setActiveView(tab);
    onSelectSubTab?.(tab);
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", margin: 0 }}>
          Reports & Settings
        </h1>
        <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "4px 0 0" }}>
          Executive reports, Google Search Console sync, integrations, and project configurations.
        </p>

        {/* Sub Navigation Bar */}
        <div
          role="tablist"
          aria-label="Reports and Settings Sections"
          style={{
            display: "flex",
            gap: 6,
            marginTop: 16,
            borderBottom: "1px solid #e2e8f0",
            paddingBottom: 2,
            overflowX: "auto",
          }}
        >
          {(
            [
              "Reports",
              "Google Search Console",
              "Integrations",
              "Project Settings",
            ] as NavSubTab[]
          ).map((tab) => {
            const isSelected = activeView === tab;
            return (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={isSelected}
                onClick={() => handleTabChange(tab)}
                style={{
                  background: isSelected ? "#ffffff" : "transparent",
                  border: isSelected ? "1px solid #cbd5e1" : "1px solid transparent",
                  borderBottom: isSelected ? "2px solid #2563eb" : "2px solid transparent",
                  borderRadius: "6px 6px 0 0",
                  padding: "8px 14px",
                  fontSize: 13,
                  fontWeight: isSelected ? 700 : 500,
                  color: isSelected ? "#1d4ed8" : "var(--ink-muted)",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                {tab}
              </button>
            );
          })}
        </div>
      </div>

      {/* Main Content Area */}
      {activeView === "Reports" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
              Monthly SEO & AI Visibility PDF Summary
            </h3>
            <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "0 0 14px" }}>
              Download client-ready executive PDF reports covering health score trends, top fixes applied, and ranked keywords.
            </p>
            <button
              type="button"
              style={{
                background: "#2563eb",
                color: "#ffffff",
                border: "none",
                borderRadius: 6,
                padding: "8px 16px",
                fontSize: 12.5,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Export Latest Report (PDF)
            </button>
          </div>
        </div>
      )}

      {activeView === "Google Search Console" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
            <div>
              <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 6px" }}>
                Google Search Console Integration
              </h3>
              <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
                Directly sync verified organic impressions, click-through rates, and live Google index status.
              </p>
            </div>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                padding: "3px 8px",
                borderRadius: 4,
                background: gscConnected ? "#dcfce7" : "#fef3c7",
                color: gscConnected ? "#166534" : "#92400e",
              }}
            >
              {gscConnected ? "Connected" : "Needs Google Search Console connection"}
            </span>
          </div>

          <div style={{ marginTop: 18, padding: 16, background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>Connect Your Property via OAuth 2.0</div>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "4px 0 12px" }}>
              Read-only permission is required. We never modify your live search console property or indexing settings without explicit consent.
            </p>
            <a
              href="/integrations/google"
              style={{
                display: "inline-block",
                background: "#2563eb",
                color: "#ffffff",
                borderRadius: 6,
                padding: "7px 14px",
                fontSize: 12.5,
                fontWeight: 600,
                textDecoration: "none",
              }}
            >
              Configure Google Search Console →
            </a>
          </div>
        </div>
      )}

      {activeView === "Integrations" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Connected Services & Webhooks
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Manage API connections for GitHub PR staging, Slack notifications, and search analytics providers.
          </p>
        </div>
      )}

      {activeView === "Project Settings" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Project Configuration
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Configure primary domain, secondary staging URLs, crawler rate limits, and audit schedules.
          </p>
        </div>
      )}
    </div>
  );
}
