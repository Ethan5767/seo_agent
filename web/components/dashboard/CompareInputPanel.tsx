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
      <section aria-label={label} className="tool-head">
        <div className="tool-head__text">
          <h1 className="tool-head__title">{label}</h1>
          <p className="tool-head__blurb">
            {hasProjects ? "Select a project first: a tool checks the project's own domain." : "Create a project first: a tool checks the project's own domain."}
          </p>
        </div>
        {!hasProjects && onCreateProject && (
          <div className="tool-bar">
            <button type="button" className="btn btn--primary btn--sm" onClick={onCreateProject}>Create a project</button>
          </div>
        )}
      </section>
    );
  }

  return (
    <section aria-label={label} className="tool-head">
      <div className="tool-head__text">
        <h1 className="tool-head__title">{label}</h1>
        {subtitle && <p className="tool-head__blurb">{subtitle}</p>}
      </div>

      <div className="tool-bar">
        <div className="tool-bar__fields">
          {/* The project's domain: read-only. */}
          <div className="tool-field">
            <span className="tool-field__tag tool-field__tag--you">You</span>
            <div aria-label="Project domain" className="tool-field__value">{you}</div>
            {onEditProject && (
              <button type="button" onClick={onEditProject} className="link" title="The domain belongs to the project. Edit the project to change it.">
                Change
              </button>
            )}
          </div>

          {competitors.map((c, i) => (
            <div key={i} className="tool-field">
              <span className="tool-field__tag">{competitors.length === 1 ? "vs" : `vs ${i + 1}`}</span>
              <input
                type="text" inputMode="url" value={c} disabled={busy}
                placeholder="Competitor domain (optional)"
                aria-label={`Competitor domain ${i + 1}`}
                onChange={(e) => setCompetitors((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                onKeyDown={onEnter} className="tool-field__input"
              />
              {i > 0 && (
                <button type="button" onClick={() => removeCompetitor(i)} disabled={busy} aria-label={`Remove competitor ${i + 1}`} className="tool-field__remove">×</button>
              )}
            </div>
          ))}
          {competitorSlots > 1 && competitors.length < competitorSlots && (
            <button type="button" onClick={addCompetitor} disabled={busy} className="link">
              + Add competitor
            </button>
          )}

          {keywordInput && (
            <div className="tool-field tool-field--wide">
              <span className="tool-field__tag">Terms</span>
              <textarea
                value={keywords} disabled={busy} rows={1}
                placeholder="Keywords, separated by commas"
                aria-label="Keywords"
                onChange={(e) => setKeywords(e.target.value)}
                className="tool-field__input tool-field__input--area"
              />
            </div>
          )}
        </div>

        <div className="tool-bar__run">
          <button type="button" className="btn btn--primary btn--sm" onClick={run} disabled={!ready}>
            {busy ? "Working…" : `${verb} ${object}`}
          </button>
          <span className="tool-bar__price">{price ? `Paid: ${price}` : "Free"}</span>
        </div>

        {(competitorSlots > 0 || keywordInput) && (
          <p className="tool-bar__hint">
            {competitorSlots === 1 && "Leave the competitor empty to use the top one DataForSEO finds."}
            {competitorSlots === 3 && "Add up to 3 competitors, or leave them empty to use the top ones DataForSEO finds."}
            {keywordInput && ` Prefilled from the project's keywords${keywordLimit ? `; the first ${keywordLimit} are checked` : ""}.`}
          </p>
        )}

        {badCompetitor && (
          <p role="alert" className="tool-bar__note tool-bar__note--bad">
            {badCompetitor === you ? "A competitor cannot be your own domain." : `"${badCompetitor}" is not a domain.`}
          </p>
        )}
        {needsKeywords && <p className="tool-bar__note tool-bar__note--warn">Enter at least one keyword.</p>}
        {blocked && (
          <div role="note" className="tool-bar__note tool-bar__note--warn">
            <b>Cannot run:</b> {blocked}
          </div>
        )}
        {error && !busy && (
          <div role="alert" className="tool-bar__note tool-bar__note--bad">
            <b>It did not run.</b> {error}
          </div>
        )}
      </div>
    </section>
  );
}
