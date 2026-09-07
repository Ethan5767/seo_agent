"use client";
import { useState } from "react";

type Row = { code: string; what: string; why: string; fix: string; detail: string; severity: string };
type Audit = { seo: Row[]; aeo: Row[]; perf: Row[]; tech: Row[]; site: Row[]; score: number; counts: Record<string, number> };
type Cycle =
  | { model: "A"; brief: string; worklist: unknown[] }
  | { model: "B"; diff: string; decision: { action: string; reason: string } };
type ScanResult = { audit?: Audit; cycle?: Cycle; error?: string; log?: string[] };

const COLOR: Record<string, string> = { error: "#b00", warn: "#a60", info: "#999", ok: "#1a5" };

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
  const [url, setUrl] = useState("");
  const [repo, setRepo] = useState("");
  const [model, setModel] = useState("B");
  const [crawl, setCrawl] = useState(false);
  const [busy, setBusy] = useState(false);
  const [data, setData] = useState<ScanResult | null>(null);

  const [live, setLive] = useState<string[]>([]);

  async function run() {
    setBusy(true);
    setData(null);
    setLive([]);
    try {
      const res = await fetch("/api/scan", {
        method: "POST",
        body: JSON.stringify({ url, repo, model, crawl, max_pages: 25 }),
      });
      const reader = res.body!.getReader();
      const dec = new TextDecoder();
      let buf = "";
      const lines: string[] = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split("\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          if (!part.trim()) continue;
          const ev = JSON.parse(part);
          if (ev.log !== undefined) { lines.push(ev.log); setLive([...lines]); }
          else if (ev.result) setData(ev.result);
          else if (ev.error) setData({ error: ev.error, log: ev.log });
        }
      }
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
      <label style={{ display: "block", margin: ".5rem 0" }}>
        <input type="checkbox" checked={crawl} onChange={(e) => setCrawl(e.target.checked)} />{" "}
        Scan the whole site (crawl up to 25 pages — slower, finds orphans/broken links/duplicates)
      </label>
      <button onClick={run} disabled={busy}
        style={{ padding: ".6rem 1.2rem", background: "#1a5", color: "#fff", border: 0, borderRadius: 6, cursor: "pointer" }}>
        {busy ? "Running… (a real fix can take 10-60s)" : "Run"}
      </button>

      {busy && live.length > 0 && (
        <div style={{ background: "#f4f7ff", border: "1px solid #cdd8ff", borderRadius: 6, padding: "1rem", margin: "1rem 0" }}>
          <b>Scanning…</b>
          <ul style={{ lineHeight: 1.7, margin: ".5rem 0 0" }}>
            {live.map((ln, i) => <li key={i}>{ln}</li>)}
          </ul>
        </div>
      )}

      {data?.error && <pre style={{ background: "#fee", padding: "1rem" }}>{data.error}</pre>}

      {data?.log && data.log.length > 0 && (
        <div style={{ background: "#f4f7ff", border: "1px solid #cdd8ff", borderRadius: 6, padding: "1rem", margin: "1rem 0" }}>
          <h2 style={{ marginTop: 0 }}>What we did</h2>
          <ul style={{ lineHeight: 1.8, margin: 0 }}>
            {data.log.map((ln, i) => <li key={i}>{ln}</li>)}
          </ul>
        </div>
      )}

      {a && (
        <div>
          <div style={{ fontSize: "2rem", fontWeight: 700, margin: "1rem 0 0" }}>Score {a.score}/100</div>
          <div style={{ color: "#555", marginBottom: "1rem" }}>
            {a.counts.error || 0} errors · {a.counts.warn || 0} warnings · {a.counts.ok || 0} passing
          </div>
          <h2>SEO</h2><Rows list={a.seo} />
          <h2>AEO (AI answer engines)</h2><Rows list={a.aeo} />
          <h2>Performance</h2><Rows list={a.perf} />
          <h2>Technical</h2><Rows list={a.tech} />
          {a.site && a.site.length > 0 && <><h2>Whole site</h2><Rows list={a.site} /></>}
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
    </main>
  );
}
