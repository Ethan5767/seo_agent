"use client";
import { useState, useEffect } from "react";
import { AuthGate } from "./auth";
import { saveClient, saveScan } from "../lib/db";
import { listRepos } from "../lib/github";
import { supabase } from "../lib/supabase";

type Row = { code: string; what: string; why: string; fix: string; detail: string; severity: string };
type Audit = {
  seo: Row[]; aeo: Row[]; perf: Row[]; tech: Row[]; site: Row[]; rankings: Row[]; keywords: Row[]; ai: Row[]; source: Row[];
  score: number; counts: Record<string, number>; cost?: number;
};
type Cycle =
  | { model: "A"; brief: string; worklist: unknown[] }
  | { model: "B"; diff: string; decision: { action: string; reason: string } };
type ScanResult = { audit?: Audit; cycle?: Cycle; error?: string; log?: string[] };
type Tool = { name: string; state: string; rows: Row[]; status: string; cost: number };
type CatalogTool = { key: string; label: string; group: string; cost: string; cost_num: number };

const COLOR: Record<string, string> = { error: "#b00", warn: "#a60", info: "#999", ok: "#1a5" };
const box = { padding: ".5rem", margin: ".25rem 0", width: "100%", boxSizing: "border-box" as const };

// The tool groups, in display order — mirrors the backend `group` field.
const GROUPS: { key: string; title: string; note: string }[] = [
  { key: "free", title: "Free tools", note: "run on the page we already fetched — no cost" },
  { key: "dataforseo", title: "DataForSEO (paid)", note: "live API data — costs per call" },
  { key: "source", title: "Source code", note: "read-only, needs a connected GitHub repo" },
];

function sevCounts(rows: Row[]) {
  const c = { error: 0, warn: 0, ok: 0 };
  for (const r of rows) { if (r.severity === "error") c.error++; else if (r.severity === "warn") c.warn++; else if (r.severity === "ok") c.ok++; }
  return c;
}

function Rows({ list }: { list?: Row[] }) {
  return (
    <>
      {(list || []).map((r, i) => (
        <div key={i} style={{ padding: ".5rem", borderLeft: `4px solid ${COLOR[r.severity] || "#ccc"}`, marginBottom: ".4rem" }}>
          <b>{r.severity === "ok" ? "✓ PASS" : r.severity.toUpperCase()}</b> {r.what} {r.detail ? `(${r.detail})` : ""}
          <div>{r.why}</div>
          {r.severity !== "ok" && <div><i>Fix:</i> {r.fix}</div>}
        </div>
      ))}
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
    }).catch(() => {});
  }, []);
  const [filter, setFilter] = useState<"all" | "error" | "warn" | "ok">("all");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<string[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [data, setData] = useState<ScanResult | null>(null);

  function toggleTool(key: string) {
    setSelected((s) => { const n = new Set(s); n.has(key) ? n.delete(key) : n.add(key); return n; });
  }
  function setGroup(groupKey: string, on: boolean) {
    setSelected((s) => {
      const n = new Set(s);
      for (const t of catalog) if (t.group === groupKey) { on ? n.add(t.key) : n.delete(t.key); }
      return n;
    });
  }
  const estCost = catalog.filter((t) => selected.has(t.key)).reduce((s, t) => s + (t.cost_num || 0), 0);

  async function run() {
    setBusy(true); setData(null); setLive([]); setTools([]);
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
          if (ev.tool) {
            toolMap.set(ev.tool, { name: ev.tool, state: ev.state, rows: ev.rows || [], status: ev.status || "", cost: ev.cost || 0 });
            setTools([...toolMap.values()]);
          } else if (ev.log !== undefined) { lines.push(ev.log); setLive([...lines]); }
          else if (ev.result) {
            setData(ev.result);
            saveScan(clientId || "", { url, model, tools: [...selected] }, ev.result.audit || {}, ev.result.log || []);
          }
          else if (ev.error) setData({ error: ev.error, log: ev.log });
        }
      }
    } catch (e) {
      setData({ error: String(e) });
    } finally {
      setBusy(false);
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

      {/* ── Tool checklist — pick which Measure tools run ─────────────────── */}
      <div style={{ border: "1px solid #ddd", borderRadius: 8, overflow: "hidden", margin: "1rem 0" }}>
        <div style={{ background: "#eef2ff", padding: ".6rem .9rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <b>Tools to run</b>
          <span style={{ fontSize: 13, color: "#555" }}>
            <a onClick={() => setSelected(new Set(catalog.map((t) => t.key)))} style={{ color: "#1a5", cursor: "pointer" }}>all</a>
            {" · "}
            <a onClick={() => setSelected(new Set())} style={{ color: "#a00", cursor: "pointer" }}>none</a>
          </span>
        </div>
        {GROUPS.filter((g) => catalog.some((t) => t.group === g.key)).map((g) => {
          const groupTools = catalog.filter((t) => t.group === g.key);
          const allOn = groupTools.every((t) => selected.has(t.key));
          return (
            <div key={g.key} style={{ borderTop: "1px solid #eee" }}>
              <div style={{ padding: ".4rem .9rem", background: "#fafafa", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <label style={{ fontWeight: 600, cursor: "pointer" }}>
                  <input type="checkbox" checked={allOn} onChange={(e) => setGroup(g.key, e.target.checked)} />{" "}
                  {g.title} <span style={{ fontWeight: 400, color: "#888", fontSize: 12 }}>· {g.note}</span>
                </label>
              </div>
              {groupTools.map((t) => (
                <label key={t.key} style={{ display: "flex", justifyContent: "space-between", padding: ".3rem .9rem .3rem 1.8rem", cursor: "pointer" }}>
                  <span><input type="checkbox" checked={selected.has(t.key)} onChange={() => toggleTool(t.key)} /> {t.label}</span>
                  <span style={{ color: t.cost_num > 0 ? "#a60" : "#1a5", fontSize: 13 }}>{t.cost}</span>
                </label>
              ))}
            </div>
          );
        })}
        <div style={{ borderTop: "1px solid #eee", padding: ".55rem .9rem", display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f7f7f7" }}>
          <span style={{ color: "#555" }}>{selected.size} of {catalog.length} tools · est <b style={{ color: "#a60" }}>~${estCost.toFixed(4)}</b></span>
          <button onClick={run} disabled={busy || selected.size === 0}
            style={{ padding: ".55rem 1.3rem", background: busy || selected.size === 0 ? "#aaa" : "#1a5", color: "#fff", border: 0, borderRadius: 6, cursor: busy || selected.size === 0 ? "not-allowed" : "pointer" }}>
            {busy ? "Measuring…" : `Run Measure (${selected.size})`}
          </button>
        </div>
      </div>

      {data?.error && <pre style={{ background: "#fee", padding: "1rem" }}>{data.error}</pre>}

      {(a || tools.length > 0) && (() => {
        const runCost = (data?.audit?.cost) ?? tools.reduce((s, t) => s + (t.cost || 0), 0);
        const err = a ? (a.counts.error || 0) : tools.reduce((s, t) => s + sevCounts(t.rows).error, 0);
        const wrn = a ? (a.counts.warn || 0) : tools.reduce((s, t) => s + sevCounts(t.rows).warn, 0);
        const okc = a ? (a.counts.ok || 0) : tools.reduce((s, t) => s + sevCounts(t.rows).ok, 0);
        const score = a?.score ?? 0;
        const sColor = score >= 80 ? "#1a5" : score >= 50 ? "#a60" : "#b00";
        const chip = (key: typeof filter, label: string, color: string) => (
          <span onClick={() => setFilter(filter === key ? "all" : key)}
            style={{ cursor: "pointer", padding: ".25rem .7rem", borderRadius: 14, fontWeight: 600, fontSize: 13,
              border: `1.5px solid ${color}`, color: filter === key ? "#fff" : color, background: filter === key ? color : "#fff" }}>
            {label}
          </span>
        );
        return (
          <div style={{ display: "flex", alignItems: "center", gap: "1.25rem", flexWrap: "wrap", margin: "1.25rem 0", padding: "1rem", background: "#fafafa", border: "1px solid #eee", borderRadius: 10 }}>
            {a && (
              <div style={{ width: 84, height: 84, borderRadius: "50%", border: `6px solid ${sColor}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                <span style={{ fontSize: "1.6rem", fontWeight: 800, color: sColor, lineHeight: 1 }}>{score}</span>
                <span style={{ fontSize: 10, color: "#888" }}>/ 100</span>
              </div>
            )}
            <div style={{ display: "flex", gap: ".5rem", flexWrap: "wrap" }}>
              {chip("error", `${err} errors`, "#b00")}
              {chip("warn", `${wrn} warnings`, "#a60")}
              {chip("ok", `${okc} passing`, "#1a5")}
              {filter !== "all" && <span onClick={() => setFilter("all")} style={{ cursor: "pointer", fontSize: 13, color: "#666", alignSelf: "center" }}>clear filter ✕</span>}
            </div>
            <div style={{ marginLeft: "auto", textAlign: "right" }}>
              <div style={{ color: "#a60", fontWeight: 700, fontSize: "1.1rem" }}>${runCost.toFixed(4)}</div>
              <div style={{ fontSize: 12, color: "#888" }}>cost this run</div>
            </div>
          </div>
        );
      })()}

      {/* One card per tool — loads live, then fills with its result + cost.
          Filter chips above narrow the rows shown; a card with no matching
          rows under an active filter is hidden. */}
      {tools.map((t) => {
        const cnt = sevCounts(t.rows);
        const shown = filter === "all" ? t.rows : t.rows.filter((r) => r.severity === filter);
        if (t.state === "done" && filter !== "all" && shown.length === 0) return null;
        const badge = (n: number, color: string) => n > 0 ? (
          <span style={{ background: color, color: "#fff", borderRadius: 10, padding: "0 .5rem", fontSize: 12, fontWeight: 700, marginLeft: ".3rem" }}>{n}</span>
        ) : null;
        return (
          <div key={t.name} style={{ border: "1px solid #ddd", borderRadius: 8, margin: ".75rem 0", overflow: "hidden" }}>
            <div style={{ background: "#f7f7f7", padding: ".6rem .9rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <b>{t.state === "running" ? "⏳" : "✓"} {t.name}
                {t.state === "done" && <>{badge(cnt.error, "#b00")}{badge(cnt.warn, "#a60")}{badge(cnt.ok, "#1a5")}</>}
              </b>
              <span style={{ color: "#666", fontSize: 13 }}>
                {t.state === "running" ? "running…" : t.status}
                {" · "}<span style={{ color: t.cost > 0 ? "#a60" : "#1a5" }}>{t.cost > 0 ? `$${t.cost.toFixed(4)}` : "free"}</span>
              </span>
            </div>
            {t.state === "done" && <div style={{ padding: ".5rem .9rem" }}><Rows list={shown} /></div>}
          </div>
        );
      })}

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
