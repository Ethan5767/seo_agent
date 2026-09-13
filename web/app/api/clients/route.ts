import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, getScopedDb, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

export async function GET(req: NextRequest) {
  try {
    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const db = getScopedDb(auth.user, auth.token);

    const { data: clients, error } = await db
      .from("clients")
      .select("*")
      .eq("user_id", auth.user.id)
      .order("created_at", { ascending: false });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    const { data: scans } = await db
      .from("scans")
      .select("id, client_id, score, counts, created_at")
      .eq("user_id", auth.user.id)
      .order("created_at", { ascending: false });

    type Agg = { n: number; lastScore: number | null; lastAt: string | null; lastCounts: Record<string, number> | null; lastScanId: string | null };
    const byClient = new Map<string, Agg>();
    for (const s of scans || []) {
      const cur = byClient.get(s.client_id) || { n: 0, lastScore: null, lastAt: null, lastCounts: null, lastScanId: null };
      if (cur.lastAt === null) {
        cur.lastScore = s.score ?? null;
        cur.lastAt = s.created_at;
        cur.lastCounts = (s.counts as Record<string, number>) ?? null;
        cur.lastScanId = s.id;
      }
      cur.n += 1;
      byClient.set(s.client_id, cur);
    }

    const enriched = (clients || []).map((c: any) => {
      const agg = byClient.get(c.id) || { n: 0, lastScore: null, lastAt: null, lastCounts: null, lastScanId: null };
      return {
        ...c,
        scans: agg.n,
        lastScore: agg.lastScore,
        lastScannedAt: agg.lastAt,
        lastCounts: agg.lastCounts,
        lastScanId: agg.lastScanId,
      };
    });

    return NextResponse.json({ ok: true, clients: enriched });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
    const rl = checkRateLimit(`clients-write:${auth.user.id || clientIp}`, 30, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Rate limit exceeded. Please retry after ${rl.retryAfterSeconds} seconds.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } }
      );
    }

    const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(req, 512 * 1024);
    if (errorResponse) {
      return errorResponse;
    }

    const db = getScopedDb(auth.user, auth.token);
    const { business, domain, website, model, repo, tier, keywords, competitors, goal } = body || {};
    const cleanDomain = (domain || website || "").replace(/^https?:\/\//, "").replace(/\/.*$/, "").trim();

    const { data, error } = await db
      .from("clients")
      .insert({
        business: business || cleanDomain,
        domain: cleanDomain,
        website: website || `https://${cleanDomain}`,
        model: model || "B",
        repo: repo || "",
        tier: tier || 1,
        keywords: Array.isArray(keywords) ? keywords : [],
        competitors: Array.isArray(competitors) ? competitors : [],
        goal: goal || "",
        user_id: auth.user.id,
      })
      .select()
      .single();

    if (error) {
      console.error("POST /api/clients error:", error);
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ ok: true, client: data });
  } catch (err: any) {
    console.error("POST /api/clients catch:", err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
