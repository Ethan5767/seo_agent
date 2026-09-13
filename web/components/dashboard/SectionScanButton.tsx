"use client";

import React from "react";
import { sectionById, toolsForSection, sectionCost, type ToolLike } from "@/lib/sectionScans";

/**
 * "Scan this section" - and only this section.
 *
 * Every scan used to run all 25 tools, so pressing Scan on the Local page spent
 * money on backlinks and rank tracking before showing five local rows. A section
 * now scans its own concern.
 *
 * It states the cost BEFORE the click, naming each paid tool. A scoped scan is
 * mostly an argument about money, and an operator should be able to see what
 * this one spends rather than discover it on the invoice.
 *
 * Disabled without a tool list rather than falling back to everything: the whole
 * point is not running the other twenty tools, and a "safe" fallback here would
 * quietly reinstate the behaviour this replaces.
 */
export function SectionScanButton({
  sectionId, domain, tools, busy, onScan, hasProjects, onCreateProject, error,
}: {
  sectionId: string;
  domain: string | null | undefined;
  tools: ToolLike[] | null | undefined;
  busy?: boolean;
  onScan: (url: string, toolKeys: string[]) => void;
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
}) {
  const section = sectionById(sectionId);
  const keys = toolsForSection(sectionId, tools);
  const cost = sectionCost(sectionId, tools);
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

  const ready = Boolean(keys && keys.length);
  const paid = cost?.paid ?? [];

  return (
    <div style={shell}>
      <button
        type="button"
        disabled={!ready || busy}
        onClick={() => { if (ready && keys) onScan(domain, keys); }}
        title={ready ? `Runs ${keys!.length} tool(s): ${keys!.join(", ")}` : "Tool list not loaded"}
        style={{
          ...primary,
          background: ready && !busy ? "#1e293b" : "#e2e8f0",
          color: ready && !busy ? "#fff" : "var(--ink-muted)",
          cursor: ready && !busy ? "pointer" : "not-allowed",
        }}
      >
        {busy ? "Scanning…" : `Scan ${section.label} only`}
      </button>

      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: 12, color: "var(--ink-body)", lineHeight: 1.45 }}>{section.scope}</div>
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
  border: "1px solid #e2e8f0", background: "#f8fafc", marginBottom: 14,
};

const primary: React.CSSProperties = {
  background: "#1e293b", color: "#fff", border: 0, borderRadius: 6,
  padding: "8px 14px", fontSize: 12.5, fontWeight: 700, cursor: "pointer",
  whiteSpace: "nowrap",
};
