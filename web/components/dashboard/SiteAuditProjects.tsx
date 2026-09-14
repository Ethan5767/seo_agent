"use client";

import React from "react";
import { AUDIT_THEMES, delta, summarizeAudit, type AuditSummary, type Share } from "@/lib/auditThemes";

type Project = { id: string; business?: string | null; domain?: string | null; website?: string | null };
type Loaded = { summary: AuditSummary; previous: AuditSummary | null; at: string | null };

/**
 * Site Audit landing: every project as one row, Semrush-style. Click a project
 * to open its audit. Scores come from each project's saved scans
 * (`lib/auditThemes.ts`); nothing here is estimated.
 */
export function SiteAuditProjects({
  projects,
  loadTwo,
  onOpen,
  onCreate,
}: {
  projects: Project[];
  loadTwo: (clientId: string) => Promise<{ current: Record<string, unknown> | null; previous: Record<string, unknown> | null; at: string | null }>;
  onOpen: (p: Project) => void;
  onCreate?: () => void;
}) {
  const [query, setQuery] = React.useState("");
  const [data, setData] = React.useState<Record<string, Loaded | "loading" | "none">>({});
  const [page, setPage] = React.useState(0);
  const [perPage, setPerPage] = React.useState(10);

  React.useEffect(() => {
    let alive = true;
    for (const p of projects) {
      if (data[p.id]) continue;
      setData((d) => ({ ...d, [p.id]: "loading" }));
      loadTwo(p.id)
        .then(({ current, previous, at }) => {
          if (!alive) return;
          setData((d) => ({
            ...d,
            [p.id]: current ? { summary: summarizeAudit(current), previous: previous ? summarizeAudit(previous) : null, at } : "none",
          }));
        })
        .catch(() => alive && setData((d) => ({ ...d, [p.id]: "none" })));
    }
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projects]);

  const q = query.trim().toLowerCase();
  const filtered = projects.filter((p) =>
    !q || [p.business, p.domain, p.website].some((v) => String(v || "").toLowerCase().includes(q)));
  const pages = Math.max(1, Math.ceil(filtered.length / perPage));
  const safe = Math.min(page, pages - 1);
  const visible = filtered.slice(safe * perPage, safe * perPage + perPage);

  return (
    <section className="sap">
      <style>{CSS}</style>
      <h1 className="sap-title">Site Audit</h1>
      <div className="sap-card">
        <div className="sap-bar">
          <input className="sap-search" placeholder="Project name or domain" value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(0); }} aria-label="Search projects" />
          {onCreate && <button type="button" className="sap-create" onClick={onCreate}>+ Create project</button>}
        </div>
        <div className="sap-scroll">
          <table className="sap-table">
            <thead>
              <tr>
                <th className="sap-sticky">Project</th>
                <th>Last Update</th>
                <th>Pages Crawled</th>
                <th>Site Health</th>
                <th>Errors</th>
                <th>Warnings</th>
                {AUDIT_THEMES.map((t) => <th key={t.id}>{t.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 && (
                <tr><td colSpan={6 + AUDIT_THEMES.length} className="sap-empty">
                  {projects.length ? "No project matches that search." : "No projects yet. Create one to run its first audit."}
                </td></tr>
              )}
              {visible.map((p) => {
                const d = data[p.id];
                const loaded = d && d !== "loading" && d !== "none" ? d : null;
                const s = loaded?.summary;
                const prev = loaded?.previous ?? null;
                return (
                  <tr key={p.id}>
                    <td className="sap-sticky">
                      <button type="button" className="sap-link" onClick={() => onOpen(p)}>
                        {p.domain || hostOf(p.website) || p.business || "Untitled project"}
                      </button>
                      <div className="sap-sub">{p.business || ""}</div>
                    </td>
                    {d === "loading" || !d ? (
                      <td colSpan={5 + AUDIT_THEMES.length} className="sap-muted">Loading…</td>
                    ) : d === "none" ? (
                      <td colSpan={5 + AUDIT_THEMES.length} className="sap-muted">
                        Not scanned yet. <button type="button" className="sap-link" onClick={() => onOpen(p)}>Run the first audit</button>
                      </td>
                    ) : (
                      <>
                        <td>{timeAgo(loaded!.at)}</td>
                        <td>{s!.pagesCrawled ?? "—"}</td>
                        <Pct share={s!.health} prev={prev?.health} strong />
                        <Num v={s!.errors} prev={prev?.errors} bad />
                        <Num v={s!.warnings} prev={prev?.warnings} bad />
                        {AUDIT_THEMES.map((t) => <Pct key={t.id} share={s!.themes[t.id]} prev={prev?.themes[t.id]} />)}
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="sap-foot">
          <span>Page</span>
          <button type="button" disabled={safe === 0} onClick={() => setPage(safe - 1)} aria-label="Previous page">‹</button>
          <span>{safe + 1} of {pages}</span>
          <button type="button" disabled={safe >= pages - 1} onClick={() => setPage(safe + 1)} aria-label="Next page">›</button>
          <select value={perPage} onChange={(e) => { setPerPage(Number(e.target.value)); setPage(0); }} aria-label="Rows per page">
            {[10, 25, 50].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>
    </section>
  );
}

function Pct({ share, prev, strong }: { share: Share; prev?: Share; strong?: boolean }) {
  if (share.pct === null) return <td className="sap-muted" title="No check of this kind in the latest scan">Not measured</td>;
  const tone = share.pct >= 90 ? "sap-good" : share.pct >= 70 ? "sap-mid" : "sap-bad";
  return (
    <td title={`${share.passed} of ${share.graded} checks passed`}>
      <div className={`${tone} ${strong ? "sap-strong" : ""}`}>{share.pct}%</div>
      <div className="sap-sub">{delta(share.pct, prev?.pct ?? null, "%")}</div>
    </td>
  );
}

function Num({ v, prev, bad }: { v: number; prev?: number; bad?: boolean }) {
  return (
    <td>
      <div className={bad && v > 0 ? "sap-link-num" : ""}>{v}</div>
      <div className="sap-sub">{delta(v, prev ?? null)}</div>
    </td>
  );
}

function hostOf(url?: string | null): string {
  return String(url || "").replace(/^https?:\/\//i, "").replace(/[/?#].*$/, "").replace(/^www\./i, "");
}

function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  if (s < 604800) return `${Math.round(s / 86400)}d ago`;
  return `${Math.round(s / 604800)}w ago`;
}

const CSS = `
.sap-title{font-size:22px;font-weight:700;color:var(--ink);margin:0 0 14px}
.sap-card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden}
.sap-bar{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:14px 16px;flex-wrap:wrap}
.sap-search{flex:1;max-width:340px;min-width:180px;padding:8px 12px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px}
.sap-create{background:#111827;color:#fff;border:0;border-radius:6px;padding:9px 14px;font-size:13px;font-weight:600;cursor:pointer}
.sap-scroll{overflow-x:auto}
.sap-table{width:100%;border-collapse:collapse;font-size:13px;min-width:1100px}
.sap-table th{background:#f8fafc;color:#475569;font-weight:600;text-align:right;padding:10px 12px;border-bottom:1px solid #e2e8f0;white-space:nowrap}
.sap-table td{text-align:right;padding:12px;border-bottom:1px solid #f1f5f9;vertical-align:top;white-space:nowrap;font-variant-numeric:tabular-nums}
.sap-table th.sap-sticky,.sap-table td.sap-sticky{text-align:left;position:sticky;left:0;background:#fff;z-index:1;min-width:220px}
.sap-table th.sap-sticky{background:#f8fafc}
.sap-link{background:none;border:0;padding:0;color:#2563eb;font-weight:600;font-size:13px;cursor:pointer;text-align:left}
.sap-link:hover{text-decoration:underline}
.sap-sub{color:#94a3b8;font-size:12px;margin-top:2px}
.sap-muted{color:#94a3b8;text-align:left!important}
.sap-strong{font-weight:700}
.sap-good{color:#2563eb}.sap-mid{color:#d97706}.sap-bad{color:#dc2626}
.sap-link-num{color:#2563eb}
.sap-empty{text-align:center!important;color:#64748b;padding:28px!important}
.sap-foot{display:flex;align-items:center;gap:8px;padding:12px 16px;font-size:13px;color:#334155}
.sap-foot button{border:1px solid #cbd5e1;background:#fff;border-radius:5px;padding:2px 8px;cursor:pointer}
.sap-foot button:disabled{opacity:.4;cursor:default}
.sap-foot select{border:1px solid #cbd5e1;border-radius:5px;padding:3px 6px}
`;
