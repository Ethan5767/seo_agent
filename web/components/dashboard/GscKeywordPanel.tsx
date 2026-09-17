"use client";

import React, { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/authedFetch";
import { formatGscValue, type GscRow } from "@/lib/gscViews";
import { SourceBadge } from "@/components/dashboard/SourceBadge";

/**
 * First-party query evidence, deliberately separate from the paid keyword
 * lookup above it. GSC tells an owner what their verified property already
 * earned; it does not estimate volume, discover terms, or calculate difficulty.
 */
export function GscKeywordPanel({ siteUrl }: { siteUrl: string }) {
  const [rows, setRows] = useState<GscRow[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    setState("loading");
    setMessage("");
    try {
      const response = await authedFetch("/api/gsc/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ siteUrl, dimensions: ["query"], days: 28, rowLimit: 50 }),
      });
      const data = await response.json();
      if (!response.ok) {
        setRows([]);
        setState("error");
        setMessage(data?.error || `Search Console returned HTTP ${response.status}.`);
        return;
      }
      setRows(Array.isArray(data?.rows) ? data.rows : []);
      setState("ready");
    } catch (error: any) {
      setRows([]);
      setState("error");
      setMessage(error?.message || "Could not reach Search Console.");
    }
  }, [siteUrl]);

  useEffect(() => { load(); }, [load]);

  return (
    <section
      aria-labelledby="gsc-keyword-heading"
      style={{
        marginTop: "var(--space-6)", padding: "var(--space-5)",
        border: "1px solid var(--ok-border)", borderRadius: "var(--radius-md)",
        background: "var(--ok-tint)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <div>
          <div style={{ marginBottom: "var(--space-2)" }}><SourceBadge label="Google Search Console — your verified property" kind="google" /></div>
          <h2 id="gsc-keyword-heading" style={{ margin: 0, fontSize: 18, color: "var(--ink)" }}>
            Queries already earning impressions
          </h2>
          <p style={{ margin: "var(--space-2) 0 0", maxWidth: "72ch", color: "var(--ink-body)", fontSize: 13, lineHeight: 1.55 }}>
            Actual Google Search Console queries for this verified domain in the last 28 days. This is not search volume, keyword discovery, or difficulty data; the DataForSEO Keyword Overview above remains the primary keyword research source.
          </p>
        </div>
        <button type="button" onClick={load} disabled={state === "loading"} style={{
          padding: "var(--space-2) var(--space-3)", minHeight: 34, borderRadius: "var(--radius-sm)",
          border: "1px solid var(--ok-border)", background: "var(--surface)", color: "var(--ink-body)",
          fontSize: 13, fontWeight: 600, cursor: state === "loading" ? "wait" : "pointer",
        }}>{state === "loading" ? "Loading…" : "Refresh Google data"}</button>
      </div>

      {state === "error" ? (
        <p role="alert" style={{ margin: "var(--space-4) 0 0", color: "var(--warn)", fontSize: 13 }}>{message}</p>
      ) : state === "ready" && rows.length === 0 ? (
        <p style={{ margin: "var(--space-4) 0 0", color: "var(--ink-muted)", fontSize: 13 }}>
          Search Console returned no query rows for this property and period.
        </p>
      ) : (
        <div className="table-scroll" style={{ marginTop: "var(--space-4)" }}>
          <table className="data-table">
            <thead><tr><th scope="col">Query</th><th scope="col" className="num">Impressions</th><th scope="col" className="num">Clicks</th><th scope="col" className="num">CTR</th><th scope="col" className="num">Avg position</th></tr></thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.keys?.[0] || "query"}-${index}`}>
                  <th scope="row">{formatGscValue("keys", row.keys)}</th>
                  <td className="num">{formatGscValue("impressions", row.impressions)}</td>
                  <td className="num">{formatGscValue("clicks", row.clicks)}</td>
                  <td className="num">{formatGscValue("ctr", row.ctr)}</td>
                  <td className="num">{formatGscValue("position", row.position)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
