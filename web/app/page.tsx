"use client";
import { useState, useEffect } from "react";
import { AuthGate } from "./auth";
import { saveClient, saveScan } from "../lib/db";
import { listRepos } from "../lib/github";

type Row = { code: string; what: string; why: string; fix: string; detail: string; severity: string };
type Audit = {
  seo: Row[]; aeo: Row[]; perf: Row[]; tech: Row[]; site: Row[]; rankings: Row[]; keywords: Row[]; ai: Row[];
  score: number; counts: Record<string, number>;
};
type Cycle =
  | { model: "A"; brief: string; worklist: unknown[] }
  | { model: "B"; diff: string; decision: { action: string; reason: string } };
type ScanResult = { audit?: Audit; cycle?: Cycle; error?: string; log?: string[] };
type Tool = { name: string; state: string; rows: Row[]; status: string; cost: number };

const COLOR: Record<string, string> = { error: "#b00", warn: "#a60", info: "#999", ok: "#1a5" };
const box = { padding: ".5rem", margin: ".25rem 0", width: "100%", boxSizing: "border-box" as const };

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
  // Measure options
  const [crawl, setCrawl] = useState(false);
  const [deep, setDeep] = useState(false);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<string[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [data, setData] = useState<ScanResult | null>(null);

  async function run() {
    setBusy(true); setData(null); setLive([]); setTools([]);
    const toolMap = new Map<string, Tool>();
    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        body: JSON.stringify({ url, repo, model, crawl, deep, business, keywords: kwList, competitors, goal, max_pages: 25 }),
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
            saveScan(clientId || "", { url, model, crawl, deep }, ev.result.audit || {}, ev.result.log || []);
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

      <label style={{ display: "block", margin: ".25rem 0" }}>
        <input type="checkbox" checked={crawl} onChange={(e) => setCrawl(e.target.checked)} />{" "}
        Site audit — crawl the whole site via DataForSEO (JS-aware; finds broken links, orphans, duplicates · 💰 paid, ~$0.0003/page)
      </label>
      <label style={{ display: "block", margin: ".25rem 0" }}>
        <input type="checkbox" checked={deep} onChange={(e) => setDeep(e.target.checked)} />{" "}
        Deep scan — rankings via DataForSEO (💰 paid, ~$0.01-0.05 per run)
      </label>
      <button onClick={run} disabled={busy}
        style={{ padding: ".6rem 1.2rem", background: "#1a5", color: "#fff", border: 0, borderRadius: 6, cursor: "pointer" }}>
        {busy ? "Measuring…" : "Run Measure"}
      </button>

      {data?.error && <pre style={{ background: "#fee", padding: "1rem" }}>{data.error}</pre>}

      {(a || tools.length > 0) && (
        <div style={{ margin: "1rem 0" }}>
          {a && <span style={{ fontSize: "2rem", fontWeight: 700 }}>Score {a.score}/100</span>}
          {a && <span style={{ color: "#555", marginLeft: "1rem" }}>
            {a.counts.error || 0} errors · {a.counts.warn || 0} warnings · {a.counts.ok || 0} passing
          </span>}
          <div style={{ marginTop: ".25rem", color: "#a60", fontWeight: 600 }}>
            Cost this run: ${((data?.audit?.cost) ?? tools.reduce((s, t) => s + (t.cost || 0), 0)).toFixed(4)}
          </div>
        </div>
      )}

      {/* One card per tool — loads live, then fills with its result + cost. */}
      {tools.map((t) => (
        <div key={t.name} style={{ border: "1px solid #ddd", borderRadius: 8, margin: ".75rem 0", overflow: "hidden" }}>
          <div style={{ background: "#f7f7f7", padding: ".6rem .9rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <b>{t.state === "running" ? "⏳" : "✓"} {t.name}</b>
            <span style={{ color: "#666", fontSize: 13 }}>
              {t.state === "running" ? "running…" : t.status}
              {" · "}<span style={{ color: t.cost > 0 ? "#a60" : "#1a5" }}>{t.cost > 0 ? `$${t.cost.toFixed(4)}` : "free"}</span>
            </span>
          </div>
          {t.state === "done" && <div style={{ padding: ".5rem .9rem" }}><Rows list={t.rows} /></div>}
        </div>
      ))}

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
