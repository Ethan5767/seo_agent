import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, getScopedDb, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    if (!id) return NextResponse.json({ error: "Missing client ID" }, { status: 400 });

    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const db = getScopedDb(auth.user, auth.token);

    // Verify client belongs to authenticated user
    const { data: client, error: clientErr } = await db
      .from("clients")
      .select("id")
      .eq("id", id)
      .eq("user_id", auth.user.id)
      .single();

    if (clientErr || !client) {
      return NextResponse.json({ error: "Client not found" }, { status: 404 });
    }

    const { data: scans, error } = await db
      .from("scans")
      .select("id, created_at, url, score, counts, cost")
      .eq("client_id", id)
      .eq("user_id", auth.user.id)
      .order("created_at", { ascending: false });

    if (error) return NextResponse.json({ error: error.message }, { status: 500 });
    return NextResponse.json({ ok: true, scans: scans || [] });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: clientId } = await params;
    if (!clientId) return NextResponse.json({ error: "Missing client ID" }, { status: 400 });

    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
    const rl = checkRateLimit(`client-scans-write:${auth.user.id || clientIp}`, 30, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Rate limit exceeded. Please retry after ${rl.retryAfterSeconds} seconds.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } }
      );
    }

    const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(req, 1024 * 1024);
    if (errorResponse) {
      return errorResponse;
    }

    const db = getScopedDb(auth.user, auth.token);

    // Verify client belongs to authenticated user
    const { data: client, error: clientErr } = await db
      .from("clients")
      .select("id")
      .eq("id", clientId)
      .eq("user_id", auth.user.id)
      .single();

    if (clientErr || !client) {
      return NextResponse.json({ error: "Client not found or unauthorized" }, { status: 404 });
    }

    const { opts, audit, log, toolEvents = [] } = body || {};
    const user_id = auth.user.id;

    // 1. Insert Scan Row
    const { data: scan, error: scanErr } = await db
      .from("scans")
      .insert({
        client_id: clientId,
        user_id,
        url: opts?.url || "",
        model: opts?.model || "B",
        tools: opts?.tools || [],
        score: audit?.score ?? null,
        counts: audit?.counts ?? {},
        cost: audit?.cost ?? 0,
        report: audit ?? {},
        log: log ?? [],
      })
      .select("id")
      .single();

    if (scanErr || !scan) {
      console.error("POST /api/clients/[id]/scans error:", scanErr);
      return NextResponse.json({ error: scanErr?.message || "Failed to save scan" }, { status: 500 });
    }

    const scanId = scan.id;

    // 2. Insert Tools breakdown (scan_tools)
    const done = (toolEvents as Array<any>).filter((t) => t.state === "done");
    if (done.length > 0) {
      const toolRows = done.map((t) => ({
        scan_id: scanId,
        user_id,
        tool: t.name || "",
        status: t.status || "",
        cost: t.cost || 0,
        n_error: (t.rows || []).filter((r: any) => r.severity === "error").length,
        n_warn: (t.rows || []).filter((r: any) => r.severity === "warn").length,
        n_info: (t.rows || []).filter((r: any) => r.severity === "info").length,
        n_ok: (t.rows || []).filter((r: any) => r.severity === "ok").length,
        result: t.rows || [],
      }));
      await db.from("scan_tools").insert(toolRows);

      // 3. Insert individual findings
      const findingRows = done.flatMap((t) =>
        (t.rows || []).map((r: any) => ({
          scan_id: scanId,
          user_id,
          tool: t.name || "",
          code: r.code || "",
          what: r.what || "",
          severity: r.severity || "",
          why: r.why || "",
          fix: r.fix || "",
          detail: r.detail || "",
          category: r.code?.split(".")[0]?.toUpperCase() || "GENERAL",
          finding_fp: r.code || "",
        }))
      );
      if (findingRows.length > 0) {
        await db.from("findings").insert(findingRows);
      }
    }

    // 4. Insert Scan Metrics & Derived Stats (DataForSEO + Core metrics)
    const cn = audit?.counts || {};
    const aeoRows = (audit?.aeo || []) as Array<any>;
    const aeoOk = aeoRows.filter((r) => r.severity === "ok").length;

    let backlinks: number | null = null;
    let refDomains: number | null = null;
    const blRows = (audit?.backlinks || []) as Array<any>;
    for (const r of blRows) {
      const b = (r.what || r.detail || "").match(/([\d,]+)\s*backlink/i);
      if (b) backlinks = parseInt(b[1].replace(/,/g, ""), 10);
      const d = (r.what || r.detail || "").match(/([\d,]+)\s*(?:referring|ref)\s*domain/i);
      if (d) refDomains = parseInt(d[1].replace(/,/g, ""), 10);
    }

    const rankingRows = (audit?.rankings || []) as Array<any>;
    const organicKw = rankingRows.length ? rankingRows.length : ((audit?.keywords || []).length || null);

    await db.from("scan_metrics").insert({
      scan_id: scanId,
      client_id: clientId,
      user_id,
      score: audit?.score ?? null,
      n_error: cn.error || 0,
      n_warn: cn.warn || 0,
      n_info: cn.info || 0,
      n_ok: cn.ok || 0,
      checks_total: Object.keys(audit || {}).length,
      cost: audit?.cost || 0,
      ai_visibility: aeoRows.length ? Math.round((100 * aeoOk) / aeoRows.length) : null,
      organic_keywords: organicKw,
      backlinks,
      ref_domains: refDomains,
    });

    if (rankingRows.length > 0) {
      const kws = rankingRows.map((r: any) => {
        const q = r.what?.match(/"([^"]+)"/);
        const keyword = q ? q[1] : (r.what || "").replace(/—.*$/, "").trim();
        const pos = r.what?.match(/rank #?(\d+)/i) || (r.detail || "").match(/position (\d+)/i);
        const vol = (r.detail || "").match(/~?([\d,]+)\s*\/\s*mo/i);
        return {
          scan_id: scanId,
          client_id: clientId,
          user_id,
          keyword,
          position: pos ? parseInt(pos[1], 10) : null,
          volume: vol ? parseInt(vol[1].replace(/,/g, ""), 10) : null,
          intent: "",
          url: (r.pages && r.pages[0]) || "",
        };
      }).filter((k: any) => k.keyword);
      if (kws.length > 0) {
        try {
          await db.from("keywords").insert(kws);
        } catch (kwErr) {
          console.warn("Failed to insert keywords table rows", kwErr);
        }
      }
    }

    if (backlinks !== null || refDomains !== null) {
      try {
        await db.from("backlink_snapshots").insert({
          scan_id: scanId,
          client_id: clientId,
          user_id,
          backlinks,
          ref_domains: refDomains,
          toxic: null,
        });
      } catch (blErr) {
        console.warn("Failed to insert backlink_snapshots row", blErr);
      }
    }

    return NextResponse.json({ ok: true, scanId });
  } catch (err: any) {
    console.error("POST /api/clients/[id]/scans catch:", err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
