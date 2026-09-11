"use client";

import React, { useState } from "react";
import { contentToolById, missingRequired } from "@/lib/contentTools";

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
}

export function ContentPanel({ toolId, domain, business, keywords }: ContentPanelProps) {
  const tool = contentToolById(toolId);
  const [values, setValues] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  if (!tool) return null;

  const missing = missingRequired(tool, values);

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
          context: { domain, business, keywords },
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
          <div key={field.name} style={{ display: "flex", flexDirection: "column", gap: "var(--space-1)" }}>
            <label
              htmlFor={`content-${tool.id}-${field.name}`}
              style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-body)" }}
            >
              {field.label}
              {field.required && <span style={{ color: "var(--bad)" }}> *</span>}
            </label>
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

        {keywords && keywords.length > 0 && (
          <p style={{ fontSize: 12, color: "var(--ink-muted)", margin: 0 }}>
            Using {keywords.length} keyword{keywords.length === 1 ? "" : "s"} measured in your last
            scan as context.
          </p>
        )}

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
