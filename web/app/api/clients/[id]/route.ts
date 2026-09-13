/**
 * Edit a project that already exists.
 *
 * "I create a project, done — I also want to edit those details too. Example: I
 * put the wrong website URL, so I should be able to edit it."
 *
 * A project was write-once: a typo in the domain meant every later scan measured
 * the wrong site, and the only remedy was a second project carrying a duplicate
 * history. PATCH exists so the record can be corrected in place.
 */
import { NextRequest, NextResponse } from "next/server";
import {
  authenticateRequest,
  getScopedDb,
  checkRateLimit,
  readJsonBodyWithLimit,
  validateScanTargetUrlAsync,
} from "@/lib/server-security";

/** The fields a human may correct. `user_id`, `id` and `created_at` are not among them. */
const EDITABLE = ["business", "domain", "website", "model", "repo", "tier", "keywords", "competitors", "goal"] as const;

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    if (!id) return NextResponse.json({ error: "Missing client ID" }, { status: 400 });

    const auth = await authenticateRequest(req);
    if (!auth.user) {
      return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
    }

    const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
    const rl = checkRateLimit(`clients-write:${auth.user.id || clientIp}`, 30, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Rate limit exceeded. Please retry after ${rl.retryAfterSeconds} seconds.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
      );
    }

    const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(req, 512 * 1024);
    if (errorResponse) return errorResponse;

    const db = getScopedDb(auth.user, auth.token);

    // Read the row first, under the same ownership filter the write uses. This
    // is what turns "someone else's id" into a 404 rather than an update that
    // silently matches nothing and reports success.
    const { data: existing, error: readErr } = await db
      .from("clients")
      .select("*")
      .eq("id", id)
      .eq("user_id", auth.user.id)
      .single();

    if (readErr || !existing) {
      return NextResponse.json({ error: "Project not found" }, { status: 404 });
    }

    const patch: Record<string, unknown> = {};

    // The website is the one field with a consequence beyond itself: it is what
    // every future scan measures, so it gets the same SSRF/DNS validation a scan
    // target gets. Correcting a typo must not become a way to point the scanner
    // at an internal address.
    if (typeof body?.website === "string" && body.website.trim()) {
      const check = await validateScanTargetUrlAsync(body.website.trim());
      // `normalizedUrl` is optional on the result type. Treat its absence as a
      // refusal rather than asserting it away: writing an unnormalised URL here
      // is what makes `domain` and `website` disagree later.
      if (!check.valid || !check.normalizedUrl) {
        return NextResponse.json(
          { error: `Rejected website: ${check.reason || "could not be normalised"}` },
          { status: 400 },
        );
      }
      patch.website = check.normalizedUrl;
      // `domain` is derived, never taken from the caller: two fields that can
      // disagree is how a project ends up scanning one site and reporting another.
      patch.domain = new URL(check.normalizedUrl).hostname;
    }

    for (const key of EDITABLE) {
      if (key === "website" || key === "domain") continue; // handled above
      if (!(key in (body || {}))) continue;                // absent means "leave it"
      const v = body[key];
      if (key === "keywords" || key === "competitors") {
        if (!Array.isArray(v)) {
          return NextResponse.json({ error: `${key} must be an array` }, { status: 400 });
        }
        patch[key] = v.filter((x: unknown) => typeof x === "string" && x.trim()).map((x: string) => x.trim());
      } else if (key === "tier") {
        const n = Number(v);
        if (![1, 2, 3].includes(n)) {
          return NextResponse.json({ error: "tier must be 1, 2 or 3" }, { status: 400 });
        }
        patch[key] = n;
      } else if (key === "model") {
        if (v !== "A" && v !== "B") {
          return NextResponse.json({ error: "model must be 'A' or 'B'" }, { status: 400 });
        }
        patch[key] = v;
      } else if (typeof v === "string") {
        patch[key] = v.trim();
      } else {
        return NextResponse.json({ error: `${key} must be a string` }, { status: 400 });
      }
    }

    if (Object.keys(patch).length === 0) {
      return NextResponse.json({ error: "Nothing to update." }, { status: 400 });
    }

    // A business name is what the project is called. Blanking it leaves a row no
    // one can identify in a list, so fall back to the domain the way create does.
    if (patch.business === "") {
      patch.business = (patch.domain as string) || existing.domain;
    }

    const { data, error } = await db
      .from("clients")
      .update(patch)
      .eq("id", id)
      .eq("user_id", auth.user.id)
      .select()
      .single();

    if (error) {
      console.error("PATCH /api/clients/[id] error:", error);
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    /**
     * Past scans measured the OLD site. They stay attached to this project
     * because they are its history, and each `scans` row carries the `url` it
     * actually ran against — but a score on this screen now sits under a
     * different domain than the one that produced it. Say so rather than let the
     * number quietly re-attribute itself to a site it was never measured on.
     */
    let domainChanged: { from: string; to: string; staleScans: number } | null = null;
    if (patch.domain && patch.domain !== existing.domain) {
      const { count } = await db
        .from("scans")
        .select("id", { count: "exact", head: true })
        .eq("client_id", id)
        .eq("user_id", auth.user.id);
      domainChanged = {
        from: existing.domain,
        to: patch.domain as string,
        staleScans: count ?? 0,
      };
    }

    return NextResponse.json({ ok: true, client: data, domainChanged });
  } catch (err: any) {
    console.error("PATCH /api/clients/[id] catch:", err);
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
