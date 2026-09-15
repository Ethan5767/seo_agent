"use client";

import React, { useCallback, useRef, useState } from "react";
import { authedFetch } from "@/lib/authedFetch";
import { actionable, type FixFinding } from "@/lib/fixAdvisor";

/**
 * "Fix with Claude" - drop it under any findings table.
 *
 * The operator's argument, and it settles the design: *"everything should use
 * Claude, that's why it's automate - if a human does it anyway, why call it
 * automate."* Every screen measured something and then stopped. Measuring is the
 * easy half.
 *
 * Deliberately generic. It takes findings, not a screen, so Local, AEO,
 * Technical and Content all get the same treatment from one component rather
 * than four bespoke buttons that drift apart.
 *
 * The button is DISABLED when nothing is failing, and says so. A fix plan for a
 * site nobody measured is the exact bug class this session has spent the day
 * unpicking, and a model would produce a beautifully formatted one on request.
 */
export function FixWithClaude({
  findings, business, domain, facts, label = "Fix with Claude",
}: {
  findings: FixFinding[] | null | undefined;
  business?: string;
  domain?: string;
  /** Only facts the operator actually supplied. Anything absent becomes [confirm:]. */
  facts?: Record<string, string | undefined>;
  label?: string;
}) {
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);
  const abort = useRef<AbortController | null>(null);

  const todo = actionable(findings);

  const run = useCallback(async () => {
    setBusy(true); setErr(""); setOut(""); setCopied(false);
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      const res = await authedFetch("/api/fix/advise", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ findings: todo, business, domain, facts }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        const j = await res.json().catch(() => ({}));
        setErr(j.error || `Request failed (${res.status}).`);
        return;
      }
      // Streamed, so a long answer shows as it arrives rather than after.
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        setOut((prev) => prev + dec.decode(value, { stream: true }));
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") setErr(e?.message || "Could not reach Claude.");
    } finally {
      setBusy(false);
    }
  }, [todo, business, domain, facts]);

  const copy = async () => {
    try { await navigator.clipboard.writeText(out); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { setErr("Could not copy. Select the text and copy it manually."); }
  };

  const none = todo.length === 0;

  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={run}
          disabled={busy || none}
          title={none ? "Nothing is failing, so there is nothing to fix" : "Send these findings to Claude"}
          style={{
            background: none ? "var(--border)" : "var(--accent)",
            color: none ? "var(--ink-muted)" : "#fff",
            border: 0, borderRadius: 6, padding: "8px 14px",
            fontSize: 12.5, fontWeight: 700,
            cursor: busy || none ? "not-allowed" : "pointer",
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          <span>⚡</span>
          {busy ? "Claude is writing the fixes…" : none ? "Nothing to fix" : `${label} (${todo.length})`}
        </button>

        {busy && (
          <button type="button" onClick={() => abort.current?.abort()} style={linkBtn}>Stop</button>
        )}
        {out && !busy && (
          <>
            <button type="button" onClick={copy} style={linkBtn}>{copied ? "Copied" : "Copy all"}</button>
            <button type="button" onClick={run} style={linkBtn}>Regenerate</button>
          </>
        )}
        <span style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>
          {none
            ? "Run a scan first. A fix plan written without findings is a guess."
            : "Grounded in the findings above. Facts it does not have come back as [confirm: ...]."}
        </span>
      </div>

      {err && (
        <div style={{ marginTop: 10, padding: "10px 12px", borderRadius: 6, border: "1px solid #fecaca", background: "var(--bad-tint)", fontSize: 12, color: "#991b1b" }}>
          {err}
        </div>
      )}

      {(out || busy) && (
        <pre style={{
          marginTop: 10, padding: "14px 16px", borderRadius: 8,
          border: "1px solid #e2e8f0", background: "var(--ink)", color: "var(--border)",
          fontSize: 12, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word",
          maxHeight: 460, overflowY: "auto", fontFamily: "ui-monospace, SFMono-Regular, monospace",
        }}>
          {out || "…"}
        </pre>
      )}
    </div>
  );
}

const linkBtn: React.CSSProperties = {
  background: "none", border: "none", padding: 0,
  fontSize: 11.5, color: "var(--accent)", cursor: "pointer", fontWeight: 600,
};
