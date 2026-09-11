"use client";

import React, { useState } from "react";
import type { NavSubTab } from "./types";

interface StagedFixItem {
  id: string;
  title: string;
  category: "SEO" | "AI Search";
  fileTarget: string;
  status: "Staged for review" | "Applied via PR" | "Manual Review Required";
  prUrl?: string;
  diff: string;
}

const DEFAULT_STAGED_FIXES: StagedFixItem[] = [
  // Removed a hardcoded set of staged fixes, complete with invented git diffs
  // against a fictional client ("Acme Roofing"). Real staged fixes come from
  // the remediation rail (/api/remediate/dryrun), which this screen does not
  // call yet. Nothing is better than a convincing fake.
];

interface FixReviewProps {
  subTab?: NavSubTab;
  onSelectSubTab?: (sub: NavSubTab) => void;
  onApplyFix?: (id: string) => Promise<void>;
}

export function FixReview({
  subTab = "Auto-Fix Review",
  onSelectSubTab,
  onApplyFix,
}: FixReviewProps) {
  const [activeView, setActiveView] = useState<NavSubTab>(subTab);
  const [selectedFix, setSelectedFix] = useState<StagedFixItem>(DEFAULT_STAGED_FIXES[0]);
  const [isApplying, setIsApplying] = useState(false);
  const [appliedFixes, setAppliedFixes] = useState<Record<string, boolean>>({});

  const handleTabChange = (tab: NavSubTab) => {
    setActiveView(tab);
    onSelectSubTab?.(tab);
  };

  const handleApply = async (fixId: string) => {
    setIsApplying(true);
    try {
      if (onApplyFix) {
        await onApplyFix(fixId);
      }
      setAppliedFixes((prev) => ({ ...prev, [fixId]: true }));
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", paddingBottom: 40 }}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 800, color: "#0f172a", margin: 0 }}>
              Fix & Improve
            </h1>
            <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "4px 0 0" }}>
              Review staged code fixes, inspect diffs, and approve changes before deployment.
            </p>
          </div>
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              padding: "3px 8px",
              borderRadius: 4,
              background: "#ecfdf5",
              color: "#047857",
              border: "1px solid #a7f3d0",
            }}
          >
            Review First Workflow Active
          </span>
        </div>

        {/* Sub Navigation Bar */}
        <div
          role="tablist"
          aria-label="Fix and Improve Sections"
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
              "Priority Actions",
              "Auto-Fix Review",
              "Content Opportunities",
              "Change History",
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
                  borderBottom: isSelected ? "2px solid #059669" : "2px solid transparent",
                  borderRadius: "6px 6px 0 0",
                  padding: "8px 14px",
                  fontSize: 13,
                  fontWeight: isSelected ? 700 : 500,
                  color: isSelected ? "#047857" : "var(--ink-muted)",
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
      {activeView === "Auto-Fix Review" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 16 }}>
          {/* Staged Fix List */}
          <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: 14 }}>
            <h3 style={{ fontSize: 14, fontWeight: 700, color: "#0f172a", margin: "0 0 12px" }}>
              Staged Fixes Awaiting Review ({DEFAULT_STAGED_FIXES.length})
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {DEFAULT_STAGED_FIXES.map((fix) => {
                const isSelected = selectedFix.id === fix.id;
                const isApplied = !!appliedFixes[fix.id];

                return (
                  <div
                    key={fix.id}
                    onClick={() => setSelectedFix(fix)}
                    style={{
                      padding: "12px 14px",
                      borderRadius: 6,
                      background: isSelected ? "#f0fdf4" : "#f8fafc",
                      border: isSelected ? "1px solid #86efac" : "1px solid #e2e8f0",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#1e293b" }}>{fix.title}</span>
                      <span
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: isApplied ? "#dcfce7" : "#fef3c7",
                          color: isApplied ? "#166534" : "#92400e",
                        }}
                      >
                        {isApplied ? "Applied" : "Staged for review"}
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                      Target: <code>{fix.fileTarget}</code>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Diff Viewer & Review Action */}
          <div style={{ background: "#ffffff", borderRadius: 8, border: "1px solid #e2e8f0", padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
              <div>
                <h3 style={{ fontSize: 14.5, fontWeight: 700, color: "#0f172a", margin: 0 }}>
                  {selectedFix.title}
                </h3>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                  Inspecting diff for <code>{selectedFix.fileTarget}</code>
                </div>
              </div>

              {appliedFixes[selectedFix.id] ? (
                <span style={{ fontSize: 12, fontWeight: 700, color: "#166534", background: "#dcfce7", padding: "4px 10px", borderRadius: 4 }}>
                  ✓ Fix Applied to Staging
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => handleApply(selectedFix.id)}
                  disabled={isApplying}
                  style={{
                    background: "#059669",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: 6,
                    padding: "7px 14px",
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: isApplying ? "wait" : "pointer",
                  }}
                >
                  {isApplying ? "Applying..." : "Approve & Apply Fix"}
                </button>
              )}
            </div>

            {/* Code Diff Display */}
            <div style={{ marginTop: 12 }}>
              <pre
                style={{
                  margin: 0,
                  padding: 14,
                  background: "#0f172a",
                  color: "#e2e8f0",
                  borderRadius: 6,
                  fontSize: 12,
                  lineHeight: 1.5,
                  overflowX: "auto",
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                }}
              >
                <code>{selectedFix.diff}</code>
              </pre>
            </div>
          </div>
        </div>
      )}

      {activeView === "Priority Actions" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Priority Actions List
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Rank-ordered backlog of high-impact fixes categorized by effort and potential ranking lift.
          </p>
        </div>
      )}

      {activeView === "Content Opportunities" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Content Opportunities
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: 0 }}>
            Identify search query gaps where competitors are gaining rankings that your site does not yet cover.
          </p>
        </div>
      )}

      {activeView === "Change History" && (
        <div style={{ background: "#ffffff", padding: 20, borderRadius: 8, border: "1px solid #e2e8f0" }}>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#0f172a", margin: "0 0 10px" }}>
            Change History & Audit Trail
          </h3>
          <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "0 0 14px" }}>
            Complete ledger of applied fixes with timestamp and reviewer attribution.
          </p>
          <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            No live deployments committed yet. All items require manual approval.
          </div>
        </div>
      )}
    </div>
  );
}
