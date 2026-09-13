"use client";

import React, { useState, useEffect, useMemo } from "react";
import { contentToolById, missingRequired, evidenceFor, checkDraft } from "@/lib/contentTools";

/**
 * A content tool: the operator's inputs on the left, the streamed draft on the
 * right. Text arrives as it is written rather than after a spinner, because a
 * long draft takes long enough that a spinner reads as a hang.
 *
 * The draft is labelled as a draft everywhere it appears. That is the product
 * rule, not a disclaimer: generated copy goes to a human before it goes to a
 * page, and the publishing gate refuses claims that cannot be traced.
 */

export interface ContentPanelProps {
  toolId: string;
  domain?: string;
  business?: string;
  /** Keyword rows from the last scan, so drafts build on measured demand. */
  keywords?: string[];
  /** Findings from the last scan. The tool argues from the ones it matches. */
  findings?: Array<{ code?: string; what?: string; detail?: string; severity?: string }>;
  /** Real Search Console queries for this page, highest impressions first. */
  queries?: Array<{ query: string; impressions?: number; position?: number }>;
}

export function ContentPanel({ toolId, domain, business, keywords, findings, queries }: ContentPanelProps) {
  const tool = contentToolById(toolId);
  const [values, setValues] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  if (!tool) return null;

  const missing = missingRequired(tool, values);
  const ctx = useMemo(
    () => ({ domain, business, keywords, findings, queries }) as any,
    [domain, business, keywords, findings, queries],
  );

  // The findings this tool declares it argues from, matched against the scan.
  const evidence = evidenceFor(tool, ctx);

  /**
   * Fields the pipeline filled in for itself, and why.
   *
   * An automated pipeline that stops to ask for a target keyword it already
   * measured is not automated. It is also less accurate: a typed keyword is
   * the operator's guess at what the page is about, while Search Console knows
   * what it actually ranks for.
   *
   * Derived values are pre-filled and overridable — the operator stays in
   * charge, they just start from the measurement instead of a blank box.
   */
  const derived = useMemo(() => {
    const out: Record<string, { value: string; because: string }> = {};
    for (const f of tool?.fields ?? []) {
      const s = f.suggest?.(ctx);
      if (s?.value) out[f.name] = s;
    }
    return out;
  }, [tool, ctx]);

  /**
   * Lint the finished draft against what we can actually source.
   *
   * Same idea the PR gate applies, run early: a figure the page never stated is
   * the most common way generated copy becomes a liability, and it is far
   * cheaper to catch here than after a commit.
   */
  const issues = useMemo(
    () => (busy || !draft ? [] : checkDraft(draft, [
      ...(evidence ?? []).map((r: any) => `${r.what ?? ""} ${r.detail ?? ""}`),
      ...(queries ?? []).map((q) => q.query),
      ...(keywords ?? []),
      business ?? "", domain ?? "",
    ])),
    [draft, busy, evidence, queries, keywords, business, domain],
  );

  // Fill once the derivation is available, without clobbering a typed value.
  useEffect(() => {
    setValues((v) => {
      let next = v;
      for (const [name, s] of Object.entries(derived)) {
        if (!next[name]) next = { ...next, [name]: s.value };
      }
      return next;
    });
  }, [derived]);

  async function generate() {
    if (!tool) return;
    setError("");
    setDraft("");
    setBusy(true);
    try {
      const res = await fetch("/api/content/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool: tool.id,
          values,
          context: { domain, business, keywords, findings, queries },
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data?.error || `Generation failed (HTTP ${res.status}).`);
        return;
      }
      if (!res.body) {
        setError("No response body.");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        setDraft((d) => d + decoder.decode(value, { stream: true }));
      }
    } catch (err: any) {
      setError(err?.message || "Could not reach the generator.");
    } finally {
      setBusy(false);
    }
  }

  async function copyDraft() {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      setError("Could not copy. Select the text and copy manually.");
    }
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 22rem) minmax(0, 1fr)",
        gap: "var(--space-5)",
        alignItems: "start",
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (missing.length === 0 && !busy) generate();
        }}
        style={{
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          background: "var(--surface)",
          padding: "var(--space-4)",
          display: "flex",
          flexDirection: "column",
          gap: "var(--space-3)",
        }}
      >
        {tool.fields.map((field) => (
          <div key={field.name} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <label
              htmlFor={`content-${tool.id}-${field.name}`}
              style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap", fontSize: 12, fontWeight: 600, color: "var(--ink-body)" }}
            >
              {field.label}{field.required ? " *" : ""}
              {derived[field.name] ? (
                <span
                  title={derived[field.name].because}
                  style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase",
                    padding: "2px 6px", borderRadius: 3, background: "#e4efe9", color: "#2c6b4f",
                    border: "1px solid #c7e0d3",
                  }}
                >
                  measured
                </span>
              ) : null}
            </label>
            {derived[field.name] ? (
              <div style={{ fontSize: 11.5, color: "var(--ink-muted)", lineHeight: 1.5 }}>
                Filled from your data — {derived[field.name].because}. Change it if you disagree.
              </div>
            ) : null}
            {field.multiline ? (
              <textarea
                id={`content-${tool.id}-${field.name}`}
                value={values[field.name] || ""}
                onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                placeholder={field.placeholder}
                rows={8}
                style={{ ...inputStyle, resize: "vertical", lineHeight: 1.5 }}
              />
            ) : (
              <input
                id={`content-${tool.id}-${field.name}`}
                type="text"
                value={values[field.name] || ""}
                onChange={(e) => setValues((v) => ({ ...v, [field.name]: e.target.value }))}
                placeholder={field.placeholder}
                style={inputStyle}
              />
            )}
          </div>
        ))}

        {/*
          What this tool will argue from, shown before the draft is written.

          Every tool already put the matching findings and the real Search
          Console queries in front of the model — and none of it was on screen,
          so the operator saw two inputs and a button and had no way to tell
          whether the draft would be grounded in this page or in nothing. On a
          tool like Striking Distance, which takes no input at all, the screen
          was literally a button.

          Showing the evidence is also the honest half: where there is none, it
          says so and names what would supply it, rather than letting a
          confident-looking draft imply a measurement that never happened.
        */}
        <div style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", overflow: "hidden" }}>
          <div style={{
            padding: "8px 12px", background: "var(--surface-sunk, #f1f5f9)",
            borderBottom: "1px solid var(--border)", fontSize: 11, fontWeight: 700,
            letterSpacing: ".07em", textTransform: "uppercase", color: "var(--ink-muted)",
          }}>
            What this draft will be argued from
          </div>

          <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 10 }}>
            {evidence.length > 0 ? (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-body)", marginBottom: 5 }}>
                  {evidence.length} measured finding{evidence.length === 1 ? "" : "s"} on this page
                </div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12.5, lineHeight: 1.6, color: "var(--ink-muted)" }}>
                  {evidence.slice(0, 6).map((r, i) => (
                    <li key={`${r.code}-${i}`}>
                      <span style={{
                        fontWeight: 700,
                        color: r.severity === "error" ? "#a33a22" : r.severity === "warn" ? "#8a6a14" : "var(--ink-muted)",
                      }}>{r.severity ?? "info"}</span>
                      {" · "}
                      <span style={{ color: "var(--ink-body)" }}>{r.what || r.code}</span>
                      {r.detail ? <span> — {r.detail}</span> : null}
                    </li>
                  ))}
                </ul>
                {evidence.length > 6 ? (
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 4 }}>
                    and {evidence.length - 6} more
                  </div>
                ) : null}
              </div>
            ) : (
              <div style={{ fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.6 }}>
                {tool.evidenceCodes?.length
                  ? "No findings of this kind on the scanned page. The draft will be written from the page copy and the queries alone — there is no measured gap for it to argue from."
                  : "This tool argues from measured demand rather than from findings."}
              </div>
            )}

            {queries && queries.length > 0 ? (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-body)", marginBottom: 5 }}>
                  {queries.length} query{queries.length === 1 ? "" : " terms"} this page already appears for
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                  {queries.slice(0, 8).map((q) => (
                    <span key={q.query} style={{
                      fontSize: 11.5, padding: "2px 7px", borderRadius: 3,
                      background: "var(--surface-sunk, #f1f5f9)", border: "1px solid var(--border)",
                      color: "var(--ink-body)",
                    }}>
                      {q.query}
                      {typeof q.position === "number" ? (
                        <span style={{ color: "var(--ink-muted)" }}> · #{q.position.toFixed(0)}</span>
                      ) : null}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div style={{ fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.6 }}>
                No Search Console queries for this page. Connect Search Console and the draft can be
                written toward what people actually search for, instead of toward a guess.
              </div>
            )}

            {keywords && keywords.length > 0 ? (
              <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
                Plus {keywords.length} keyword{keywords.length === 1 ? "" : "s"} measured in the last scan.
              </div>
            ) : null}
          </div>
        </div>

        <button
          type="submit"
          disabled={busy || missing.length > 0}
          title={missing.length > 0 ? `Fill in: ${missing.join(", ")}` : undefined}
          style={{
            padding: "var(--space-2) var(--space-4)",
            minHeight: 38,
            borderRadius: "var(--radius-sm)",
            border: 0,
            background: busy || missing.length > 0 ? "var(--border-strong)" : "var(--accent)",
            color: busy || missing.length > 0 ? "var(--ink-muted)" : "#ffffff",
            fontSize: 13,
            fontWeight: 600,
            cursor: busy || missing.length > 0 ? "not-allowed" : "pointer",
          }}
        >
          {busy ? "Writing…" : "Write draft"}
        </button>
      </form>

      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          background: "var(--surface)",
          minHeight: "22rem",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--space-3)",
            padding: "var(--space-3) var(--space-4)",
            borderBottom: "1px solid var(--border)",
            background: "var(--surface-2)",
          }}
        >
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: "var(--warn)",
              background: "var(--warn-tint)",
              border: "1px solid var(--warn-border)",
              borderRadius: "var(--radius-xs)",
              padding: "2px 8px",
            }}
          >
            Draft, review before publishing
          </span>
          {issues.length > 0 ? (
            <span
              title={`${issues.length} thing${issues.length === 1 ? "" : "s"} to resolve before this ships`}
              style={{
                fontSize: 11, fontWeight: 700, color: "#a33a22", background: "#f8e8e3",
                border: "1px solid #eccfc5", borderRadius: "var(--radius-xs)", padding: "2px 8px",
              }}
            >
              {issues.length} to check
            </span>
          ) : draft && !busy ? (
            <span
              title="Every figure in this draft appears in the page or the measured evidence"
              style={{
                fontSize: 11, fontWeight: 700, color: "#2c6b4f", background: "#e4efe9",
                border: "1px solid #c7e0d3", borderRadius: "var(--radius-xs)", padding: "2px 8px",
              }}
            >
              Figures traced
            </span>
          ) : null}
          {draft && (
            <button
              type="button"
              onClick={copyDraft}
              style={{
                padding: "var(--space-1) var(--space-3)",
                minHeight: 30,
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-strong)",
                background: "var(--surface)",
                color: "var(--ink-body)",
                fontSize: 12,
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          )}
        </div>

        {issues.length > 0 && !busy ? (
          <div style={{ borderBottom: "1px solid var(--border)", background: "#fdf7f5", padding: "10px 14px" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#a33a22", marginBottom: 6 }}>
              Check before publishing
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12.5, lineHeight: 1.6, color: "var(--ink-body)" }}>
              {issues.slice(0, 8).map((iss, i) => (
                <li key={`${iss.kind}-${i}`}>
                  <code style={{ background: "#fff", border: "1px solid #eccfc5", borderRadius: 3, padding: "0 4px" }}>{iss.text}</code>
                  {" — "}
                  <span style={{ color: "var(--ink-muted)" }}>{iss.note}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {error && (
          <div
            style={{
              margin: "var(--space-4)",
              border: "1px solid var(--bad-border)",
              background: "var(--bad-tint)",
              color: "var(--bad)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-3) var(--space-4)",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        )}

        {!draft && !error && (
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              padding: "var(--space-5)",
              textAlign: "center",
            }}
          >
            <div style={{ maxWidth: "46ch" }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-body)" }}>
                {busy ? "Writing…" : "Nothing drafted yet"}
              </div>
              <p style={{ fontSize: 13, color: "var(--ink-muted)", marginTop: "var(--space-1)" }}>
                {tool.blurb}
              </p>
            </div>
          </div>
        )}

        {draft && (
          <pre
            style={{
              margin: 0,
              padding: "var(--space-4)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              fontFamily: "inherit",
              fontSize: 13,
              lineHeight: 1.6,
              color: "var(--ink-body)",
            }}
          >
            {draft}
          </pre>
        )}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "var(--space-2) var(--space-3)",
  minHeight: 36,
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border-strong)",
  background: "var(--surface)",
  color: "var(--ink-body)",
  fontSize: 13,
};
