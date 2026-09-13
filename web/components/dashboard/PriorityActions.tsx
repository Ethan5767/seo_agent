"use client";

import React, { useState } from "react";
import type { PriorityItem } from "./types";

interface PriorityActionsProps {
  /** Findings derived from the current scan report. Empty means nothing measured. */
  priorities: PriorityItem[];
  onSelectAction?: (priority: PriorityItem) => void;
}


export function PriorityActions({
  priorities,
  onSelectAction,
}: PriorityActionsProps) {
  const [expandedDetails, setExpandedDetails] = useState<Record<string, boolean>>({});

  const toggleDetails = (id: string) => {
    setExpandedDetails((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <section aria-labelledby="priority-actions-heading" style={{ marginBottom: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 14 }}>
        <div>
          <h2 id="priority-actions-heading" style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", margin: 0 }}>
            Top Priorities
          </h2>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "3px 0 0" }}>
            The highest-impact actions for your site right now. One clear action per item.
          </p>
        </div>
        {priorities.length > 0 && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: "var(--radius-xs)",
              background: "var(--ok-tint)",
              color: "var(--ok)",
              border: "1px solid var(--ok-border)",
            }}
          >
            From your last scan
          </span>
        )}
      </div>

      {priorities.length === 0 && (
        <div
          style={{
            border: "1px dashed var(--border-strong)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-5)",
            textAlign: "center",
            background: "var(--surface-2)",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-body)" }}>
            Nothing measured yet
          </div>
          <div
            style={{
              fontSize: 13,
              color: "var(--ink-muted)",
              marginTop: "var(--space-1)",
              maxWidth: "46ch",
              marginInline: "auto",
            }}
          >
            Priorities are derived from your last audit. Run one and the findings
            the scanner reports will be ranked here.
          </div>
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {priorities.map((item, index) => {
          const isExpanded = !!expandedDetails[item.id];
          const severityBadge =
            item.severity === "critical"
              ? { text: "[Critical]", bg: "#fee2e2", color: "#991b1b", border: "#fecaca" }
              : item.severity === "warning"
              ? { text: "[Warning]", bg: "#fef3c7", color: "#92400e", border: "#fde68a" }
              : { text: "[Improvement]", bg: "#e0f2fe", color: "#075985", border: "#bae6fd" };

          const categoryBadge =
            item.category === "SEO"
              ? { bg: "#f1f5f9", color: "#334155" }
              : item.category === "AI Search"
              ? { bg: "#f5f3ff", color: "#5b21b6" }
              : { bg: "#ecfdf5", color: "#065f46" };

          return (
            <div
              key={item.id}
              style={{
                background: "#ffffff",
                border: "1px solid #e2e8f0",
                borderRadius: 8,
                padding: "16px 18px",
                transition: "border-color 0.15s ease",
              }}
            >
              {/* Header row */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: "50%",
                      background: "#0f172a",
                      color: "#ffffff",
                      fontSize: 12,
                      fontWeight: 700,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {index + 1}
                  </span>
                  <h3 style={{ fontSize: 14.5, fontWeight: 700, color: "#1e293b", margin: 0 }}>
                    {item.title}
                  </h3>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: severityBadge.bg,
                      color: severityBadge.color,
                      border: `1px solid ${severityBadge.border}`,
                    }}
                  >
                    {severityBadge.text}
                  </span>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 600,
                      padding: "2px 6px",
                      borderRadius: 4,
                      background: categoryBadge.bg,
                      color: categoryBadge.color,
                    }}
                  >
                    {item.category}
                  </span>
                  {item.isAutoFixable && (
                    <span
                      style={{
                        fontSize: 12,
                        fontWeight: 600,
                        padding: "2px 6px",
                        borderRadius: 4,
                        background: "#ecfdf5",
                        color: "#047857",
                        border: "1px solid #a7f3d0",
                      }}
                    >
                      Auto-Fix Available
                    </span>
                  )}
                </div>

                {/* Primary Action Button */}
                <div>
                  <button
                    type="button"
                    onClick={() => onSelectAction?.(item)}
                    style={{
                      background: "#2563eb",
                      color: "#ffffff",
                      border: "none",
                      borderRadius: 6,
                      padding: "7px 14px",
                      fontSize: 12.5,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    {item.actionLabel} →
                  </button>
                </div>
              </div>

              {/* Problem & Why it matters */}
              <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr", gap: 6 }}>
                <div style={{ fontSize: 13, color: "#334155" }}>
                  <strong style={{ color: "#0f172a" }}>Problem: </strong>
                  {item.problem}
                </div>
                <div style={{ fontSize: 12.5, color: "#475569" }}>
                  <strong style={{ color: "#0f172a" }}>Why it matters: </strong>
                  {item.whyItMatters}
                </div>
                <div style={{ fontSize: 12.5, color: "#166534", background: "#f0fdf4", padding: "6px 10px", borderRadius: 4, marginTop: 2 }}>
                  <strong style={{ color: "#14532d" }}>Expected outcome: </strong>
                  {item.expectedOutcome}
                </div>
              </div>

              {/* Footer Meta: Source + Confidence + Expand Technical Details */}
              <div
                style={{
                  marginTop: 12,
                  paddingTop: 10,
                  borderTop: "1px solid #f1f5f9",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  flexWrap: "wrap",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12, color: "var(--ink-muted)" }}>
                  <span>
                    <strong>Source:</strong> {item.source}
                  </span>
                  <span>•</span>
                  <span>
                    <strong>Confidence:</strong> {item.confidence}
                  </span>
                </div>

                <button
                  type="button"
                  onClick={() => toggleDetails(item.id)}
                  aria-expanded={isExpanded}
                  style={{
                    background: "none",
                    border: "none",
                    color: "#475569",
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                    textDecoration: "underline",
                    padding: 0,
                  }}
                >
                  {isExpanded ? "Hide Technical Details ▲" : "View Technical Details ▼"}
                </button>
              </div>

              {/* Collapsible Technical Details (Keeps advanced jargon hidden by default) */}
              {isExpanded && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    borderRadius: 6,
                    fontSize: 12,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, color: "#1e293b" }}>
                      Technical Details ({item.technicalDetails.category})
                    </span>
                    <span style={{ color: "var(--ink-muted)", fontSize: 12 }}>For developers and technical audits</span>
                  </div>
                  <p style={{ margin: "0 0 8px", color: "#475569" }}>
                    {item.technicalDetails.summary}
                  </p>

                  {item.technicalDetails.metrics && (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 6, marginBottom: 8 }}>
                      {Object.entries(item.technicalDetails.metrics).map(([key, val]) => (
                        <div key={key} style={{ background: "#ffffff", padding: "4px 8px", borderRadius: 4, border: "1px solid #e2e8f0" }}>
                          <span style={{ color: "var(--ink-muted)", fontSize: 12 }}>{key}: </span>
                          <strong style={{ color: "#0f172a" }}>{val}</strong>
                        </div>
                      ))}
                    </div>
                  )}

                  {item.technicalDetails.codeSnippet && (
                    <pre
                      style={{
                        margin: 0,
                        padding: 10,
                        background: "#0f172a",
                        color: "#f8fafc",
                        borderRadius: 4,
                        fontSize: 12,
                        overflowX: "auto",
                        fontFamily: "ui-monospace, monospace",
                      }}
                    >
                      <code>{item.technicalDetails.codeSnippet}</code>
                    </pre>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
