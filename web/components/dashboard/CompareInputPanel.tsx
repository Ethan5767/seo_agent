"use client";

import React from "react";

/**
 * The input panel at the top of a search tool (Domain Overview, keyword tools,
 * Backlinks, the comparison tools).
 *
 * Every input here is one the tool really reads (operator, 2026-09-15):
 *   - the DOMAIN is the project's, shown read-only. One project is one domain;
 *     a box that took any domain created or switched projects behind the page.
 *   - a COMPETITOR box appears only where the tool compares, with exactly as
 *     many slots as the tool uses (Keyword Gap reads one; Compare Domains and
 *     Backlink Gap read up to three). Empty means "use the ones DataForSEO finds".
 *   - a KEYWORD box appears on the keyword tools, prefilled from the project.
 *   - a paid tool names its price on the button's line, before the click.
 */
export type RunInput = { competitors: string[]; keywords: string[] };

export function CompareInputPanel({
  domain,
  label,
  subtitle,
  verb,
  object,
  busy,
  error,
  price,
  blocked,
  competitorSlots = 0,
  defaultCompetitors = [],
  keywordInput = false,
  keywordLimit,
  defaultKeywords = [],
  hasProjects = true,
  onCreateProject,
  onEditProject,
  onRun,
}: {
  /** The open project's domain. Read-only: tools check the project's site. */
  domain: string | null | undefined;
  label: string;
  subtitle?: string;
  verb: string;
  object: string;
  busy?: boolean;
  error?: string | null;
  /** e.g. "Compare Domains (DataForSEO) ~$0.05". Null when the run is free. */
  price?: string | null;
  /** Why this tool cannot run right now ("" or undefined when it can). */
  blocked?: string;
  /** How many competitors the tool reads: 0 (no box), 1, or 3. */
  competitorSlots?: 0 | 1 | 3;
  defaultCompetitors?: string[];
  keywordInput?: boolean;
  /** The tool reads only the first N keywords (SERP Positions reads 5). */
  keywordLimit?: number;
  defaultKeywords?: string[];
  hasProjects?: boolean;
  onCreateProject?: () => void;
  onEditProject?: () => void;
  onRun: (input: RunInput) => void;
}) {
  const [competitors, setCompetitors] = React.useState<string[]>([]);
  const [keywords, setKeywords] = React.useState("");

  // Prefill from the project, and again when the project changes.
  const compKey = defaultCompetitors.join("|");
  const kwKey = defaultKeywords.join("|");
  // One competitor row to start; "+ Add competitor" reveals the next, up to
  // what the tool reads (operator, 2026-09-15: not all at once).
  React.useEffect(() => {
    setCompetitors(competitorSlots ? [defaultCompetitors[0] ?? ""] : []);
  }, [compKey, competitorSlots, domain]); // eslint-disable-line react-hooks/exhaustive-deps
  const addCompetitor = () =>
    setCompetitors((prev) => (prev.length < competitorSlots ? [...prev, defaultCompetitors[prev.length] ?? ""] : prev));
  const removeCompetitor = (i: number) => setCompetitors((prev) => prev.filter((_, j) => j !== i));
  React.useEffect(() => {
    setKeywords(defaultKeywords.join(", "));
  }, [kwKey, domain]); // eslint-disable-line react-hooks/exhaustive-deps

  const cleanDomain = (s: string) => s.trim().replace(/^https?:\/\//i, "").replace(/\/.*$/, "").replace(/^www\./i, "").toLowerCase();
  const isDomain = (s: string) => /^[^\s]+\.[^\s]+$/.test(s);
  const you = cleanDomain(domain || "");
  const typedCompetitors = competitors.map(cleanDomain).filter(Boolean);
  const badCompetitor = typedCompetitors.find((c) => !isDomain(c) || c === you);
  const keywordList = keywords.split(/[,\n]/).map((k) => k.trim()).filter(Boolean);
  const needsKeywords = keywordInput && keywordList.length === 0;
  const ready = Boolean(you) && !busy && !blocked && !badCompetitor && !needsKeywords;

  const run = () => {
    if (!ready) return;
    onRun({ competitors: [...new Set(typedCompetitors)], keywords: keywordLimit ? keywordList.slice(0, keywordLimit) : keywordList });
  };
  const onEnter = (e: React.KeyboardEvent) => { if (e.key === "Enter") run(); };

  if (!hasProjects || !you) {
    return (
      <section aria-label={label} style={wrap}>
        <div style={card}>
          <h1 style={title}>{label}</h1>
          <p style={{ ...sub, marginTop: "var(--space-3)" }}>
            {hasProjects ? "Select a project first: a tool checks the project's own domain." : "Create a project first: a tool checks the project's own domain."}
          </p>
          {!hasProjects && onCreateProject && (
            <div style={{ textAlign: "center", marginTop: "var(--space-4)" }}>
              <button type="button" className="btn-primary" onClick={onCreateProject} style={{ height: 40, padding: "0 var(--space-5)" }}>Create a project</button>
            </div>
          )}
        </div>
      </section>
    );
  }

  return (
    <section aria-label={label} style={wrap}>
      <div style={card}>
        <h1 style={title}>{label}</h1>
        {subtitle && <p style={sub}>{subtitle}</p>}

        <div style={{ margin: "var(--space-6) auto 0", maxWidth: 620, display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
          {/* The project's domain: read-only. */}
          <div style={fieldRow}>
            <span style={{ ...tag, background: "var(--accent-tint)", color: "var(--accent)" }}>You</span>
            <div aria-label="Project domain" style={{ ...input, display: "flex", alignItems: "center", background: "var(--surface-2)", color: "var(--ink)" }}>
              {you}
            </div>
            {onEditProject && (
              <button type="button" onClick={onEditProject} style={linkBtn} title="The domain belongs to the project. Edit the project to change it.">
                Edit project
              </button>
            )}
          </div>

          {competitors.map((c, i) => (
            <div key={i} style={fieldRow}>
              <span style={{ ...tag, background: "var(--surface-3)", color: "var(--ink-muted)" }}>{competitors.length === 1 ? "vs" : `vs ${i + 1}`}</span>
              <input
                type="text" inputMode="url" value={c} disabled={busy}
                placeholder="Competitor domain (optional)"
                aria-label={`Competitor domain ${i + 1}`}
                onChange={(e) => setCompetitors((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                onKeyDown={onEnter} style={input}
              />
              {i > 0 && (
                <button type="button" onClick={() => removeCompetitor(i)} disabled={busy} aria-label={`Remove competitor ${i + 1}`} style={removeBtn}>×</button>
              )}
            </div>
          ))}
          {competitorSlots > 1 && competitors.length < competitorSlots && (
            <button type="button" onClick={addCompetitor} disabled={busy} style={{ ...linkBtn, alignSelf: "flex-start", marginLeft: 56 }}>
              + Add competitor
            </button>
          )}

          {keywordInput && (
            <div style={{ ...fieldRow, alignItems: "flex-start" }}>
              <span style={{ ...tag, background: "var(--surface-3)", color: "var(--ink-muted)", marginTop: 10 }}>Terms</span>
              <textarea
                value={keywords} disabled={busy} rows={2}
                placeholder="Keywords, separated by commas"
                aria-label="Keywords"
                onChange={(e) => setKeywords(e.target.value)}
                style={{ ...input, height: "auto", minHeight: 44, padding: "var(--space-2) var(--space-4)", resize: "vertical", fontFamily: "inherit" }}
              />
            </div>
          )}

          <button
            type="button" className="btn-primary" onClick={run} disabled={!ready}
            style={{ alignSelf: "center", height: 44, padding: "0 var(--space-6)", fontSize: "var(--text-base)", whiteSpace: "nowrap", ...(ready ? {} : { opacity: 0.55, cursor: "not-allowed", boxShadow: "none" }) }}
          >
            {busy ? "Working…" : `${verb} ${object}`}
          </button>
        </div>

        <p style={hint}>
          {price ? `Paid: ${price}.` : "Free."}
          {competitorSlots === 1 && " Leave the competitor empty to use the top one DataForSEO finds."}
          {competitorSlots === 3 && " Add up to 3 competitors, or leave them empty to use the top ones DataForSEO finds."}
          {keywordInput && ` Prefilled from the project's keywords${keywordLimit ? `; the first ${keywordLimit} are checked` : ""}.`}
        </p>

        {badCompetitor && (
          <p role="alert" style={{ ...hint, color: "var(--bad)" }}>
            {badCompetitor === you ? "A competitor cannot be your own domain." : `"${badCompetitor}" is not a domain.`}
          </p>
        )}
        {needsKeywords && <p style={{ ...hint, color: "var(--warn)" }}>Enter at least one keyword.</p>}
        {blocked && (
          <div role="note" style={note}>
            <b>Cannot run:</b> {blocked}
          </div>
        )}
        {error && !busy && (
          <div role="alert" style={{ ...note, color: "var(--bad)", background: "var(--bad-tint)", borderColor: "var(--bad-border)" }}>
            <b>It did not run.</b> {error}
          </div>
        )}
      </div>
    </section>
  );
}

const wrap: React.CSSProperties = { display: "flex", justifyContent: "center", marginBottom: "var(--space-6)" };
const card: React.CSSProperties = {
  width: "100%", maxWidth: 760, background: "var(--surface)", border: "1px solid var(--border)",
  borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-sm)", padding: "var(--space-7) var(--space-6) var(--space-6)",
};
const title: React.CSSProperties = { textAlign: "center", fontSize: "var(--text-2xl)", fontWeight: 750, color: "var(--ink)", margin: 0, letterSpacing: "-0.02em" };
const sub: React.CSSProperties = { textAlign: "center", fontSize: "var(--text-md)", color: "var(--ink-muted)", margin: "var(--space-2) auto 0", maxWidth: "52ch", lineHeight: "var(--leading-snug)" };
const fieldRow: React.CSSProperties = { display: "flex", alignItems: "center", gap: "var(--space-2)" };
const tag: React.CSSProperties = {
  flexShrink: 0, width: 48, textAlign: "center", padding: "6px 0", borderRadius: "var(--radius-sm)",
  fontSize: "var(--text-xs)", fontWeight: 700, letterSpacing: "-0.01em",
};
const input: React.CSSProperties = {
  flex: 1, minWidth: 0, height: 44, padding: "0 var(--space-4)", borderRadius: "var(--radius-md)",
  border: "1px solid var(--border-strong)", background: "var(--surface)", color: "var(--ink)", fontSize: "var(--text-md)",
};
const linkBtn: React.CSSProperties = {
  flexShrink: 0, border: 0, background: "transparent", color: "var(--accent)", fontSize: "var(--text-sm)", fontWeight: 600, cursor: "pointer", padding: 0,
};
const removeBtn: React.CSSProperties = {
  flexShrink: 0, width: 30, height: 30, display: "inline-flex", alignItems: "center", justifyContent: "center",
  border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", background: "var(--surface)",
  color: "var(--ink-muted)", fontSize: 18, lineHeight: 1, cursor: "pointer",
};
const hint: React.CSSProperties = {
  textAlign: "center", fontSize: "var(--text-xs)", color: "var(--ink-faint)",
  margin: "var(--space-4) auto 0", maxWidth: "60ch", lineHeight: "var(--leading-snug)",
};
const note: React.CSSProperties = {
  margin: "var(--space-4) auto 0", maxWidth: 620, fontSize: "var(--text-sm)", lineHeight: "var(--leading-snug)",
  color: "var(--warn)", background: "var(--warn-tint)", border: "1px solid var(--warn-border)", borderRadius: "var(--radius-sm)", padding: "var(--space-2) var(--space-3)",
};
