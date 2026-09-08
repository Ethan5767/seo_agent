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

/** Insert a scan row linked to a client. Best-effort — never blocks the UI. */
export async function saveScan(
  clientId: string,
  opts: { url: string; model: string; tools: string[] },
  audit: { score?: number; counts?: unknown } & Record<string, unknown>,
  log: string[],
): Promise<void> {
  const user_id = await uid();
  if (!user_id || !clientId) return;
  const { error } = await supabase.from("scans").insert({
    client_id: clientId, user_id,
    url: opts.url, model: opts.model, tools: opts.tools,
    score: audit?.score ?? null, counts: audit?.counts ?? {},
    cost: (audit as { cost?: number })?.cost ?? 0,
    report: audit ?? {}, log: log ?? [],
  });
  if (error) console.error("saveScan", error);
}
