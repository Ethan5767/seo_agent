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
  sectionId, domain, tools, busy, onScan,
}: {
  sectionId: string;
  domain: string | null | undefined;
  tools: ToolLike[] | null | undefined;
  busy?: boolean;
  onScan: (url: string, toolKeys: string[]) => void;
}) {
  const section = sectionById(sectionId);
  const keys = toolsForSection(sectionId, tools);
  const cost = sectionCost(sectionId, tools);
  if (!section) return null;

  const ready = Boolean(domain && keys && keys.length);
  const paid = cost?.paid ?? [];

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
      padding: "10px 14px", borderRadius: 8,
      border: "1px solid #e2e8f0", background: "#f8fafc", marginBottom: 14,
    }}>
      <button
        type="button"
        disabled={!ready || busy}
        onClick={() => { if (ready && domain && keys) onScan(domain, keys); }}
        title={
          !domain ? "Select a client first"
          : !keys ? "Tool list not loaded"
          : `Runs ${keys.length} tool(s): ${keys.join(", ")}`
        }
        style={{
          background: ready && !busy ? "#1e293b" : "#e2e8f0",
          color: ready && !busy ? "#fff" : "var(--ink-muted)",
          border: 0, borderRadius: 6, padding: "8px 14px",
          fontSize: 12.5, fontWeight: 700,
          cursor: ready && !busy ? "pointer" : "not-allowed",
          whiteSpace: "nowrap",
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
    </div>
  );
}
