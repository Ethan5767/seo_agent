"use client";
import { useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { AuthGate } from "./auth";
import { ReaiDashboard } from "./ReaiDashboard";
import { saveClient, updateClient, saveScan, lastTwoScansFindings,
  listClients, scanHistory, getScanReport,
  saveRemediation, remediationHistory,
  type ClientWithStats, type ScanRow, type RemediationRow } from "../lib/db";
import { scoreTrend, sparklinePath } from "../lib/trend";
import { listRepos } from "../lib/github";
import { supabase } from "../lib/supabase";
import { authedFetch } from "@/lib/authedFetch";
import { readScanStream } from "@/lib/scanStream";
import { mergeScanReport } from "@/lib/reportMerge";
import { marketFor } from "@/lib/market";
import { pickScanProject, sameSite } from "@/lib/scanTarget";
import { applyScanEvent, type ToolActivity } from "@/lib/scanActivity";

type Row = { code: string; what: string; why: string; fix: string; detail: string; severity: string; tool?: string; pages?: string[] };
type Audit = {
  seo: Row[]; aeo: Row[]; perf: Row[]; tech: Row[]; site: Row[]; rankings: Row[]; keywords: Row[]; ai: Row[]; source: Row[];
  score: number; counts: Record<string, number>; cost?: number;
};
type Cycle =
  | { model: "A"; brief: string; worklist: unknown[] }
  | { model: "B"; diff: string; decision: { action: string; reason: string } };
type ScanResult = { audit?: Audit; cycle?: Cycle; error?: string; log?: string[] };
type Tool = { name: string; state: string; rows: Row[]; status: string; cost: number };
type CatalogTool = { key: string; label: string; category: string; group: string; cost: string; cost_num: number; checks?: string[]; available?: boolean; unavailable_reason?: string };
type PlanItem = Row & { status: string; priority: number };
type PlanResult = { worklist: PlanItem[]; resolved: Row[]; counts: Record<string, number> };
type RemedItem = PlanItem & { lane: string; lane_label: string; auto: boolean; effort: string };
type RemedLane = { key: string; label: string; auto: boolean; items: RemedItem[] };
type RemedResult = { steps: RemedItem[]; lanes: RemedLane[]; counts: Record<string, number>; error?: string };
const EFFORT_LABEL: Record<string, string> = { quick: "Quick", moderate: "Moderate", deep: "Deep" };
type DryPrompt = { header: string; prompt: string };
type DryUnbridged = { code: string; what: string; reason: string };
type DryRunResult = { ok: boolean; error?: string; note?: string; exit_code?: number;
  items?: unknown[]; prompts?: DryPrompt[]; unbridged?: DryUnbridged[] };
type ApplyItem = { id: string; code: string; url: string; status: string; note: string; files: string[] };
type ApplyResult = { ok: boolean; error?: string; note?: string; applied?: number; exit_code?: number;
  cycle?: string; diffstat?: string; summary?: { attempted?: number; stopped?: string | null; cost_usd?: number; items: ApplyItem[] } };
const APPLY_STATUS: Record<string, { fg: string; bg: string; label: string }> = {
  fixed: { fg: "#1e8a4c", bg: "#eaf6ef", label: "Fixed" },
  no_change: { fg: "#a86710", bg: "#fbf3e4", label: "No change" },
  error: { fg: "#c0392b", bg: "#fdeceb", label: "Error" },
  stopped: { fg: "#5b6570", bg: "#eef1f4", label: "Stopped" },
};
const STATUS_COLOR: Record<string, string> = { NEW: "#b00", REGRESSION: "#7a1fa2", PERSISTING: "#a86710" };

// ── Design tokens (product register: restrained, one accent, semantic states) ─
const T = {
  ink: "#161a1d", muted: "#5b6570", faint: "#6e7883", line: "#e5e8ec",
  bg: "#ffffff", panel: "#f6f8fa", accent: "#0e8a4c", accentInk: "#0a6d3c",
};
// Severity: leading-icon + tinted row (no side-stripe borders — banned).
const SEV: Record<string, { fg: string; bg: string; icon: string; label: string }> = {
  error: { fg: "#c0392b", bg: "#fdeceb", icon: "✕", label: "Error" },
  warn: { fg: "#a86710", bg: "#fbf3e4", icon: "!", label: "Warning" },
  info: { fg: "#2e6fb0", bg: "#eaf1f9", icon: "i", label: "Info" },
  ok: { fg: "#1e8a4c", bg: "#eaf6ef", icon: "✓", label: "Pass" },
};
const font = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const linkBtn = (color: string) => ({ background: "none", border: 0, color, cursor: "pointer", font, fontSize: 13, padding: 0, fontWeight: 600 });
const box = { padding: ".55rem .65rem", margin: ".3rem 0 0", width: "100%", boxSizing: "border-box" as const,
  border: `1px solid ${T.line}`, borderRadius: 8, font, fontSize: 14 };

function sevCounts(rows: Row[]) {
  const c = { error: 0, warn: 0, info: 0, ok: 0 };
  for (const r of rows) { if (r.severity in c) (c as Record<string, number>)[r.severity]++; }
  return c;
}

// Where a finding came from — decoded from its code prefix. Shown on every row
// so a result is never a black box (proof it was measured, not invented).
function sourceOf(code: string): string {
  const c = code || "";
  // `health.*` is OUR free On-page SEO tool (pipeline/scanner/audit.py), not
  // DataForSEO. It was labelled "DataForSEO — live data" while DataForSEO was
  // switched off, which made our own results look like paid ones.
  if (c.startsWith("unavailable.")) return "Not run — see the reason";
  if (c.startsWith("dfs.")) return "DataForSEO — live data";
  if (c.startsWith("health.")) return "Our on-page checks (free)";
  if (c.startsWith("lh.")) return "Google Lighthouse";
  if (c.startsWith("src.")) return "Your source code (repo)";
  if (c.startsWith("crux") || c.includes("perf")) return "Google CrUX — real users";
  if (c.startsWith("video")) return "Page HTML + YouTube API";
  return "Live page analysis";
}

function Rows({ list }: { list?: Row[] }) {
  return (
    <>
      {(list || []).map((r, i) => {
        const s = SEV[r.severity] || SEV.info;
        return (
          <div key={i} style={{ display: "flex", gap: ".6rem", padding: ".55rem .7rem", borderRadius: 8,
            background: s.bg, marginBottom: ".35rem", alignItems: "flex-start" }}>
            <span aria-hidden style={{ flexShrink: 0, width: 20, height: 20, borderRadius: "50%", background: s.fg,
              color: "#fff", fontSize: 12, fontWeight: 700, display: "grid", placeItems: "center", marginTop: 1 }}>{s.icon}</span>
            <div style={{ minWidth: 0 }}>
              <div style={{ color: T.ink }}>
                <b>{r.what}</b>{r.detail ? <span style={{ color: T.muted }}> · {r.detail}</span> : null}
              </div>
              <div style={{ color: T.muted, fontSize: 13, marginTop: 1 }}>{r.why}</div>
              {r.severity !== "ok" && r.fix && (
                <div style={{ fontSize: 13, marginTop: 2 }}>
                  <span style={{ color: s.fg, fontWeight: 600 }}>Fix:</span> <span style={{ color: T.ink }}>{r.fix}</span>
                </div>
              )}
              {r.pages && r.pages.length > 0 && (
                <details style={{ fontSize: 12, marginTop: 3 }}>
                  <summary style={{ cursor: "pointer", color: s.fg }}>Show {r.pages.length} affected page{r.pages.length > 1 ? "s" : ""}</summary>
                  <ul style={{ margin: ".3rem 0 0", paddingLeft: "1.1rem", color: T.muted }}>
                    {r.pages.map((u, j) => <li key={j}><a href={u} target="_blank" rel="noopener" style={{ color: T.accentInk }}>{u}</a></li>)}
                  </ul>
                </details>
              )}
              <div style={{ fontSize: 12, color: T.faint, marginTop: 3 }}>
                source: {sourceOf(r.code)}{r.code ? <> · <code style={{ fontFamily: "monospace" }}>{r.code}</code></> : null}
              </div>
            </div>
          </div>
        );
      })}
    </>
  );
}

// ── Dashboard primitives (REAI-style widgets) ────────────────────────────
function Widget({ title, action, span, children }: { title?: string; action?: ReactNode; span?: number; children: ReactNode }) {
  return (
    <div style={{ gridColumn: span ? `span ${span}` : undefined, border: `1px solid ${T.line}`, borderRadius: 14,
      background: T.bg, overflow: "hidden", display: "flex", flexDirection: "column" }}>
      {title && (
        <div style={{ padding: ".7rem .95rem", borderBottom: `1px solid ${T.line}`, display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem" }}>
          <b style={{ color: T.ink, fontSize: 14 }}>{title}</b>
          {action}
        </div>
      )}
      <div style={{ padding: ".85rem .95rem", flex: 1 }}>{children}</div>
    </div>
  );
}

function Metric({ label, value, sub, color, delta }: { label: string; value: ReactNode; sub?: string; color?: string; delta?: { n: number; good?: boolean } }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 12, color: T.muted, marginBottom: 2, display: "flex", alignItems: "center", gap: ".3rem" }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: ".4rem" }}>
        <span style={{ fontSize: "1.7rem", fontWeight: 800, color: color || T.ink, lineHeight: 1 }}>{value}</span>
        {delta && delta.n !== 0 && (
          <span style={{ fontSize: 12, fontWeight: 700, color: delta.good ? SEV.ok.fg : SEV.error.fg }}>
            {delta.good ? "▲" : "▼"}{Math.abs(delta.n)}
          </span>
        )}
      </div>
      {sub && <div style={{ fontSize: 12, color: T.faint, marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

function Gauge({ score, size = 96 }: { score: number; size?: number }) {
  const c = score >= 80 ? SEV.ok.fg : score >= 50 ? SEV.warn.fg : SEV.error.fg;
  const inner = size - 20;
  return (
    <div style={{ width: size, height: size, borderRadius: "50%", display: "grid", placeItems: "center", flexShrink: 0,
      background: `conic-gradient(${c} ${score * 3.6}deg, ${T.line} 0deg)` }}>
      <div style={{ width: inner, height: inner, borderRadius: "50%", background: T.bg, display: "grid", placeItems: "center" }}>
        <span style={{ fontSize: size * 0.28, fontWeight: 800, color: c, lineHeight: 1 }}>{score}</span>
      </div>
    </div>
  );
}

// SVG donut — segments render as arcs; center shows the total. No chart library.
function Donut({ segments, size = 150, thickness = 20, centerLabel, centerSub }: {
  segments: { label: string; value: number; color: string }[]; size?: number; thickness?: number; centerLabel?: ReactNode; centerSub?: string;
}) {
  const total = segments.reduce((s, x) => s + x.value, 0);
  const r = (size - thickness) / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "1.1rem", flexWrap: "wrap" }}>
      <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={T.line} strokeWidth={thickness} />
          {total > 0 && segments.filter((s) => s.value > 0).map((seg, i) => {
            const len = (seg.value / total) * circ;
            const el = (
              <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={seg.color} strokeWidth={thickness}
                strokeDasharray={`${len} ${circ - len}`} strokeDashoffset={-offset} strokeLinecap="butt" />
            );
            offset += len;
            return el;
          })}
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", textAlign: "center" }}>
          <div>
            <div style={{ fontSize: size * 0.24, fontWeight: 800, color: T.ink, lineHeight: 1 }}>{centerLabel}</div>
            {centerSub && <div style={{ fontSize: 12, color: T.faint, marginTop: 2 }}>{centerSub}</div>}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: ".35rem" }}>
        {segments.map((seg, i) => (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: ".45rem", fontSize: 13 }}>
            <span style={{ width: 11, height: 11, borderRadius: 3, background: seg.color, flexShrink: 0 }} />
            <span style={{ color: T.ink, fontWeight: 600 }}>{seg.value}</span>
            <span style={{ color: T.muted }}>{seg.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Horizontal bar chart — one labelled bar per row, value scaled to 0-100.
function BarChart({ rows }: { rows: { label: string; pct: number | null; color: string; note?: string }[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".6rem" }}>
      {rows.map((r, i) => (
        <div key={i}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, marginBottom: 3 }}>
            <span style={{ color: T.ink, fontWeight: 600 }}>{r.label}</span>
            <span style={{ color: r.color, fontWeight: 700 }}>{r.pct === null ? "—" : `${r.pct}%`}{r.note ? <span style={{ color: T.faint, fontWeight: 400 }}> · {r.note}</span> : null}</span>
          </div>
          <div style={{ height: 9, borderRadius: 5, background: T.line, overflow: "hidden" }}>
            <div style={{ height: "100%", width: `${r.pct ?? 0}%`, background: r.color, borderRadius: 5, transition: "width .6s cubic-bezier(.22,1,.36,1)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function ReaiApp({ initialTab }: { initialTab?: any }) {
  return <AuthGate><Scanner initialTab={initialTab} /></AuthGate>;
}

function Scanner({ initialTab }: { initialTab?: any }) {
  const [stage, setStage] = useState<"onboard" | "measure" | "history">("history");
  const [clientId, setClientId] = useState<string | null>(null);
  const [repos, setRepos] = useState<string[]>([]);

  // ── History dashboard state (pure DB reads, no scanner, no paid call) ──
  const [clients, setClients] = useState<ClientWithStats[]>([]);
  const [histClient, setHistClient] = useState<ClientWithStats | null>(null);
  const [hist, setHist] = useState<ScanRow[]>([]);
  const [remedHist, setRemedHist] = useState<RemediationRow[]>([]);
  const [openReport, setOpenReport] = useState<{ report: Audit; scan: ScanRow } | null>(null);
  const [histBusy, setHistBusy] = useState(false);
  const [showTechnicalReport, setShowTechnicalReport] = useState(false);
  const [scanBudget, setScanBudget] = useState<{ dailyBudget: number; spentToday: number } | null>(null);

  const refreshBudget = useCallback(async () => {
    try {
      const res = await authedFetch("/api/scan");
      if (res.ok) {
        const json = await res.json();
        if (typeof json.budget === "number" && typeof json.spentToday === "number") {
          setScanBudget({ dailyBudget: json.budget, spentToday: json.spentToday });
        }
      }
    } catch {}
  }, []);

  async function openHistory() {
    setShowTechnicalReport(false);
    setStage("history"); setHistClient(null); setHist([]); setOpenReport(null);
    setHistBusy(true);
    try { setClients(await listClients()); } finally { setHistBusy(false); }
  }
  async function openClient(c: ClientWithStats, preserveReport = false) {
    setHistClient(c); setClientId(c.id);
    setUrl(c.website || c.domain || "");
    setRepo(c.repo || "");
    setModel(c.model || "B");
    setBusiness(c.business || "");
    setKwList(c.keywords || []);
    setCompetitors((c.competitors || []).join(", "));
    setGoal(c.goal || "");
    if (!preserveReport) setOpenReport(null);
    setRemedHist([]); setHistBusy(true);
    try {
      const [scans, remeds] = await Promise.all([scanHistory(c.id), remediationHistory(c.id)]);
      setHist(scans); setRemedHist(remeds);
      // Land straight on the project's SEO Dashboard (its latest scan), like REAI.
      if (!preserveReport || !openReport) {
        if (scans.length) {
          const report = await getScanReport(scans[0].id);
          if (report) setOpenReport({ report: report as unknown as Audit, scan: scans[0] });
        } else if (c.lastScanId) {
          const report = await getScanReport(c.lastScanId);
          if (report) {
            const pseudoScan: ScanRow = {
              id: c.lastScanId,
              created_at: c.lastScannedAt || new Date().toISOString(),
              url: c.website || c.domain,
              score: c.lastScore,
              counts: c.lastCounts,
              cost: 0,
            };
            setOpenReport({ report: report as unknown as Audit, scan: pseudoScan });
          }
        }
      }
    } finally { setHistBusy(false); }
  }
  async function openScan(s: ScanRow) {
    setHistBusy(true);
    try {
      const report = await getScanReport(s.id);
      if (report) setOpenReport({ report: report as unknown as Audit, scan: s });
    } finally { setHistBusy(false); }
  }
  // Rehydrate the Onboard form from a saved client so Measure runs against the
  // right profile (not stale/empty state), then jump to Measure.
  function measureClient(c: ClientWithStats) {
    setClientId(c.id);
    setBusiness(c.business || ""); setUrl(c.website || c.domain || "");
    setModel(c.model || "B"); setRepo(c.repo || "");
    setKwList(c.keywords || []); setCompetitors((c.competitors || []).join(", "));
    setGoal(c.goal || "");
    setData(null); setPlan(null); setRemed(null); setDry(null); setApply(null); setConfirmApply(false); setTools([]);
    setStage("measure");
  }

  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => { listRepos().then(setRepos); }, []);
  // Land on the projects Dashboard: load the client list on mount.
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        // listClients() is a browser-side Supabase call. If the session is
        // missing or the network stalls it can hang rather than throw, and the
        // loading flag it gates would never clear. Racing it against a timeout
        // means a stalled call costs an empty client list, not a dead app.
        const loaded = await Promise.race([
          listClients(),
          new Promise<never[]>((resolve) => setTimeout(() => resolve([]), 8000)),
        ]);
        if (!active) return;
        setClients(loaded);
        if (loaded && loaded.length > 0) {
          await openClient(loaded[0]);
        }
      } catch (e) {
        console.error("Failed to load initial clients", e);
      } finally {
        if (active) {
          setInitialLoading(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    refreshBudget();
  }, [refreshBudget]);
  // Onboard profile
  const [business, setBusiness] = useState("");
  const [url, setUrl] = useState("");
  const [model, setModel] = useState("B");
  const [repo, setRepo] = useState("");
  const [kwList, setKwList] = useState<string[]>([]);
  const [kwInput, setKwInput] = useState("");
  const [competitors, setCompetitors] = useState("");

  function addKeyword() {
    const v = kwInput.trim();
    if (v && !kwList.includes(v)) setKwList([...kwList, v]);
    setKwInput("");
  }
  const [goal, setGoal] = useState("");
  // Measure tool selection — the checklist. Catalog comes from the backend
  // (/api/tools → Python /tools), so adding a tool there shows it here. All
  // ticked by default; untick to skip a tool (and its cost).
  const [catalog, setCatalog] = useState<CatalogTool[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => {
    authedFetch("/api/tools").then((r) => r.json()).then((d) => {
      const t: CatalogTool[] = d.tools || [];
      setCatalog(t);
      // The GENERIC scan triggers (top-bar Run Scan, quick search, sample chips,
      // Refresh Local Signals, tool-directory cards) send this selection, and no
      // screen renders a picker or a cost before they fire. So it stays free:
      // ticking every available tool made each of those clicks spend ~$0.53 on
      // eight paid tools with nothing shown first (review, 2026-09-14).
      //
      // DataForSEO is still the default where the operator chose it: on each
      // tool page, whose Data source dropdown opens on DataForSEO and names the
      // cost next to its Test button. That is an explicit, priced choice; this
      // is not.
      setSelected(new Set(t.filter((x) => x.group === "free").map((x) => x.key)));
    }).catch((e) => console.error("tool catalog fetch failed — is the backend running?", e));
  }, []);
  const [filter, setFilter] = useState<"all" | "error" | "warn" | "ok">("all");
  const [crawlPages, setCrawlPages] = useState(5);  // free multi-page crawl depth (default 5 pages, max 25)
  const [busy, setBusy] = useState(false);
  const scanInFlight = useRef(false);
  const [live, setLive] = useState<string[]>([]);
  const [phaseLine, setPhaseLine] = useState("");
  const [tools, setTools] = useState<Tool[]>([]);
  const [data, setData] = useState<ScanResult | null>(null);
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [planBusy, setPlanBusy] = useState(false);
  const [remed, setRemed] = useState<RemedResult | null>(null);
  const [remedBusy, setRemedBusy] = useState(false);
  const [dry, setDry] = useState<DryRunResult | null>(null);
  const [dryBusy, setDryBusy] = useState(false);
  const [confirmApply, setConfirmApply] = useState(false);
  const [apply, setApply] = useState<ApplyResult | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);

  async function runPlan() {
    const activeId = clientId || histClient?.id;
    if (!activeId) return;
    setPlanBusy(true); setPlan(null); setRemed(null); setDry(null); setApply(null); setConfirmApply(false);
    try {
      const { current, previous } = await lastTwoScansFindings(activeId);
      const res = await authedFetch("/api/plan", {
        method: "POST",
        body: JSON.stringify({ current, previous }),
      });
      setPlan(await res.json());
    } catch (e) {
      console.error("runPlan", e);
    } finally {
      setPlanBusy(false);
    }
  }

  async function runRemediate() {
    if (!plan?.worklist?.length) return;
    setRemedBusy(true); setRemed(null); setDry(null);
    try {
      const res = await authedFetch("/api/remediate", {
        method: "POST",
        body: JSON.stringify({ worklist: plan.worklist }),
      });
      setRemed(await res.json());
    } catch (e) {
      console.error("runRemediate", e);
    } finally {
      setRemedBusy(false);
    }
  }

  // Non-destructive preview: bridge the worklist to the pipeline + run
  // wf-site-remediate --dry-run (streams the fix prompts, edits nothing).
  async function runDryRun() {
    if (!plan?.worklist?.length) return;
    setDryBusy(true); setDry(null); setApply(null); setConfirmApply(false);
    try {
      const res = await authedFetch("/api/remediate/dryrun", {
        method: "POST",
        body: JSON.stringify({ repo, url, tier: 1, worklist: plan.worklist }),
      });
      setDry(await res.json());
    } catch (e) {
      console.error("runDryRun", e);
    } finally {
      setDryBusy(false);
    }
  }

  // The REAL edit-run — Claude Code (subscription) edits the repo. Irreversible,
  // so it only fires after an explicit in-UI confirm and sends confirm:true.
  async function runApply() {
    if (!plan?.worklist?.length) return;
    setApplyBusy(true); setApply(null); setConfirmApply(false);
    try {
      const res = await authedFetch("/api/remediate/apply", {
        method: "POST",
        body: JSON.stringify({ repo, url, tier: 1, worklist: plan.worklist, confirm: true, max_items: 3 }),
      });

      // The backend streams newline-delimited JSON: {"log": "..."} per line as
      // Claude writes it, then one {"result": {...}}. Reading it with
      // res.json() would block until the whole run finished, which is what made
      // an apply look hung for up to half an hour.
      let r: ApplyResult = { ok: false, error: "apply produced no result" } as ApplyResult;
      if (res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n");
          buf = parts.pop() ?? "";           // keep the partial last line
          for (const line of parts) {
            if (!line.trim()) continue;
            try {
              const ev = JSON.parse(line);
              if (ev.log) setLive((l) => [...l, ev.log]);
              if (ev.result) r = ev.result as ApplyResult;
            } catch {
              // A partial or malformed line is not worth failing the run over.
            }
          }
        }
      }
      setApply(r);
      const activeId = clientId || histClient?.id;
      if (r.ok && !r.error && activeId) {
        await saveRemediation(activeId, {
          url, cycle: r.cycle || "", applied: r.applied || 0,
          cost_usd: r.summary?.cost_usd || 0, diffstat: r.diffstat || "",
          items: (r.summary?.items || []).map((it) => ({
            code: it.code, url: it.url, status: it.status, note: it.note, files: it.files })),
        });
      }
    } catch (e) {
      console.error("runApply", e);
    } finally {
      setApplyBusy(false);
    }
  }

  function toggleTool(key: string) {
    setSelected((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; });
  }
  function setGroup(groupTools: CatalogTool[], on: boolean) {
    setSelected((s) => {
      const n = new Set(s);
      for (const t of groupTools) { if (on) n.add(t.key); else n.delete(t.key); }
      return n;
    });
  }
  const estCost = catalog.filter((t) => selected.has(t.key)).reduce((s, t) => s + (t.cost_num || 0), 0);

  /**
   * `overrideTools` is how a section scans only its own concern: the SEO screen
   * passes the SEO tool keys, the Local screen passes the local ones. Absent, it
   * falls back to the picker's selection, which is the full-scan behaviour that
   * existed before. One optional argument rather than a second scan path -
   * everything downstream already took a tool list.
   */
  async function run(overrideUrl?: string, overrideTools?: string[]): Promise<void>;
  async function run(overrideUrl?: string, overrideTools?: string[], overrideCrawlPages?: number): Promise<void>;
  async function run(overrideUrl?: string, overrideTools?: string[], overrideCrawlPages?: number) {
    // One scan at a time. Several triggers ignore `busy`, and a second press
    // during a paid scan starts a second paid scan that /api/scan admits against
    // the same not-yet-saved spend. A ref, not state: two clicks in one tick
    // both read the old `busy`.
    if (scanInFlight.current) return;
    scanInFlight.current = true;
    const activeUrl = (overrideUrl || url || "").trim();
    setBusy(true); setData(null); setLive([]); setTools([]); setPhaseLine("");
    const toolMap = new Map<string, Tool>();
    try {
      // Every tool checks the live DOMAIN (operator, 2026-09-14). The repository
      // is not sent to a scan, so no tool reads source code; the repo stays on
      // the project only for Fix.
      const res = await authedFetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: activeUrl, model, tools: (overrideTools ?? [...selected]).filter((k) => k !== "source"), business, keywords: kwList, competitors, goal, max_pages: 25, crawl_pages: overrideCrawlPages ?? crawlPages, location_code: marketFor(activeUrl).location_code, language_code: marketFor(activeUrl).language_code }),
      });
      const lines: string[] = [];
      let resultEv: any = null;
      let activity: ToolActivity[] = [];
      const outcome = await readScanStream(res, (ev) => {
        if (ev.state === "phase") {
          setPhaseLine(ev.tool);  // a phase marker, not a tool card
        } else if (ev.tool) {
          // Running / progress / done, folded into per-tool activity for the
          // live panel. Progress never overwrites a tool's rows or state.
          activity = applyScanEvent(activity, ev, Date.now());
          setTools(activity as unknown as Tool[]);
          if (ev.state === "done") {
            toolMap.set(ev.tool, { name: ev.tool, state: ev.state, rows: ev.rows || [], status: ev.status || "", cost: ev.cost || 0 });
          }
        } else if (ev.log !== undefined) { lines.push(ev.log); setLive([...lines]); }
        else if (ev.result) resultEv = ev;
      });
      if (outcome.blockedTools.length) {
        lines.push(`Skipped to stay inside today's scan budget: ${outcome.blockedTools.join(", ")}.`);
        setLive([...lines]);
      }
      if (outcome.error || !resultEv) {
        setData({ error: outcome.error || "The scan ended without a result.", log: lines });
        return;
      }
      {
        const ev = resultEv;
        {
            setData(ev.result);
            let finalAudit = ev.result.audit;
            // Merge only into a report of the SAME site (B-126): a github.com scan
            // merged into the hospital's report put github.com findings on six
            // hospital pages.
            const openReportUrl = ((openReport?.report as any)?.site_url || (openReport?.scan as any)?.url || "") as string;
            if (finalAudit && (overrideTools || openReport?.report) && sameSite(openReportUrl, activeUrl)) {
              const baseReport = (openReport?.report || {}) as Record<string, unknown>;
              const merged: Record<string, unknown> = {
                ...mergeScanReport(baseReport, finalAudit as unknown as Record<string, unknown>, overrideTools ?? [...selected]),
                page: (finalAudit as any).page || baseReport.page,
                site_url: activeUrl,
              };
              const NON_GROUP = new Set(["score", "counts", "cost", "log", "cycle", "url", "site_url", "page", "graded", "score_version"]);
              const counts: Record<string, number> = { error: 0, warn: 0, info: 0, ok: 0 };
              for (const [k, v] of Object.entries(merged)) {
                if (NON_GROUP.has(k) || !Array.isArray(v)) continue;
                for (const r of v as any[]) {
                  if (r?.severity && counts[r.severity] !== undefined) {
                    counts[r.severity]++;
                  }
                }
              }
              const graded = counts.ok + counts.warn + counts.error;
              const score = graded > 0 ? Math.round((100 * counts.ok) / graded) : (finalAudit.score ?? (baseReport.score as number | undefined) ?? 0);
              merged.counts = counts;
              merged.score = score;
              merged.graded = graded;
              finalAudit = merged as unknown as Audit;
            }

            if (finalAudit) {
              setOpenReport({
                report: finalAudit,
                scan: {
                  id: "latest",
                  created_at: new Date().toISOString(),
                  url: activeUrl,
                  score: finalAudit.score || 0,
                  counts: (finalAudit.counts as Record<string, number>) || {},
                  cost: finalAudit.cost || 0,
                },
              });
            }
            // The scan belongs to the project that is open, or to the project
            // that owns this domain. It used to fall back to `clients[0]`, which
            // filed a scan of one site under whichever project listed first.
            // The scanned domain decides the project (B-126), never whichever
            // project is open: the owner of this domain, else the open project
            // only if it IS this domain, else a new project below.
            let targetClientId: string | null | undefined = pickScanProject(clients as any, histClient as any, activeUrl);
            if (!targetClientId && activeUrl) {
              try {
                const domain = activeUrl.replace(/^https?:\/\//i, "").replace(/\/.*$/, "").replace(/^www\./i, "");
                targetClientId = await saveClient({
                  business: domain,
                  website: activeUrl,
                  domain,
                  model: model || "B",
                  repo: repo || "",
                  tier: 1,
                  keywords: kwList || [],
                  competitors: competitors ? competitors.split(",").map((c) => c.trim()).filter(Boolean) : [],
                  goal: goal || "",
                });
              } catch (err) {
                console.warn("Failed to auto-create client for scan", err);
              }
            }
            if (targetClientId) {
              setClientId(targetClientId);
              await saveScan(targetClientId, { url: activeUrl, model, tools: overrideTools ?? [...selected] }, finalAudit || {}, ev.result.log || [], [...toolMap.values()]);
            }
            try {
              const refreshed = await listClients();
              setClients(refreshed);
              const fresh = refreshed.find((c) => c.id === targetClientId);
              if (fresh) {
                setHistClient(fresh);
                setClientId(fresh.id);
              }
              if (targetClientId) {
                const [scans, remeds] = await Promise.all([
                  scanHistory(targetClientId),
                  remediationHistory(targetClientId),
                ]);
                setHist(scans);
                setRemedHist(remeds);
                if (scans.length > 0 && finalAudit) {
                  setOpenReport({
                    report: finalAudit,
                    scan: scans[0],
                  });
                }
              }
            } catch (refErr) {
              console.warn("Failed to refresh clients after scan", refErr);
            }
          }
      }
    } catch (e) {
      setData({ error: String(e) });
    } finally {
      scanInFlight.current = false;
      setBusy(false); setPhaseLine("");
    }
  }

  /**
   * Correct an existing project.
   *
   * The selected client is re-read from the refreshed list rather than patched
   * in place from the response, so the screen shows what the database holds and
   * not what the form hoped it would hold. `domainChanged` is passed back up
   * untouched: it is the caller's job to tell the operator that the site changed
   * under scans that measured the old one.
   */
  async function handleUpdateClient(id: string, patch: any) {
    const res = await updateClient(id, patch);
    if (!res.ok) return res;
    const refreshed = await listClients();
    setClients(refreshed);
    const fresh = refreshed.find((c) => c.id === id);
    if (fresh) {
      setHistClient(fresh);
      setClientId(fresh.id);
      // The domain may have moved, and `url` drives the next scan.
      if (fresh.website) setUrl(fresh.website);
      setRepo(fresh.repo || "");
      if (fresh.model) setModel(fresh.model);
      if (fresh.business) setBusiness(fresh.business);
      if (fresh.keywords) setKwList(fresh.keywords);
    }
    return res;
  }

  async function handleSaveNewClient(profile: any) {
    const id = await saveClient(profile);
    const refreshed = await listClients();
    setClients(refreshed);
    if (id) {
      setClientId(id);
      const created = refreshed.find((x) => x.id === id);
      if (created) openClient(created);
    }
  }

  async function handleTriggerScan(targetUrl: string, toolKeys?: string[]): Promise<void>;
  async function handleTriggerScan(targetUrl: string, toolKeys?: string[], customCrawlPages?: number): Promise<void>;
  async function handleTriggerScan(targetUrl: string, toolKeys?: string[], customCrawlPages?: number) {
    const cleanUrl = targetUrl.trim();
    setUrl(cleanUrl);
    if (typeof customCrawlPages === "number") {
      setCrawlPages(customCrawlPages);
    }
    await run(cleanUrl, toolKeys, customCrawlPages);
    await refreshBudget();
  }

  return (
    <ReaiDashboard
      clients={clients}
      selectedClient={histClient || (clients.length > 0 ? clients[0] : null)}
      onSelectClient={(c) => {
        setHistClient(c);
        setClientId(c.id);
        openClient(c);
      }}
      openReport={openReport}
      onSaveNewClient={handleSaveNewClient}
      onUpdateClient={handleUpdateClient}
      onTriggerScan={handleTriggerScan}
      crawlPages={crawlPages}
      onCrawlPagesChange={(p) => setCrawlPages(p)}
      /*
       * B-104. `error` was missing here, and that is why a broken scan looked
       * like nothing at all: `run()` writes the failure into `data`, `data` is
       * not a dashboard prop, so a 403 from the scanner set busy true, then busy
       * false, and drew no message anywhere. The operator could not tell a
       * refusal from a site with no findings. A run that could not run must say
       * so on the screen the button is on.
       */
      scanState={{ busy, phaseLine, live, tools, error: data?.error ? String(data.error) : null }}
      toolPicker={{
        catalog, selected, estCost,
        onToggle: toggleTool,
        onAll: () => setSelected(new Set(catalog.map((t) => t.key))),
        onClear: () => setSelected(new Set()),
      }}
      planState={{
        plan, planBusy, runPlan,
        remed, remedBusy, runRemediate,
        dry, dryBusy, runDryRun,
        apply, applyBusy, runApply,
      }}
      remedHist={remedHist}
      initialTab={initialTab}
      isLoading={initialLoading || histBusy}
      budget={scanBudget ?? {
        dailyBudget: 5,
        spentToday: hist
          .filter((s) => (s.created_at || "").slice(0, 10) === new Date().toISOString().slice(0, 10))
          .reduce((sum, s) => sum + (Number(s.cost) || 0), 0),
      }}
    />
  );
}
