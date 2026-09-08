"use client";
import { useState, useEffect } from "react";
import { AuthGate } from "./auth";
import { saveClient, saveScan, lastTwoScansFindings } from "../lib/db";
import { listRepos } from "../lib/github";
import { supabase } from "../lib/supabase";

type Row = { code: string; what: string; why: string; fix: string; detail: string; severity: string; tool?: string };
type Audit = {
  seo: Row[]; aeo: Row[]; perf: Row[]; tech: Row[]; site: Row[]; rankings: Row[]; keywords: Row[]; ai: Row[]; source: Row[];
  score: number; counts: Record<string, number>; cost?: number;
};
type Cycle =
  | { model: "A"; brief: string; worklist: unknown[] }
  | { model: "B"; diff: string; decision: { action: string; reason: string } };
type ScanResult = { audit?: Audit; cycle?: Cycle; error?: string; log?: string[] };
type Tool = { name: string; state: string; rows: Row[]; status: string; cost: number };
type CatalogTool = { key: string; label: string; category: string; group: string; cost: string; cost_num: number };
type PlanItem = Row & { status: string; priority: number };
type PlanResult = { worklist: PlanItem[]; resolved: Row[]; counts: Record<string, number> };
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
            </div>
          </div>
        );
      })}
    </>
  );
}

export default function Home() {
  return <AuthGate><Scanner /></AuthGate>;
}

function Scanner() {
  const [stage, setStage] = useState<"onboard" | "measure">("onboard");
  const [clientId, setClientId] = useState<string | null>(null);
  const [repos, setRepos] = useState<string[]>([]);

  useEffect(() => { listRepos().then(setRepos); }, []);
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
    fetch("/api/tools").then((r) => r.json()).then((d) => {
      const t: CatalogTool[] = d.tools || [];
      setCatalog(t);
      setSelected(new Set(t.map((x) => x.key)));  // all ticked
    }).catch((e) => console.error("tool catalog fetch failed — is the backend running?", e));
  }, []);
  const [filter, setFilter] = useState<"all" | "error" | "warn" | "ok">("all");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<string[]>([]);
  const [phaseLine, setPhaseLine] = useState("");
  const [tools, setTools] = useState<Tool[]>([]);
  const [data, setData] = useState<ScanResult | null>(null);
  const [plan, setPlan] = useState<PlanResult | null>(null);
  const [planBusy, setPlanBusy] = useState(false);

  async function runPlan() {
    if (!clientId) return;
    setPlanBusy(true); setPlan(null);
    try {
      const { current, previous } = await lastTwoScansFindings(clientId);
      const res = await fetch("/api/plan", {
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

  async function run() {
    setBusy(true); setData(null); setLive([]); setTools([]); setPhaseLine("");
    const toolMap = new Map<string, Tool>();
    try {
      const { data: sess } = await supabase.auth.getSession();
      const github_token = sess.session?.provider_token || "";  // read-only source lane
      const res = await fetch("/api/scan", {
        method: "POST",
        body: JSON.stringify({ url, repo, model, tools: [...selected], business, keywords: kwList, competitors, goal, github_token, max_pages: 25 }),
      });
      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let buf = ""; const lines: string[] = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n"); buf = parts.pop() || "";
        for (const part of parts) {
          if (!part.trim()) continue;
          const ev = JSON.parse(part);
          if (ev.state === "phase") {
            setPhaseLine(ev.tool);  // a phase marker, not a tool card
          } else if (ev.tool) {
            toolMap.set(ev.tool, { name: ev.tool, state: ev.state, rows: ev.rows || [], status: ev.status || "", cost: ev.cost || 0 });
            setTools([...toolMap.values()]);
          } else if (ev.log !== undefined) { lines.push(ev.log); setLive([...lines]); }
          else if (ev.result) {
            setData(ev.result);
            saveScan(clientId || "", { url, model, tools: [...selected] }, ev.result.audit || {}, ev.result.log || [], [...toolMap.values()]);
          }
          else if (ev.error) setData({ error: ev.error, log: ev.log });
        }
      }
    } catch (e) {
      setData({ error: String(e) });
    } finally {
      setBusy(false); setPhaseLine("");
    }
  }

  // ── Stage 1: Onboard ───────────────────────────────────────────────────────
  if (stage === "onboard") {
    return (
      <main>
        <h1>SEO / AEO Pipeline</h1>
        <p style={{ color: "#666" }}>Step 1 of the pipeline · <b>Onboard</b> → Measure → Plan → Remediate → Gate → Merge → Monitor</p>
        <div style={{ background: "#f4f7ff", border: "1px solid #cdd8ff", borderRadius: 6, padding: "1.25rem", margin: "1rem 0" }}>
          <h2 style={{ marginTop: 0 }}>Onboard a client</h2>
          <label>Business name<input style={box} value={business} onChange={(e) => setBusiness(e.target.value)} placeholder="Orienda International Hospital" /></label>
          <label>Website URL<input style={box} value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://oriendainternationalhospital.com.kh/" /></label>
          <label>Model
            <select style={box} value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="B">Model B — we fix the code</option>
              <option value="A">Model A — we hand you a brief (read-only)</option>
            </select>
          </label>
          {model === "B" && (
            <label>Repo (choose an existing one, or type a path)
              {repos.length > 0 && (
                <select style={box} value={repos.includes(repo) ? repo : ""} onChange={(e) => setRepo(e.target.value)}>
                  <option value="">— pick a repo —</option>
                  {repos.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              )}
              <input style={box} value={repo} onChange={(e) => setRepo(e.target.value)}
                placeholder={repos.length ? "or type owner/repo / a local path" : "owner/repo or /path/to/repo"} />
            </label>
          )}
          <label>Target keywords (type one, press Enter to add)
            <input style={box} value={kwInput}
              onChange={(e) => setKwInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addKeyword(); } }}
              placeholder="hospital phnom penh" />
          </label>
          {kwList.length > 0 && (
            <div style={{ margin: ".25rem 0" }}>
              {kwList.map((k) => (
                <span key={k} style={{ display: "inline-block", background: "#e6efe9", borderRadius: 12, padding: ".15rem .6rem", margin: ".15rem" }}>
                  {k} <span style={{ cursor: "pointer", color: "#a00" }} onClick={() => setKwList(kwList.filter((x) => x !== k))}>×</span>
                </span>
              ))}
            </div>
          )}
          <label>Competitors (comma-separated)<input style={box} value={competitors} onChange={(e) => setCompetitors(e.target.value)} placeholder="competitor1.com, competitor2.com" /></label>
          <label>Growth goal<input style={box} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="More booking calls from local search" /></label>
          <button disabled={!url.trim()} onClick={async () => {
            const host = url.trim().replace(/^https?:\/\//, "").replace(/\/.*$/, "");
            const id = await saveClient({
              business, domain: host, website: url.trim(), model, repo, tier: 1,
              keywords: kwList,
              competitors: competitors.split(",").map((s) => s.trim()).filter(Boolean),
              goal,
            });
            setClientId(id);
            setStage("measure");
          }}
            style={{ marginTop: ".75rem", padding: ".6rem 1.2rem", background: url.trim() ? "#1a5" : "#aaa", color: "#fff", border: 0, borderRadius: 6, cursor: url.trim() ? "pointer" : "not-allowed" }}>
            Onboard → Measure
          </button>
        </div>
      </main>
    );
  }

  // ── Stage 2: Measure ─────────────────────────────────────────────────────────
  const a = data?.audit; const c = data?.cycle;
  // Functional sections, in catalog order (backend groups tools by category).
  const cats = [...new Set(catalog.map((t) => t.category))];
  const labelToCat = new Map(catalog.map((t) => [t.label, t.category]));
  const catOf = (label: string) => labelToCat.get(label) || "Other";

  // One result card per tool; returns null when a filter hides all its rows.
  const badge = (n: number, sv: { fg: string }) => n > 0 ? (
    <span style={{ background: sv.fg, color: "#fff", borderRadius: 10, padding: "0 .45rem", fontSize: 11, fontWeight: 700, marginLeft: ".3rem" }}>{n}</span>
  ) : null;
  function renderCard(t: Tool) {
    const cnt = sevCounts(t.rows);
    const shown = filter === "all" ? t.rows : t.rows.filter((r) => r.severity === filter);
    if (t.state === "done" && filter !== "all" && shown.length === 0) return null;
    return (
      <div key={t.name} style={{ border: `1px solid ${T.line}`, borderRadius: 10, marginBottom: ".6rem", overflow: "hidden", background: T.bg }}>
        <div style={{ background: T.panel, padding: ".6rem .85rem", display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem" }}>
          <span style={{ fontWeight: 600, color: T.ink, display: "flex", alignItems: "center" }}>
            <span aria-hidden style={{ marginRight: ".45rem" }}>{t.state === "running" ? "◌" : "✓"}</span>{t.name}
            {t.state === "done" && <>{badge(cnt.error, SEV.error)}{badge(cnt.warn, SEV.warn)}{badge(cnt.ok, SEV.ok)}</>}
          </span>
          <span style={{ color: T.muted, fontSize: 12.5, whiteSpace: "nowrap" }}>
            {t.state === "running" ? "running…" : t.status}
            {" · "}<span style={{ color: t.cost > 0 ? "#a86710" : T.accent, fontWeight: 600 }}>{t.cost > 0 ? `$${t.cost.toFixed(4)}` : "free"}</span>
          </span>
        </div>
        {t.state === "done" && <div style={{ padding: ".55rem .7rem" }}><Rows list={shown} /></div>}
      </div>
    );
  }
  return (
    <main>
      <h1>SEO / AEO Pipeline</h1>
      <p style={{ color: "#666" }}>Onboard → <b>Measure</b> → Plan → Remediate → Gate → Merge → Monitor · <a onClick={() => setStage("onboard")} style={{ color: "#1a5", cursor: "pointer" }}>← edit client</a></p>

      <div style={{ background: "#f7f7f7", borderRadius: 6, padding: "1rem", margin: "1rem 0" }}>
        <b>{business || url}</b> · Model {model}{repo ? ` · ${repo}` : ""}<br />
        {kwList.length > 0 && <>Keywords: {kwList.join(", ")}<br /></>}
        {competitors && <>Competitors: {competitors}<br /></>}
        {goal && <>Goal: {goal}</>}
      </div>

      {/* ── Tool checklist — pick which Measure tools run, grouped by section ─ */}
      <div style={{ border: `1px solid ${T.line}`, borderRadius: 10, overflow: "hidden", margin: "1rem 0", background: T.bg }}>
        <div style={{ background: T.panel, padding: ".7rem .9rem", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: `1px solid ${T.line}` }}>
          <b style={{ color: T.ink }}>Tools to run</b>
          <span style={{ fontSize: 13, color: T.muted }}>
            <button onClick={() => setSelected(new Set(catalog.map((t) => t.key)))} style={linkBtn(T.accentInk)}>Select all</button>
            <span style={{ color: T.line }}> · </span>
            <button onClick={() => setSelected(new Set())} style={linkBtn(T.muted)}>Clear</button>
          </span>
        </div>
        {cats.map((cat) => {
          const catTools = catalog.filter((t) => t.category === cat);
          const allOn = catTools.every((t) => selected.has(t.key));
          const someOn = catTools.some((t) => selected.has(t.key));
          const paid = catTools.reduce((s, t) => s + (selected.has(t.key) ? t.cost_num : 0), 0);
          return (
            <div key={cat} style={{ borderBottom: `1px solid ${T.line}` }}>
              <div style={{ padding: ".5rem .9rem", background: "#fbfcfd", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <label style={{ fontWeight: 600, cursor: "pointer", color: T.ink, display: "flex", alignItems: "center", gap: ".5rem" }}>
                  <input type="checkbox" checked={allOn} ref={(el) => { if (el) el.indeterminate = someOn && !allOn; }}
                    onChange={(e) => setGroup(catTools, e.target.checked)} />
                  {cat}
                </label>
                {paid > 0 && <span style={{ fontSize: 12, color: "#a86710" }}>${paid.toFixed(4)}</span>}
              </div>
              {catTools.map((t) => (
                <label key={t.key} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: ".5rem",
                  padding: ".38rem .9rem .38rem 2.1rem", cursor: "pointer", transition: "background .15s ease",
                  background: selected.has(t.key) ? "#f4faf6" : "transparent" }}>
                  <span style={{ color: T.ink, fontSize: 14 }}>
                    <input type="checkbox" checked={selected.has(t.key)} onChange={() => toggleTool(t.key)} /> {t.label}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, whiteSpace: "nowrap",
                    color: t.cost_num > 0 ? "#a86710" : T.accent }}>{t.cost_num > 0 ? t.cost : "Free"}</span>
                </label>
              ))}
            </div>
          );
        })}
        <div style={{ padding: ".7rem .9rem", display: "flex", justifyContent: "space-between", alignItems: "center", background: T.panel }}>
          <span style={{ color: T.muted, fontSize: 14 }}>{selected.size} of {catalog.length} tools · est <b style={{ color: "#a86710" }}>~${estCost.toFixed(4)}</b></span>
          <button onClick={run} disabled={busy || selected.size === 0}
            style={{ padding: ".6rem 1.4rem", background: busy || selected.size === 0 ? "#b7bdc4" : T.accent, color: "#fff", border: 0,
              borderRadius: 8, fontWeight: 600, fontSize: 14, cursor: busy || selected.size === 0 ? "not-allowed" : "pointer", transition: "background .15s ease" }}>
            {busy ? "Measuring…" : `Run Measure (${selected.size})`}
          </button>
        </div>
      </div>

      {data?.error && <pre style={{ background: "#fee", padding: "1rem" }}>{data.error}</pre>}

      {busy && phaseLine && (
        <div style={{ display: "flex", alignItems: "center", gap: ".6rem", margin: "1rem 0", padding: ".7rem .9rem",
          background: "#eef2ff", border: `1px solid ${T.line}`, borderRadius: 10, color: T.ink, fontWeight: 600 }}>
          <span aria-hidden style={{ width: 16, height: 16, borderRadius: "50%", border: "2px solid #b7c3ff", borderTopColor: T.accent, animation: "spin 0.8s linear infinite" }} />
          {phaseLine}…
          <style>{"@keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){*{animation:none!important}}"}</style>
        </div>
      )}

      {(a || tools.length > 0) && (() => {
        const runCost = (data?.audit?.cost) ?? tools.reduce((s, t) => s + (t.cost || 0), 0);
        const err = a ? (a.counts.error || 0) : tools.reduce((s, t) => s + sevCounts(t.rows).error, 0);
        const wrn = a ? (a.counts.warn || 0) : tools.reduce((s, t) => s + sevCounts(t.rows).warn, 0);
        const okc = a ? (a.counts.ok || 0) : tools.reduce((s, t) => s + sevCounts(t.rows).ok, 0);
        const score = a?.score ?? 0;
        const sColor = score >= 80 ? SEV.ok.fg : score >= 50 ? SEV.warn.fg : SEV.error.fg;
        const chip = (key: typeof filter, label: string, sv: { fg: string }) => (
          <button onClick={() => setFilter(filter === key ? "all" : key)}
            style={{ cursor: "pointer", padding: ".32rem .8rem", borderRadius: 20, fontWeight: 600, fontSize: 13, font,
              border: `1.5px solid ${sv.fg}`, color: filter === key ? "#fff" : sv.fg, background: filter === key ? sv.fg : T.bg,
              transition: "background .15s ease, color .15s ease" }}>
            {label}
          </button>
        );
        return (
          <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", flexWrap: "wrap", margin: "1.25rem 0", padding: "1rem 1.15rem", background: T.panel, border: `1px solid ${T.line}`, borderRadius: 12 }}>
            {a && (
              <div style={{ width: 82, height: 82, borderRadius: "50%", display: "grid", placeItems: "center", flexShrink: 0,
                background: `conic-gradient(${sColor} ${score * 3.6}deg, ${T.line} 0deg)` }}>
                <div style={{ width: 64, height: 64, borderRadius: "50%", background: T.bg, display: "grid", placeItems: "center" }}>
                  <span style={{ fontSize: "1.5rem", fontWeight: 800, color: sColor, lineHeight: 1 }}>{score}</span>
                </div>
              </div>
            )}
            <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap", alignItems: "center" }}>
              {chip("error", `${err} errors`, SEV.error)}
              {chip("warn", `${wrn} warnings`, SEV.warn)}
              {chip("ok", `${okc} passing`, SEV.ok)}
              {filter !== "all" && <button onClick={() => setFilter("all")} style={linkBtn(T.muted)}>clear ✕</button>}
            </div>
            <div style={{ marginLeft: "auto", textAlign: "right" }}>
              <div style={{ color: "#a86710", fontWeight: 700, fontSize: "1.15rem" }}>${runCost.toFixed(4)}</div>
              <div style={{ fontSize: 12, color: T.faint }}>cost this run</div>
            </div>
          </div>
        );
      })()}

      {/* Results grouped by functional section — each tool card loads live,
          then fills with its result + cost. The filter chips narrow rows; a
          section with no matching cards is hidden. */}
      {cats.map((cat) => {
        const cards = tools.filter((t) => catOf(t.name) === cat).map(renderCard).filter(Boolean);
        if (!cards.length) return null;
        return (
          <section key={cat} style={{ margin: "1.4rem 0 .3rem" }}>
            <h3 style={{ font, fontSize: 12, fontWeight: 700, letterSpacing: ".04em", textTransform: "uppercase", color: T.faint, margin: "0 0 .55rem" }}>{cat}</h3>
            {cards}
          </section>
        );
      })}

      {/* ── Plan stage — ratchet the stored findings into a worklist ──────── */}
      {(tools.length > 0 || plan) && !busy && (
        <div style={{ margin: "1.5rem 0", padding: "1rem", border: `1px solid ${T.line}`, borderRadius: 10, background: T.panel }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <b style={{ color: T.ink }}>Plan — what to fix first</b>
            <button onClick={runPlan} disabled={planBusy || !clientId}
              style={{ padding: ".5rem 1.1rem", background: planBusy || !clientId ? "#b7bdc4" : T.accent, color: "#fff", border: 0, borderRadius: 8, fontWeight: 600, fontSize: 13, cursor: planBusy || !clientId ? "not-allowed" : "pointer" }}>
              {planBusy ? "Building…" : "Build plan"}
            </button>
          </div>
          {plan && (
            <div style={{ marginTop: ".8rem" }}>
              <div style={{ fontSize: 13, color: T.muted, marginBottom: ".6rem" }}>
                {plan.counts.NEW || 0} new · {plan.counts.REGRESSION || 0} regressions · {plan.counts.PERSISTING || 0} persisting · <span style={{ color: T.accent }}>{plan.counts.RESOLVED || 0} resolved ✓</span>
              </div>
              {plan.worklist.length === 0 && <div style={{ color: T.muted }}>No open issues to fix — clean scan.</div>}
              {plan.worklist.map((w, i) => (
                <div key={i} style={{ display: "flex", gap: ".6rem", padding: ".5rem .6rem", borderRadius: 8, background: T.bg, marginBottom: ".35rem", border: `1px solid ${T.line}` }}>
                  <span style={{ flexShrink: 0, width: 22, textAlign: "right", color: T.faint, fontWeight: 700 }}>{w.priority}</span>
                  <div style={{ minWidth: 0 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#fff", background: STATUS_COLOR[w.status] || T.muted, borderRadius: 6, padding: "1px .4rem", marginRight: ".4rem" }}>{w.status}</span>
                    <b style={{ color: T.ink }}>{w.what}</b>
                    {w.tool && <span style={{ color: T.faint, fontSize: 12 }}> · {w.tool}</span>}
                    <div style={{ fontSize: 13, marginTop: 1 }}><span style={{ color: SEV[w.severity]?.fg, fontWeight: 600 }}>Fix:</span> {w.fix}</div>
                  </div>
                </div>
              ))}
              {plan.resolved.length > 0 && (
                <details style={{ marginTop: ".6rem", color: T.accent }}>
                  <summary>{plan.resolved.length} resolved since last scan (wins)</summary>
                  <ul style={{ lineHeight: 1.7, color: T.muted }}>{plan.resolved.map((r, i) => <li key={i}>{r.what}</li>)}</ul>
                </details>
              )}
            </div>
          )}
        </div>
      )}

      {data?.log && data.log.length > 0 && !busy && (
        <details style={{ margin: "1rem 0", color: "#555" }}>
          <summary>What we did (full log)</summary>
          <ul style={{ lineHeight: 1.8 }}>{data.log.map((ln, i) => <li key={i}>{ln}</li>)}</ul>
        </details>
      )}

      {c && c.model === "B" && (
        <div><h2>Fix (Model B)</h2>
          <p>Decision: <b>{c.decision.action}</b> — {c.decision.reason}</p>
          <pre style={{ background: "#f6f6f6", padding: "1rem", overflow: "auto" }}>{c.diff}</pre>
        </div>
      )}
      {c && c.model === "A" && (
        <div><h2>Brief (Model A)</h2>
          <pre style={{ background: "#f6f6f6", padding: "1rem", overflow: "auto" }}>{c.brief}</pre>
        </div>
      )}
    </main>
  );
}
