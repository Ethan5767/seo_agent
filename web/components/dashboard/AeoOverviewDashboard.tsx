"use client";

import React from "react";

/**
 * AI Visibility overview, rendered as charts rather than three tiles and a
 * table. Reads the real AEO findings (severity per signal) and the AI-mentions
 * row — nothing invented. Every block explains a slice of "how ready is this
 * site to be cited by answer engines": the overall readiness ring, the pass
 * rate of each signal group, and the split of passing vs needs-fix signals.
 *
 * Degrades on absence: no rows → an explicit "not measured" state, never a
 * green ring over zero measurements (B-094).
 */

interface CitationMetrics {
  mentions: number;
  cited: boolean;
  engines: Array<{ name: string; count: number }>;
  sources: Array<{ domain: string; count: number }>;
}
interface Row { code?: string; what?: string; severity?: string; detail?: string; fix?: string; metrics?: CitationMetrics }

const GROUPS: { key: string; label: string; match: (code: string, what: string) => boolean }[] = [
  { key: "answer", label: "Answer Readiness", match: (c) => c.includes("answer") || c.includes("statistics") || c.includes("data_tables") || c.includes("no_answer") },
  { key: "crawler", label: "Crawler Access", match: (c) => c.includes("crawler") || c.includes("robots") },
  { key: "citation", label: "Citation Signals", match: (c) => c.includes("citation") || c.includes("author") },
];

export function AeoOverviewDashboard({ aeoRows, aiRows }: { aeoRows: Row[]; aiRows: Row[] }) {
  const measured = aeoRows.length > 0;
  const passing = aeoRows.filter((r) => r.severity === "ok").length;
  const needsFix = aeoRows.filter((r) => r.severity === "warn" || r.severity === "error").length;
  const score = measured ? Math.round((passing / aeoRows.length) * 100) : 0;

  const llm = aiRows.find((r) => r.code === "dfs.llm_mentions" || (r.what || "").toLowerCase().includes("cited"));
  const mentions = llm?.detail || (llm?.severity === "ok" ? "Cited" : "0");

  const groups = GROUPS.map((g) => {
    const rows = aeoRows.filter((r) => g.match((r.code || "").toLowerCase(), (r.what || "").toLowerCase()));
    const ok = rows.filter((r) => r.severity === "ok").length;
    return { label: g.label, total: rows.length, ok, pct: rows.length ? Math.round((ok / rows.length) * 100) : null };
  }).filter((g) => g.total > 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)", marginBottom: "var(--space-5)" }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 16rem), 1fr))", gap: "var(--space-4)", alignItems: "stretch" }}>
        {/* Overall readiness ring. */}
        <section style={{ ...panel, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: "var(--space-2)" }}>
          <Ring score={score} measured={measured} />
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: "var(--ink)" }}>AI Readiness</div>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)" }}>
            {measured ? `${passing} of ${aeoRows.length} signals passing` : "Not measured yet"}
          </div>
        </section>

        {/* Signal-group pass rates. */}
        <section style={panel}>
          <h2 style={panelTitle}>Readiness by Signal Group</h2>
          {groups.length ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)", marginTop: "var(--space-4)" }}>
              {groups.map((g) => (
                <div key={g.label} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                  <span style={{ width: "clamp(6rem, 30%, 9rem)", fontSize: "var(--text-sm)", color: "var(--ink-body)", fontWeight: 600, flexShrink: 0 }}>{g.label}</span>
                  <div style={{ flex: 1, height: 12, background: "var(--surface-3)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
                    <div style={{ width: `${g.pct ?? 0}%`, height: "100%", background: barColor(g.pct), borderRadius: "var(--radius-full)", transition: "width var(--dur) var(--ease)" }} />
                  </div>
                  <span style={{ width: "5.5rem", textAlign: "right", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--ink)", flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
                    {g.pct == null ? "—" : `${g.pct}% · ${g.ok}/${g.total}`}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)", marginTop: "var(--space-3)" }}>Run an AI Visibility scan to populate this.</p>
          )}
        </section>
      </div>

      {/* Headline counts. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "var(--space-3)" }}>
        <Stat label="Signals passing" value={measured ? String(passing) : "—"} tone="var(--ok)" />
        <Stat label="Needs fix" value={measured ? String(needsFix) : "—"} tone={needsFix ? "var(--warn)" : "var(--ink)"} />
        <Stat label="AI engine mentions" value={llm?.metrics ? String(llm.metrics.mentions) : String(mentions)} tone={llm?.severity === "ok" ? "var(--ok)" : "var(--ink)"} />
        <Stat label="Total signals checked" value={measured ? String(aeoRows.length) : "—"} tone="var(--ink)" />
      </div>

      {/* AI citations, the product's sharpest differentiator: which engines cite
          the brand and, crucially, who gets cited INSTEAD. Only when the mentions
          tool actually ran (the row exists). */}
      {llm && <CitationPanel llm={llm} />}
    </div>
  );
}

/** Per-engine share of voice + who is cited instead, from `dfs.llm_mentions`
 *  metrics. Handles cited / not-cited / cited-but-no-competitors distinctly. */
function CitationPanel({ llm }: { llm: Row }) {
  const m = llm.metrics;
  // No structured metrics (older scan) — fall back to the one-line row, no panel.
  if (!m) return null;

  if (!m.cited || m.mentions === 0) {
    return (
      <section style={panel}>
        <h2 style={panelTitle}>AI Citations</h2>
        <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)", marginTop: "var(--space-3)", lineHeight: 1.6 }}>
          Not cited by AI answer engines yet. {llm.fix || "Publish citable, factual content (clear answers, statistics, entity schema) so engines reference you."}
        </p>
      </section>
    );
  }

  const engineTotal = m.engines.reduce((a, e) => a + e.count, 0) || 1;
  return (
    <section style={panel}>
      <h2 style={panelTitle}>AI Citations</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 18rem), 1fr))", gap: "var(--space-5)", marginTop: "var(--space-4)" }}>
        <div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--ink)", marginBottom: "var(--space-3)" }}>
            Cited {m.mentions} time{m.mentions === 1 ? "" : "s"} across {m.engines.length} engine{m.engines.length === 1 ? "" : "s"}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
            {m.engines.map((e) => (
              <div key={e.name} style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                <span style={{ width: "clamp(5rem, 28%, 8rem)", fontSize: "var(--text-sm)", color: "var(--ink-body)", fontWeight: 600, flexShrink: 0, textTransform: "capitalize" }}>{e.name}</span>
                <div style={{ flex: 1, height: 12, background: "var(--surface-3)", borderRadius: "var(--radius-full)", overflow: "hidden" }}>
                  <div style={{ width: `${Math.round((e.count / engineTotal) * 100)}%`, height: "100%", background: "var(--ok-fill)", borderRadius: "var(--radius-full)" }} />
                </div>
                <span style={{ width: "4.5rem", textAlign: "right", fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--ink)", flexShrink: 0, fontVariantNumeric: "tabular-nums" }}>
                  {e.count} · {Math.round((e.count / engineTotal) * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: "var(--ink)", marginBottom: "var(--space-3)" }}>
            Who gets cited instead
          </div>
          {m.sources.length ? (
            <ol style={{ margin: 0, paddingLeft: "1.2rem", display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
              {m.sources.map((s) => (
                <li key={s.domain} style={{ fontSize: "var(--text-sm)", color: "var(--ink-body)" }}>
                  <span style={{ fontFamily: "ui-monospace, monospace" }}>{s.domain}</span>
                  <span style={{ color: "var(--ink-muted)" }}> · cited {s.count}×</span>
                </li>
              ))}
            </ol>
          ) : (
            <p style={{ fontSize: "var(--text-sm)", color: "var(--ink-muted)", lineHeight: 1.6 }}>
              No competitor domains were captured in the answers that cite you — the answers point to you directly.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

/** An SVG progress ring for the readiness percentage. */
function Ring({ score, measured }: { score: number; measured: boolean }) {
  const size = 132, stroke = 12, r = (size - stroke) / 2, c = 2 * Math.PI * r;
  const pct = measured ? Math.max(0, Math.min(100, score)) : 0;
  const color = !measured ? "var(--border-strong)" : pct >= 70 ? "var(--ok-fill)" : pct >= 40 ? "var(--warn-fill)" : "var(--bad-fill)";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`AI readiness ${measured ? `${pct}%` : "not measured"}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={`${(pct / 100) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="48%" textAnchor="middle" dominantBaseline="middle" style={{ fontSize: 30, fontWeight: 750, fill: "var(--ink)" }}>
        {measured ? `${pct}` : "—"}
      </text>
      {measured && <text x="50%" y="64%" textAnchor="middle" style={{ fontSize: 12, fill: "var(--ink-muted)" }}>/ 100</text>}
    </svg>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div style={panel}>
      <div style={{ fontSize: "var(--text-xs)", color: "var(--ink-muted)", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: "var(--text-2xl)", fontWeight: 750, color: tone, lineHeight: 1.1, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{value}</div>
    </div>
  );
}

function barColor(pct: number | null): string {
  if (pct == null) return "var(--border-strong)";
  return pct >= 70 ? "var(--ok-fill)" : pct >= 40 ? "var(--warn-fill)" : "var(--bad-fill)";
}

const panel: React.CSSProperties = {
  padding: "var(--space-4) var(--space-5)",
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-md)",
};

const panelTitle: React.CSSProperties = {
  fontSize: "var(--text-base)",
  fontWeight: 700,
  color: "var(--ink)",
  margin: 0,
};
