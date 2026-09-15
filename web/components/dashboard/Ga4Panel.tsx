"use client";

import React, { useCallback, useEffect, useState } from "react";
import { authedFetch } from "@/lib/authedFetch";
import type { Ga4Property, Ga4Report, Ga4Row } from "@/lib/ga4";

/**
 * Google Analytics 4 for the project's own property.
 *
 * Every figure is read from GA4 through the operator's Google connection. The
 * property is the one whose web stream is the project's domain; when none
 * matches, the operator picks one, and nothing is shown until they do.
 */

export interface Ga4PanelProps {
  /** The project's domain, used to find its GA4 property. */
  domain: string;
  /** Sends the operator to the Google connection screen. */
  onConnect?: () => void;
}

type Status = "idle" | "loading" | "ready" | "error";

const num = (v: unknown) => (Number(v) || 0).toLocaleString();
const pct = (v: unknown) => `${((Number(v) || 0) * 100).toFixed(1)}%`;

const box: React.CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
  background: "var(--surface)",
};

const control: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  minHeight: 34,
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border-strong)",
  background: "var(--surface)",
  color: "var(--ink-body)",
  fontSize: 13,
};

function Notice({ title, message, onConnect }: { title: string; message: string; onConnect?: () => void }) {
  return (
    <div
      role="status"
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
      <strong style={{ display: "block", marginBottom: "var(--space-1)" }}>{title}</strong>
      {message}
      {onConnect && /connect google/i.test(message) && (
        <div>
          <button
            type="button"
            onClick={onConnect}
            style={{ ...control, marginTop: "var(--space-3)", border: 0, background: "var(--accent)", color: "var(--surface)", fontWeight: 600, cursor: "pointer" }}
          >
            Connect Google
          </button>
        </div>
      )}
    </div>
  );
}

function RowsTable({ title, rows, dimension, dimensionLabel }: { title: string; rows: Ga4Row[]; dimension: string; dimensionLabel: string }) {
  return (
    <section style={{ ...box, marginBottom: "var(--space-4)", overflow: "hidden" }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)", margin: 0, padding: "var(--space-3) var(--space-4)", borderBottom: "1px solid var(--border)" }}>
        {title}
      </h2>
      {rows.length === 0 ? (
        <p style={{ margin: 0, padding: "var(--space-4)", fontSize: 13, color: "var(--ink-muted)" }}>
          GA4 recorded no sessions here in this period.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: "left", color: "var(--ink-muted)" }}>
                {[dimensionLabel, "Sessions", "Users", "Engagement", "Key events"].map((h, i) => (
                  <th key={h} style={{ padding: "var(--space-2) var(--space-4)", fontWeight: 600, textAlign: i ? "right" : "left", whiteSpace: "nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r[dimension]}-${i}`} style={{ borderTop: "1px solid var(--border)" }}>
                  <td style={{ padding: "var(--space-2) var(--space-4)", color: "var(--ink-body)", wordBreak: "break-all" }}>{String(r[dimension] || "(not set)")}</td>
                  <td style={{ padding: "var(--space-2) var(--space-4)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{num(r.sessions)}</td>
                  <td style={{ padding: "var(--space-2) var(--space-4)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{num(r.activeUsers)}</td>
                  <td style={{ padding: "var(--space-2) var(--space-4)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{pct(r.engagementRate)}</td>
                  <td style={{ padding: "var(--space-2) var(--space-4)", textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{num(r.keyEvents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DailyBars({ daily }: { daily: Ga4Row[] }) {
  const max = Math.max(1, ...daily.map((d) => Number(d.sessions) || 0));
  return (
    <section style={{ ...box, marginBottom: "var(--space-4)", padding: "var(--space-3) var(--space-4)" }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)", margin: "0 0 var(--space-3)" }}>Sessions per day</h2>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 96 }} aria-label="Sessions per day">
        {daily.map((d) => {
          const v = Number(d.sessions) || 0;
          return (
            <div
              key={String(d.date)}
              title={`${d.date}: ${v.toLocaleString()} sessions, ${num(d.activeUsers)} users`}
              style={{ flex: 1, minWidth: 2, height: `${Math.max(2, (v / max) * 100)}%`, background: "var(--accent)", borderRadius: 2, opacity: 0.85 }}
            />
          );
        })}
      </div>
      {daily.length > 0 && (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-muted)", marginTop: "var(--space-1)" }}>
          <span>{String(daily[0].date)}</span>
          <span>{String(daily[daily.length - 1].date)}</span>
        </div>
      )}
    </section>
  );
}

export function Ga4Panel({ domain, onConnect }: Ga4PanelProps) {
  const [properties, setProperties] = useState<Ga4Property[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [propStatus, setPropStatus] = useState<Status>("idle");
  const [report, setReport] = useState<Ga4Report | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [message, setMessage] = useState("");

  const loadProperties = useCallback(async () => {
    setPropStatus("loading");
    setMessage("");
    setReport(null);
    try {
      const res = await authedFetch(`/api/ga4/properties?domain=${encodeURIComponent(domain)}`);
      const data = await res.json();
      if (!res.ok) {
        setPropStatus("error");
        setMessage(data?.error || `Google Analytics returned HTTP ${res.status}.`);
        return;
      }
      setProperties(Array.isArray(data.properties) ? data.properties : []);
      setPropertyId(data.matchedId || "");
      setPropStatus("ready");
    } catch (err: any) {
      setPropStatus("error");
      setMessage(err?.message || "Could not reach Google Analytics.");
    }
  }, [domain]);

  const loadReport = useCallback(async (id: string) => {
    if (!id) return;
    setStatus("loading");
    setMessage("");
    try {
      const res = await authedFetch("/api/ga4/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ propertyId: id, days: 28 }),
      });
      const data = await res.json();
      if (!res.ok) {
        setStatus("error");
        setMessage(data?.error || `Google Analytics returned HTTP ${res.status}.`);
        setReport(null);
        return;
      }
      setReport(data);
      setStatus("ready");
    } catch (err: any) {
      setStatus("error");
      setMessage(err?.message || "Could not reach Google Analytics.");
      setReport(null);
    }
  }, []);

  useEffect(() => {
    loadProperties();
  }, [loadProperties]);

  useEffect(() => {
    if (propertyId) loadReport(propertyId);
  }, [propertyId, loadReport]);

  const selected = properties.find((p) => p.id === propertyId);
  const t = report?.totals;
  const cells = [
    { label: "Users", value: num(t?.activeUsers) },
    { label: "New users", value: num(t?.newUsers) },
    { label: "Sessions", value: num(t?.sessions) },
    { label: "Engagement rate", value: pct(t?.engagementRate) },
    { label: "Page views", value: num(t?.screenPageViews) },
    { label: "Key events", value: num(t?.keyEvents) },
  ];

  return (
    <div>
      {propStatus === "error" && <Notice title="Google Analytics is not readable" message={message} onConnect={onConnect} />}

      {propStatus === "ready" && properties.length === 0 && (
        <Notice
          title="No GA4 property on this Google account"
          message="The connected Google account cannot see any GA4 property. Connect Google with the account that has Analytics access, or add this account as a viewer in GA4 (Admin → Property access management)."
          onConnect={onConnect}
        />
      )}

      {properties.length > 0 && (
        <div style={{ display: "flex", gap: "var(--space-3)", alignItems: "center", flexWrap: "wrap", marginBottom: "var(--space-3)" }}>
          <label htmlFor="ga4-property" style={{ fontSize: 13, color: "var(--ink-muted)" }}>GA4 property</label>
          <select id="ga4-property" value={propertyId} onChange={(e) => setPropertyId(e.target.value)} style={{ ...control, flex: "1 1 16rem", minWidth: 0 }}>
            <option value="">Choose a property…</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.displayName}{p.account ? ` · ${p.account}` : ""}{p.webUris[0] ? ` · ${p.webUris[0]}` : ""}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => (propertyId ? loadReport(propertyId) : loadProperties())}
            disabled={status === "loading" || propStatus === "loading"}
            style={{ ...control, fontWeight: 500, cursor: status === "loading" ? "wait" : "pointer" }}
          >
            {status === "loading" || propStatus === "loading" ? "Loading…" : "Refresh"}
          </button>
          <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
            {report ? `${report.startDate} to ${report.endDate}` : "Last 28 days"}
          </span>
        </div>
      )}

      {propStatus === "ready" && properties.length > 0 && !propertyId && (
        <p style={{ fontSize: 13, color: "var(--ink-muted)", margin: "0 0 var(--space-3)" }}>
          No GA4 web stream on this account points at {domain || "this project"}. Choose the property that measures it.
        </p>
      )}
      {selected && domain && propStatus === "ready" && !selected.webUris.length && (
        <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: "0 0 var(--space-3)" }}>
          This property has no web stream, so it cannot be confirmed as {domain}.
        </p>
      )}

      {status === "error" && <Notice title="GA4 did not return data" message={message} onConnect={onConnect} />}

      {propertyId && (
        <dl style={{ ...box, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(8rem, 1fr))", margin: "0 0 var(--space-4)", overflow: "hidden" }}>
          {cells.map((c) => (
            <div key={c.label} style={{ padding: "var(--space-3) var(--space-4)", borderRight: "1px solid var(--border)" }}>
              <dt style={{ fontSize: 12, color: "var(--ink-muted)", fontWeight: 500 }}>{c.label}</dt>
              <dd style={{ margin: "var(--space-1) 0 0", fontSize: 22, fontWeight: 700, lineHeight: 1, color: "var(--ink)", fontVariantNumeric: "tabular-nums" }}>
                {report ? c.value : "–"}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {report && (
        <>
          <DailyBars daily={report.daily} />
          <RowsTable title="Traffic channels" rows={report.channels} dimension="sessionDefaultChannelGroup" dimensionLabel="Channel" />
          <RowsTable title="Organic search landing pages" rows={report.organicLandingPages} dimension="landingPagePlusQueryString" dimensionLabel="Landing page" />
          <RowsTable title="All landing pages" rows={report.landingPages} dimension="landingPagePlusQueryString" dimensionLabel="Landing page" />
        </>
      )}
    </div>
  );
}
