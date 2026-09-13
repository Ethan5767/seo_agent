"use client";

/**
 * The Measure screen (the "Site Health & Audit" tab).
 *
 * Lifted verbatim out of ReaiDashboard.tsx, which was 13,437 lines against
 * the 1,000-line ceiling in AGENTS.md Rule 1. A move, not a rewrite: every
 * identifier the block referenced and did not define became a prop, and the
 * rendering is unchanged.
 */

import React from "react";

import type { ReaiTab } from "@/components/dashboard/types";
import { ALL_FINDINGS_VIEW, CHECKS_VIEW } from "@/lib/reportViews";
import { derivePillars, severityMark, severityTone } from "@/lib/pillars";
import { tone } from "@/lib/ui";
import { ReportTable, ReportStats } from "@/components/dashboard/ReportTable";
import { AuditHeroBar } from "@/components/dashboard/AuditHeroBar";
import {
  IconTerminal,
  MiniRadialGauge,
  SiteHealthDonut,
  CrawledPagesBar,
} from "@/components/dashboard/primitives";

type AuditSubTab = "summary" | "all_checks" | "progress" | "remediation";

export interface MeasureScreenProps {
  report: any;
  allIssues: Array<{
    category: string; what: string; why: string; fix: string;
    detail: string; severity: string; code: string;
  }>;
  auditSubTab: AuditSubTab;
  onSubTabChange: (t: AuditSubTab) => void;
  currentDomain?: string;
  onRunAudit?: (url: string) => void;
  scanState?: { busy: boolean; phaseLine: string; live: string[]; tools: any[] };

  /*
   * Beyond the interface in the task brief. The block references all of these
   * and defines none of them, so each one has to cross the boundary. They are
   * typed to exactly what the markup reads, never to the wider dashboard
   * state they come from.
   */
  currentBusiness: string;
  okChecks: number;
  warnChecks: number;
  errChecks: number;
  infoChecks: number;
  /** Null when nothing gradeable ran. Not zero: a scan that measured nothing
   *  has no health to report, and 0% reads as "everything is broken". */
  dynamicHealth: number | null;
  auditCategoryFilter: string;
  setAuditCategoryFilter: (key: string) => void;
  auditSeverityFilter: CheckSeverityFilter;
  setAuditSeverityFilter: (sev: CheckSeverityFilter) => void;
  setActiveTab: (tab: ReaiTab) => void;
  planState?: {
    plan: any; planBusy: boolean; runPlan: () => Promise<void>;
    remed: any; remedBusy: boolean; runRemediate: () => Promise<void>;
    dry: any; dryBusy: boolean; runDryRun: () => Promise<void>;
    apply: any; applyBusy: boolean; runApply: () => Promise<void>;
  };
  setShowExecutiveReportModal: (open: boolean) => void;
}

/**
 * The filter bar above the All Checks table.
 *
 * Category grouping and severity are real filters the shared ReportTable does
 * not provide, so they stay when the rest of that sub-tab moves onto the
 * shared table. They live here rather than inline so the sub-tab reads as
 * filter, count strip, table.
 */
export type CheckSeverityFilter = "all" | "error" | "warn" | "ok";

export function ChecksFilterBar({
  categories,
  rows,
  category,
  onCategory,
  severity,
  onSeverity,
}: {
  categories: Array<{ key: string; label: string }>;
  rows: Array<{ catKey?: string }>;
  category: string;
  onCategory: (key: string) => void;
  severity: CheckSeverityFilter;
  onSeverity: (sev: CheckSeverityFilter) => void;
}) {
  return (
    <>
      {/* Category filter chips */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14, borderBottom: "1px solid var(--surface-3)", paddingBottom: 12 }}>
        {categories.map((cat) => {
          // The count is a count of the rows themselves, never an estimate.
          const count = cat.key === "all"
            ? rows.length
            : rows.filter((r) => r.catKey === cat.key).length;
          const isSelected = category === cat.key;
          return (
            <button
              key={cat.key}
              type="button"
              onClick={() => onCategory(cat.key)}
              style={{
                background: isSelected ? "var(--ink-body)" : "var(--surface-2)",
                color: isSelected ? "var(--surface)" : "var(--ink-muted)",
                border: "1px solid", borderColor: isSelected ? "var(--ink-body)" : "var(--border)",
                borderRadius: 20, padding: "4px 12px", fontSize: 12, fontWeight: isSelected ? 700 : 500,
                cursor: "pointer", display: "flex", alignItems: "center", gap: 6,
                transition: "all 0.15s ease",
              }}
            >
              <span>{cat.label}</span>
              <span style={{
                fontSize: 12, padding: "1px 5px", borderRadius: 10,
                background: isSelected ? "rgba(255,255,255,0.2)" : "var(--border)",
                color: isSelected ? "var(--surface)" : "var(--ink-muted)",
              }}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Severity quick filters */}
      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", gap: 6 }}>
          {(["all", "error", "warn", "ok"] as const).map((sev) => (
            <button
              key={sev}
              type="button"
              onClick={() => onSeverity(sev)}
              style={{
                background: severity === sev ? "var(--border)" : "transparent",
                border: "1px solid", borderColor: severity === sev ? "var(--border-strong)" : "var(--border)",
                borderRadius: 4, padding: "3px 8px", fontSize: 12, fontWeight: 600,
                color: sev === "error" ? "var(--bad)" : sev === "warn" ? "var(--warn)" : sev === "ok" ? "var(--ok)" : "var(--ink-muted)",
                cursor: "pointer", textTransform: "capitalize",
              }}
            >
              {sev === "all" ? "All Severities" : sev === "ok" ? "Passed Only" : `${sev}s`}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

export function MeasureScreen({
  report,
  allIssues,
  auditSubTab,
  onSubTabChange,
  currentDomain,
  onRunAudit,
  scanState,
  currentBusiness,
  okChecks,
  warnChecks,
  errChecks,
  infoChecks,
  dynamicHealth,
  auditCategoryFilter,
  setAuditCategoryFilter,
  auditSeverityFilter,
  setAuditSeverityFilter,
  setActiveTab,
  planState,
  setShowExecutiveReportModal,
}: MeasureScreenProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── UNIFIED WEBSITE AUDIT INPUT BAR & PROGRESS ── */}
      <AuditHeroBar
        currentDomain={currentDomain}
        onRunAudit={(url) => {
          if (onRunAudit) onRunAudit(url);
        }}
        isScanning={scanState?.busy}
        phaseLine={scanState?.phaseLine}
        scanTools={scanState?.tools}
        liveLogs={scanState?.live}
        report={report}
        onSelectFix={(code) => {
          setActiveTab("Auto-Fix Engine");
          if (planState && !planState.plan?.worklist) planState.runPlan();
        }}
      />

      {/* Header Navigation & CTA Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #edf0f4", paddingBottom: 12, flexWrap: "wrap", gap: 10 }}>
        <div style={{ display: "flex", gap: 8 }}>
          {[
            { id: "summary", label: "Executive Summary & Issues" },
            { id: "all_checks", label: "All Technical Checks (Full Report)" },
            { id: "progress", label: "Crawl History & Timeline" },
          ].map((st) => (
            <button
              key={st.id}
              type="button"
              onClick={() => onSubTabChange(st.id as any)}
              style={{
                background: auditSubTab === st.id ? "var(--ink-body)" : "var(--surface)",
                color: auditSubTab === st.id ? "var(--surface)" : "#475569",
                border: "1px solid",
                borderColor: auditSubTab === st.id ? "var(--ink-body)" : "var(--border)",
                borderRadius: 6, padding: "7px 16px",
                fontSize: 12.5, fontWeight: 600, cursor: "pointer",
                boxShadow: auditSubTab === st.id ? "0 1px 2px rgba(30, 41, 59, 0.2)" : "0 1px 2px rgba(0,0,0,0.03)",
              }}
            >
              {st.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => {
            setActiveTab("Auto-Fix Engine");
            if (planState && !planState.plan?.worklist) planState.runPlan();
          }}
          style={{
            background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
            color: "var(--surface)", border: 0, borderRadius: 6,
            padding: "7px 16px", fontSize: 12, fontWeight: 700, cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6,
            boxShadow: "0 2px 4px rgba(16, 185, 129, 0.3)",
          }}
        >
          <IconTerminal size={15} /> Launch Auto-Fix Engine →
        </button>
      </div>

      {auditSubTab === "summary" && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 12 }}>
            <div style={{ background: "var(--surface)", padding: "18px 20px", borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
              {dynamicHealth === null ? (
                <div style={{ width: 92, height: 92, borderRadius: "50%", border: "2px dashed #cbd5e1",
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 12, color: "var(--ink-muted)", textAlign: "center", padding: 8 }}>
                  Not measured
                </div>
              ) : (
                <SiteHealthDonut score={dynamicHealth} size={92} />
              )}
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-body)", marginTop: 10 }}>Site Health Score</div>
              <div style={{ fontSize: 12, color: "var(--ink-muted)", textAlign: "center", marginTop: 3 }}>
                {okChecks + warnChecks + errChecks} technical checks
              </div>
            </div>

            <div style={{ background: "var(--surface)", padding: "18px 20px", borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 12 }}>
                <div style={{ padding: "10px 12px", borderRadius: 6, background: "var(--bad-tint)", border: "1px solid var(--bad-border)" }}>
                  <div style={{ fontSize: 12, color: "#991b1b", fontWeight: 600 }}>Errors (Critical)</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: "var(--bad)", marginTop: 2 }}>{errChecks}</div>
                </div>
                <div style={{ padding: "10px 12px", borderRadius: 6, background: "var(--warn-tint)", border: "1px solid var(--warn-border)" }}>
                  <div style={{ fontSize: 12, color: "#92400e", fontWeight: 600 }}>Warnings</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: "var(--warn)", marginTop: 2 }}>{warnChecks}</div>
                </div>
                <div style={{ padding: "10px 12px", borderRadius: 6, background: "var(--ok-tint)", border: "1px solid var(--ok-border)" }}>
                  <div style={{ fontSize: 12, color: "#065f46", fontWeight: 600 }}>Passing Checks</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: "var(--ok)", marginTop: 2 }}>{okChecks}</div>
                </div>
                <div style={{ padding: "10px 12px", borderRadius: 6, background: "#f0f9ff", border: "1px solid #bae6fd" }}>
                  <div style={{ fontSize: 12, color: "#0369a1", fontWeight: 600 }}>Notices</div>
                  <div style={{ fontSize: 24, fontWeight: 800, color: "var(--info)", marginTop: 2 }}>{infoChecks}</div>
                </div>
              </div>
              <CrawledPagesBar ok={okChecks} warn={warnChecks} error={errChecks} info={infoChecks} />
            </div>
          </div>

          {/* ── THEMATIC MEASURE CHECKING TOOL ── */}
          <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "18px 20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "var(--ink-body)" }}>
                    Thematic Measure Checking Tool
                  </h4>
                  <span style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)", background: "#eef2ff", border: "1px solid #c7d2fe", padding: "2px 7px", borderRadius: 4 }}>
                    Technical SEO + AEO
                  </span>
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                  Comprehensive category diagnostic health scores across 6 core technical pillars
                </div>
              </div>
              <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                {okChecks + warnChecks + errChecks} total evaluated checks
              </span>
            </div>

            {/*
              Pillar cards.

              Every bullet, score, badge and colour below is read from
              derivePillars(report), which slices the report's own tool groups.
              What was here before was six literals: green-ticked claims like
              "SSL/TLS 256-bit active", "HSTS header enabled", "0 orphan URLs
              detected" and "MedicalBusiness JSON-LD" (a healthcare schema
              asserted for every client, whatever the industry), each card
              scoring 0 while painted with the pass colour, and one badge
              reading "AI Ready" over a pillar nothing had measured.
            */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--space-3)" }}>
              {derivePillars(report).map((m) => {
                const t = tone(m.tone);
                return (
                <div key={m.catKey} style={{
                  border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: "var(--space-4)",
                  background: "var(--surface)", display: "flex", flexDirection: "column", justifyContent: "space-between",
                }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)", gap: "var(--space-2)" }}>
                      <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--ink-body)" }}>{m.title}</span>
                      <span style={{
                        fontSize: "var(--text-xs)", fontWeight: 700, color: t.fg,
                        background: t.bg, border: `1px solid ${t.border}`,
                        padding: "2px var(--space-2)", borderRadius: "var(--radius-xs)", whiteSpace: "nowrap",
                      }}>
                        {m.status}
                      </span>
                    </div>

                    <div style={{ display: "flex", alignItems: "baseline", gap: "var(--space-2)", marginBottom: "var(--space-2)" }}>
                      {/* A pillar with no graded rows shows an em dash, never a 0% dressed as a pass. */}
                      <span style={{ fontSize: "var(--text-2xl)", fontWeight: 800, color: m.score === null ? "var(--ink-muted)" : "var(--ink)" }}>
                        {m.score === null ? "—" : `${m.score}%`}
                      </span>
                      <span style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)" }}>
                        {m.score === null ? "no graded checks" : `${m.ok} of ${m.ok + m.warn + m.error} checks passing`}
                      </span>
                    </div>

                    {/*
                      The distribution, not the average again.
                      This was a single bar filled to the score, which restates
                      the number above it and hides the shape: 60% passing looks
                      identical whether the other 40% is all notices or all
                      server errors. Sitebulb never shows an average without its
                      spread, and that is the right rule - the average is what
                      you report, the spread is what you act on.
                      Segments are labelled in the title text as well as
                      coloured, so the information survives greyscale and
                      colour-vision deficiency (WCAG 1.4.1).
                    */}
                    <div
                      title={m.measured
                        ? `${m.error} error, ${m.warn} warning, ${m.info} notice, ${m.ok} passing`
                        : "nothing gradeable ran"}
                      style={{ display: "flex", height: "var(--space-1)", background: "var(--surface-3)",
                               borderRadius: "var(--radius-full)", overflow: "hidden",
                               marginBottom: "var(--space-3)" }}
                    >
                      {m.measured && [
                        { n: m.error, c: "var(--bad)" },
                        { n: m.warn, c: "var(--warn)" },
                        { n: m.info, c: "var(--info)" },
                        { n: m.ok, c: "var(--ok)" },
                      ].map(({ n, c }, si) => n > 0 && (
                        <div key={si} style={{ flexGrow: n, background: c }} />
                      ))}
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
                      {m.items.length === 0 ? (
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)" }}>
                          No check in this area has run on {currentDomain || "this site"} yet.
                        </div>
                      ) : m.items.map((it, idx) => (
                        <div key={idx} style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)", display: "flex", alignItems: "baseline", gap: "var(--space-2)" }}>
                          <span style={{ color: tone(severityTone(it.severity)).fg, fontWeight: 700 }}>
                            {severityMark(it.severity)}
                          </span>
                          <span>
                            {it.label}
                            {it.detail ? <span style={{ color: "var(--ink-faint)" }}> · {it.detail}</span> : null}
                          </span>
                        </div>
                      ))}
                      {m.total > m.items.length ? (
                        <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-faint)" }}>
                          + {m.total - m.items.length} more check{m.total - m.items.length === 1 ? "" : "s"}
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      onSubTabChange("all_checks");
                      setAuditCategoryFilter(m.catKey);
                    }}
                    style={{
                      marginTop: "var(--space-3)", borderTop: "1px solid var(--surface-3)", paddingTop: "var(--space-2)",
                      background: "none", border: 0, color: "var(--accent)",
                      fontSize: "var(--text-xs)", fontWeight: 600, cursor: "pointer",
                      textAlign: "left", padding: "var(--space-2) 0 0", display: "flex", justifyContent: "space-between", alignItems: "center",
                    }}
                  >
                    <span>Inspect {m.title.split(" ")[0]} Checks</span>
                    <span>→</span>
                  </button>
                </div>
                );
              })}
            </div>
          </div>

          {/*
            Audited Findings.

            This was a bespoke list with four severity buttons and no
            search, sort or pagination, rendering its own row markup.
            It now goes through the same table every report view uses,
            so the audit screen gains filtering and sorting, the row
            treatment matches the rest of the product, and there is one
            findings table to maintain instead of two.
          */}
          <div style={{ marginBottom: "var(--space-5)" }}>
            <h4 style={{ margin: "0 0 var(--space-1)", fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>
              Audited Findings
            </h4>
            <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 var(--space-4)" }}>
              Every finding from every tool that ran on this scan.
            </p>
            <ReportStats rows={allIssues as any} />
            <ReportTable
              view={ALL_FINDINGS_VIEW}
              rows={allIssues as any}
              onRunAudit={() => {
                if (onRunAudit && currentDomain) onRunAudit(currentDomain);
              }}
            />
          </div>
        </>
      )}

      {/* Sub-tab: All Checks Full Report */}
      {auditSubTab === "all_checks" && (() => {
        const categoryList = [
          { key: "all", label: "All Checks" },
          { key: "seo", label: "Crawlability & SEO" },
          { key: "tech", label: "Security & HTTPS" },
          { key: "perf", label: "Core Web Vitals & Speed" },
          { key: "aeo", label: "AEO & LLM Search Readiness" },
          { key: "site", label: "Architecture & Linking" },
          { key: "schema", label: "Structured Data (Schema)" },
          { key: "content", label: "Content & Metadata" },
          { key: "eeat", label: "E-E-A-T & Trust" },
        ];

        const allCategoryRows: Array<any & { catKey: string }> = [];
        ["seo", "tech", "aeo", "perf", "site", "schema", "content", "eeat"].forEach((ck) => {
          const rows = ((report && report[ck]) || []) as Array<any>;
          rows.forEach((r) => allCategoryRows.push({ ...r, catKey: ck }));
        });

        // An empty report stays empty. A real pass is an "ok" row from
        // audit.py; the 19 hardcoded ones that were here measured nothing.

        const filteredChecks = allCategoryRows.filter((r) => {
          if (auditCategoryFilter !== "all" && r.catKey !== auditCategoryFilter) return false;
          if (auditSeverityFilter !== "all" && r.severity !== auditSeverityFilter) return false;
          return true;
        });

        return (
          <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div>
                <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "var(--ink-body)" }}>
                  Complete Technical Checks & Graded Rules
                </h4>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>
                  Every check that ran on <b>{currentDomain}</b>, passes included.
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab("Auto-Fix Engine");
                    if (planState && !planState.plan?.worklist) planState.runPlan();
                  }}
                  style={{
                    background: "var(--accent)", color: "#fff", border: 0, borderRadius: 6,
                    padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer",
                    display: "flex", alignItems: "center", gap: 6,
                  }}
                >
                  <IconTerminal size={14} /> Launch Auto-Fix Engine
                </button>
              </div>
            </div>

            <ChecksFilterBar
              categories={categoryList}
              rows={allCategoryRows}
              category={auditCategoryFilter}
              onCategory={setAuditCategoryFilter}
              severity={auditSeverityFilter}
              onSeverity={setAuditSeverityFilter}
            />

            {/* Was ~90 lines of bespoke rows and its own search box. */}
            <ReportStats rows={filteredChecks as any} />
            {filteredChecks.length === 0 && allCategoryRows.length > 0 ? (
              // Data exists; the filter hid it. ReportTable's empty state
              // would say "no data" and offer a paid scan as the way out.
              <div
                style={{
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-md)",
                  background: "var(--surface-2)",
                  padding: "var(--space-5)",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: 13, color: "var(--ink-body)", fontWeight: 600 }}>
                  No Diagnostic Checks Match This Filter
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: "var(--space-1)" }}>
                  {allCategoryRows.length} check{allCategoryRows.length === 1 ? "" : "s"} ran on this
                  site. None of them match the selected category and severity.
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setAuditCategoryFilter("all");
                    setAuditSeverityFilter("all");
                  }}
                  style={{
                    marginTop: "var(--space-3)",
                    background: "var(--surface)",
                    color: "var(--ink-body)",
                    border: "1px solid var(--border-strong)",
                    borderRadius: "var(--radius-sm)",
                    padding: "var(--space-2) var(--space-4)",
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Clear Filters
                </button>
              </div>
            ) : (
              <ReportTable
                view={CHECKS_VIEW}
                rows={filteredChecks as any}
                onRunAudit={() => {
                  if (onRunAudit && currentDomain) onRunAudit(currentDomain);
                }}
              />
            )}
          </div>
        );
      })()}

      {/* Sub-tab: Crawl History & Progress Timeline */}
      {auditSubTab === "progress" && (() => {
        const historicalSnapshots: any[] = [
          // Was a hardcoded fixture: past crawl scores. Real values come from
          // the scan report; with no scan there is nothing to show, and an
          // empty list is the honest answer.
        ];

        const issueDiffAudit: any[] = [
          // Was six entries, every one status: "Resolved", describing
          // fixes that never ran (including "Auto-injected Next.js 14
          // Metadata API in app/layout.tsx & page.tsx"). Real applied
          // fixes live in the cycle's changelog.json, written by
          // wf-site-remediate; this screen does not read it yet, so it
          // shows nothing rather than a convincing fake.
        ];

        return (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Header Banner */}
            <div style={{
              background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 20px",
              display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12,
            }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h4 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "var(--ink-body)" }}>
                    Crawl History & Health Recovery Timeline
                  </h4>
                  {/* Was a hardcoded "+26%
                      Health Recovery" badge. A real lift
                      requires two scans in the `scans` table to diff; this screen
                      does not read scan history yet, so no badge renders. */}
                </div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>
                  Tracking audit progression and error resolution across crawl checkpoints for <b>{currentBusiness}</b>
                </div>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => setShowExecutiveReportModal(true)}
                  style={{
                    background: "var(--info-tint)", border: "1px solid var(--info-border)", color: "#1d4ed8",
                    borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 600,
                    cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
                  }}
                >
                  <span>📄</span> Export to Client Report
                </button>
              </div>
            </div>

            {/* Spend Safety Latch Banner */}
            <div style={{
              background: "var(--ok-tint)", border: "1px solid var(--ok-border)", borderRadius: 8, padding: "10px 14px",
              display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#065f46", fontWeight: 600,
            }}>
              <span style={{ fontSize: 14 }}>🛡️</span>
              <span><b>Zero-Spend Guarantee Active:</b> Historical crawl comparisons and AST remediation audits are processed locally with <b>$0.00 external API spend</b>.</span>
            </div>

            {/* 3 Crawl Milestone Cards Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              {historicalSnapshots.map((snap, i) => (
                <div
                  key={snap.id}
                  style={{
                    background: "var(--surface)", borderRadius: 8, border: "1px solid",
                    borderColor: i === 2 ? "#86efac" : "var(--border)",
                    padding: "16px 18px", display: "flex", flexDirection: "column",
                    boxShadow: i === 2 ? "0 4px 12px rgba(16, 185, 129, 0.08)" : "none",
                    position: "relative",
                  }}
                >
                  {i === 2 && (
                    <span style={{
                      position: "absolute", top: 12, right: 14, fontSize: 12, fontWeight: 800,
                      color: "#047857", background: "#d1fae5", padding: "2px 7px", borderRadius: 4,
                    }}>
                      ACTIVE TODAY
                    </span>
                  )}

                  <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-muted)", textTransform: "uppercase" }}>
                    Crawl #{i + 1} · {snap.date}
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-body)", marginTop: 2, marginBottom: 10 }}>
                    {snap.label}
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12, padding: "10px 12px", background: "var(--surface-2)", borderRadius: 8 }}>
                    <MiniRadialGauge score={snap.score} size={44} strokeWidth={4} color={snap.color} />
                    <div>
                      <div style={{ fontSize: 20, fontWeight: 800, color: snap.color, lineHeight: 1.1 }}>
                        {snap.score}%
                      </div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>{snap.grade}</div>
                    </div>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, textAlign: "center", marginBottom: 10 }}>
                    <div style={{ background: "var(--bad-tint)", borderRadius: 6, padding: "6px 4px" }}>
                      <div style={{ fontSize: 14, fontWeight: 800, color: snap.errors > 0 ? "#b91c1c" : "var(--ok)" }}>{snap.errors}</div>
                      <div style={{ fontSize: 12, color: "#991b1b", fontWeight: 600 }}>Errors</div>
                    </div>
                    <div style={{ background: "var(--warn-tint)", borderRadius: 6, padding: "6px 4px" }}>
                      <div style={{ fontSize: 14, fontWeight: 800, color: "#b45309" }}>{snap.warns}</div>
                      <div style={{ fontSize: 12, color: "#92400e", fontWeight: 600 }}>Warnings</div>
                    </div>
                    <div style={{ background: "var(--surface-3)", borderRadius: 6, padding: "6px 4px" }}>
                      <div style={{ fontSize: 14, fontWeight: 800, color: "#334155" }}>{snap.pages}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Pages</div>
                    </div>
                  </div>

                  <div style={{ fontSize: 12, color: "#475569", lineHeight: 1.4, marginTop: "auto" }}>
                    {snap.summary}
                  </div>
                </div>
              ))}
            </div>

            {/* Was a "Crawl-to-Crawl
                Recovery Delta" panel with four hardcoded cards: a health
                score lift ("+26
                pts", "68% → 94%
                Grade A"), errors fixed ("-24
                Errors", "100% Critical Errs
                Resolved"), warnings resolved ("-14
                Warnings", "78%
                Reduction"), and a pages-audited count. A real delta
                requires diffing two rows in the `scans` table, which this
                screen does not read yet, so the panel is removed rather
                than showing invented figures. */}

            {/* Historical Issue Diff Table */}
            <div style={{ background: "var(--surface)", borderRadius: 8, border: "1px solid var(--border)", padding: "16px 18px" }}>
              <h4 style={{ margin: "0 0 12px", fontSize: 13.5, fontWeight: 700, color: "var(--ink-body)", textTransform: "uppercase" }}>
                Historical Issue Diff & Remediation Audit Log
              </h4>
              {issueDiffAudit.length === 0 ? (
                // Empty state, matching the pattern in
                // components/dashboard/ReportTable.tsx ("No data here yet"):
                // a heading, why it's empty, and where real data comes from.
                // Applied fixes are recorded in the cycle's changelog.json by
                // wf-site-remediate; this screen does not read it yet.
                <div
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-md)",
                    background: "var(--surface)",
                    padding: "var(--space-5) var(--space-4)",
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>
                    No data here yet
                  </div>
                  <p
                    style={{
                      fontSize: 13,
                      color: "var(--ink-muted)",
                      margin: "var(--space-2) auto 0",
                      maxWidth: "54ch",
                      lineHeight: 1.55,
                    }}
                  >
                    No remediation has been recorded against a baseline crawl for{" "}
                    <b>{currentBusiness}</b> yet.
                  </p>
                  <p
                    style={{
                      fontSize: 13,
                      color: "var(--ink-muted)",
                      margin: "var(--space-2) auto 0",
                      maxWidth: "54ch",
                    }}
                  >
                    Applied fixes are written to the cycle&apos;s changelog.json by
                    wf-site-remediate; once this screen reads it, resolved issues
                    will appear here automatically.
                  </p>
                </div>
              ) : (
                <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
                      <thead>
                        <tr style={{ background: "var(--surface-2)", borderBottom: "1px solid var(--border)", color: "var(--ink-muted)", fontSize: 12, textTransform: "uppercase" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Diagnostic Code & Category</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Initial Baseline Crawl</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Current Audit</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700 }}>Autonomous Claude Code Remediation</th>
                          <th style={{ padding: "10px 14px", fontWeight: 700, textAlign: "right" }}>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {issueDiffAudit.map((diff, i) => (
                          <tr key={diff.code} style={{ borderBottom: i === issueDiffAudit.length - 1 ? "none" : "1px solid var(--surface-3)" }}>
                            <td style={{ padding: "11px 14px" }}>
                              <div style={{ fontWeight: 700, color: "var(--ink-body)", fontFamily: "monospace" }}>{diff.code}</div>
                              <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>{diff.category}</div>
                            </td>
                            <td style={{ padding: "11px 14px" }}>
                              <span style={{ fontSize: 12, fontWeight: 600, color: "#b91c1c", background: "var(--bad-tint)", padding: "2px 7px", borderRadius: 4 }}>
                                {diff.baseline}
                              </span>
                            </td>
                            <td style={{ padding: "11px 14px" }}>
                              <span style={{ fontSize: 12, fontWeight: 700, color: "#047857", background: "var(--ok-tint)", padding: "2px 7px", borderRadius: 4 }}>
                                {diff.current}
                              </span>
                            </td>
                            <td style={{ padding: "11px 14px", color: "#334155", maxWidth: 320 }}>
                              {diff.fixAction}
                            </td>
                            <td style={{ padding: "11px 14px", textAlign: "right" }}>
                              <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "var(--ok-tint)", border: "1px solid var(--ok-border)", padding: "3px 8px", borderRadius: 4 }}>
                                ✓ {diff.status.toUpperCase()}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
