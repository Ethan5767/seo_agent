"use client";

import React, { useCallback, useRef, useState } from "react";
import { Icon } from "@/components/dashboard/Icon";
import { authedFetch } from "@/lib/authedFetch";

/**
 * "Brainstorm the plan with Claude" - a CONVERSATION, the way the Superpowers
 * brainstorming skill works.
 *
 * Not a one-shot report. Claude asks one question at a time (goal this cycle,
 * time budget, who does the work), proposes approaches, and converges on a
 * "## Cycle Plan". The whole transcript is sent each turn; the reply streams.
 *
 * Sibling of FixWithClaude in look and mechanics (stream, stop, copy), but it
 * keeps a message history and has an input box.
 */
type Msg = { role: "user" | "assistant"; content: string };

export function BrainstormPlan({
  worklist, business, domain, tier, goal,
}: {
  worklist: any[] | null | undefined;
  business?: string;
  domain?: string;
  tier?: number;
  goal?: string;
}) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [started, setStarted] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement | null>(null);

  const items = Array.isArray(worklist) ? worklist : [];
  const none = items.length === 0;

  // One turn: POST the whole transcript, stream the reply into a trailing
  // assistant message. `history` is the messages to send (already including the
  // operator's new line, if any).
  const turn = useCallback(async (history: Msg[]) => {
    setBusy(true); setErr("");
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    // Add an empty assistant bubble we stream into.
    setMessages([...history, { role: "assistant", content: "" }]);
    try {
      const res = await authedFetch("/api/plan/brainstorm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ worklist: items, messages: history, business, domain, tier, goal }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        const j = await res.json().catch(() => ({}));
        setErr(j.error || `Request failed (${res.status}).`);
        setMessages(history); // drop the empty bubble
        return;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let acc = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += dec.decode(value, { stream: true });
        setMessages([...history, { role: "assistant", content: acc }]);
        scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
      }
    } catch (e: any) {
      if (e?.name !== "AbortError") setErr(e?.message || "Could not reach Claude.");
      setMessages(history);
    } finally {
      setBusy(false);
    }
  }, [items, business, domain, tier, goal]);

  const start = useCallback(() => { setStarted(true); void turn([]); }, [turn]);

  const send = useCallback(() => {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    void turn([...messages, { role: "user", content: text }]);
  }, [draft, busy, messages, turn]);

  const reset = () => { abort.current?.abort(); setMessages([]); setStarted(false); setErr(""); setDraft(""); };

  // Before it starts: a single button, same as FixWithClaude.
  if (!started) {
    return (
      <div style={{ marginTop: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button
            type="button" onClick={start} disabled={none}
            title={none ? "No worklist yet. Build the plan first." : "Brainstorm the cycle with Claude, one question at a time"}
            style={{
              background: none ? "var(--border)" : "var(--accent)",
              color: none ? "var(--ink-muted)" : "var(--color-white)",
              border: 0, borderRadius: 6, padding: "8px 14px",
              fontSize: 12.5, fontWeight: 700, cursor: none ? "not-allowed" : "pointer",
              display: "flex", alignItems: "center", gap: 6,
            }}
          >
            <Icon name="bolt" />
            {none ? "No worklist to brainstorm" : `Brainstorm the plan with Claude (${items.length})`}
          </button>
          <span style={{ fontSize: 11.5, color: "var(--ink-muted)" }}>
            {none
              ? "Build the plan first. A strategy written without a worklist is a guess."
              : "Claude asks one question at a time and converges on a cycle plan. Grounded in the worklist above."}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 14, border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", borderBottom: "1px solid var(--border)", background: "var(--surface, #fafbfc)" }}>
        <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--ink-body)", display: "flex", alignItems: "center", gap: 6 }}>
          <Icon name="bolt" /> Brainstorm the plan
        </span>
        <div style={{ display: "flex", gap: 12 }}>
          {busy && <button type="button" onClick={() => abort.current?.abort()} style={linkBtn}>Stop</button>}
          <button type="button" onClick={reset} style={linkBtn}>Reset</button>
        </div>
      </div>

      <div ref={scroller} style={{ maxHeight: 420, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === "user" ? "flex-end" : "flex-start",
            maxWidth: "88%",
            background: m.role === "user" ? "var(--accent)" : "var(--ink)",
            color: m.role === "user" ? "var(--color-white)" : "var(--border)",
            borderRadius: 8, padding: "10px 12px",
            fontSize: 12.5, lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word",
            fontFamily: m.role === "assistant" ? "ui-monospace, SFMono-Regular, monospace" : undefined,
          }}>
            {m.content || (busy ? "…" : "")}
          </div>
        ))}
      </div>

      {err && (
        <div style={{ margin: "0 12px 10px", padding: "10px 12px", borderRadius: 6, border: "1px solid var(--bad-border)", background: "var(--bad-tint)", fontSize: 12, color: "var(--bad)" }}>
          {err}
        </div>
      )}

      <div style={{ display: "flex", gap: 8, padding: 12, borderTop: "1px solid var(--border)" }}>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Answer, or steer the plan… (Enter to send, Shift+Enter for a newline)"
          rows={2}
          disabled={busy}
          style={{
            flex: 1, resize: "vertical", minHeight: 38, borderRadius: 6,
            border: "1px solid var(--border)", padding: "8px 10px", fontSize: 12.5,
            fontFamily: "inherit", color: "var(--ink-body)", background: "var(--color-white, #fff)",
          }}
        />
        <button
          type="button" onClick={send} disabled={busy || !draft.trim()}
          style={{
            alignSelf: "stretch", background: busy || !draft.trim() ? "var(--border)" : "var(--accent)",
            color: busy || !draft.trim() ? "var(--ink-muted)" : "var(--color-white)",
            border: 0, borderRadius: 6, padding: "0 16px", fontSize: 12.5, fontWeight: 700,
            cursor: busy || !draft.trim() ? "not-allowed" : "pointer",
          }}
        >
          {busy ? "…" : "Send"}
        </button>
      </div>
    </div>
  );
}

const linkBtn: React.CSSProperties = {
  background: "none", border: "none", padding: 0,
  fontSize: 11.5, color: "var(--accent)", cursor: "pointer", fontWeight: 600,
};
