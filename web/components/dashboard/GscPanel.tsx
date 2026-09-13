"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  GSC_METRIC_COLUMNS,
  gscTotals,
  formatGscValue,
  type GscView,
  type GscRow,
} from "@/lib/gscViews";
import { authedFetch } from "@/lib/authedFetch";

/**
 * A Search Console screen.
 *
 * Every figure here is measured: real clicks, impressions and average position
 * from the client's own property, not modelled from a SERP index and a
 * click-through curve. Where nothing is loaded, the strip reads zero rather
 * than going blank, and the reason is stated plainly.
 */

const PAGE_SIZE = 25;

export interface GscPanelProps {
  view: GscView;
  /** The Search Console property, e.g. "sc-domain:example.com". */
  siteUrl?: string;
  /** Sends the operator to the Google connection screen. */
  onConnect?: () => void;
}

type Status = "idle" | "loading" | "ready" | "error";

export function GscPanel({ view, siteUrl, onConnect }: GscPanelProps) {
  const [rows, setRows] = useState<GscRow[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const load = useCallback(async () => {
    setStatus("loading");
    setMessage("");
    try {
      const res = await authedFetch("/api/gsc/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          siteUrl,
          dimensions: [view.dimension],
          rowLimit: 250,
          days: 28,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus("error");
        // Google's own message is more useful than anything we could invent.
        setMessage(data?.error || `Search Console returned HTTP ${res.status}.`);
        setRows([]);
        return;
      }
      setRows(Array.isArray(data?.rows) ? data.rows : []);
      setStatus("ready");
    } catch (err: any) {
      setStatus("error");
      setMessage(err?.message || "Could not reach Search Console.");
      setRows([]);
    }
  }, [siteUrl, view.dimension]);

  useEffect(() => {
    setPage(0);
    setQuery("");
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => (r.keys || []).join(" ").toLowerCase().includes(q));
  }, [rows, query]);

  const totals = gscTotals(filtered);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const cells = [
    { label: "Rows", value: totals.rows.toLocaleString() },
    { label: "Clicks", value: totals.clicks.toLocaleString() },
    { label: "Impressions", value: totals.impressions.toLocaleString() },
    { label: "CTR", value: formatGscValue("ctr", totals.ctr) },
    { label: "Avg position", value: formatGscValue("position", totals.position) },
  ];

  return (
    <div>
      {/* Zeroes are a reading. The strip renders before any data arrives. */}
      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(8rem, 1fr))",
          margin: "0 0 var(--space-4)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          background: "var(--surface)",
          overflow: "hidden",
        }}
      >
        {cells.map((c, i) => (
          <div
            key={c.label}
            style={{
              padding: "var(--space-3) var(--space-4)",
              borderRight: i < cells.length - 1 ? "1px solid var(--border)" : 0,
            }}
          >
            <dt style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 500 }}>{c.label}</dt>
            <dd
              style={{
                margin: "var(--space-1) 0 0",
                fontSize: 22,
                fontWeight: 700,
                lineHeight: 1,
                color: "var(--ink)",
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {c.value}
            </dd>
          </div>
        ))}
      </dl>

      <div
        style={{
          display: "flex",
          gap: "var(--space-3)",
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: "var(--space-3)",
        }}
      >
        <label htmlFor={`gsc-filter-${view.id}`} style={{ position: "absolute", left: -9999 }}>
          Filter {view.label}
        </label>
        <input
          id={`gsc-filter-${view.id}`}
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
          placeholder={`Filter ${rows.length} rows`}
          style={{
            flex: "1 1 16rem",
            minWidth: 0,
            padding: "var(--space-2) var(--space-3)",
            minHeight: 34,
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border-strong)",
            background: "var(--surface)",
            color: "var(--ink-body)",
            fontSize: 13,
          }}
        />
        <button
          type="button"
          onClick={load}
          disabled={status === "loading"}
          style={{
            padding: "var(--space-2) var(--space-3)",
            minHeight: 34,
            borderRadius: "var(--radius-sm)",
            border: "1px solid var(--border-strong)",
            background: "var(--surface)",
            color: "var(--ink-body)",
            fontSize: 13,
            fontWeight: 500,
            cursor: status === "loading" ? "wait" : "pointer",
          }}
        >
          {status === "loading" ? "Loading…" : "Refresh"}
        </button>
        <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>Last 28 days</span>
      </div>

      {status === "error" && (
        <div
          style={{
            border: "1px solid var(--warn-border)",
            background: "var(--warn-tint)",
            color: "var(--warn)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            fontSize: 13,
            marginBottom: "var(--space-3)",
          }}
        >
          <strong style={{ display: "block", marginBottom: "var(--space-1)" }}>
            Search Console did not return data
          </strong>
          {message}
          {onConnect && (
            <div>
              <button
                type="button"
                onClick={onConnect}
                style={{
                  marginTop: "var(--space-3)",
                  padding: "var(--space-2) var(--space-4)",
                  minHeight: 34,
                  borderRadius: "var(--radius-sm)",
                  border: 0,
                  background: "var(--accent)",
                  color: "#ffffff",
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Connect Google
              </button>
            </div>
          )}
        </div>
      )}

      <div
        style={{
          overflowX: "auto",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
        }}
      >
        <table
          style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, minWidth: "42rem" }}
        >
          <caption style={{ position: "absolute", left: -9999 }}>{view.blurb}</caption>
          <thead>
            <tr>
              <th scope="col" style={{ ...headStyle, width: "34%" }}>
                {view.keyLabel}
              </th>
              {GSC_METRIC_COLUMNS.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  style={{ ...headStyle, width: c.width, textAlign: "right" }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={GSC_METRIC_COLUMNS.length + 1} style={{ ...cellStyle, textAlign: "center" }}>
                  <div style={{ padding: "var(--space-4) 0", color: "var(--ink-muted)" }}>
                    <div style={{ fontWeight: 600, color: "var(--ink-body)", marginBottom: "var(--space-1)" }}>
                      {status === "loading" ? "Loading from Search Console…" : "No rows yet"}
                    </div>
                    <div style={{ maxWidth: "52ch", marginInline: "auto" }}>
                      {status === "loading" ? view.blurb : view.emptyHint}
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              visible.map((r, i) => (
                <tr key={`${(r.keys || []).join("|")}-${i}`}>
                  <td style={{ ...cellStyle, color: "var(--ink)", fontWeight: 500, wordBreak: "break-word" }}>
                    {formatGscValue("keys", r.keys)}
                  </td>
                  {GSC_METRIC_COLUMNS.map((c) => (
                    <td
                      key={c.key}
                      style={{ ...cellStyle, textAlign: "right", fontVariantNumeric: "tabular-nums" }}
                    >
                      {formatGscValue(c.key, (r as Record<string, unknown>)[c.key])}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div
          style={{
            display: "flex",
            gap: "var(--space-2)",
            alignItems: "center",
            justifyContent: "flex-end",
            marginTop: "var(--space-3)",
          }}
        >
          <span style={{ fontSize: 12, color: "var(--ink-muted)", marginRight: "auto" }}>
            Page {safePage + 1} of {pageCount}
          </span>
          <PageButton label="Previous" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} />
          <PageButton
            label="Next"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage(safePage + 1)}
          />
        </div>
      )}
    </div>
  );
}

const headStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "var(--space-2) var(--space-3)",
  background: "var(--surface-2)",
  borderBottom: "1px solid var(--border-strong)",
  fontSize: 12,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--ink-muted)",
};

const cellStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--border)",
  verticalAlign: "top",
};

function PageButton({
  label,
  disabled,
  onClick,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "var(--space-2) var(--space-3)",
        minHeight: 34,
        borderRadius: "var(--radius-sm)",
        border: "1px solid var(--border-strong)",
        background: "var(--surface)",
        color: disabled ? "var(--ink-faint)" : "var(--ink-body)",
        fontSize: 13,
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.55 : 1,
      }}
    >
      {label}
    </button>
  );
}
