import { NextRequest, NextResponse } from "next/server";
import { googleSession, reasonFor } from "@/lib/googleSession";
import { checkRateLimit } from "@/lib/server-security";
import { listGa4Properties } from "@/lib/ga4";

/**
 * The GA4 properties the caller's own Google connection can read, and the one
 * whose web stream is `?domain=` (null when none is, never a guess).
 */
export async function GET(request: NextRequest) {
  try {
    const session = await googleSession(request);
    if (session.state !== "owned" || !session.gscToken) {
      return NextResponse.json(
        { error: reasonFor(session.state) || "Google account not connected." },
        { status: 401 },
      );
    }

    const rl = checkRateLimit(`ga4-properties:${session.userId}`, 20, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Too many Google Analytics requests. Retry in ${rl.retryAfterSeconds}s.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
      );
    }

    const domain = (request.nextUrl.searchParams.get("domain") || "").slice(0, 253);
    const result = await listGa4Properties(session.gscToken, domain);
    if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status });
    return NextResponse.json({ properties: result.properties, matchedId: result.matchedId });
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "Failed to list Google Analytics properties" }, { status: 500 });
  }
}
