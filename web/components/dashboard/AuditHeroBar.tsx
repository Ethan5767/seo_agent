"use client";

import React, { useState } from "react";
import { AUDIT_CRAWL_OPTIONS, ONPAGE_AUDIT_TOOLS } from "@/lib/auditBreakdown";

/**
 * The on-page audit's run bar: the project's domain, how many pages to crawl,
 * and the button. Shared by the Dashboard and Site Audit.
 *
 * It shows no results. It used to render its own score banner and a full list
 * of every check under the button, so Site Audit drew three health summaries
 * on one page (operator, 2026-09-15: "why there one more dashboard below
 * that?"). Results are the AuditResults blocks, one set per page.
 */

interface AuditHeroBarProps {
  currentDomain?: string;
  /** Runs every `ONPAGE_AUDIT_TOOLS` check over `pages` crawled pages. */
  onRunAudit: (url: string, tools: string[], pages: number) => void;
  isScanning?: boolean;
  phaseLine?: string;
  scanTools?: Array<{ name?: string; state?: string }>;
  liveLogs?: string[];
  pages: number;
  onPagesChange: (n: number) => void;
  /** When the last scan was saved, for the "Last audit" line. */
  lastScanAt?: string | null;
  onEditProject?: () => void;
  onCreateProject?: () => void;
}

export function AuditHeroBar({
  currentDomain = "",
  onRunAudit,
  isScanning = false,
  phaseLine,
  scanTools = [],
  liveLogs = [],
  pages,
  onPagesChange,
  lastScanAt,
  onCreateProject,
}: AuditHeroBarProps) {
  // The project's domain, never a typed one: a typed site created or switched
  // projects behind the page (operator, 2026-09-15: one project, one domain).
  const domain = currentDomain.trim();
  const [showLogs, setShowLogs] = useState(false);
  const shownDomain = domain.replace(/^https?:\/\//, "").replace(/\/$/, "");
  const depth = AUDIT_CRAWL_OPTIONS.includes(pages as (typeof AUDIT_CRAWL_OPTIONS)[number]) ? pages : AUDIT_CRAWL_OPTIONS[0];

  const run = (e: React.FormEvent) => {
    e.preventDefault();
    if (!domain || isScanning) return;
    onRunAudit(domain, [...ONPAGE_AUDIT_TOOLS], depth);
  };

  return (
    <div>
      <form className="run-bar" onSubmit={run} aria-label="On-page audit">
        <div className="run-bar__head">
          <h2 className="run-bar__title">On-page audit</h2>
          <p className="run-bar__sub">
            Checks every technical SEO signal: on-page, crawl, headers, schema, AI access, field data and Lighthouse on every selected page. Includes DataForSEO Site Health (paid).
            {lastScanAt ? ` Last audit ${new Date(lastScanAt).toLocaleDateString()}.` : ""}
          </p>
        </div>
        {/* One input-style bar, one button. The domain is the project's and is
            read-only (operator, 2026-09-15: one project, one domain); change it
            by editing the project. */}
        <div className="run-bar__input" data-disabled={!domain || undefined}>
          {domain ? (
            <input
              className="run-bar__domain"
              aria-label="Project domain"
              value={shownDomain}
              readOnly
              title="The open project's domain"
            />
          ) : (
            <span className="run-bar__domain run-bar__domain--empty" aria-label="Project domain">
              No project selected.
              {onCreateProject && <button type="button" className="link" onClick={onCreateProject}>Create a project</button>}
            </span>
          )}
          <select
            className="run-bar__pages"
            aria-label="Pages to crawl"
            value={depth}
            onChange={(e) => onPagesChange(Number(e.target.value))}
            disabled={isScanning}
          >
            {AUDIT_CRAWL_OPTIONS.map((n) => <option key={n} value={n}>{n} pages</option>)}
          </select>
          <button type="submit" className="btn btn--primary btn--sm run-bar__go" disabled={isScanning || !domain}>
            {isScanning ? "Auditing…" : "Run Audit"}
          </button>
        </div>
      </form>

      {isScanning && (
        <div className="run-progress" role="status" aria-live="polite">
          <div className="run-progress__head">
            <p className="run-progress__title"><span className="run-progress__dot" aria-hidden="true" /> Auditing {shownDomain}</p>
            <span className="run-progress__phase">{phaseLine || "Starting"}</span>
          </div>
          {scanTools.length > 0 && (
            <ul className="run-progress__tools">
              {scanTools.filter((t) => t.state !== "phase").map((t, i) => (
                <li key={`${t.name}-${i}`} data-state={t.state}>
                  <span aria-hidden="true">{t.state === "done" ? "✓" : "…"}</span>
                  {t.name}
                </li>
              ))}
            </ul>
          )}
          <button type="button" className="link" onClick={() => setShowLogs((v) => !v)} aria-expanded={showLogs}>
            {showLogs ? "Hide scan log" : "Show scan log"}
          </button>
          {showLogs && (
            <div className="run-progress__log">
              {liveLogs.length ? liveLogs.map((l, i) => <div key={i}>{l}</div>) : <div>Connecting to the scanner…</div>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
