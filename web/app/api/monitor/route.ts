import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";
import { scannerPost, ScannerUnconfigured } from "@/lib/scannerFetch";

/**
 * The live production watch, polled by the Monitor screen.
 *
 * Separate from /api/scan on purpose: the screen refreshes on a timer, and a
 * saved scan per refresh would bury the audit history in the same table. This
 * saves nothing — it reads the live site and returns what it saw.
 */
export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
  }

  const clientIp = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown-ip";
  // Generous: the screen polls on a timer, and the checks cost nothing but time.
  const rl = checkRateLimit(`monitor:${auth.user.id || clientIp}`, 120, 60_000);
  if (!rl.allowed) {
    return NextResponse.json(
      { error: `Rate limit exceeded. Retry after ${rl.retryAfterSeconds}s.` },
      { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
    );
  }

  const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(req, 8 * 1024);
  if (errorResponse) return errorResponse;

  const url = String(body?.url || "").trim();
  if (!url) {
    return NextResponse.json({ error: "no url given — the monitor needs the site to watch", rows: [] }, { status: 400 });
  }

  try {
    // The walk is serial over up to `limit` routes, so allow for a slow origin.
    const res = await scannerPost("/monitor", { url, limit: body?.limit, min_sitemap: body?.min_sitemap },
                                  { headerTimeoutMs: 120_000 });
    if (!res.ok) {
      return NextResponse.json(
        { error: `the scanner refused the monitor run (HTTP ${res.status})`, rows: [] },
        { status: 502 },
      );
    }
    return NextResponse.json(await res.json());
  } catch (e) {
    // The scanner not running is the common case in development, and it is a
    // fact about the setup rather than about the client's site.
    const why = e instanceof ScannerUnconfigured
      ? "the scanner is not running, so the live site was not read"
      : `the monitor could not reach the scanner: ${(e as Error).message}`;
    return NextResponse.json({ error: why, rows: [] }, { status: 503 });
  }
}
