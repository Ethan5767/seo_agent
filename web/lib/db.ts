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
    // A project for this domain already exists: open it. Never fall through to
    // the direct insert below, which would create the duplicate the route refused.
    if (res.status === 409) {
      const json = await res.json().catch(() => ({}));
      return json.existingId || null;
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

export type KeywordHistoryPoint = { at: string; position: number | null };
export type KeywordSeries = {
  keyword: string;
  volume: number | null;
  points: KeywordHistoryPoint[];  // oldest first
  first: number | null;           // earliest measured position
  latest: number | null;          // most recent measured position
  delta: number | null;           // latest - first, negative = improved (moved up)
};

/**
 * Per-keyword position over time, for real rank tracking (not a snapshot).
 *
 * The `keywords` table already stores one row per keyword per scan (written by
 * `saveScan`), so the history is simply those rows grouped by keyword and
 * ordered by scan date. A keyword needs at least two scans to have a trend;
 * `points` still returns the single point so the caller can say "one reading so
 * far" rather than showing nothing. `delta` uses screen convention: a smaller
 * position number is better, so a negative delta is an improvement.
 */
export async function keywordRankHistory(clientId: string): Promise<KeywordSeries[]> {
  if (!clientId) return [];
  let data: Array<{ keyword: string; position: number | null; volume: number | null; created_at: string }> = [];
  try {
    const res = await supabase
      .from("keywords").select("keyword, position, volume, created_at")
      .eq("client_id", clientId).order("created_at", { ascending: true });
    if (res.error) { console.error("keywordRankHistory", res.error); return []; }
    data = (res.data as typeof data) || [];
  } catch (e) {
    console.error("keywordRankHistory", e);
    return [];
  }

  const byKeyword = new Map<string, KeywordSeries>();
  for (const r of data) {
    const kw = (r.keyword || "").trim();
    if (!kw) continue;
    let s = byKeyword.get(kw);
    if (!s) {
      s = { keyword: kw, volume: null, points: [], first: null, latest: null, delta: null };
      byKeyword.set(kw, s);
    }
    s.points.push({ at: r.created_at, position: r.position });
    if (typeof r.volume === "number") s.volume = r.volume;
  }

  const series: KeywordSeries[] = [];
  for (const s of byKeyword.values()) {
    const measured = s.points.filter((p) => typeof p.position === "number") as Array<{ at: string; position: number }>;
    s.first = measured.length ? measured[0].position : null;
    s.latest = measured.length ? measured[measured.length - 1].position : null;
    s.delta = s.first !== null && s.latest !== null ? s.latest - s.first : null;
    series.push(s);
  }
  // Most-tracked (most data points) first, then best current position.
  series.sort((a, b) => b.points.length - a.points.length || (a.latest ?? 999) - (b.latest ?? 999));
  return series;
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

/** Flatten a scan's `report` snapshot into finding rows, for scans whose
 *  normalized `findings` table has no rows — a report-only seed (the DEMO
 *  project), or a scan saved before findings were normalized. Without this a
 *  project that clearly has issues (its report shows 13) plans to an empty
 *  worklist.
 *
 *  The report scatters findings across MANY top-level keys, not just `_GROUPS`:
 *  the DEMO report's warn/error issues live under `eeat`, `video`, `content`,
 *  `lh_perf`, `backlinks`, etc. So we walk every top-level value and take any
 *  array whose elements look like findings (a `code` and a `severity`). The Plan
 *  route filters to error/warn, so the info/ok rows we pick up here are dropped
 *  there — including them costs nothing and missing a key costs the whole plan.
 *  Codes duplicated across keys are de-duped by the Plan route (highest severity
 *  wins). */
function findingsFromReport(report: unknown): FindingRow[] {
  if (!report || typeof report !== "object") return [];
  const out: FindingRow[] = [];
  for (const value of Object.values(report as Record<string, unknown>)) {
    if (!Array.isArray(value)) continue;
    for (const row of value as Array<Record<string, unknown>>) {
      if (!row || typeof row !== "object") continue;
      if (typeof row.code !== "string" || typeof row.severity !== "string") continue;
      out.push({
        code: String(row.code ?? ""),
        what: String(row.what ?? ""),
        why: String(row.why ?? ""),
        fix: String(row.fix ?? ""),
        detail: String(row.detail ?? ""),
        severity: String(row.severity ?? ""),
        tool: row.tool ? String(row.tool) : undefined,
      });
    }
  }
  return out;
}

/** The findings from a client's two most recent scans — {current, previous} —
 *  for the Plan-stage ratchet. `previous` is [] when only one scan exists.
 *  Falls back to the report snapshot when the normalized findings table is empty
 *  for a scan (see `findingsFromReport`). */
export async function lastTwoScansFindings(
  clientId: string,
): Promise<{ current: FindingRow[]; previous: FindingRow[]; currentScanId?: string }> {
  const empty = { current: [], previous: [] };
  if (!clientId) return empty;
  const { data: scans, error } = await supabase
    .from("scans").select("id, created_at, report")
    .eq("client_id", clientId).order("created_at", { ascending: false }).limit(2);
  if (error) { console.error("lastTwoScansFindings.scans", error); return empty; }
  if (!scans?.length) return empty;

  const findingsFor = async (scan: { id: string; report?: unknown }): Promise<FindingRow[]> => {
    const { data, error: fErr } = await supabase
      .from("findings").select("code, what, why, fix, detail, severity, tool")
      .eq("scan_id", scan.id);
    // Surface a real read failure — a silent [] would fake a clean/all-NEW plan.
    if (fErr) { console.error("lastTwoScansFindings.findings", fErr); throw fErr; }
    const rows = (data as FindingRow[]) || [];
    // No normalized rows -> derive from the report the scan always carries, so a
    // report-only project (DEMO, or a pre-normalization scan) still plans.
    return rows.length ? rows : findingsFromReport(scan.report);
  };
  const current = await findingsFor(scans[0]);
  const previous = scans[1] ? await findingsFor(scans[1]) : [];
  return { current, previous, currentScanId: scans[0].id };
}

/**
 * A project's two most recent saved reports, for the Site Audit project list
 * (current scores and the change since the scan before). Reads only the two
 * newest scans' reports.
 */
export async function latestTwoReports(clientId: string): Promise<{
  current: Record<string, unknown> | null;
  previous: Record<string, unknown> | null;
  at: string | null;
}> {
  const scans = await scanHistory(clientId);
  const [a, b] = scans;
  const [current, previous] = await Promise.all([
    a ? getScanReport(a.id) : Promise.resolve(null),
    b ? getScanReport(b.id) : Promise.resolve(null),
  ]);
  return { current, previous, at: a?.created_at ?? null };
}
