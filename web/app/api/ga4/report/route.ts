import { NextRequest, NextResponse } from "next/server";
import { googleSession, reasonFor } from "@/lib/googleSession";
import { checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";
import { runGa4Report } from "@/lib/ga4";

/**
 * A GA4 report for one property the caller's own connection can read: totals,
 * a daily series, channels, landing pages, and organic-search landing pages.
 * Google decides access from the token, so a property id the account cannot
 * read gets Google's 403, mapped to one sentence (see `ga4ErrorMessage`).
 */
export async function POST(request: NextRequest) {
  try {
    const session = await googleSession(request);
    if (session.state !== "owned" || !session.gscToken) {
      return NextResponse.json(
        { error: reasonFor(session.state) || "Google account not connected." },
        { status: 401 },
      );
    }

    const rl = checkRateLimit(`ga4-report:${session.userId}`, 30, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Too many Google Analytics requests. Retry in ${rl.retryAfterSeconds}s.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
      );
    }

    const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(request, 8 * 1024);
    if (errorResponse) return errorResponse;

    const propertyId = typeof body?.propertyId === "string" ? body.propertyId.replace(/^properties\//, "").trim() : "";
    if (!/^\d{1,20}$/.test(propertyId)) {
      return NextResponse.json({ error: "propertyId must be a numeric GA4 property id." }, { status: 400 });
    }
    const days = Number.isFinite(body?.days) ? Math.min(Math.max(Math.trunc(body.days), 1), 365) : 28;

    const result = await runGa4Report(session.gscToken, propertyId, days);
    if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status });
    const { ok: _ok, ...report } = result;
    return NextResponse.json(report);
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "Failed to read Google Analytics" }, { status: 500 });
  }
}
