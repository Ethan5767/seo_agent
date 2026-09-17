"use client";

import React from "react";
import { IssuesTable } from "@/components/dashboard/AuditResults";
import { scoreBreakdown, rankedIssues, type Report } from "@/lib/auditBreakdown";

/**
 * The report a plan is made FROM, on the Plan page.
 *
 * Plan used to open on "Nothing planned for this cycle yet" and a bare Run Plan
 * button, so an operator could not see what would be planned (operator,
 * 2026-09-15: "there should be a report in Plan I can see, and a button that
 * turns it into a plan"). Before a plan: the report and the button. After: the
 * same report, folded, so the worklist can be read against its source.
 *
 * Every number comes from lib/auditBreakdown over the saved report; nothing is
 * recomputed here.
 */

interface PlanSourceReportProps {
  report: Report;
  domain: string;
  /** When the report's scan was saved. */
  savedAt?: string | null;
  /** True once a plan exists: the report renders folded under the worklist. */
  planned: boolean;
  busy?: boolean;
  onPlan?: () => void;
  onOpenAudit: () => void;
}

export function PlanSourceReport({ report, domain, savedAt, planned, busy = false, onPlan, onOpenAudit }: PlanSourceReportProps) {
  const shownDomain = domain.replace(/^https?:\/\//, "").replace(/\/$/, "");
  const b = scoreBreakdown(report);
  const issues = rankedIssues(report).length;

  if (!report || b.score === null) {
    return (
      <div className="plan-src plan-src--empty">
        <h2 className="plan-src__title">No audit report to plan yet</h2>
        <p className="plan-src__meta">
          A plan is built from a saved audit. Run the on-page audit for {shownDomain || "this project"} first, then come back here.
        </p>
        <div className="plan-src__actions">
          <button type="button" className="btn btn--primary btn--sm" onClick={onOpenAudit}>Go to Site Audit</button>
        </div>
      </div>
    );
  }

  const meta = (
    <p className="plan-src__meta">
      {shownDomain}
      {savedAt ? ` · saved ${new Date(savedAt).toLocaleString()}` : ""}
      {` · health ${b.score}`}
      {` · ${b.error} error${b.error === 1 ? "" : "s"}, ${b.warn} warning${b.warn === 1 ? "" : "s"}`}
      {` · ${issues} issue${issues === 1 ? "" : "s"}`}
    </p>
  );

  if (planned) {
    return (
      <details className="plan-src plan-src--folded">
        <summary className="plan-src__summary">
          <span className="plan-src__title">Source report</span>
          {meta}
        </summary>
        <div className="plan-src__body">
          <IssuesTable report={report} limit={10} onSeeAll={onOpenAudit} />
        </div>
      </details>
    );
  }

  return (
    <div className="plan-src">
      <div className="plan-src__head">
        <div>
          <span className="plan-src__eyebrow">Report to plan</span>
          <h2 className="plan-src__title">Site audit</h2>
          {meta}
        </div>
        <div className="plan-src__actions">
          <button type="button" className="btn btn--secondary btn--sm" onClick={onOpenAudit}>Open in Site Audit</button>
          {onPlan && (
            <button type="button" className="btn btn--primary btn--sm" onClick={onPlan} disabled={busy || issues === 0}>
              {busy ? "Planning…" : "Turn this report into a plan"}
            </button>
          )}
        </div>
      </div>
      <p className="plan-src__note">
        The plan compares this scan with the one before it: each finding is sorted into New, Persisting or Regression, fixed ones
        are marked Resolved, and every item is checked against the project&rsquo;s tier.
      </p>
      <div className="plan-src__body">
        <IssuesTable report={report} limit={10} onSeeAll={onOpenAudit} />
      </div>
    </div>
  );
}
