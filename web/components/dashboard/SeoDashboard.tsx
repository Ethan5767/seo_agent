"use client";

import React from "react";
import {
  Metric, TrendChart, StackedBars, Gauge, Donut, DistributionBars, Empty, toneFor,
} from "@/components/dashboard/Charts";
import {
  healthTrend, issueHistory, rankedKeywords, positionDistribution, organic, backlinks, lighthouse, aiSearch,
  type Report, type ScanLike,
} from "@/lib/dashboardMetrics";
import { ScoreWhy, IssuesTable, PagesTable } from "@/components/dashboard/AuditResults";
import { crawledPages, rankedIssues } from "@/lib/auditBreakdown";

/**
 * The SEO dashboard. Two sections:
 *
 *   1. The on-page audit: Site Health and where its points went, the health
 *      trend, the top issues and the worst pages (components/dashboard/
 *      AuditResults.tsx). Site Audit shows the same blocks in full.
 *   2. Search and links: organic, keywords, backlinks, speed and AI search,
 *      each from the tool that measured it.
 *
 * A panel with nothing measured says which tool fills it; nothing is estimated
 * to fill the space. Layout is the `.audit-dash` and `.seo-dash` grids in
 * app/tokens.css: named areas whose rows always sum to the full width.
 */
export type DashboardTarget =
  | "site-audit" | "issues" | "pages"
  | "domain-overview" | "organic-rankings" | "backlinks" | "core-web-vitals" | "ai";

// Chart marks take the brand fills; text keeps the AA shades (DESIGN.md §2.4).
const COLORS = {
  error: "var(--bad-fill)",
  warn: "var(--warn-fill)",
  ok: "var(--ok-fill)",
  info: "var(--ink-faint)",
};

const INK = "var(--ink)";

const fmt = (n: number | null | undefined) => (typeof n === "number" ? n.toLocaleString() : "—");

/** Panel chrome: title, provenance, and the one link into the full tool. */
function Panel({
  area, title, subtitle, action, children,
}: {
  area: "score" | "trend" | "issues" | "pages" | "org" | "kw" | "link" | "perf" | "ai";
  title: string;
  subtitle?: React.ReactNode;
  action?: { label: string; onClick: () => void };
  children: React.ReactNode;
}) {
  const id = `seo-panel-${area}`;
  return (
    <section className="seo-panel" style={{ gridArea: area }} aria-labelledby={id}>
      <header className="seo-panel__head">
        <div style={{ minWidth: 0 }}>
          <h3 id={id} className="seo-panel__title">{title}</h3>
          {subtitle && <div className="seo-panel__sub">{subtitle}</div>}
        </div>
        {action && (
          <button type="button" className="seo-panel__link" onClick={action.onClick}>
            {action.label}
            <span aria-hidden="true">→</span>
          </button>
        )}
      </header>
      <div className="seo-panel__body">{children}</div>
    </section>
  );
}

export function SeoDashboard({
  report, scans, domain, onOpen, onRun,
}: {
  report: Report;
  scans: ScanLike[] | null | undefined;
  domain: string;
  onOpen: (target: DashboardTarget) => void;
  /** Runs the on-page audit, for the empty states. */
  onRun?: () => void;
}) {
  const keywords = rankedKeywords(report);
  const dist = positionDistribution(keywords);
  const org = organic(report);
  const links = backlinks(report);
  const lh = lighthouse(report);
  const ai = aiSearch(report);
  const top3 = dist[0].value;
  const top10 = dist[0].value + dist[1].value;
  const shown = Math.min(8, keywords.length);
  const issues = rankedIssues(report);
  const pages = crawledPages(report);

  return (
    <div className="seo-dash-wrap dash-sections">
      <section aria-labelledby="dash-audit-heading">
        <h2 id="dash-audit-heading" className="dash-section-title">On-page audit</h2>
        <div className="audit-dash">
          <Panel area="score" title="Site Health" subtitle="Scored on the on-page audit only" action={{ label: "Site Audit", onClick: () => onOpen("site-audit") }}>
            <ScoreWhy report={report} onRun={onRun} />
          </Panel>
          <HealthTrendPanel scans={scans} domain={domain} />
          <Panel
            area="issues" title="Top Issues"
            subtitle={issues.length ? `Ranked by severity, then pages affected. ${issues.length} in total.` : undefined}
            action={issues.length ? { label: "All issues", onClick: () => onOpen("issues") } : undefined}
          >
            <IssuesTable report={report} limit={8} onSeeAll={() => onOpen("issues")} onRun={onRun} />
          </Panel>
          <Panel
            area="pages" title="Crawled Pages"
            subtitle={pages ? `Worst first. ${pages.length} ${pages.length === 1 ? "page" : "pages"} read.` : undefined}
            action={pages?.length ? { label: "All pages", onClick: () => onOpen("pages") } : undefined}
          >
            <PagesTable report={report} limit={8} onSeeAll={() => onOpen("pages")} onRun={onRun} />
          </Panel>
        </div>
      </section>

      <section aria-labelledby="dash-search-heading">
        <h2 id="dash-search-heading" className="dash-section-title">Search and links</h2>
      <div className="seo-dash">
        {/* Organic search: DataForSEO figures and the ranked keywords' spread. */}
        <Panel area="org" title="Organic Search" subtitle="DataForSEO" action={{ label: "Domain overview", onClick: () => onOpen("domain-overview") }}>
          {org || keywords.length ? (
            <>
              <div className="seo-stats seo-stats--pairs">
                <Metric label="Organic keywords" value={fmt(org?.keywordsTotal ?? keywords.length)} tone={INK} />
                <Metric label="Est. traffic / mo" value={fmt(org?.traffic)} tone={INK} sub={org?.traffic == null ? "Not reported" : "Estimate"} />
                <Metric label="Top 3" value={fmt(top3)} tone={INK} />
                <Metric label="Top 10" value={fmt(top10)} tone={INK} />
              </div>
              {org?.trend && org.trend.length > 1 && (
                <TrendChart points={org.trend} height={90} empty="" />
              )}
              <div>
                <p className="seo-label">Positions, {keywords.length} tracked keywords</p>
                <DistributionBars items={dist} empty="No ranked keywords in the last scan." />
              </div>
            </>
          ) : (
            <Empty height={180}>Run Domain Overview to see organic keywords, traffic and positions.</Empty>
          )}
        </Panel>

        {/* Top keywords, best position first. */}
        <Panel
          area="kw" title="Top Keywords"
          subtitle={keywords.length ? `Best ${shown} of ${keywords.length}, by position` : undefined}
          action={keywords.length ? { label: "All rankings", onClick: () => onOpen("organic-rankings") } : undefined}
        >
          {keywords.length ? (
            <table className="seo-table">
              <thead>
                <tr>
                  <th scope="col">Keyword</th>
                  <th scope="col" className="num">Position</th>
                  <th scope="col" className="num">Volume</th>
                </tr>
              </thead>
              <tbody>
                {keywords.slice(0, shown).map((k) => (
                  <tr key={k.keyword}>
                    <td title={k.keyword} style={{ maxWidth: 0, width: "62%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--ink-body)" }}>
                      {k.keyword}
                    </td>
                    <td className="num" style={{ fontWeight: 600, color: INK }}>{k.position}</td>
                    <td className="num" style={{ color: "var(--ink-muted)" }}>{fmt(k.volume)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Empty height={180}>Run Organic Rankings to list the keywords this site ranks for.</Empty>
          )}
        </Panel>

        {/* Backlinks. */}
        <Panel area="link" title="Backlinks" subtitle="DataForSEO" action={{ label: "Details", onClick: () => onOpen("backlinks") }}>
          {links ? (
            <>
              <div className="seo-stats">
                <Metric label="Referring domains" value={fmt(links.referringDomains)} tone={INK} />
                <Metric label="Backlinks" value={fmt(links.backlinks)} tone={INK} />
              </div>
              {typeof links.backlinks === "number" && typeof links.broken === "number" ? (
                <div>
                  <p className="seo-label">Link status</p>
                  <Donut
                    size={96}
                    center={<span><b style={{ color: INK, fontSize: 14 }}>{links.broken}</b><br />broken</span>}
                    segments={[
                      { label: "Working", value: Math.max(0, links.backlinks - links.broken), color: COLORS.ok },
                      { label: "Broken", value: links.broken, color: COLORS.error },
                    ]}
                  />
                </div>
              ) : null}
              {links.rank !== null && (
                <div style={{ marginTop: "auto", fontSize: "var(--text-xs)", color: "var(--ink-muted)" }}>
                  DataForSEO domain rank <b style={{ color: "var(--ink-body)", fontVariantNumeric: "tabular-nums" }}>{fmt(links.rank)}</b>
                </div>
              )}
            </>
          ) : (
            <Empty height={180}>Run Backlinks to count referring domains and broken links.</Empty>
          )}
        </Panel>

        {/* Lighthouse. */}
        <Panel area="perf" title="Page Performance" subtitle="Google Lighthouse, homepage" action={{ label: "Core Web Vitals", onClick: () => onOpen("core-web-vitals") }}>
          {lh.some((c) => c.score !== null) ? (
            <div style={{ display: "flex", justifyContent: "space-around", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-4)" }}>
              {lh.map((c) => <Gauge key={c.label} value={c.score} label={c.label} size={128} caption={c.score === null ? "Not run" : undefined} />)}
            </div>
          ) : (
            <Empty height={140}>Run Core Web Vitals to score performance, SEO, accessibility and best practices.</Empty>
          )}
        </Panel>

        {/* AI search. */}
        <Panel area="ai" title="AI Search" subtitle="Answer readiness and AI citations" action={{ label: "Details", onClick: () => onOpen("ai") }}>
          {ai ? (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "var(--space-5)" }}>
              <Donut
                size={96}
                center={<span><b style={{ color: INK, fontSize: 14 }}>{ai.passed}</b><br />passed</span>}
                segments={[
                  { label: "Passed", value: ai.passed, color: COLORS.ok },
                  { label: "Needs work", value: ai.failing, color: COLORS.warn },
                ]}
              />
              <Metric label="AI engine mentions" value={fmt(ai.mentions)} tone={ai.mentions ? toneFor(90) : INK} sub={ai.mentions === null ? "Not checked" : undefined} />
            </div>
          ) : (
            <Empty height={140}>Run the AI Search checks to see answer readiness and citations.</Empty>
          )}
        </Panel>
      </div>
      </section>
    </div>
  );
}

/** Health over time, from every graded scan of this domain. Shared with Site Audit. */
export function HealthTrendPanel({ scans, domain }: { scans: ScanLike[] | null | undefined; domain: string }) {
  const trend = healthTrend(scans, domain);
  const issues = issueHistory(scans, domain);
  return (
    <Panel
      area="trend" title="Health Trend"
      subtitle={trend.length ? `${trend.length} graded scan${trend.length === 1 ? "" : "s"}. Scans before Sep 15, 2026 also counted rankings and Lighthouse.` : undefined}
    >
      <div>
        <p className="seo-label">Site Health</p>
        <TrendChart points={trend} yMax={100} color="var(--accent-fill)" height={110} empty="Each audit adds a point here." />
      </div>
      <div>
        <p className="seo-label">Errors and warnings per scan</p>
        <StackedBars
          bars={issues}
          height={110}
          keys={[
            { key: "errors", label: "Errors", color: COLORS.error },
            { key: "warnings", label: "Warnings", color: COLORS.warn },
          ]}
          empty="No graded scans yet."
        />
      </div>
    </Panel>
  );
}
