"use client";

import React from "react";

/**
 * The four Google Business Profile tiles.
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
 *   "🏥"           a hospital emoji, hardcoded, on every client.
 *
 * Three states everywhere, never two: measured-and-fine, measured-and-not, and
 * not measured. Nothing unmeasured is green, and nothing unmeasured is drawn.
 */

type Row = { what?: string; code?: string; detail?: string; severity?: string };

const MUTED = "#64748b";

function Tile({
  label, badge, badgeColor, value, valueColor, note, right,
}: {
  label: string; badge: string; badgeColor: string;
  value: string; valueColor: string; note: string; right?: React.ReactNode;
}) {
  return (
    <div style={{
      border: "1px solid #e2e8f0", borderRadius: 8, padding: "12px 14px", background: "#fff",
      display: "flex", flexDirection: "column", justifyContent: "space-between", minHeight: 82,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-muted)", textTransform: "uppercase" }}>{label}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: badgeColor, whiteSpace: "nowrap" }}>{badge}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginTop: 4, gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontSize: 17, fontWeight: 700, color: valueColor, lineHeight: 1.1,
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {value}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 3 }}>{note}</div>
        </div>
        {right}
      </div>
    </div>
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
  const statusColor = !measured ? MUTED : ok ? "var(--ok)" : "#d97706";

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 14 }}>
      <Tile
        label="GBP status"
        badge={!measured ? "Not asked" : ok ? "Verified" : "Action needed"}
        badgeColor={statusColor}
        value={status}
        valueColor={statusColor}
        note={measured ? "From the live profile" : "Run the Local tool to read the profile"}
      />
      <Tile
        label="Rating & reviews"
        badge={review ? "Trust signal" : "Not measured"}
        badgeColor={review ? "var(--ok)" : MUTED}
        value={review?.detail || "Not measured"}
        valueColor={review ? "#0f172a" : MUTED}
        note={review ? "From the live profile" : "No rating read yet"}
      />
      <Tile
        label="Primary category"
        badge={category ? "Primary" : "Not measured"}
        badgeColor={category ? "#4f46e5" : MUTED}
        value={category?.detail || "Not measured"}
        valueColor={category ? "#0f172a" : MUTED}
        note="The single strongest local ranking input"
        right={<span style={{ fontSize: 16 }}>{category ? "🏷️" : ""}</span>}
      />
      <Tile
        label="Web mentions"
        badge={mention ? "Reach" : "Not measured"}
        badgeColor={mention ? "#4f46e5" : MUTED}
        value={mention?.detail || "Not measured"}
        valueColor={mention ? "#0f172a" : MUTED}
        note={mention ? "News, blogs and directories" : "The mentions tool has not run"}
      />
    </div>
  );
}
