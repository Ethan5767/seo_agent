"use client";

import React from "react";
import { sectionById, toolsForSection, sectionCost, toolsForView, viewCost, type ToolLike } from "@/lib/sectionScans";
import { SOURCE_LABEL, type SourceId } from "@/lib/toolSources";
import { toolVerb } from "@/lib/toolVerbs";

/**
 * "Scan this section" or "Test this tool" specifically.
 *
 * Scopes scan execution to either a specific tool view (e.g. Crawl Issues,
 * Position Tracking, Backlinks) or the entire section.
 */
export function SectionScanButton({
  sectionId, viewId, viewLabel, domain, repo, onEditProject, tools, busy, onScan, onCrawlScan, crawlPages = 5, onCrawlPagesChange, hasProjects, onCreateProject, error,
  source, sourceTools, sourceBlockers, onSourceChange,
}: {
  sectionId: string;
  viewId?: string;
  viewLabel?: string;
  domain: string | null | undefined;
  repo?: string | null;
  onEditProject?: () => void;
  tools: ToolLike[] | null | undefined;
  busy?: boolean;
  onScan: (url: string, toolKeys: string[]) => void;
  onCrawlScan?: (url: string, toolKeys: string[], pages: number) => void;
  crawlPages?: number;
  onCrawlPagesChange?: (pages: number) => void;
  /** Does this account have ANY project? Distinct from "none selected". */
  hasProjects?: boolean;
  onCreateProject?: () => void;
  /**
   * Why the last run produced nothing. B-104: a scan that the backend refused
   * left the screen identical to a scan that had not been started, so the
   * operator pressed the button again instead of reading an error. A failure
   * has to be visible where the button is.
   */
  error?: string | null;
  /**
   * The page's Data source dropdown (`lib/toolSources.ts`). When set, the Test
   * button runs exactly `sourceTools`, and `sourceBlockers[s]` is why source `s`
   * cannot be picked ("" when it can).
   */
  source?: SourceId;
  sourceTools?: string[];
  sourceBlockers?: Record<SourceId, string>;
  onSourceChange?: (s: SourceId) => void;
}) {
  const [selectedPages, setSelectedPages] = React.useState<number>(crawlPages || 5);
  React.useEffect(() => {
    if (crawlPages && crawlPages !== selectedPages) setSelectedPages(crawlPages);
  }, [crawlPages]);

  const handlePagesChange = (n: number) => {
    setSelectedPages(n);
    onCrawlPagesChange?.(n);
  };
  const section = sectionById(sectionId);
  const catalogKeys = new Set((tools ?? []).map((t) => t.key));
  const sourced = sourceTools ? sourceTools.filter((k) => catalogKeys.has(k)) : null;
  const viewKeys = sourced ? (sourced.length ? sourced : null) : viewId ? toolsForView(viewId, tools) : null;
  const viewPrice = sourced
    ? {
        free: (tools ?? []).filter((t) => sourced.includes(t.key) && t.group === "free").length,
        paid: (tools ?? []).filter((t) => sourced.includes(t.key) && t.group && t.group !== "free"),
      }
    : viewId ? viewCost(viewId, tools) : null;
  const sourceBlocked = source && sourceBlockers ? sourceBlockers[source] : "";
  const sectionKeys = toolsForSection(sectionId, tools);
  const sectionPrice = sectionCost(sectionId, tools);
  // "Scan all <section>" from a tool page: the section's FREE tools plus what
  // this page's chosen source runs. It sent every tool in the section, so on a
  // page reading "Our tools (free) / all free" it billed Site Health and
  // Backlinks without naming either (review, 2026-09-14).
  const scanAllKeys = sectionKeys && sourced
    ? sectionKeys.filter((k) => sourced.includes(k) || (tools ?? []).some((t) => t.key === k && t.group === "free"))
    : sectionKeys;
  const scanAllPaid = (tools ?? []).filter((t) => (scanAllKeys ?? []).includes(t.key) && t.group === "dataforseo");

  // If this specific view has dedicated tools, scope to them; otherwise use section tools.
  const isViewScoped = Boolean(viewKeys && viewKeys.length);
  // The word on the button and in the caption fits the tool's real action
  // (look up / compare / find / track / measure), never a blanket "Test".
  const action = toolVerb(viewId, viewLabel);
  const keys = isViewScoped ? viewKeys : sectionKeys;
  const cost = isViewScoped ? viewPrice : sectionPrice;
  if (!section) return null;

  // A project is the precondition for auditing anything: a scan needs a domain,
  // and a domain is what a project carries. The three states below are kept
  // apart on purpose - "you have no projects" and "you have projects but have
  // not picked one" need different actions, and collapsing them into one
  // disabled button with a tooltip means the operator has to HOVER to find out
  // why nothing works. That was the previous behaviour.
  if (!hasProjects) {
    return (
      <div style={{ ...shell, borderStyle: "dashed", flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-body)" }}>
          Create a project before auditing
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.5, maxWidth: "68ch" }}>
          A scan runs against a specific site, and a project is what carries the domain, the
          business name and the repository. {section.scope}
        </div>
        {onCreateProject && (
          <button type="button" onClick={onCreateProject} className="btn btn--primary btn--sm">
            Create a project
          </button>
        )}
      </div>
    );
  }

  if (!domain) {
    return (
      <div style={{ ...shell, borderStyle: "dashed" }}>
        <div style={{ fontSize: 12.5, color: "var(--ink-body)" }}>
          <b>Select a project</b> to scan. {section.scope}
        </div>
      </div>
    );
  }

  const ready = Boolean(keys && keys.length) && !sourceBlocked;
  const paidOnly = Boolean(keys && keys.length) &&
    keys!.every((k) => (tools ?? []).find((t) => t.key === k)?.group === "dataforseo");
  const paid = cost?.paid ?? [];

  return (
    <div style={shell}>
      {source && onSourceChange && sourceBlockers && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <label htmlFor={`source-${viewId}`} style={label}>
            Data source
          </label>
          <select
            id={`source-${viewId}`}
            aria-label="Data source"
            value={source}
            disabled={busy}
            onChange={(e) => onSourceChange(e.target.value as SourceId)}
            style={{ ...select, cursor: busy ? "not-allowed" : "pointer" }}
          >
            {(["dataforseo", "ours"] as SourceId[]).map((s) => (
              <option key={s} value={s} disabled={Boolean(sourceBlockers[s]) && s !== source} title={sourceBlockers[s] || undefined}>
                {SOURCE_LABEL[s]}{sourceBlockers[s] ? " — unavailable" : ""}
              </option>
            ))}
          </select>
        </div>
      )}
      <button
        type="button"
        disabled={!ready || busy}
        onClick={() => {
          if (ready && keys) {
            if (paidOnly && onCrawlScan) {
              // Every tool this Test runs is DataForSEO, which crawls on its own
              // servers. Our free multi-page crawl would add 1.5-2 minutes (25
              // pages) for rows this page does not show.
              onCrawlScan(domain, keys, 1);
            } else if (viewId === "site-crawl" && onCrawlScan) {
              onCrawlScan(domain, keys, selectedPages);
            } else {
              onScan(domain, keys);
            }
          }
        }}
        title={ready ? `Runs ${keys!.length} tool(s): ${keys!.join(", ")}` : "Tool list not loaded"}
        className="btn btn--primary btn--sm"
      >
        {busy ? "Scanning…" : isViewScoped ? `${action.verb} ${action.object}` : `Scan ${section.label} only`}
      </button>

      {viewId === "site-crawl" && !paidOnly && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="crawl-depth-select" style={label}>
            Pages
          </label>
          <select
            id="crawl-depth-select"
            value={selectedPages}
            disabled={busy}
            onChange={(e) => handlePagesChange(Number(e.target.value))}
            style={{ ...select, cursor: busy ? "not-allowed" : "pointer" }}
          >
            <option value={2}>2 pages (fast link check)</option>
            <option value={5}>5 pages (standard)</option>
            <option value={10}>10 pages (deep crawl)</option>
            <option value={15}>15 pages (comprehensive)</option>
            <option value={20}>20 pages (thorough)</option>
            <option value={25}>25 pages (maximum)</option>
          </select>
        </div>
      )}

      {isViewScoped && scanAllKeys && scanAllKeys.length > (keys?.length ?? 0) && (
        <button
          type="button"
          disabled={busy}
          onClick={() => onScan(domain, scanAllKeys)}
          title={`Scan ${scanAllKeys.length} tools in ${section.label}: ${scanAllKeys.join(", ")}`}
          className="btn btn--secondary btn--sm"
        >
          Scan all {section.label}{scanAllPaid.length ? ` (${scanAllPaid.map((t) => `${t.label}${t.cost ? ` ${t.cost}` : ""}`).join(", ")})` : " (free)"}
        </button>
      )}

      {/* The price before the click (operator, 2026-09-15: "price on paid
          buttons"). Each paid tool named, not a total: a total hides which one
          is expensive, and that is the decision being made. */}
      <div style={{ minWidth: 0, flex: 1, fontSize: "var(--text-sm)", color: "var(--ink-muted)" }}>
        {!keys
          ? "Tool list not loaded, so this cannot be scoped yet."
          : paid.length === 0
            ? `${cost?.free ?? keys.length} checks, all free.`
            : `${cost?.free ?? 0} free · ${paid.length} paid: ${paid.map((t) => `${t.label}${t.cost ? ` ${t.cost}` : ""}`).join(", ")}`}
      </div>

      {sourceBlocked && (
        <div
          role="note"
          style={{
            flexBasis: "100%", fontSize: 12, lineHeight: 1.5,
            color: "var(--warn)", background: "var(--warn-tint)",
            border: "1px solid var(--warn-border)", borderRadius: 6, padding: "8px 10px",
          }}
        >
          <b>{SOURCE_LABEL[source!]} cannot run this page:</b> {sourceBlocked}
        </div>
      )}
      {source && sourceBlockers && !sourceBlocked && (["dataforseo", "ours"] as SourceId[]).filter((s) => s !== source && sourceBlockers[s]).map((s) => (
        <div key={s} style={{ flexBasis: "100%", fontSize: "var(--text-xs)", color: "var(--ink-muted)" }}>
          {SOURCE_LABEL[s]} unavailable here: {sourceBlockers[s]}
        </div>
      ))}

      {error && !busy && (
        <div
          role="alert"
          style={{
            flexBasis: "100%", fontSize: 12, lineHeight: 1.5,
            color: "var(--bad)", background: "var(--bad-tint)",
            border: "1px solid var(--bad-border)", borderRadius: 6, padding: "8px 10px",
          }}
        >
          <b>The last scan did not run.</b> {error}
        </div>
      )}
    </div>
  );
}

const shell: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: "var(--space-3) var(--space-4)", flexWrap: "wrap",
  padding: "var(--space-4) var(--space-6)", borderRadius: "var(--radius-md)",
  // Longhands, not `border`: three states override borderStyle to "dashed", and
  // React warns (and can mis-style) when a rerender drops a longhand that
  // conflicts with a shorthand still set.
  borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)", background: "var(--surface)",
  boxShadow: "var(--shadow-sm)", marginBottom: "var(--space-6)",
};

const label: React.CSSProperties = { fontSize: "var(--text-sm)", fontWeight: 500, color: "var(--ink-muted)" };

const select: React.CSSProperties = {
  minHeight: 36, fontSize: "var(--text-sm)", fontWeight: 500, padding: "0 var(--space-3)", borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border-strong)", background: "var(--color-white)", color: "var(--ink-body)",
};
