import { NextRequest, NextResponse } from "next/server";
import { googleSession, reasonFor } from "@/lib/googleSession";
import { checkRateLimit } from "@/lib/server-security";

/**
 * GA4 Property Listing for the caller's verified Google account.
 *
 * Uses the account's session token to call Google Analytics Admin API (accountSummaries).
 * Complies with googleIsolation contracts by resolving session ownership before token use.
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

    const rl = checkRateLimit(`ga4-props:${session.userId}`, 60, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Too many Google Analytics requests. Retry in ${rl.retryAfterSeconds}s.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
      );
    }

    const endpoint = "https://analyticsadmin.googleapis.com/v1alpha/accountSummaries";
    const res = await fetch(endpoint, {
      headers: {
        Authorization: `Bearer ${session.gscToken}`,
      },
      cache: "no-store",
    });

    if (!res.ok) {
      if (res.status === 401) {
        return NextResponse.json(
          { error: "The Google connection expired. Reconnect Google Analytics." },
          { status: 401 },
        );
      }
      if (res.status === 403) {
        // Analytics API may not be enabled or user may have no GA4 permissions
        return NextResponse.json({ properties: [] });
      }
      return NextResponse.json(
        { error: `Google Analytics Admin API returned HTTP ${res.status}.` },
        { status: res.status },
      );
    }

    const data = await res.json();
    const accountSummaries = Array.isArray(data?.accountSummaries) ? data.accountSummaries : [];

    const properties = accountSummaries.flatMap((acc: any) => {
      const summaries = Array.isArray(acc?.propertySummaries) ? acc.propertySummaries : [];
      return summaries.map((p: any) => ({
        id: typeof p.property === "string" ? p.property.replace(/^properties\//, "") : "",
        property: p.property || "",
        displayName: p.displayName || p.property || "",
      }));
    }).filter((p: any) => p.id && p.property);

    return NextResponse.json({ properties });
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message || "Failed to list Google Analytics properties." },
      { status: 500 },
    );
  }
}
