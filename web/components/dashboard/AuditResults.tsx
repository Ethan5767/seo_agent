"use client";

import React from "react";
import { Gauge, fillFor } from "@/components/dashboard/Charts";
import {
  scoreBreakdown, rankedIssues, crawledPages, CATEGORIES,
  type AuditIssue, type CategoryId, type CrawledPage, type Report,
} from "@/lib/auditBreakdown";

/**
 * The on-page audit's results, as blocks the Dashboard and Site Audit share:
 * the score and where its points went, the issues ranked by impact, and the
 * pages the crawl read. Every number comes from lib/auditBreakdown, which reads
 * the report's own rows.
 */

const fmtPts = (n: number) => (n === 0 ? "0" : n < 0.05 ? "<0.1" : n.toFixed(1));
const pathOf = (url: string) => {
  try {
    const u = new URL(url);
    return (u.pathname + u.search) || "/";
  } catch {
    return url;
  }
};

export function SeverityMark({ severity }: { severity: "error" | "warn" | "ok" | string }) {
  const map: Record<string, { glyph: string; word: string; cls: string }> = {
    error: { glyph: "✕", word: "Error", cls: "sev sev--error" },
    warn: { glyph: "!", word: "Warning", cls: "sev sev--warn" },
    ok: { glyph: "✓", word: "Passed", cls: "sev sev--ok" },
  };
  const m = map[severity] ?? { glyph: "i", word: "Notice", cls: "sev" };
  return (
    <span className={m.cls}>
      <span className="sev__glyph" aria-hidden="true">{m.glyph}</span>
      {m.word}
    </span>
  );
}

function EmptyAudit({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="audit-empty">
      <p>{children}</p>
      {action}
    </div>
  );
}

/* ── Score and why ─────────────────────────────────────────────────────── */

export function ScoreWhy({ report, onRun }: { report: Report; onRun?: () => void }) {
  const b = scoreBreakdown(report);
  if (b.score === null) {
    return (
      <EmptyAudit action={onRun ? <button type="button" className="btn btn--primary" onClick={onRun}>Run Audit</button> : undefined}>
        No current server-side Site Health score. Run a full on-page audit to score this site and see where the weight went.
      </EmptyAudit>
    );
  }
  const failing = b.error + b.warn;
  const lost = Number((b.weighted as any)?.lost_weight ?? 0);
  const maxLoss = Math.max(...b.categories.map((c) => c.pointsLost), 0.0001);
  return (
    <div className="score-why">
      <div className="score-why__head">
        <Gauge value={b.score} size={148} />
        <div className="score-why__summary">
          <p className="score-why__lede">
            <b>{b.ok}</b> of <b>{b.graded}</b> checks pass, so Site Health is <b>{b.score}</b>.
          </p>
          <p className="score-why__rule">
            Severity-weighted: critical issues count more than high, medium, and low issues.
          </p>
          <ul className="score-why__counts">
            <li><SeverityMark severity="error" /> <b>{b.error}</b></li>
            <li><SeverityMark severity="warn" /> <b>{b.warn}</b></li>
            <li><SeverityMark severity="ok" /> <b>{b.ok}</b></li>
            {b.info > 0 && <li className="score-why__muted">{b.info} notices, not scored</li>}
          </ul>
        </div>
      </div>

      <div className="table-scroll">
        <table className="data-table">
          <caption className="data-table__caption">Where {fmtPts(lost)} weighted checks were lost</caption>
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col" className="col-bar">Pass rate</th>
              <th scope="col" className="num">Failing</th>
              <th scope="col" className="num">Weight lost</th>
            </tr>
          </thead>
          <tbody>
            {b.categories.map((c) => (
              <tr key={c.id}>
                <th scope="row">{c.label}</th>
                <td className="col-bar">
                  <span className="meter" aria-hidden="true">
                    <span className="meter__fill" style={{ width: `${c.passRate ?? 0}%`, background: fillFor(c.passRate) }} />
                  </span>
                  <span className="meter__value">{c.passRate}%</span>
                  <span className="meter__sub">{c.ok} of {c.graded}</span>
                </td>
                <td className="num">
                  {c.failing === 0 ? <span className="muted">None</span> : (
                    <span className="failing">
                      {c.errors > 0 && <span className="failing__err">{c.errors} {c.errors === 1 ? "error" : "errors"}</span>}
                      {c.warnings > 0 && <span className="failing__warn">{c.warnings} {c.warnings === 1 ? "warning" : "warnings"}</span>}
                    </span>
                  )}
                </td>
                <td className="num">
                  <span className="loss">
                    <span className="loss__bar" aria-hidden="true" style={{ width: `${(c.pointsLost / maxLoss) * 100}%` }} />
                    <span className="loss__value">{c.pointsLost ? `−${fmtPts(c.pointsLost)}` : "0"}</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row">Total</th>
              <td className="col-bar muted">{b.graded} checks graded</td>
              <td className="num">{failing}</td>
              <td className="num"><b>−{fmtPts(lost)}</b> <span className="muted">(server score {b.score})</span></td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

/* ── Issues ────────────────────────────────────────────────────────────── */

export function IssuesTable({
  report, limit, onSeeAll, onRun,
}: {
  report: Report;
  /** Show only the top N, with a link to the full list. */
  limit?: number;
  onSeeAll?: () => void;
  onRun?: () => void;
}) {
  const all = rankedIssues(report);
  const [sev, setSev] = React.useState<"all" | "error" | "warn">("all");
  const [cat, setCat] = React.useState<CategoryId | "all">("all");
  const [q, setQ] = React.useState("");
  const [open, setOpen] = React.useState<string | null>(null);

  if (!all.length) {
    const s = scoreBreakdown(report);
    return (
      <EmptyAudit action={s.graded === 0 && onRun ? <button type="button" className="btn btn--primary" onClick={onRun}>Run Audit</button> : undefined}>
        {s.graded === 0 ? "No on-page audit yet, so there are no issues to rank." : `No failing checks. All ${s.graded} graded checks pass.`}
      </EmptyAudit>
    );
  }

  const filtered = limit ? all : all.filter((i) =>
    (sev === "all" || i.severity === sev)
    && (cat === "all" || i.category === cat)
    && (!q || `${i.what} ${i.code} ${i.detail}`.toLowerCase().includes(q.toLowerCase())));
  const shown = limit ? filtered.slice(0, limit) : filtered;
  const cats = CATEGORIES.filter((c) => all.some((i) => i.category === c.id));

  return (
    <div className="issues">
      {!limit && (
        <div className="toolbar" role="group" aria-label="Filter issues">
          <div className="segmented">
            {([["all", `All ${all.length}`], ["error", `Errors ${all.filter((i) => i.severity === "error").length}`], ["warn", `Warnings ${all.filter((i) => i.severity === "warn").length}`]] as const).map(([id, label]) => (
              <button key={id} type="button" aria-pressed={sev === id} onClick={() => setSev(id)}>{label}</button>
            ))}
          </div>
          <label className="field">
            <span className="visually-hidden">Category</span>
            <select value={cat} onChange={(e) => setCat(e.target.value as CategoryId | "all")}>
              <option value="all">All categories</option>
              {cats.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </label>
          <label className="field field--grow">
            <span className="visually-hidden">Search issues</span>
            <input type="search" placeholder="Search issues" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>
      )}

      <div className="table-scroll">
        <table className="data-table data-table--rows">
          <thead>
            <tr>
              <th scope="col">Issue</th>
              <th scope="col">Severity</th>
              <th scope="col" className="hide-narrow">Category</th>
              <th scope="col" className="num">Pages</th>
              <th scope="col" className="num">Points</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((i) => <IssueRow key={i.code + i.detail} issue={i} open={open === i.code + i.detail} onToggle={() => setOpen(open === i.code + i.detail ? null : i.code + i.detail)} />)}
            {shown.length === 0 && (
              <tr><td colSpan={5} className="muted" style={{ textAlign: "center", padding: "var(--space-5)" }}>
                No issue matches these filters. <button type="button" className="link" onClick={() => { setSev("all"); setCat("all"); setQ(""); }}>Clear filters</button>
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {limit && all.length > limit && onSeeAll && (
        <button type="button" className="see-all" onClick={onSeeAll}>See all {all.length} issues <span aria-hidden="true">→</span></button>
      )}
    </div>
  );
}

function IssueRow({ issue: i, open, onToggle }: { issue: AuditIssue; open: boolean; onToggle: () => void }) {
  const id = `issue-${i.code.replace(/[^a-z0-9]/gi, "-")}-${i.detail.length}`;
  return (
    <>
      <tr className={open ? "is-open" : undefined}>
        <td>
          <button type="button" className="row-toggle" aria-expanded={open} aria-controls={id} onClick={onToggle}>
            <span className="row-toggle__chev" aria-hidden="true">›</span>
            <span className="row-toggle__text">{i.what}</span>
          </button>
          {i.detail && !i.pageCount && <div className="cell-sub">{i.detail}</div>}
        </td>
        <td><SeverityMark severity={i.severity} /></td>
        <td className="hide-narrow muted">{CATEGORIES.find((c) => c.id === i.category)?.label ?? "Uncategorised"}</td>
        <td className="num">{i.pageCount ?? <span className="muted" title="Found once for the whole site">Site</span>}</td>
        <td className="num">−{fmtPts(i.points)}</td>
      </tr>
      {open && (
        <tr className="detail-row" id={id}>
          <td colSpan={5}>
            <div className="detail">
              {(i.effort || i.timeline || i.optional) && (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                  {i.effort && <span className="chip">Effort: {i.effort}</span>}
                  {i.timeline && <span className="chip">Timeline: {i.timeline}</span>}
                  {i.optional && <span className="chip">Optional — a business choice</span>}
                </div>
              )}
              {/* Client-register plain-language line leads; falls back to why. */}
              {(i.plain || i.why) && <div><h4>What this means</h4><p>{i.plain || i.why}</p></div>}
              {i.impact && <div><h4>Why it matters</h4><p>{i.impact}</p></div>}
              {/* Implementer register: ordered steps, else the one-line fix. */}
              {i.steps && i.steps.length > 0 ? (
                <div><h4>How to fix</h4>
                  <ol style={{ margin: 0, paddingLeft: "1.2rem", lineHeight: 1.6 }}>
                    {i.steps.map((s, n) => <li key={n}>{s}</li>)}
                  </ol>
                </div>
              ) : (i.fix && i.fix !== "passing" && <div><h4>How to fix</h4><p>{i.fix}</p></div>)}
              {i.snippet && (
                <div><h4>Paste this</h4>
                  <pre style={{ margin: 0, padding: "10px 12px", borderRadius: 6, overflowX: "auto",
                                background: "var(--ink)", color: "var(--border)", fontSize: 12, lineHeight: 1.5,
                                whiteSpace: "pre-wrap", wordBreak: "break-word",
                                fontFamily: "ui-monospace, SFMono-Regular, monospace" }}>{i.snippet}</pre>
                </div>
              )}
              {i.verify && <div><h4>Confirm it worked</h4><p>{i.verify}</p></div>}
              {i.pages.length > 0 && (
                <div>
                  <h4>Pages ({i.pages.length})</h4>
                  <ul className="page-list">
                    {i.pages.map((p) => <li key={p}><a href={p} target="_blank" rel="noreferrer">{pathOf(p)}</a></li>)}
                  </ul>
                </div>
              )}
              <p className="detail__code">Check <code>{i.code}</code></p>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/* ── Pages ─────────────────────────────────────────────────────────────── */

export function PagesTable({
  report, limit, onSeeAll, onRun,
}: {
  report: Report;
  limit?: number;
  onSeeAll?: () => void;
  onRun?: () => void;
}) {
  const pages = crawledPages(report);
  const [open, setOpen] = React.useState<string | null>(null);
  if (!pages) {
    const graded = scoreBreakdown(report).graded;
    return (
      <EmptyAudit action={onRun ? <button type="button" className="btn btn--secondary" onClick={onRun}>Run Audit</button> : undefined}>
        {graded ? "This scan was saved before page summaries existed. Run the audit again to list every page it reads." : "No on-page audit yet. Run one to list the pages it crawls."}
      </EmptyAudit>
    );
  }
  const whatOf = new Map<string, string>();
  for (const i of rankedIssues(report)) whatOf.set(i.code, i.what);
  const shown = limit ? pages.slice(0, limit) : pages;
  const wide = !limit;

  return (
    <div className="pages">
      <div className="table-scroll">
        <table className="data-table data-table--rows">
          <thead>
            <tr>
              <th scope="col">Page</th>
              <th scope="col" className="num">Status</th>
              {wide && <th scope="col" className="num hide-narrow">Words</th>}
              {wide && <th scope="col" className="num hide-narrow">H1</th>}
              {wide && <th scope="col" className="num hide-narrow">Links in</th>}
              <th scope="col" className="num">Errors</th>
              <th scope="col" className="num">Warnings</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((p) => <PageRow key={p.url} page={p} wide={wide} open={open === p.url} onToggle={() => setOpen(open === p.url ? null : p.url)} whatOf={whatOf} />)}
          </tbody>
        </table>
      </div>
      {limit && pages.length > limit && onSeeAll && (
        <button type="button" className="see-all" onClick={onSeeAll}>See all {pages.length} pages <span aria-hidden="true">→</span></button>
      )}
    </div>
  );
}

function PageRow({ page: p, wide, open, onToggle, whatOf }: {
  page: CrawledPage; wide: boolean; open: boolean; onToggle: () => void; whatOf: Map<string, string>;
}) {
  const issues = Object.entries(p.issues).sort((a, b) => (a[1] === b[1] ? 0 : a[1] === "error" ? -1 : 1));
  const cols = wide ? 7 : 4;
  const bad = p.status !== 200;
  return (
    <>
      <tr className={open ? "is-open" : undefined}>
        <td>
          <button type="button" className="row-toggle" aria-expanded={open} onClick={onToggle} disabled={!issues.length && !wide}>
            <span className="row-toggle__chev" aria-hidden="true">{issues.length || wide ? "›" : ""}</span>
            <span className="row-toggle__text">{pathOf(p.url)}</span>
          </button>
          <div className="cell-sub">{p.title || <span className="bad-text">No title</span>}</div>
        </td>
        <td className="num">{bad ? <span className="bad-text">{p.status || "Failed"}</span> : p.status}</td>
        {wide && <td className="num hide-narrow">{p.words.toLocaleString()}</td>}
        {wide && <td className="num hide-narrow">{p.h1_count === 1 ? 1 : <span className="warn-text">{p.h1_count}</span>}</td>}
        {wide && <td className="num hide-narrow">{p.links_in}</td>}
        <td className="num">{p.errors ? <span className="bad-text">{p.errors}</span> : <span className="muted">0</span>}</td>
        <td className="num">{p.warnings ? <span className="warn-text">{p.warnings}</span> : <span className="muted">0</span>}</td>
      </tr>
      {open && (
        <tr className="detail-row">
          <td colSpan={cols}>
            <div className="detail">
              <div>
                <h4>Page</h4>
                <p><a href={p.url} target="_blank" rel="noreferrer">{p.url}</a></p>
                <p className="muted">
                  {p.has_description ? "Has a meta description" : "No meta description"}, {p.h1_count} H1, {p.words.toLocaleString()} words, {p.links_out} internal links out, {p.links_in} in from crawled pages.
                </p>
              </div>
              <div>
                <h4>Failing checks on this page ({issues.length})</h4>
                {issues.length ? (
                  <ul className="issue-list">
                    {issues.map(([code, sev]) => <li key={code}><SeverityMark severity={sev} /> {whatOf.get(code) ?? code}</li>)}
                  </ul>
                ) : <p className="muted">None. Site-wide checks such as the sitemap are listed under Issues.</p>}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
