"use client";

import React from "react";
import { StatStrip, type Stat } from "./Panel";
import styles from "./LocalPresence.module.css";

/**
 * The four Google Business Profile figures, as one stat strip.
 *
 * B-097. Every one of them claimed something it had not measured:
 *
 *   `isClaimed = claimedFinding ? ... : true`  - ABSENCE meant claimed, so an
 *       account that had never run the Local tool was told its profile was
 *       claimed and active.
 *   "Verified"     printed unconditionally, beside a status that could read
 *                  "Needs Setup".
 *   "Trust Signal" printed beside a rating that could read "Not measured".
 *   "Rank #1"      printed beside a primary category. Nothing measures a
 *                  category's rank, and a category is not a ranking.
 *   a sparkline    fed `[4.1, 4.3, 4.5, 4.6, 4.7, 4.8]` - an invented rating
 *                  trend, drawn as a real chart. One scan is a point, not a
 *                  line, and nothing stores a rating history to draw.
 *   a radial gauge fed 100-or-50 from a boolean: a picture of a number nobody
 *                  computed.
 *   a hospital pictogram, hardcoded, on every client.
 *
 * Three states everywhere, never two: measured-and-fine, measured-and-not, and
 * not measured. Nothing unmeasured is green, and nothing unmeasured is drawn.
 */

type Row = { what?: string; code?: string; detail?: string; severity?: string };

const MUTED = "var(--ink-muted)";

/** ok/warn: a verdict. info: measured, but not a pass or a fail. none: not measured. */
type MarkState = "ok" | "warn" | "info" | "none";

/** A status word with its icon (DESIGN.md §2.5: never colour alone). */
function Mark({ state, word }: { state: MarkState; word: string }) {
  if (state === "info") {
    return <span className={styles.statBadge} style={{ color: "var(--ink-body)", fontWeight: 600 }}>{word}</span>;
  }
  const cls = state === "ok" ? "sev sev--ok" : state === "warn" ? "sev sev--warn" : "sev";
  return (
    <span className={`${cls} ${styles.statBadge}`}>
      <span className="sev__glyph" aria-hidden="true">
        <svg className={styles.glyphIcon} width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          {state === "ok" ? <polyline points="20 6 9 17 4 12" />
            : state === "warn" ? <><line x1="12" y1="6" x2="12" y2="13" /><line x1="12" y1="18" x2="12.01" y2="18" /></>
            : <line x1="6" y1="12" x2="18" y2="12" />}
        </svg>
      </span>
      {word}
    </span>
  );
}

function sub(state: MarkState, badge: string, note: string) {
  return (
    <>
      <Mark state={state} word={badge} />
      {note}
    </>
  );
}

export function GbpMatrix({ gbpRows, mentionsRows }: { gbpRows: Row[]; mentionsRows: Row[] }) {
  const find = (rows: Row[], needle: string) =>
    rows.find((r) => (r.what || "").toLowerCase().includes(needle));

  const profile = find(gbpRows, "business profile");
  const claimed = find(gbpRows, "claimed");
  const review = find(gbpRows, "review");
  const category = find(gbpRows, "category");
  const mention = mentionsRows.find(
    (r) => (r.what || "").toLowerCase().includes("mention")
      && !(r.what || "").toLowerCase().includes("sentiment"),
  );

  const measured = Boolean(profile || claimed);
  const status = !measured ? "Not measured"
    : profile?.severity === "warn" ? "Needs setup"
    : claimed?.severity === "warn" ? "Unclaimed"
    : "Claimed & active";
  const ok = status === "Claimed & active";
  const statusColor = !measured ? MUTED : ok ? "var(--ok)" : "var(--warn)";

  // A finding's icon follows its own severity. A row existing is not a pass.
  const stateOf = (row: Row | undefined): MarkState =>
    !row ? "none" : row.severity === "ok" ? "ok" : row.severity === "warn" ? "warn" : "info";
  const value = (text: string) => <span className={styles.statValue}>{text}</span>;

  const stats: Stat[] = [
    {
      label: "GBP status",
      value: value(status),
      tone: statusColor,
      sub: sub(
        !measured ? "none" : ok ? "ok" : "warn",
        !measured ? "Not asked" : ok ? "Verified" : "Action needed",
        measured ? "From the live profile" : "Run the Local tool to read the profile",
      ),
    },
    {
      label: "Rating & reviews",
      value: value(review?.detail || "Not measured"),
      tone: review ? "var(--ink)" : MUTED,
      sub: sub(stateOf(review), review ? "Trust signal" : "Not measured", review ? "From the live profile" : "No rating read yet"),
    },
    {
      label: "Primary category",
      value: value(category?.detail || "Not measured"),
      tone: category ? "var(--ink)" : MUTED,
      sub: sub(stateOf(category), category ? "Primary" : "Not measured", "The single strongest local ranking input"),
    },
    {
      label: "Web mentions",
      value: value(mention?.detail || "Not measured"),
      tone: mention ? "var(--ink)" : MUTED,
      sub: sub(stateOf(mention), mention ? "Reach" : "Not measured", mention ? "News, blogs and directories" : "The mentions tool has not run"),
    },
  ];

  return (
    <div style={{ marginBottom: "var(--space-4)" }}>
      <StatStrip stats={stats} label="Local signals" />
    </div>
  );
}
