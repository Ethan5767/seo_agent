// Persistence helpers — save the Onboard client and each Measure scan. RLS keys
// off the logged-in user, so these only work for a signed-in session; user_id is
// stamped from the current session.
import { supabase } from "./supabase";
import { authedFetch } from "./authedFetch";

export type ClientProfile = {
  business: string; domain: string; website: string; model: string;
  repo: string; tier: number; keywords: string[]; competitors: string[]; goal: string;
};

async function uid(): Promise<string | null> {
  const { data } = await supabase.auth.getUser();
  return data.user?.id ?? null;
}

async function authHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  try {
    const { data } = await supabase.auth.getSession();
    const token = data?.session?.access_token;
    if (token) {
      return { ...extra, Authorization: `Bearer ${token}` };
    }
  } catch {}
  return extra;
}

/** Insert a client row, return its id (or null if not signed in / failed). */
export async function saveClient(p: ClientProfile): Promise<string | null> {
  try {
    const headers = await authHeaders({ "Content-Type": "application/json" });
    const res = await fetch("/api/clients", {
      method: "POST",
      headers,
      body: JSON.stringify(p),
    });
    if (res.ok) {
      const json = await res.json();
      return json.client?.id || null;
    }
  } catch (e) {
    console.error("saveClient API error", e);
  }

  // Fallback to client-side supabase if authenticated
  const user_id = await uid();
  if (!user_id) return null;
  const { data, error } = await supabase
    .from("clients")
    .insert({ ...p, user_id })
    .select("id")
    .single();
  if (error) { console.error("saveClient fallback", error); return null; }
  return data.id;
}

/**
 * Correct a project that already exists.
 *
 * "I create a project, done — I also want to edit those details too. Example: I
 * put the wrong website URL, so I should be able to edit it."
 *
 * Only the keys present are sent, so a form that does not carry a field cannot
 * blank it. There is deliberately NO supabase fallback like `saveClient` has:
 * the route derives `domain` from the validated `website`, and a direct table
 * write would skip that and leave the two disagreeing — a project that scans one
 * site and reports another.
 */
export async function updateClient(
  id: string,
  patch: Partial<ClientProfile>,
): Promise<{ ok: true; client: any; domainChanged: DomainChange | null } | { ok: false; error: string }> {
  try {
    const res = await authedFetch(`/api/clients/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { ok: false, error: json?.error || `Update failed (HTTP ${res.status})` };
    }
    return { ok: true, client: json.client, domainChanged: json.domainChanged ?? null };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** Reported when the site a project points at changes under existing scans. */
export type DomainChange = { from: string; to: string; staleScans: number };

export type FindingRow = { code: string; what: string; why: string; fix: string; detail: string; severity: string; tool?: string };
type ToolEvent = { name: string; state: string; rows: FindingRow[]; status: string; cost: number };

// Insert that degrades quietly when the target table hasn't been migrated yet
// (42P01 / PGRST205) — so a not-yet-run migration never trips the dev overlay.
async function quietInsert(table: string, rows: unknown): Promise<void> {
  const { error } = await supabase.from(table).insert(rows as never);
  if (error && error.code !== "42P01" && error.code !== "PGRST205") console.warn(`insert ${table}`, error.message || error.code);
}

const _int = (v: string | undefined | null): number | null => {
  if (!v) return null; const n = parseInt(v.replace(/,/g, ""), 10); return isNaN(n) ? null : n;
};
// Which category a finding belongs to, from its stable code prefix.
function categoryOf(code: string): string {
  const c = code || "";
  if (c.startsWith("lh.")) return "Lighthouse";
  if (c.startsWith("crux") || c.includes("perf")) return "Performance";
  if (c.startsWith("aeo.")) return "AEO";
  if (c.startsWith("src.")) return "Source code";
  if (c.startsWith("content.")) return "Content";
  if (c.startsWith("health.") || c.startsWith("dfs.")) return "SEO";
  if (c.startsWith("video")) return "Media";
  return "General";
}

const _GROUPS = ["seo", "aeo", "perf", "tech", "site", "rankings", "keywords", "ai", "source"];
type ReportLike = Record<string, unknown> & { counts?: Record<string, number>; score?: number };

/** Flat headline metrics for one scan — the numbers a trend chart reads without
 *  digging through report jsonb. Derived from what every scan always has. */
function deriveScanMetrics(report: ReportLike, cost: number) {
  const rows = (k: string) => (Array.isArray(report[k]) ? (report[k] as FindingRow[]) : []);
  const all = _GROUPS.flatMap(rows);
  const cn = report.counts || {};
  const aeo = rows("aeo");
  const aeoOk = aeo.filter((r) => r.severity === "ok").length;
  const rankings = rows("rankings");
  const bl = rows("backlinks");
  let backlinks: number | null = null, refDomains: number | null = null;
  for (const r of bl) {
    const b = r.detail?.match(/([\d,]+)\s*backlink/i); if (b) backlinks = _int(b[1]);
    const d = r.detail?.match(/([\d,]+)\s*(?:referring|ref)\s*domain/i); if (d) refDomains = _int(d[1]);
  }
  return {
    score: report.score ?? null,
    n_error: cn.error || 0, n_warn: cn.warn || 0, n_info: cn.info || 0, n_ok: cn.ok || 0,
    checks_total: all.length,
    cost: cost || 0,
    ai_visibility: aeo.length ? Math.round((100 * aeoOk) / aeo.length) : null,
    organic_keywords: rankings.length || null,
    organic_traffic: null,
    backlinks, ref_domains: refDomains,
  };
}

/** Ranked keywords parsed from the report's rankings rows (best-effort). */
function deriveKeywords(report: ReportLike): Array<{ keyword: string; position: number | null; volume: number | null; intent: string; url: string }> {
  const rows = Array.isArray(report.rankings) ? (report.rankings as FindingRow[]) : [];
  return rows.map((r) => {
    const q = r.what?.match(/"([^"]+)"/);
    const keyword = q ? q[1] : (r.what || "").replace(/—.*$/, "").trim();
    const pos = r.what?.match(/rank #?(\d+)/i) || r.detail?.match(/position (\d+)/i);
    const vol = r.detail?.match(/~?([\d,]+)\s*\/\s*mo/i);
    return { keyword, position: _int(pos?.[1]), volume: _int(vol?.[1]), intent: "", url: (r as { pages?: string[] }).pages?.[0] || "" };
  }).filter((k) => k.keyword);
}

/** Insert a scan and its normalized children (scan_tools + findings).
 *  Best-effort — never blocks the UI. Stores everything: the full report
 *  snapshot on `scans.report`, one row per tool, one row per finding. */
export async function saveScan(
  clientId: string,
  opts: { url: string; model: string; tools: string[] },
  audit: { score?: number; counts?: unknown } & Record<string, unknown>,
  log: string[],
  toolEvents: ToolEvent[] = [],
): Promise<void> {
  // Always trigger server-side persistence with service role key
  try {
    const headers = await authHeaders({ "Content-Type": "application/json" });
    const res = await fetch(`/api/clients/${clientId}/scans`, {
      method: "POST",
      headers,
      body: JSON.stringify({ opts, audit, log, toolEvents }),
    });
    if (res.ok) {
      return;
    }
  } catch (e) {
    console.error("saveScan API error, attempting direct supabase fallback", e);
  }

  const user_id = await uid();
  if (!user_id || !clientId) return;

  const { data, error } = await supabase.from("scans").insert({
    client_id: clientId, user_id,
    url: opts.url, model: opts.model, tools: opts.tools,
    score: audit?.score ?? null, counts: audit?.counts ?? {},
    cost: (audit as { cost?: number })?.cost ?? 0,
    report: audit ?? {}, log: log ?? [],
  }).select("id").single();
  if (error || !data) { console.error("saveScan", error); return; }
  const scan_id = data.id;

  const done = toolEvents.filter((t) => t.state === "done");
  const count = (rows: FindingRow[], sev: string) => rows.filter((r) => r.severity === sev).length;

  const toolRows = done.map((t) => ({
    scan_id, user_id, tool: t.name, status: t.status || "", cost: t.cost || 0,
    n_error: count(t.rows, "error"), n_warn: count(t.rows, "warn"),
    n_info: count(t.rows, "info"), n_ok: count(t.rows, "ok"),
    result: t.rows || [],   // the tool's complete result, kept per-tool
  }));
  if (toolRows.length) {
    const { error: e2 } = await supabase.from("scan_tools").insert(toolRows);
    if (e2) console.error("saveScan.scan_tools", e2);
  }

  const findingRows = done.flatMap((t) =>
    (t.rows || []).map((r) => ({
      scan_id, user_id, tool: t.name,
      code: r.code || "", what: r.what || "", severity: r.severity || "",
      why: r.why || "", fix: r.fix || "", detail: r.detail || "",
      category: categoryOf(r.code || ""),
      finding_fp: r.code || "",
    })),
  );
  if (findingRows.length) {
    const { error: e3 } = await supabase.from("findings").insert(findingRows);
    if (e3) console.error("saveScan.findings", e3);
  }

  // ── v2: track everything over time in normalized tables (best-effort; each
  //    degrades quietly if its table hasn't been migrated yet) ────────────────
  const report = (audit || {}) as ReportLike;
  const cost = (audit as { cost?: number })?.cost ?? 0;
  const m = deriveScanMetrics(report, cost);
  await quietInsert("scan_metrics", { scan_id, client_id: clientId, user_id, ...m });

  const kws = deriveKeywords(report);
  if (kws.length) await quietInsert("keywords", kws.map((k) => ({ scan_id, client_id: clientId, user_id, ...k })));

  if (m.backlinks !== null || m.ref_domains !== null) {
    await quietInsert("backlink_snapshots", { scan_id, client_id: clientId, user_id, backlinks: m.backlinks, ref_domains: m.ref_domains, toxic: null });
  }
}

// ── History dashboard reads (pure DB, no scanner, no paid API) ───────────────

export type ClientRow = ClientProfile & { id: string; created_at?: string };
export type ClientWithStats = ClientRow & {
  scans: number; lastScore: number | null; lastScannedAt: string | null;
  lastCounts: Record<string, number> | null;
  lastScanId?: string | null;
};
export type ScanRow = {
  id: string; created_at: string; url: string;
  score: number | null; counts: Record<string, number> | null; cost: number | null;
};

/** Every client for the signed-in user, each with a cheap scan summary
 *  (count, latest score, last scanned). One clients read + one scans read;
 *  the aggregate is done client-side to keep it to two round-trips. */
export async function listClients(): Promise<ClientWithStats[]> {
  const user_id = await uid();
  if (!user_id) {
    try {
      const headers = await authHeaders();
      const res = await fetch("/api/clients", { headers });
      if (res.ok) {
        const json = await res.json();
        if (json.clients) return json.clients;
      }
    } catch (e) {
      console.error("listClients API fallback error", e);
    }
    return [];
  }
  const { data: clients, error } = await supabase
    .from("clients").select("*")
    .eq("user_id", user_id).order("created_at", { ascending: false });
  if (error || !clients) { console.error("listClients", error); return []; }

  const { data: scans, error: sErr } = await supabase
    .from("scans").select("id, client_id, score, counts, created_at")
    .eq("user_id", user_id).order("created_at", { ascending: false });
  if (sErr) console.error("listClients.scans", sErr);

  type Agg = { n: number; lastScore: number | null; lastAt: string | null; lastCounts: Record<string, number> | null; lastScanId: string | null };
  const byClient = new Map<string, Agg>();
  for (const s of scans || []) {
    const cur = byClient.get(s.client_id) || { n: 0, lastScore: null, lastAt: null, lastCounts: null, lastScanId: null };
    // scans arrive newest-first, so the first seen per client is the latest.
    if (cur.lastAt === null) {
      cur.lastScore = s.score ?? null;
      cur.lastAt = s.created_at;
      cur.lastCounts = (s.counts as Record<string, number>) ?? null;
      cur.lastScanId = s.id;
    }
    cur.n += 1;
    byClient.set(s.client_id, cur);
  }
  return (clients as ClientRow[]).map((c) => {
    const agg = byClient.get(c.id) || { n: 0, lastScore: null, lastAt: null, lastCounts: null, lastScanId: null };
    return { ...c, scans: agg.n, lastScore: agg.lastScore, lastScannedAt: agg.lastAt, lastCounts: agg.lastCounts, lastScanId: agg.lastScanId };
  });
}

export type RemediationItem = { code: string; url: string; status: string; note: string; files: string[] };
export type RemediationRow = {
  id: string; created_at: string; url: string; cycle: string;
  applied: number; cost_usd: number; diffstat: string; items: RemediationItem[];
};

/** Record one Model-B apply run against a client. Best-effort — never blocks the
 *  UI. Stores the applied count, cost, diffstat, and per-item outcomes. */
export async function saveRemediation(
  clientId: string,
  r: { url: string; cycle: string; applied: number; cost_usd: number; diffstat: string; items: RemediationItem[] },
): Promise<void> {
  const user_id = await uid();
  if (!user_id || !clientId) return;
  const { error } = await supabase.from("remediations").insert({
    client_id: clientId, user_id,
    url: r.url || "", cycle: r.cycle || "", applied: r.applied || 0,
    cost_usd: r.cost_usd || 0, diffstat: r.diffstat || "", items: r.items || [],
  });
  if (error && error.code !== "42P01" && error.code !== "PGRST205") console.warn("saveRemediation", error.message || error.code);
}

/** A client's remediation runs, newest-first, for the History timeline. */
export async function remediationHistory(clientId: string): Promise<RemediationRow[]> {
  if (!clientId) return [];
  const { data, error } = await supabase
    .from("remediations").select("id, created_at, url, cycle, applied, cost_usd, diffstat, items")
    .eq("client_id", clientId).order("created_at", { ascending: false });
  // The remediations table is optional (added by a later migration). If it's not
  // there yet, degrade quietly — no console.error (which would trip the dev overlay).
  if (error) { if (error.code !== "42P01" && error.code !== "PGRST205") console.warn("remediationHistory", error.message || error.code); return []; }
  return (data as RemediationRow[]) || [];
}

/** A client's scans, newest-first, for the history table + score trend. */
export async function scanHistory(clientId: string): Promise<ScanRow[]> {
  if (!clientId) return [];
  try {
    const { data, error } = await supabase
      .from("scans").select("id, created_at, url, score, counts, cost")
      .eq("client_id", clientId).order("created_at", { ascending: false });
    if (!error && data && data.length > 0) return data as ScanRow[];
  } catch {}

  try {
    const headers = await authHeaders();
    const res = await fetch(`/api/clients/${clientId}/scans`, { headers });
    if (res.ok) {
      const json = await res.json();
      const list = json.scans || (Array.isArray(json) ? json : []);
      if (Array.isArray(list)) return list as ScanRow[];
    }
  } catch (e) {
    console.error("scanHistory API fallback failed", e);
  }
  return [];
}

/** The stored full report snapshot for one scan — reopen a past Measure result
 *  with no re-scan and no paid call. Null if missing / not readable. */
export async function getScanReport(scanId: string): Promise<Record<string, unknown> | null> {
  if (!scanId) return null;
  try {
    const { data, error } = await supabase
      .from("scans").select("report").eq("id", scanId).single();
    if (!error && data?.report) return data.report as Record<string, unknown>;
  } catch {}

  try {
    const headers = await authHeaders();
    const res = await fetch(`/api/clients/scans/${scanId}`, { headers });
    if (res.ok) {
      const json = await res.json();
      if (json.report) return json.report;
      if (json.scan?.report) return json.scan.report;
    }
  } catch (e) {
    console.error("getScanReport API fallback failed", e);
  }
  return null;
}

/** The findings from a client's two most recent scans — {current, previous} —
 *  for the Plan-stage ratchet. `previous` is [] when only one scan exists. */
export async function lastTwoScansFindings(
  clientId: string,
): Promise<{ current: FindingRow[]; previous: FindingRow[]; currentScanId?: string }> {
  const empty = { current: [], previous: [] };
  if (!clientId) return empty;
  const { data: scans, error } = await supabase
    .from("scans").select("id, created_at")
    .eq("client_id", clientId).order("created_at", { ascending: false }).limit(2);
  if (error) { console.error("lastTwoScansFindings.scans", error); return empty; }
  if (!scans?.length) return empty;

  const findingsFor = async (scanId: string): Promise<FindingRow[]> => {
    const { data, error: fErr } = await supabase
      .from("findings").select("code, what, why, fix, detail, severity, tool")
      .eq("scan_id", scanId);
    // Surface a real read failure — a silent [] would fake a clean/all-NEW plan.
    if (fErr) { console.error("lastTwoScansFindings.findings", fErr); throw fErr; }
    return (data as FindingRow[]) || [];
  };
  const current = await findingsFor(scans[0].id);
  const previous = scans[1] ? await findingsFor(scans[1].id) : [];
  return { current, previous, currentScanId: scans[0].id };
}
