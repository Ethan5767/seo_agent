"use client";

import React from "react";

/**
 * Says which source produced the data on a screen — Google (free, first-party),
 * DataForSEO (paid), or nothing connected yet. Provenance is not decoration: a
 * rankings table from Search Console and one from a paid index are different
 * facts, and the operator should never have to guess which they are looking at.
 *
 * Colour follows meaning: Google green (free + real), DataForSEO neutral (paid),
 * none muted. Never colour alone — the label always says the source in words.
 */
export function SourceBadge({ label, kind }: { label: string; kind: "google" | "paid" | "none" }) {
  const tone =
    kind === "google" ? { fg: "var(--ok)", bg: "var(--ok-tint)", border: "var(--ok-border)" }
    : kind === "paid" ? { fg: "var(--ink-body)", bg: "var(--surface-3)", border: "var(--border)" }
    : { fg: "var(--ink-muted)", bg: "var(--surface-2)", border: "var(--border)" };
  return (
    <span
      title={`Data source: ${label}`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        fontSize: "var(--text-xs)", fontWeight: 600, whiteSpace: "nowrap",
        color: tone.fg, background: tone.bg, border: `1px solid ${tone.border}`,
        borderRadius: "var(--radius-full)", padding: "2px 10px",
      }}
    >
      <span aria-hidden="true" style={{ width: 6, height: 6, borderRadius: "50%", background: tone.fg }} />
      Source: {label}
    </span>
  );
}
