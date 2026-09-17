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
import { Icon } from "@/components/dashboard/Icon";

import type { ReaiTab } from "@/components/dashboard/types";
import { CHECKS_VIEW } from "@/lib/reportViews";
import { ReportTable, ReportStats } from "@/components/dashboard/ReportTable";
import { AuditHeroBar } from "@/components/dashboard/AuditHeroBar";
import { ScoreWhy, IssuesTable, PagesTable } from "@/components/dashboard/AuditResults";
import { HealthTrendPanel } from "@/components/dashboard/SeoDashboard";
import { ONPAGE_AUDIT_TOOLS, rankedIssues, crawledPages } from "@/lib/auditBreakdown";
import type { ScanLike } from "@/lib/dashboardMetrics";
import {
  IconTerminal,
  MiniRadialGauge,
} from "@/components/dashboard/primitives";

type AuditSubTab = "summary" | "issues" | "pages" | "all_checks" | "progress" | "remediation";

export interface MeasureScreenProps {
  report: any;
  allIssues: Array<{
    category: string; what: string; why: string; fix: string;
    detail: string; severity: string; code: string;
  }>;
  auditSubTab: AuditSubTab;
  onSubTabChange: (t: AuditSubTab) => void;
  currentDomain?: string;
  /** The project's saved scans, for the health trend. */
  scans?: ScanLike[] | null;
  /** Runs the on-page audit (`ONPAGE_AUDIT_TOOLS`, `pages` deep). */
  onRunAudit?: (url: string, tools: string[], pages: number) => void;
  crawlPages: number;
  onCrawlPagesChange: (n: number) => void;
  lastScanAt?: string | null;
  onEditProject?: () => void;
  onCreateProject?: () => void;
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
  /**
   * Rendered at the foot of the screen. A slot rather than a direct import so
   * this component keeps knowing nothing about Claude, the fixer, or any route -
   * it measures and displays, and the caller decides what to offer next.
   */
  footer?: React.ReactNode;
  /** Sends these results to the Plan stage and opens it. Absent: no button. */
  onSendToPlan?: () => void;
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
  scans,
  onRunAudit,
  crawlPages,
  onCrawlPagesChange,
  lastScanAt,
  onEditProject,
  onCreateProject,
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
  footer,
  onSendToPlan,
  setAuditSeverityFilter,
  setActiveTab,
  planState,
  setShowExecutiveReportModal,
}: MeasureScreenProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── ONE RUN BAR ── The on-page audit, and nothing else runs from here.
          It replaced an audit bar that drew its own score and check list, a
          Data source dropdown with a price, and a second set of charts above
          the page: three health summaries on one screen. ── */}
      <AuditHeroBar
        currentDomain={currentDomain}
        onRunAudit={(url, tools, pages) => onRunAudit?.(url, tools, pages)}
        isScanning={scanState?.busy}
        phaseLine={scanState?.phaseLine}
        scanTools={scanState?.tools}
        liveLogs={scanState?.live}
        pages={crawlPages}
        onPagesChange={onCrawlPagesChange}
        lastScanAt={lastScanAt}
        onEditProject={onEditProject}
        onCreateProject={onCreateProject}
      />

      {/* ── TABS ── One view of the results at a time. */}
      {(() => {
        const issueCount = rankedIssues(report).length;
        const pageCount = crawledPages(report)?.length;
        const tabs: Array<{ id: AuditSubTab; label: string; count?: number }> = [
          { id: "summary", label: "Overview" },
          { id: "issues", label: "Issues", count: issueCount },
          { id: "pages", label: "Pages", count: pageCount },
          { id: "all_checks", label: "All checks" },
          { id: "progress", label: "History" },
        ];
        return (
          <div className="audit-tabs-row">
          <div className="audit-tabs" role="tablist" aria-label="Site Audit views">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={auditSubTab === t.id}
                className="audit-tabs__tab"
                onClick={() => onSubTabChange(t.id)}
              >
                {t.label}
                {typeof t.count === "number" && <span className="audit-tabs__count">{t.count}</span>}
              </button>
            ))}
          </div>
          {/* Audit results -> Plan: the ratchet over the last two saved scans,
              then the Plan page, so the handoff is one click, not a hunt. */}
          {onSendToPlan && (
            <button
              type="button"
              className="btn btn--secondary btn--sm audit-tabs-row__plan"
              onClick={onSendToPlan}
              disabled={planState?.planBusy || issueCount === 0}
              title={issueCount === 0 ? "No issues to plan yet. Run the audit first." : "Sort these findings into a worklist on the Plan page"}
            >
              {planState?.planBusy ? "Planning…" : "Send to Plan →"}
            </button>
          )}
          </div>
        );
      })()}

      {auditSubTab === "summary" && (
        <div className="seo-dash-wrap">
          <div className="audit-overview">
            <section className="seo-panel" style={{ gridArea: "score" }} aria-labelledby="sa-score">
              <header className="seo-panel__head">
                <div>
                  <h3 id="sa-score" className="seo-panel__title">Site Health</h3>
                  <div className="seo-panel__sub">Scored on the on-page audit only</div>
                </div>
              </header>
              <div className="seo-panel__body">
                <ScoreWhy report={report} onRun={currentDomain ? () => onRunAudit?.(currentDomain, [...ONPAGE_AUDIT_TOOLS], crawlPages) : undefined} />
              </div>
            </section>
            <HealthTrendPanel scans={scans} domain={currentDomain ?? ""} />
            <section className="seo-panel" style={{ gridArea: "issues" }} aria-labelledby="sa-top">
              <header className="seo-panel__head">
                <div>
                  <h3 id="sa-top" className="seo-panel__title">Fix These First</h3>
                  <div className="seo-panel__sub">Errors first, then the checks failing on the most pages</div>
                </div>
                <button type="button" className="seo-panel__link" onClick={() => onSubTabChange("issues")}>All issues <span aria-hidden="true">→</span></button>
              </header>
              <div className="seo-panel__body">
                <IssuesTable report={report} limit={5} onSeeAll={() => onSubTabChange("issues")} />
              </div>
            </section>
          </div>
        </div>
      )}

      {auditSubTab === "issues" && (
        <div className="seo-dash-wrap">
          <section className="seo-panel" aria-labelledby="sa-issues">
            <header className="seo-panel__head">
              <div>
                <h3 id="sa-issues" className="seo-panel__title">Issues</h3>
                <div className="seo-panel__sub">Every failing check from the on-page audit. Open a row for why it matters, how to fix it and the pages.</div>
              </div>
            </header>
            <div className="seo-panel__body">
              <IssuesTable report={report} />
            </div>
          </section>
        </div>
      )}

      {auditSubTab === "pages" && (
        <div className="seo-dash-wrap">
          <section className="seo-panel" aria-labelledby="sa-pages">
            <header className="seo-panel__head">
              <div>
                <h3 id="sa-pages" className="seo-panel__title">Crawled Pages</h3>
                <div className="seo-panel__sub">Every page the audit read, worst first. Open a row for its failing checks.</div>
              </div>
            </header>
            <div className="seo-panel__body">
              <PagesTable report={report} />
            </div>
          </section>
        </div>
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
                    background: "var(--accent)", color: "var(--color-white)", border: 0, borderRadius: 6,
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
                  if (onRunAudit && currentDomain) onRunAudit(currentDomain, [...ONPAGE_AUDIT_TOOLS], crawlPages);
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
                    background: "var(--info-tint)", border: "1px solid var(--info-border)", color: "var(--info)",
                    borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 600,
                    cursor: "pointer", display: "flex", alignItems: "center", gap: 5,
                  }}
                >
                  <Icon name="file" /> Export to Client Report
                </button>
              </div>
            </div>

            {/* Spend Safety Latch Banner */}
            <div style={{
              background: "var(--ok-tint)", border: "1px solid var(--ok-border)", borderRadius: 8, padding: "10px 14px",
              display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--ok)", fontWeight: 600,
            }}>
              <Icon name="shield" size={14} />
              <span><b>Zero-Spend Guarantee Active:</b> Historical crawl comparisons and AST remediation audits are processed locally with <b>$0.00 external API spend</b>.</span>
            </div>

            {/* 3 Crawl Milestone Cards Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              {historicalSnapshots.map((snap, i) => (
                <div
                  key={snap.id}
                  style={{
                    background: "var(--surface)", borderRadius: 8, border: "1px solid",
                    borderColor: i === 2 ? "var(--ok-border)" : "var(--border)",
                    padding: "16px 18px", display: "flex", flexDirection: "column",
                    boxShadow: i === 2 ? "0 4px 12px rgba(29, 185, 84, 0.08)" : "none",
                    position: "relative",
                  }}
                >
                  {i === 2 && (
                    <span style={{
                      position: "absolute", top: 12, right: 14, fontSize: 12, fontWeight: 800,
                      color: "var(--ok)", background: "var(--ok-tint)", padding: "2px 7px", borderRadius: 4,
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
                      <div style={{ fontSize: 14, fontWeight: 800, color: snap.errors > 0 ? "var(--bad)" : "var(--ok)" }}>{snap.errors}</div>
                      <div style={{ fontSize: 12, color: "var(--bad)", fontWeight: 600 }}>Errors</div>
                    </div>
                    <div style={{ background: "var(--warn-tint)", borderRadius: 6, padding: "6px 4px" }}>
                      <div style={{ fontSize: 14, fontWeight: 800, color: "var(--warn)" }}>{snap.warns}</div>
                      <div style={{ fontSize: 12, color: "var(--warn)", fontWeight: 600 }}>Warnings</div>
                    </div>
                    <div style={{ background: "var(--surface-3)", borderRadius: 6, padding: "6px 4px" }}>
                      <div style={{ fontSize: 14, fontWeight: 800, color: "var(--ink-body)" }}>{snap.pages}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>Pages</div>
                    </div>
                  </div>

                  <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.4, marginTop: "auto" }}>
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
                              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--bad)", background: "var(--bad-tint)", padding: "2px 7px", borderRadius: 4 }}>
                                {diff.baseline}
                              </span>
                            </td>
                            <td style={{ padding: "11px 14px" }}>
                              <span style={{ fontSize: 12, fontWeight: 700, color: "var(--ok)", background: "var(--ok-tint)", padding: "2px 7px", borderRadius: 4 }}>
                                {diff.current}
                              </span>
                            </td>
                            <td style={{ padding: "11px 14px", color: "var(--ink-body)", maxWidth: 320 }}>
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
      {footer}
    </div>
  );
}
