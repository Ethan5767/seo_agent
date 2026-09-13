"use client";

import React from "react";
import {
  CRAWLERS, CLASS_LABEL, crawlerStatuses, statusColor, statusLabel,
  type AeoRowish, type CrawlerClass,
} from "@/lib/aeoCrawlers";

/**
 * Which AI crawlers this site's robots.txt allows, grouped by what blocking one
 * actually costs.
 *
 * B-095. This replaces six hardcoded verdicts that were rendered without reading
 * any robots.txt, and that described GPTBot and ClaudeBot as "required for
 * ChatGPT citations" and "required for Claude Search" - both false, and false in
 * the direction that stops a client opting out of model training. See
 * `lib/aeoCrawlers.ts`.
 */
const ORDER: CrawlerClass[] = ["citation", "training", "user"];

const NOTE: Record<CrawlerClass, string> = {
  citation: "Blocking any of these removes the site from that engine's answers. This is the group that matters.",
  training: "Blocking these opts out of model training. It costs no citations, and is a legitimate choice.",
  user: "Fetched when a person asks an assistant about a page. Listed, never graded - most vendors state robots.txt may not apply.",
};

export function AeoCrawlerTable({ aeoRows }: { aeoRows: AeoRowish[] | null | undefined }) {
  const statuses = crawlerStatuses(aeoRows);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 14 }}>
      {ORDER.map((klass) => (
        <div key={klass}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", color: "#334155" }}>
              {CLASS_LABEL[klass]}
            </span>
            <span style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>{NOTE[klass]}</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
            {CRAWLERS.filter((c) => c.klass === klass).map((c) => {
              const s = statuses.get(c.ua) ?? null;
              return (
                <div
                  key={c.ua}
                  style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 6, padding: "10px 12px" }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
                    <div style={{ fontWeight: 700, color: "#1e293b", fontSize: 13 }}>{c.ua}</div>
                    <span
                      style={{
                        fontSize: 12, fontWeight: 700, color: statusColor(s, c.klass),
                        background: "#ffffff", border: "1px solid #cbd5e1",
                        padding: "1px 6px", borderRadius: 4, whiteSpace: "nowrap",
                      }}
                    >
                      {statusLabel(s)}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 2 }}>{c.vendor}</div>
                  <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginTop: 4, lineHeight: 1.45 }}>
                    {c.consequence}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
