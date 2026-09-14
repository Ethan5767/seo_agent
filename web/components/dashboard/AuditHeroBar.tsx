"use client";

import React, { useState } from "react";

interface AuditHeroBarProps {
  currentDomain?: string;
  onRunAudit: (url: string) => void;
  isScanning?: boolean;
  phaseLine?: string;
  scanTools?: any[];
  liveLogs?: string[];
  report?: any;
  onSelectFix?: (issueCode: string) => void;
}

export function AuditHeroBar({
  currentDomain = "",
  onRunAudit,
  isScanning = false,
  phaseLine,
  scanTools = [],
  liveLogs = [],
  report,
  onSelectFix,
}: AuditHeroBarProps) {
  const [inputUrl, setInputUrl] = useState(currentDomain || "");
  const [crawlDepth, setCrawlDepth] = useState<"single" | "site">("single");
  const [showLogs, setShowLogs] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<"all" | "error" | "warn" | "ok">("all");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputUrl.trim();
    if (!trimmed || isScanning) return;
    onRunAudit(trimmed);
  };

  // Aggregate findings from report
  const allRows: any[] = [];
  if (report) {
    const categories = ["seo", "tech", "site", "perf", "aeo", "keywords", "rankings", "gbp"];
    for (const cat of categories) {
      if (Array.isArray(report[cat])) {
        allRows.push(...report[cat]);
      }
    }
  }

  const errorCount = allRows.filter((r) => r.severity === "error").length;
  const warnCount = allRows.filter((r) => r.severity === "warn").length;
  const okCount = allRows.filter((r) => r.severity === "ok").length;
  /*
   * One number, computed once, in the scanner. This carried a third health
   * formula - `max(20, 100 - 12*err - 4*warn)` - which disagreed with the
   * scanner's and with ReaiDashboard's in both weights and floor, counted issue
   * TYPES rather than affected URLs, and saturated at 9 errors. It is gone:
   * `report.score` is `audit.health_score`, a published pass rate over
   * gradeable checks, and `null` when nothing gradeable ran. See B-055.
   */
  const overallScore = report?.score ?? null;
  // Narrowed once so the render below cannot re-introduce a coercion. A score
  // of 0 is a real, terrible score and must not be treated as "no score".
  const scored: number | null = typeof overallScore === "number" ? overallScore : null;

  const filteredRows = allRows.filter((r) => {
    if (selectedCategory === "error") return r.severity === "error";
    if (selectedCategory === "warn") return r.severity === "warn";
    if (selectedCategory === "ok") return r.severity === "ok";
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── 1. PRIMARY AUDIT INPUT HERO ── */}
      <div
        style={{
          background: "#ffffff",
          borderRadius: 12,
          border: "1px solid #cbd5e1",
          padding: "24px 28px",
          boxShadow: "0 4px 20px -2px rgba(15, 23, 42, 0.06)",
        }}
      >
        <div style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 20 }}>🔍</span>
            <h2 style={{ margin: 0, fontSize: 19, fontWeight: 800, color: "#0f172a", letterSpacing: "-0.01em" }}>
              Audit Any Website
            </h2>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: "var(--ink-muted)", lineHeight: 1.5 }}>
            Enter your website to immediately check technical SEO, Google speed, broken tags, and AI search engine visibility (AEO).
          </p>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <div style={{ position: "relative", flex: "1 1 340px" }}>
            <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", fontSize: 16, color: "var(--ink-muted)" }}>
              🌐
            </span>
            <input
              type="text"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="e.g. example.com or https://mysite.com"
              disabled={isScanning}
              style={{
                width: "100%",
                padding: "12px 14px 12px 42px",
                fontSize: 14,
                border: "2px solid #cbd5e1",
                borderRadius: 8,
                outline: "none",
                color: "#0f172a",
                fontWeight: 500,
                boxSizing: "border-box",
                background: isScanning ? "#f8fafc" : "#ffffff",
              }}
            />
          </div>

          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button
              type="submit"
              disabled={isScanning || !inputUrl.trim()}
              style={{
                background: isScanning ? "#94a3b8" : "linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)",
                color: "#ffffff",
                border: "none",
                borderRadius: 8,
                padding: "12px 26px",
                fontSize: 14,
                fontWeight: 700,
                cursor: isScanning ? "wait" : "pointer",
                boxShadow: isScanning ? "none" : "0 2px 6px rgba(37, 99, 235, 0.3)",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                whiteSpace: "nowrap",
              }}
            >
              {isScanning ? (
                <>
                  <span style={{ display: "inline-block", animation: "spin 1s linear infinite" }}>🔄</span>
                  <span>Scanning Website...</span>
                </>
              ) : (
                <>
                  <span>🚀</span>
                  <span>Run Audit</span>
                </>
              )}
            </button>
          </div>
        </form>

      </div>

      {/* ── 2. HUMAN-FRIENDLY PROGRESS STATE (WHILE SCANNING) ── */}
      {isScanning && (
        <div
          style={{
            background: "#ffffff",
            borderRadius: 10,
            border: "1px solid #bfdbfe",
            padding: "20px 24px",
            boxShadow: "0 2px 8px rgba(37, 99, 235, 0.08)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#2563eb", animation: "pulse 1.5s infinite" }} />
              <div style={{ fontSize: 14.5, fontWeight: 700, color: "#1e293b" }}>
                Auditing {inputUrl}...
              </div>
            </div>
            <span style={{ fontSize: 12, color: "var(--ink-muted)", fontStyle: "italic" }}>
              {phaseLine || "Evaluating web signals..."}
            </span>
          </div>

          {/* Clean 4-Stage Progress Pills */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8, marginBottom: 14 }}>
            {[
              { id: "p1", title: "1. Connect & HTML", done: scanTools.some((t) => t.name?.toLowerCase().includes("page")) },
              { id: "p2", title: "2. Technical SEO & Tags", done: scanTools.some((t) => t.name?.toLowerCase().includes("tech")) },
              { id: "p3", title: "3. Speed & Core Web Vitals", done: scanTools.some((t) => t.name?.toLowerCase().includes("perf") || t.name?.toLowerCase().includes("schema")) },
              { id: "p4", title: "4. AI & Schema Readiness", done: scanTools.some((t) => t.name?.toLowerCase().includes("aeo") || t.state === "done") },
            ].map((step) => (
              <div
                key={step.id}
                style={{
                  background: step.done ? "#ecfdf5" : "#f8fafc",
                  border: `1px solid ${step.done ? "#a7f3d0" : "#e2e8f0"}`,
                  borderRadius: 6,
                  padding: "8px 12px",
                  fontSize: 12,
                  fontWeight: 600,
                  color: step.done ? "#065f46" : "var(--ink-muted)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span>{step.done ? "✓" : "⏳"}</span>
                <span>{step.title}</span>
              </div>
            ))}
          </div>

          {/* Toggle Developer Terminal Output */}
          <button
            type="button"
            onClick={() => setShowLogs((v) => !v)}
            style={{ background: "none", border: "none", color: "var(--ink-muted)", fontSize: 12, cursor: "pointer", padding: 0, textDecoration: "underline" }}
          >
            {showLogs ? "Hide technical audit logs" : "View technical audit logs"}
          </button>

          {showLogs && (
            <div
              style={{
                marginTop: 10,
                background: "#0f172a",
                color: "#a7f3d0",
                borderRadius: 6,
                padding: "12px 16px",
                fontFamily: "ui-monospace, monospace",
                fontSize: 12,
                maxHeight: 180,
                overflowY: "auto",
                lineHeight: 1.5,
              }}
            >
              {liveLogs.length > 0 ? (
                liveLogs.map((log, idx) => <div key={idx}>{log}</div>)
              ) : (
                <div style={{ color: "var(--ink-muted)" }}>Connecting to audit scanner backend...</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── 3. EXECUTIVE AUDIT SUMMARY (WHEN REPORT IS READY) ── */}
      {!isScanning && report && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Top Score Banner */}
          <div
            style={{
              background: "#ffffff",
              borderRadius: 10,
              border: "1px solid #e2e8f0",
              padding: "18px 22px",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 14,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              {/*
                `overallScore || 80` rendered a green "80 / 100 · Good Site
                Health" for a site nobody had scored, and swallowed a real score
                of 0 into the same 80. The component already reads
                `report?.score ?? null` correctly a few lines up — this is the
                coercion that threw that away.

                Unscored is its own state. Not 80, not 0, not a colour.
              */}
              {scored === null ? (
                <>
                  <div
                    style={{
                      width: 64, height: 64, borderRadius: "50%",
                      background: "#f1f5f9", border: "3px dashed #cbd5e1",
                      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                    }}
                  >
                    <div style={{ fontSize: 22, fontWeight: 800, color: "var(--ink-muted)", lineHeight: 1 }}>—</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 16, fontWeight: 800, color: "var(--ink-muted)" }}>Not scored yet</div>
                    <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 2 }}>
                      Run a scan to measure {inputUrl || currentDomain || "this site"}.
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: "50%",
                      background: scored >= 80 ? "#ecfdf5" : scored >= 60 ? "#fffbeb" : "#fef2f2",
                      border: `3px solid ${scored >= 80 ? "#10b981" : scored >= 60 ? "#f59e0b" : "#ef4444"}`,
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <div style={{ fontSize: 20, fontWeight: 900, color: scored >= 80 ? "#065f46" : scored >= 60 ? "#92400e" : "#991b1b", lineHeight: 1 }}>
                      {scored}
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase" }}>/ 100</div>
                  </div>

                  <div>
                    <div style={{ fontSize: 16, fontWeight: 800, color: "#0f172a" }}>
                      {scored >= 80 ? "Good Site Health" : scored >= 60 ? "Needs Improvement" : "Critical Fixes Required"}
                    </div>
                      <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 2 }}>
                        Audited <strong>{inputUrl || currentDomain}</strong> · {allRows.length} technical checks evaluated
                      </div>
                    </div>
                  </>
                )}
              </div>

            {/* Quick Filter Pill Badges */}
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                onClick={() => setSelectedCategory("all")}
                style={{
                  background: selectedCategory === "all" ? "#0f172a" : "#f1f5f9",
                  color: selectedCategory === "all" ? "#ffffff" : "#475569",
                  border: "none",
                  borderRadius: 6,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                All Checks ({allRows.length})
              </button>
              <button
                type="button"
                onClick={() => setSelectedCategory("error")}
                style={{
                  background: selectedCategory === "error" ? "#e11d48" : "#fef2f2",
                  color: selectedCategory === "error" ? "#ffffff" : "#991b1b",
                  border: `1px solid ${selectedCategory === "error" ? "#e11d48" : "#fecaca"}`,
                  borderRadius: 6,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                🔴 Errors ({errorCount})
              </button>
              <button
                type="button"
                onClick={() => setSelectedCategory("warn")}
                style={{
                  background: selectedCategory === "warn" ? "#d97706" : "#fffbeb",
                  color: selectedCategory === "warn" ? "#ffffff" : "#92400e",
                  border: `1px solid ${selectedCategory === "warn" ? "#d97706" : "#fde68a"}`,
                  borderRadius: 6,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                🟡 Warnings ({warnCount})
              </button>
              <button
                type="button"
                onClick={() => setSelectedCategory("ok")}
                style={{
                  background: selectedCategory === "ok" ? "#059669" : "#ecfdf5",
                  color: selectedCategory === "ok" ? "#ffffff" : "#065f46",
                  border: `1px solid ${selectedCategory === "ok" ? "#059669" : "#a7f3d0"}`,
                  borderRadius: 6,
                  padding: "6px 12px",
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                🟢 Passed ({okCount})
              </button>
            </div>
          </div>

          {/* Filtered Checks List */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {filteredRows.map((row, idx) => {
              const isErr = row.severity === "error";
              const isWarn = row.severity === "warn";
              const isOk = row.severity === "ok";

              return (
                <div
                  key={idx}
                  style={{
                    background: "#ffffff",
                    borderRadius: 8,
                    border: `1px solid ${isErr ? "#fecaca" : isWarn ? "#fde68a" : "#e2e8f0"}`,
                    padding: "12px 16px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: 12,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                      <span style={{ fontSize: 13 }}>{isErr ? "🔴" : isWarn ? "🟡" : "🟢"}</span>
                      <strong style={{ fontSize: 13, color: "#0f172a" }}>{row.what}</strong>
                      {row.detail && (
                        <span style={{ fontSize: 12, color: "var(--ink-muted)", background: "#f1f5f9", padding: "1px 6px", borderRadius: 4 }}>
                          {row.detail}
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: "#475569", lineHeight: 1.4 }}>
                      {row.why}
                    </div>
                    {row.fix && row.fix !== "passing" && (
                      <div style={{ fontSize: 12, color: "#166534", marginTop: 4, fontWeight: 600 }}>
                        Recommended Fix: {row.fix}
                      </div>
                    )}
                  </div>

                  {!isOk && onSelectFix && (
                    <button
                      type="button"
                      onClick={() => onSelectFix(row.code || row.what)}
                      style={{
                        background: "#0f172a",
                        color: "#ffffff",
                        border: "none",
                        borderRadius: 4,
                        padding: "5px 12px",
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: "pointer",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Review Fix →
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
