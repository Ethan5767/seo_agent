// Persistence helpers — save the Onboard client and each Measure scan. RLS keys
// off the logged-in user, so these only work for a signed-in session; user_id is
// stamped from the current session.
import { supabase } from "./supabase";

export type ClientProfile = {
  business: string; domain: string; website: string; model: string;
  repo: string; tier: number; keywords: string[]; competitors: string[]; goal: string;
};

async function uid(): Promise<string | null> {
  const { data } = await supabase.auth.getUser();
  return data.user?.id ?? null;
}

/** Insert a client row, return its id (or null if not signed in / failed). */
export async function saveClient(p: ClientProfile): Promise<string | null> {
  const user_id = await uid();
  if (!user_id) return null;
  const { data, error } = await supabase
    .from("clients")
    .insert({ ...p, user_id })
    .select("id")
    .single();
  if (error) { console.error("saveClient", error); return null; }
  return data.id;
}

export type FindingRow = { code: string; what: string; why: string; fix: string; detail: string; severity: string; tool?: string };
type ToolEvent = { name: string; state: string; rows: FindingRow[]; status: string; cost: number };

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
    })),
  );
  if (findingRows.length) {
    const { error: e3 } = await supabase.from("findings").insert(findingRows);
    if (e3) console.error("saveScan.findings", e3);
  }
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
  if (error || !scans?.length) return empty;

  const findingsFor = async (scanId: string): Promise<FindingRow[]> => {
    const { data } = await supabase
      .from("findings").select("code, what, why, fix, detail, severity, tool")
      .eq("scan_id", scanId);
    return (data as FindingRow[]) || [];
  };
  const current = await findingsFor(scans[0].id);
  const previous = scans[1] ? await findingsFor(scans[1].id) : [];
  return { current, previous, currentScanId: scans[0].id };
}
