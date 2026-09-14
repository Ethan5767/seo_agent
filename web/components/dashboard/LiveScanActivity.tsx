"use client";

import React from "react";
import { formatElapsed, outcomeOf, type ActivityLine, type ToolActivity } from "@/lib/scanActivity";

/**
 * What the scan is doing, as it does it.
 *
 * Replaces a bare "Scanning..." button that sat still for up to four minutes
 * while Site Health crawled. Every line is an event the scanner emitted
 * (`lib/scanActivity.ts`): a tool started, a DataForSEO request went out and
 * came back in N ms at $X, DataForSEO's crawl reports K of M pages. The bar
 * moves only when DataForSEO reports a new page count; a step with no count
 * shows a spinner, never an invented percentage.
 */
export function LiveScanActivity({
  tools,
  busy,
  phaseLine,
  catalog,
}: {
  tools: ToolActivity[] | null | undefined;
  busy?: boolean;
  phaseLine?: string;
  catalog?: Array<{ label?: string; checks?: string[] }> | null;
}) {
  const list = Array.isArray(tools) ? tools : [];
  const [now, setNow] = React.useState(() => Date.now());
  const [open, setOpen] = React.useState(true);
  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({});

  React.useEffect(() => {
    if (!busy) return;
    setOpen(true);
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [busy]);

  if (!busy && list.length === 0) return null;

  const started = list.length ? Math.min(...list.map((t) => t.startedAt)) : now;
  const finished = list.length && !busy ? Math.max(...list.map((t) => t.finishedAt ?? t.startedAt)) : now;
  const cost = list.reduce((s, t) => s + (t.cost || 0), 0);
  const done = list.filter((t) => t.state === "done").length;
  const checksFor = (name: string) => catalog?.find((c) => c.label === name)?.checks ?? [];

  return (
    <section className="lsa" aria-live="polite" aria-busy={busy ? "true" : "false"}>
      <style>{CSS}</style>
      <header className="lsa-head">
        <span className={`lsa-dot ${busy ? "lsa-dot--live" : ""}`} aria-hidden />
        <b>{busy ? "Live scan" : "Last scan"}</b>
        <span className="lsa-meta">{formatElapsed((busy ? now : finished) - started)}</span>
        {cost > 0 && <span className="lsa-meta">${cost.toFixed(4)}</span>}
        <span className="lsa-meta">
          {done} of {list.length || "…"} step{list.length === 1 ? "" : "s"} done
        </span>
        {busy && phaseLine && <span className="lsa-phase">{phaseLine}</span>}
        <button type="button" className="lsa-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide" : "Show"} details
        </button>
      </header>

      {open && (
        <ol className="lsa-list">
          {busy && list.length === 0 && (
            <li className="lsa-tool">
              <span className="lsa-spin" aria-hidden />
              <span className="lsa-name">Opening the page and starting the scanner…</span>
            </li>
          )}
          {list.map((t) => {
            const outcome = outcomeOf(t);
            const running = t.state === "running";
            const elapsed = (t.finishedAt ?? now) - t.startedAt;
            const checks = checksFor(t.name);
            const showAll = expanded[t.name];
            const lines = running || showAll ? t.lines.slice(showAll ? 0 : -5) : [];
            return (
              <li key={t.name} className={`lsa-tool lsa-tool--${outcome.kind}`}>
                <div className="lsa-row">
                  {running ? <span className="lsa-spin" aria-hidden /> : <span className="lsa-icon" aria-hidden>{ICON[outcome.kind]}</span>}
                  <span className="lsa-name">{t.name}</span>
                  <span className="lsa-outcome">{running ? currentStep(t) : outcome.label}</span>
                  <span className="lsa-meta">{formatElapsed(elapsed)}</span>
                  {t.cost > 0 && <span className="lsa-meta">${t.cost.toFixed(4)}</span>}
                  {!running && t.lines.length > 0 && (
                    <button type="button" className="lsa-toggle"
                      onClick={() => setExpanded({ ...expanded, [t.name]: !showAll })}>
                      {showAll ? "Hide steps" : `${t.lines.length} step${t.lines.length === 1 ? "" : "s"}`}
                    </button>
                  )}
                </div>

                {t.crawl && (running || showAll) && (
                  <div className="lsa-bar-wrap">
                    <div className="lsa-bar" role="progressbar" aria-valuemin={0} aria-valuemax={t.crawl.max} aria-valuenow={t.crawl.crawled}>
                      <span style={{ width: `${Math.min(100, (100 * t.crawl.crawled) / Math.max(1, t.crawl.max))}%` }} />
                    </div>
                    <span className="lsa-meta">
                      {t.crawl.crawled} / {t.crawl.max} pages crawled{t.crawl.queue ? ` · ${t.crawl.queue} in queue` : ""}
                    </span>
                  </div>
                )}

                {t.page && running && (
                  <div className="lsa-line"><span className="lsa-meta">Page {t.page.n} of up to {t.page.total}</span> <code>{t.page.url}</code></div>
                )}

                {running && checks.length > 0 && (
                  <div className="lsa-checks">
                    {checks.map((c) => <span key={c} className="lsa-chip">{c}</span>)}
                  </div>
                )}

                {lines.length > 0 && (
                  <ul className="lsa-lines">
                    {lines.map((l, i) => <Line key={`${l.at}-${i}`} line={l} start={t.startedAt} />)}
                  </ul>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

function currentStep(t: ToolActivity): string {
  const last = t.lines[t.lines.length - 1];
  if (t.crawl) return `Crawling ${t.crawl.crawled} / ${t.crawl.max} pages`;
  return last ? last.text : "Checking…";
}

function Line({ line, start }: { line: ActivityLine; start: number }) {
  return (
    <li className={`lsa-line lsa-line--${line.phase || "info"}`}>
      <span className="lsa-at">+{formatElapsed(line.at - start)}</span>
      <span>{line.text}</span>
      {typeof line.ms === "number" && <span className="lsa-meta">{(line.ms / 1000).toFixed(1)}s</span>}
      {typeof line.cost === "number" && line.cost > 0 && <span className="lsa-meta">${line.cost.toFixed(4)}</span>}
    </li>
  );
}

const ICON: Record<string, string> = { ok: "✓", issues: "!", "not-run": "–", running: "" };

const CSS = `
.lsa{border:1px solid #e2e8f0;border-radius:8px;background:#fff;margin:0 0 14px;overflow:hidden}
.lsa-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 14px;border-bottom:1px solid #f1f5f9;font-size:13px;color:#1e293b}
.lsa-meta{font-size:12px;color:var(--ink-muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.lsa-phase{font-size:12px;color:#4f46e5;font-weight:600}
.lsa-toggle{margin-left:auto;background:none;border:0;color:#4f46e5;font-size:12px;font-weight:600;cursor:pointer;padding:2px 4px}
.lsa-row .lsa-toggle{margin-left:0}
.lsa-dot{width:8px;height:8px;border-radius:50%;background:#94a3b8;flex:none}
.lsa-dot--live{background:#10b981;animation:lsa-pulse 1.4s ease-out infinite}
.lsa-list{list-style:none;margin:0;padding:4px 0}
.lsa-tool{padding:8px 14px;border-top:1px solid #f8fafc;animation:lsa-in .25s ease-out}
.lsa-tool:first-child{border-top:0}
.lsa-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px}
.lsa-name{font-weight:700;color:#1e293b}
.lsa-outcome{color:#475569;font-size:12.5px;min-width:0;overflow:hidden;text-overflow:ellipsis}
.lsa-tool--issues .lsa-outcome{color:#a86710}
.lsa-tool--not-run .lsa-outcome{color:#92400e}
.lsa-icon{width:18px;height:18px;border-radius:50%;display:grid;place-items:center;font-size:11px;font-weight:800;color:#fff;background:#10b981;flex:none}
.lsa-tool--issues .lsa-icon{background:#d97706}
.lsa-tool--not-run .lsa-icon{background:#94a3b8}
.lsa-spin{width:16px;height:16px;border-radius:50%;border:2px solid #c7d2fe;border-top-color:#4f46e5;animation:lsa-spin .8s linear infinite;flex:none}
.lsa-bar-wrap{display:flex;align-items:center;gap:10px;margin:8px 0 2px 28px}
.lsa-bar{flex:1;max-width:420px;height:6px;border-radius:3px;background:#eef2ff;overflow:hidden}
.lsa-bar span{display:block;height:100%;background:#4f46e5;border-radius:3px;transition:width .5s ease-out}
.lsa-checks{display:flex;flex-wrap:wrap;gap:4px;margin:8px 0 0 28px}
.lsa-chip{font-size:11px;padding:2px 7px;border-radius:10px;background:#f1f5f9;color:#475569;animation:lsa-shimmer 1.6s ease-in-out infinite}
.lsa-lines{list-style:none;margin:6px 0 0 28px;padding:0;font-size:12px;color:#334155}
.lsa-line{display:flex;gap:8px;align-items:baseline;padding:2px 0;animation:lsa-in .2s ease-out}
.lsa-line code{font-size:11.5px;color:#475569;word-break:break-all}
.lsa-at{font-size:11px;color:#94a3b8;font-variant-numeric:tabular-nums;min-width:44px}
.lsa-line--start::before,.lsa-line--progress::before,.lsa-line--posted::before,.lsa-line--fetching::before{content:"";width:6px;height:6px;border-radius:50%;background:#818cf8;flex:none;transform:translateY(-1px)}
.lsa-line--done::before{content:"";width:6px;height:6px;border-radius:50%;background:#10b981;flex:none}
.lsa-line--error::before{content:"";width:6px;height:6px;border-radius:50%;background:#dc2626;flex:none}
.lsa-line--error{color:#991b1b}
@keyframes lsa-spin{to{transform:rotate(360deg)}}
@keyframes lsa-pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.5)}100%{box-shadow:0 0 0 8px rgba(16,185,129,0)}}
@keyframes lsa-in{from{opacity:0;transform:translateY(-2px)}to{opacity:1;transform:none}}
@keyframes lsa-shimmer{0%,100%{opacity:.55}50%{opacity:1}}
@media (prefers-reduced-motion: reduce){.lsa *{animation:none!important;transition:none!important}}
`;
