"use client";

import React, { useState } from "react";
import type { NavSubTab } from "./types";
import { GoogleServicesHub } from "./GoogleServicesHub";
import { LocalBusinessManager } from "./LocalBusinessManager";

interface SeoFoundationsProps {
  subTab?: NavSubTab;
  onSelectSubTab?: (sub: NavSubTab) => void;
  onTriggerFixReview?: (issueId: string) => void;
}

export function SeoFoundations({
  subTab = "Technical SEO",
  onSelectSubTab,
  onTriggerFixReview,
}: SeoFoundationsProps) {
  const [activeView, setActiveView] = useState<NavSubTab>(subTab);

  const handleTabChange = (tab: NavSubTab) => {
    setActiveView(tab);
    onSelectSubTab?.(tab);
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", margin: 0 }}>
              SEO Foundations
            </h1>
            <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "4px 0 0" }}>
              Crawlability, technical health, on-page optimization, and ranking signals.
            </p>
          </div>
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              padding: "3px 8px",
              borderRadius: 4,
              background: "#f1f5f9",
              color: "#475569",
              border: "1px solid #e2e8f0",
            }}
          >
            Demo data (Live crawler idle)
          </span>
        </div>

        {/* Sub Navigation Bar */}
        <div
          role="tablist"
          aria-label="SEO Foundations Sections"
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
              "Technical SEO",
              "On-Page SEO",
              "Content",
              "Keywords & Rankings",
              "Links",
              "Local SEO",
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
      {activeView === "Technical SEO" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Quick Health Summary */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <div style={{ background: "#ffffff", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Crawl Health</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: "var(--ok)", marginTop: 4 }}>98%</div>
              <div style={{ fontSize: 12, color: "#166534" }}>No 5xx server errors detected</div>
            </div>
            <div style={{ background: "#ffffff", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Indexing & Robots</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: "var(--ok)", marginTop: 4 }}>142 / 142</div>
              <div style={{ fontSize: 12, color: "#166534" }}>All primary pages indexable</div>
            </div>
            <div style={{ background: "#ffffff", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Core Web Vitals</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: "#d97706", marginTop: 4 }}>Needs Review</div>
              <div style={{ fontSize: 12, color: "#92400e" }}>LCP 2.9s on mobile</div>
            </div>
          </div>

          {/* Technical Issues Table (Responsive with card fallback) */}
          <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", overflow: "hidden" }}>
            <div style={{ padding: "14px 18px", borderBottom: "1px solid #e2e8f0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ fontSize: 14.5, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                Detected Technical Issues
              </h3>
              <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Sorted by impact</span>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", color: "#475569" }}>
                    <th style={{ padding: "10px 14px", fontWeight: 600 }}>Severity</th>
                    <th style={{ padding: "10px 14px", fontWeight: 600 }}>Issue</th>
                    <th style={{ padding: "10px 14px", fontWeight: 600 }}>Affected URLs</th>
                    <th style={{ padding: "10px 14px", fontWeight: 600 }}>Source</th>
                    <th style={{ padding: "10px 14px", fontWeight: 600, textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 6px", borderRadius: 4, background: "#fee2e2", color: "#991b1b", border: "1px solid #fecaca" }}>
                        [Critical]
                      </span>
                    </td>
                    <td style={{ padding: "10px 14px", fontWeight: 600, color: "#1e293b" }}>
                      Pages missing HTML &lt;title&gt;
                    </td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-muted)" }}>8 pages</td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-muted)" }}>Site Audit</td>
                    <td style={{ padding: "10px 14px", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={() => onTriggerFixReview?.("missing-title")}
                        style={{
                          background: "#2563eb",
                          color: "#ffffff",
                          border: "none",
                          borderRadius: 4,
                          padding: "5px 10px",
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Review Fix →
                      </button>
                    </td>
                  </tr>

                  <tr style={{ borderBottom: "1px solid #f1f5f9" }}>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 6px", borderRadius: 4, background: "#fef3c7", color: "#92400e", border: "1px solid #fde68a" }}>
                        [Warning]
                      </span>
                    </td>
                    <td style={{ padding: "10px 14px", fontWeight: 600, color: "#1e293b" }}>
                      Images missing descriptive alt text
                    </td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-muted)" }}>14 images</td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-muted)" }}>Site Audit</td>
                    <td style={{ padding: "10px 14px", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={() => onTriggerFixReview?.("missing-alt")}
                        style={{
                          background: "#f8fafc",
                          color: "#1e293b",
                          border: "1px solid #cbd5e1",
                          borderRadius: 4,
                          padding: "5px 10px",
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Review Fix →
                      </button>
                    </td>
                  </tr>

                  <tr>
                    <td style={{ padding: "10px 14px" }}>
                      <span style={{ fontSize: 12, fontWeight: 600, padding: "2px 6px", borderRadius: 4, background: "#e0f2fe", color: "#075985", border: "1px solid #bae6fd" }}>
                        [Info]
                      </span>
                    </td>
                    <td style={{ padding: "10px 14px", fontWeight: 600, color: "#1e293b" }}>
                      LCP element optimization (hero image preload)
                    </td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-muted)" }}>Homepage</td>
                    <td style={{ padding: "10px 14px", color: "var(--ink-muted)" }}>Core Web Vitals</td>
                    <td style={{ padding: "10px 14px", textAlign: "right" }}>
                      <button
                        type="button"
                        onClick={() => onTriggerFixReview?.("lcp-preload")}
                        style={{
                          background: "#f8fafc",
                          color: "#1e293b",
                          border: "1px solid #cbd5e1",
                          borderRadius: 4,
                          padding: "5px 10px",
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        View Details →
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeView === "On-Page SEO" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            On-Page SEO Optimization
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Analyze page titles, meta descriptions, header hierarchy (H1-H3), and internal linking balance.
          </p>
          <div style={{ marginTop: 16, padding: 14, background: "#f8fafc", borderRadius: 6, border: "1px solid #e2e8f0" }}>
            <div style={{ fontSize: 12.5, fontWeight: 600, color: "#1e293b" }}>Suggested Meta Titles & Descriptions Ready for Review</div>
            <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
              8 staged title tag recommendations have been generated based on search volume.
            </div>
            <div style={{ marginTop: 10 }}>
              <button
                type="button"
                onClick={() => onTriggerFixReview?.("titles")}
                style={{
                  background: "#2563eb",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: 4,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Open Auto-Fix Review →
              </button>
            </div>
          </div>
        </div>
      )}

      {activeView === "Content" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Content & SERP Optimization
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Identify thin content, content decay, missing search intent topics, and readability scores.
          </p>
        </div>
      )}

      {activeView === "Keywords & Rankings" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Keywords & Rankings
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Track organic rankings, SERP position movements, and keyword search volumes.
          </p>
          <div style={{ marginTop: 14, fontSize: 12, color: "#92400e", background: "#fef3c7", padding: "6px 10px", borderRadius: 4, display: "inline-block" }}>
            Needs Google Search Console connection for daily ranking verification
          </div>
        </div>
      )}

      {activeView === "Links" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Links & Authority
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Backlink profiles, referring domains, toxic link audits, and broken link checkers.
          </p>
        </div>
      )}

      {activeView === "Local SEO" && (
        <LocalBusinessManager />
      )}

    </div>
  );
}
