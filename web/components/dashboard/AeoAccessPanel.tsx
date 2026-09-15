"use client";

import React from "react";
import { Icon } from "@/components/dashboard/Icon";
import { deriveAeoTiles, aeoVerdictColor, type AeoRow, type AeoTile } from "@/lib/aeo";

/**
 * AI crawler access, on the Overview.
 *
 * B-094. This panel was fabricated end to end: a "4/4 Ready" badge, four engine
 * statuses (Indexed / Snapshot / Direct / Compliant), "Robots.txt AI Crawlers
 * 4/4 Allowed (100%)" and "LocalBusiness JSON-LD Missing (Action Req.)". Every
 * one a literal, with no scan behind any of them - so it rendered identically
 * for an account that had never measured anything, and told that operator their
 * site was ready for all four answer engines.
 *
 * It now reads the same derivation the AEO screen does, and `null` verdicts
 * render grey and unticked. A check that scanned nothing must never report a
 * pass - the rule the engine enforces on itself with exit code 4.
 *
 * The card is also named for what it reads. It was "AI Search Citations", which
 * it does not measure: it reads robots.txt, and crawler access is a
 * precondition for citation rather than evidence of one.
 */

function Meter({ tile }: { tile: AeoTile }) {
  const none = tile.verdict === null;
  return (
    <div
      style={{
        padding: "10px 14px",
        borderRadius: 6,
        background: none ? "var(--surface-2)" : tile.verdict === "ok" ? "var(--ok-tint)" : "var(--warn-tint)",
        border: `1px solid ${none ? "var(--border)" : tile.verdict === "ok" ? "var(--ok-border)" : "var(--warn-border)"}`,
      }}
    >
      <div style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 600 }}>{tile.label}</div>
      <div style={{ fontSize: 12, fontWeight: 700, color: aeoVerdictColor(tile.verdict), marginTop: 2 }}>
        {tile.value}
      </div>
    </div>
  );
}

const ENGINES = [
  { engine: "ChatGPT / OpenAI", icon: "bot" },
  { engine: "Google AI Overviews", icon: "✨" },
  { engine: "Perplexity AI", icon: "bolt" },
  { engine: "Claude / Anthropic", icon: "globe" },
];

export function AeoAccessPanel({ aeoRows }: { aeoRows: AeoRow[] | null | undefined }) {
  const tiles = deriveAeoTiles(aeoRows);
  const measured = tiles.filter((t) => t.verdict !== null);
  const passing = measured.filter((t) => t.verdict === "ok").length;
  const crawler = tiles.find((t) => t.id === "crawlers")!;
  const schema = tiles.find((t) => t.id === "schema")!;

  // One robots.txt decides all four, so all four carry the same status. Giving
  // them different words was the tell that none of them was measured.
  const status =
    crawler.verdict === null ? "Not measured" : crawler.verdict === "ok" ? "Allowed" : "Blocked";

  return (
    <>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "var(--ink-body)" }}>AI Crawler Access</h4>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: measured.length ? "var(--accent)" : "var(--ink-muted)",
            background: measured.length ? "var(--accent-tint)" : "var(--surface-3)",
            border: `1px solid ${measured.length ? "var(--accent-border)" : "var(--border)"}`,
            padding: "2px 8px",
            borderRadius: 4,
          }}
        >
          {measured.length ? `${passing}/${measured.length} passing` : "Not measured"}
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
        {ENGINES.map((item) => (
          <div
            key={item.engine}
            style={{
              display: "flex", justifyContent: "space-between", alignItems: "center",
              padding: "9px 12px", borderRadius: 6, background: "var(--surface-2)", border: "1px solid var(--border)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name={item.icon} size={16} />
              <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink-body)" }}>{item.engine}</span>
            </div>
            <span
              style={{
                fontSize: 12, fontWeight: 700, color: aeoVerdictColor(crawler.verdict),
                background: "var(--color-white)", border: "1px solid var(--border)", padding: "2px 7px", borderRadius: 4,
              }}
            >
              {status}
            </span>
          </div>
        ))}
      </div>

      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <Meter tile={crawler} />
          <Meter tile={schema} />
        </div>
      </div>
    </>
  );
}
