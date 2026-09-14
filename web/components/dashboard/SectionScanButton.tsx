"use client";

import React from "react";
import { sectionById, toolsForSection, sectionCost, toolsForView, viewCost, type ToolLike } from "@/lib/sectionScans";
import { SOURCE_LABEL, type SourceId } from "@/lib/toolSources";

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
        <div style={{ fontSize: 13, fontWeight: 700, color: "#334155" }}>
          Create a project before auditing
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.5, maxWidth: "68ch" }}>
          An audit runs against a specific site, and a project is what carries the domain, the
          business name and the repository. {section.scope}
        </div>
        {onCreateProject && (
          <button type="button" onClick={onCreateProject} style={primary}>
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

  if (viewId === "source-code" && !repo) {
    return (
      <div style={{ ...shell, borderStyle: "dashed", flexDirection: "column", alignItems: "flex-start", gap: 6 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#334155" }}>
          Connect a GitHub repository to inspect source code
        </div>
        <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.5, maxWidth: "68ch" }}>
          Source code checks inspect next.config, routes, redirects, headers, and rendering posture.
          Attach this project&apos;s GitHub repository to enable source code analysis.
        </div>
        {onEditProject && (
          <button type="button" onClick={onEditProject} style={primary}>
            Edit Project &amp; Connect Repo
          </button>
        )}
      </div>
    );
  }

  const ready = Boolean(keys && keys.length) && !sourceBlocked;
  const paid = cost?.paid ?? [];

  return (
    <div style={shell}>
      {source && onSourceChange && sourceBlockers && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <label htmlFor={`source-${viewId}`} style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)" }}>
            Data source
          </label>
          <select
            id={`source-${viewId}`}
            aria-label="Data source"
            value={source}
            disabled={busy}
            onChange={(e) => onSourceChange(e.target.value as SourceId)}
            style={{
              fontSize: 12, fontWeight: 600, padding: "5px 10px", borderRadius: 6,
              border: "1px solid #cbd5e1", background: "#ffffff", color: "#1e293b",
              cursor: busy ? "not-allowed" : "pointer",
            }}
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
            if (viewId === "site-crawl" && onCrawlScan) {
              onCrawlScan(domain, keys, selectedPages);
            } else {
              onScan(domain, keys);
            }
          }
        }}
        title={ready ? `Runs ${keys!.length} tool(s): ${keys!.join(", ")}` : "Tool list not loaded"}
        style={{
          ...primary,
          background: ready && !busy ? "#1e293b" : "#e2e8f0",
          color: ready && !busy ? "#fff" : "var(--ink-muted)",
          cursor: ready && !busy ? "pointer" : "not-allowed",
        }}
      >
        {busy ? "Scanning…" : isViewScoped ? `Test ${viewLabel || "Tool"}` : `Scan ${section.label} only`}
      </button>

      {viewId === "source-code" && repo && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <span style={{ color: "var(--ink-muted)" }}>Repository:</span>
          <span style={{ fontWeight: 600, color: "#1e293b", background: "#f1f5f9", padding: "3px 8px", borderRadius: 6, border: "1px solid #e2e8f0" }}>
            {repo}
          </span>
          {onEditProject && (
            <button
              type="button"
              onClick={onEditProject}
              style={{
                background: "none", border: "none", color: "#4f46e5", fontSize: 11.5,
                fontWeight: 600, cursor: "pointer", textDecoration: "underline", padding: "0 4px",
              }}
            >
              Change
            </button>
          )}
        </div>
      )}

      {viewId === "site-crawl" && (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <label htmlFor="crawl-depth-select" style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)" }}>
            Pages:
          </label>
          <select
            id="crawl-depth-select"
            value={selectedPages}
            disabled={busy}
            onChange={(e) => handlePagesChange(Number(e.target.value))}
            style={{
              fontSize: 12, fontWeight: 600, padding: "5px 10px", borderRadius: 6,
              border: "1px solid #cbd5e1", background: "#ffffff", color: "#1e293b",
              cursor: busy ? "not-allowed" : "pointer",
            }}
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
          style={{
            ...secondary,
            background: !busy ? "#f8fafc" : "#e2e8f0",
            color: !busy ? "#334155" : "var(--ink-muted)",
            cursor: !busy ? "pointer" : "not-allowed",
          }}
        >
          Scan all {section.label}{scanAllPaid.length ? ` (${scanAllPaid.map((t) => `${t.label}${t.cost ? ` ${t.cost}` : ""}`).join(", ")})` : " (free)"}
        </button>
      )}

      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 12, color: "var(--ink-body)", lineHeight: 1.45 }}>
          {viewId === "site-crawl"
            ? `Audits Crawl Issues across ${selectedPages} pages: internal links, duplicate titles & descriptions, orphan pages.`
            : isViewScoped ? `Audits ${viewLabel || "this tool"}: ${keys?.join(", ")}.` : section.scope}
        </div>
        <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 2 }}>
          {!keys
            ? "Tool list not loaded, so this cannot be scoped yet."
            : paid.length === 0
              ? `${cost?.free ?? keys.length} checks, all free.`
              /* Each paid tool named, not a total. A total hides which one is
                 expensive, and that is the decision the operator is making. */
              : `${cost?.free ?? 0} free · ${paid.length} paid: ${paid.map((t) => `${t.label}${t.cost ? ` ${t.cost}` : ""}`).join(", ")}`}
        </div>
      </div>

      {sourceBlocked && (
        <div
          role="note"
          style={{
            flexBasis: "100%", fontSize: 12, lineHeight: 1.5,
            color: "#92400e", background: "#fffbeb",
            border: "1px solid #fde68a", borderRadius: 6, padding: "8px 10px",
          }}
        >
          <b>{SOURCE_LABEL[source!]} cannot run this page:</b> {sourceBlocked}
        </div>
      )}
      {source && sourceBlockers && !sourceBlocked && (["dataforseo", "ours"] as SourceId[]).filter((s) => s !== source && sourceBlockers[s]).map((s) => (
        <div key={s} style={{ flexBasis: "100%", fontSize: 11.5, color: "var(--ink-muted)" }}>
          {SOURCE_LABEL[s]} unavailable here: {sourceBlockers[s]}
        </div>
      ))}

      {error && !busy && (
        <div
          role="alert"
          style={{
            flexBasis: "100%", fontSize: 12, lineHeight: 1.5,
            color: "#991b1b", background: "#fef2f2",
            border: "1px solid #fecaca", borderRadius: 6, padding: "8px 10px",
          }}
        >
          <b>The last scan did not run.</b> {error}
        </div>
      )}
    </div>
  );
}

const shell: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
  padding: "10px 14px", borderRadius: 8,
  // Longhands, not `border`: three states override borderStyle to "dashed", and
  // React warns (and can mis-style) when a rerender drops a longhand that
  // conflicts with a shorthand still set.
  borderWidth: 1, borderStyle: "solid", borderColor: "#e2e8f0", background: "#f8fafc", marginBottom: 14,
};

const primary: React.CSSProperties = {
  background: "#1e293b", color: "#fff", border: 0, borderRadius: 6,
  padding: "8px 14px", fontSize: 12.5, fontWeight: 700, cursor: "pointer",
  whiteSpace: "nowrap",
};

const secondary: React.CSSProperties = {
  background: "#f8fafc", color: "#334155", border: "1px solid #cbd5e1", borderRadius: 6,
  padding: "8px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer",
  whiteSpace: "nowrap",
};
