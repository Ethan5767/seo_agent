import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, getScopedDb, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

// In-memory cache fallback in case Supabase table is migrating or offline
const memoryCache: Record<string, any> = {};

export async function GET(req: NextRequest) {
  try {
    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ ok: false, error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const db = getScopedDb(auth.user, auth.token);
    const { searchParams } = new URL(req.url);
    const domain = searchParams.get("domain") || "";
    const siteUrl = searchParams.get("siteUrl") || "";

    const cacheKey = `${auth.user.id}:${siteUrl || domain}`;
    if (!siteUrl && !domain) {
      return NextResponse.json({ ok: false, error: "Missing domain or siteUrl" }, { status: 400 });
    }

    // 1. Try Supabase first
    try {
      let query = db
        .from("traffic_snapshots")
        .select("*")
        .eq("user_id", auth.user.id)
        .order("created_at", { ascending: false })
        .limit(10);

      if (siteUrl) {
        query = query.eq("site_url", siteUrl);
      } else if (domain) {
        query = query.eq("domain", domain);
      }

      const { data, error } = await query;
      if (!error && data && data.length > 0) {
        return NextResponse.json({
          ok: true,
          source: "supabase",
          latest: data[0],
          history: data,
        });
      }
    } catch (dbErr) {
      console.warn("Supabase traffic_snapshots query failed, checking memory cache:", dbErr);
    }

    // 2. Fallback to memory cache
    if (memoryCache[cacheKey]) {
      return NextResponse.json({
        ok: true,
        source: "memory_cache",
        latest: memoryCache[cacheKey],
        history: [memoryCache[cacheKey]],
      });
    }

    return NextResponse.json({ ok: true, latest: null, history: [] });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err?.message || "Failed to get traffic snapshot" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ ok: false, error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
    const rl = checkRateLimit(`traffic-snapshot:${auth.user.id || clientIp}`, 30, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { ok: false, error: `Rate limit exceeded. Please retry after ${rl.retryAfterSeconds} seconds.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } }
      );
    }

    const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(req, 512 * 1024);
    if (errorResponse) {
      return errorResponse;
    }

    const db = getScopedDb(auth.user, auth.token);

    const {
      siteUrl = "",
      domain = "",
      clicks = 0,
      impressions = 0,
      ctr = 0,
      avgPosition = 0,
      topQueries = [],
      countries = [],
      // `devices` used to default to `{ mobile: 68, desktop: 32 }`. Every other
      // fabrication in this codebase is a render-time lie you can delete; this
      // one was WRITTEN INTO THE DATABASE and read back later as history, so a
      // caller that never sent a device split durably stored an invented one.
      //
      // `{}` is the honest default: the caller sent no split, so we have none.
      devices = {},
      dateTrend = [],
    } = body || {};

    const cleanDomain = domain.replace(/^https?:\/\//, "").replace(/\/$/, "");
    const cacheKey = `${auth.user.id}:${siteUrl || cleanDomain}`;

    const snapshot = {
      domain: cleanDomain,
      site_url: siteUrl,
      user_id: auth.user.id,
      clicks: Number(clicks) || 0,
      impressions: Number(impressions) || 0,
      ctr: Number(ctr) || 0,
      avg_position: Number(avgPosition) || 0,
      top_queries: topQueries,
      countries,
      devices,
      date_trend: dateTrend,
      created_at: new Date().toISOString(),
    };

    // Store in memory cache immediately
    if (siteUrl || cleanDomain) {
      memoryCache[cacheKey] = snapshot;
    }

    // Attempt insert into Supabase
    try {
      const { data, error } = await db
        .from("traffic_snapshots")
        .insert({
          domain: cleanDomain,
          site_url: siteUrl,
          user_id: auth.user.id,
          clicks: snapshot.clicks,
          impressions: snapshot.impressions,
          ctr: snapshot.ctr,
          avg_position: snapshot.avg_position,
          top_queries: topQueries,
          countries,
          devices,
          date_trend: dateTrend,
        })
        .select()
        .single();

      if (!error && data) {
        return NextResponse.json({ ok: true, source: "supabase", snapshot: data });
      }
    } catch (insertErr) {
      console.warn("Supabase traffic_snapshots insert failed, fallback to memory cache:", insertErr);
    }

    return NextResponse.json({ ok: true, source: "memory_cache", snapshot });
  } catch (err: any) {
    return NextResponse.json({ ok: false, error: err?.message || "Failed to store traffic snapshot" }, { status: 500 });
  }
}
