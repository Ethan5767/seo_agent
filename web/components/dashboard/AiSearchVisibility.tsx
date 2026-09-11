"use client";

import React, { useState } from "react";
import type { NavSubTab } from "./types";

interface AiSearchVisibilityProps {
  subTab?: NavSubTab;
  onSelectSubTab?: (sub: NavSubTab) => void;
  onTriggerFixReview?: (actionId: string) => void;
}

export function AiSearchVisibility({
  subTab = "AI Readiness",
  onSelectSubTab,
  onTriggerFixReview,
}: AiSearchVisibilityProps) {
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
              AI Search Visibility (AEO)
            </h1>
            <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "4px 0 0" }}>
              Optimizing technical extractability, structured schema, and clear answers for AI search engines.
            </p>
          </div>
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              padding: "3px 8px",
              borderRadius: 4,
              background: "#fef3c7",
              color: "#92400e",
              border: "1px solid #fde68a",
            }}
          >
            Estimated metrics
          </span>
        </div>

        {/* Sub Navigation Bar */}
        <div
          role="tablist"
          aria-label="AI Search Visibility Sections"
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
              "AI Readiness",
              "AI Citations",
              "Schema & Entities",
              "Answer Content",
              "AI Crawler Access",
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
                  borderBottom: isSelected ? "2px solid #7c3aed" : "2px solid transparent",
                  borderRadius: "6px 6px 0 0",
                  padding: "8px 14px",
                  fontSize: 13,
                  fontWeight: isSelected ? 700 : 500,
                  color: isSelected ? "#6d28d9" : "var(--ink-muted)",
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

      {/* Principle Reminder */}
      <div style={{ background: "#f5f3ff", border: "1px solid #ede9fe", borderRadius: 8, padding: "10px 14px", marginBottom: 16, fontSize: 12, color: "#5b21b6" }}>
        <strong>How AI Search works:</strong> AI answer engines like Perplexity, ChatGPT Search, and Google AI Overviews read clean HTML, structured Schema.org data, and concise question-answering paragraphs.
        {" "}<span style={{ color: "#7c3aed" }}>(AEO improves technical extractability; it does not guarantee citations or rankings).</span>
      </div>

      {/* Main Content Area */}
      {activeView === "AI Readiness" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <div style={{ background: "#ffffff", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>AI Answer Readiness</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: "#7c3aed", marginTop: 4 }}>74%</div>
              <div style={{ fontSize: 12, color: "#6d28d9" }}>Moderate extractability</div>
            </div>
            <div style={{ background: "#ffffff", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>AI Crawler Access</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: "var(--ok)", marginTop: 4 }}>Allowed</div>
              <div style={{ fontSize: 12, color: "#166534" }}>GPTBot, ClaudeBot open</div>
            </div>
            <div style={{ background: "#ffffff", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>Schema Completeness</div>
              <div style={{ fontSize: 24, fontWeight: 800, color: "#d97706", marginTop: 4 }}>Needs Schema</div>
              <div style={{ fontSize: 12, color: "#92400e" }}>LocalBusiness missing</div>
            </div>
          </div>

          <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: 16 }}>
            <h3 style={{ fontSize: 14.5, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
              Recommended Next Action for AI Visibility
            </h3>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f8fafc", padding: 12, borderRadius: 6, border: "1px solid #e2e8f0", flexWrap: "wrap", gap: 10 }}>
              <div>
                <div style={{ fontWeight: 600, color: "#1e293b", fontSize: 13 }}>
                  Add LocalBusiness & Organization JSON-LD Schema
                </div>
                <div style={{ color: "var(--ink-muted)", fontSize: 12, marginTop: 2 }}>
                  Source: AI Readiness Probe • Confidence: High
                </div>
              </div>
              <button
                type="button"
                onClick={() => onTriggerFixReview?.("schema-fix")}
                style={{
                  background: "#2563eb",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: 4,
                  padding: "6px 14px",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Review Fix →
              </button>
            </div>
          </div>
        </div>
      )}

      {activeView === "AI Citations" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            AI Search Citations
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Estimated citations across leading generative answer platforms.
          </p>
          <div style={{ marginTop: 14, fontSize: 12, color: "#475569", background: "#f1f5f9", padding: "8px 12px", borderRadius: 4 }}>
            <strong>Note:</strong> Citation monitoring samples public answer queries. Results reflect observed citation appearances.
          </div>
        </div>
      )}

      {activeView === "Schema & Entities" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Schema & Entities
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Structured data validation (Schema.org) for Google rich snippets and AI entity recognition.
          </p>
          <div style={{ marginTop: 14 }}>
            <button
              type="button"
              onClick={() => onTriggerFixReview?.("schema")}
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
              Review Staged Schema Fix →
            </button>
          </div>
        </div>
      )}

      {activeView === "Answer Content" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Answer Content & Question Snippets
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Assess page formatting for direct AI answers: concise definition blocks, FAQ accordions, and list structures.
          </p>
        </div>
      )}

      {activeView === "AI Crawler Access" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            AI Crawler Access & robots.txt Probe
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Verify whether major AI crawler user agents are permitted or blocked by your robots.txt directives.
          </p>
          <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
            {[
              { agent: "GPTBot", purpose: "OpenAI / SearchGPT", status: "Allowed" },
              { agent: "ClaudeBot", purpose: "Anthropic Claude", status: "Allowed" },
              { agent: "PerplexityBot", purpose: "Perplexity AI", status: "Allowed" },
              { agent: "Google-Extended", purpose: "Google Gemini Training", status: "Blocked" },
            ].map((crawler) => (
              <div key={crawler.agent} style={{ background: "#f8fafc", padding: 12, borderRadius: 6, border: "1px solid #e2e8f0" }}>
                <div style={{ fontWeight: 600, color: "#0f172a", fontSize: 13 }}>{crawler.agent}</div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>{crawler.purpose}</div>
                <div style={{ marginTop: 6, fontSize: 12, fontWeight: 700, color: crawler.status === "Allowed" ? "#166534" : "#991b1b" }}>
                  [{crawler.status}]
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
