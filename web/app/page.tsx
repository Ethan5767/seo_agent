"use client";
import { useState } from "react";

type Row = { code: string; what: string; why: string; fix: string; detail: string; severity: string };
type Audit = { seo: Row[]; aeo: Row[]; perf: Row[]; score: number; counts: Record<string, number> };
type Cycle =
  | { model: "A"; brief: string; worklist: unknown[] }
  | { model: "B"; diff: string; decision: { action: string; reason: string } };
type ScanResult = { audit?: Audit; cycle?: Cycle; error?: string; log?: string[] };

const COLOR: Record<string, string> = { error: "#b00", warn: "#a60", info: "#999", ok: "#1a5" };

function Rows({ list }: { list: Row[] }) {
  return (
    <>
      {list.map((r, i) => (
        <div key={i} style={{ padding: ".5rem", borderLeft: `4px solid ${COLOR[r.severity] || "#ccc"}`, marginBottom: ".4rem" }}>
          <b>{r.severity.toUpperCase()}</b> {r.what} {r.detail ? `(${r.detail})` : ""}
          <div>{r.why}</div>
          <div><i>Fix:</i> {r.fix}</div>
        </div>
      ))}
    </>
  );
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [repo, setRepo] = useState("");
  const [model, setModel] = useState("B");
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<ScanResult | null>(null);

  async function run() {
    setBusy(true);
    setData(null);
    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        body: JSON.stringify({ url, repo, model }),
      });
      setData(await res.json());
    } catch (e) {
      setData({ error: String(e) });
    } finally {
      setBusy(false);
    }
  }

  const a = data?.audit;
  const c = data?.cycle;

  return (
    <main>
      <h1>SEO / AEO Pipeline — Scan</h1>
      <p style={{ background: "#eef", padding: ".75rem", borderRadius: 6 }}>
        <b>Model A:</b> we never touch your code — we hand you the fix.{" "}
        <b>Model B:</b> we fix it, gate it, and decide. Paste a URL (and a repo path to fix it).
      </p>

      <input style={{ width: "100%", padding: ".5rem", margin: ".25rem 0", boxSizing: "border-box" }}
        placeholder="https://yoursite.com/page/" value={url} onChange={(e) => setUrl(e.target.value)} />
      <input style={{ width: "100%", padding: ".5rem", margin: ".25rem 0", boxSizing: "border-box" }}
        placeholder="/path/to/repo  (optional — needed to fix)" value={repo} onChange={(e) => setRepo(e.target.value)} />
      <select value={model} onChange={(e) => setModel(e.target.value)} style={{ padding: ".5rem", margin: ".25rem .5rem .25rem 0" }}>
        <option value="B">Model B (we fix the code)</option>
        <option value="A">Model A (brief only)</option>
      </select>
      <button onClick={run} disabled={busy}
        style={{ padding: ".6rem 1.2rem", background: "#1a5", color: "#fff", border: 0, borderRadius: 6, cursor: "pointer" }}>
        {busy ? "Running… (a real fix can take 10-60s)" : "Run"}
      </button>

      {data?.error && <pre style={{ background: "#fee", padding: "1rem" }}>{data.error}</pre>}

      {a && (
        <div>
          <div style={{ fontSize: "2rem", fontWeight: 700, margin: "1rem 0" }}>Score {a.score}/100</div>
          <h2>SEO</h2><Rows list={a.seo} />
          <h2>AEO (AI answer engines)</h2><Rows list={a.aeo} />
          <h2>Performance</h2><Rows list={a.perf} />
        </div>
      )}

      {c && c.model === "B" && (
        <div>
          <h2>Fix (Model B)</h2>
          <p>Decision: <b>{c.decision.action}</b> — {c.decision.reason}</p>
          <pre style={{ background: "#f6f6f6", padding: "1rem", overflow: "auto" }}>{c.diff}</pre>
        </div>
      )}
      {c && c.model === "A" && (
        <div>
          <h2>Brief (Model A)</h2>
          <pre style={{ background: "#f6f6f6", padding: "1rem", overflow: "auto" }}>{c.brief}</pre>
        </div>
      )}

      {data?.log && data.log.length > 0 && (
        <div>
          <h2>What we did</h2>
          <ul style={{ lineHeight: 1.8 }}>
            {data.log.map((ln, i) => <li key={i}>{ln}</li>)}
          </ul>
        </div>
      )}
    </main>
  );
}
