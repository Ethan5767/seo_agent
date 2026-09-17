import { NextRequest, NextResponse } from "next/server";
import { googleSession, reasonFor } from "@/lib/googleSession";
import { checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

const ALLOWED_METRICS = new Set([
  "sessions",
  "activeUsers",
  "totalUsers",
  "newUsers",
  "screenPageViews",
  "engagementRate",
  "bounceRate",
  "averageSessionDuration",
  "conversions",
  "eventCount",
  "userEngagementDuration",
]);

const ALLOWED_DIMENSIONS = new Set([
  "date",
  "sessionDefaultChannelGroup",
  "sessionMedium",
  "sessionSource",
  "country",
  "city",
  "deviceCategory",
  "pagePath",
  "pageTitle",
  "eventName",
  "browser",
  "operatingSystem",
]);

/**
 * GA4 Data Query API for verified Google accounts.
 *
 * Calls Google Analytics Data API v1beta (:runReport) using the verified caller's session token.
 * Strictly adheres to googleIsolation and server-security contracts.
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

    const rl = checkRateLimit(`ga4-query:${session.userId}`, 60, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Too many Google Analytics requests. Retry in ${rl.retryAfterSeconds}s.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
      );
    }

    const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(request, 32 * 1024);
    if (errorResponse) return errorResponse;

    const rawProperty = typeof body?.property === "string" ? body.property.trim() : "";
    if (!rawProperty || !/^(properties\/)?[0-9]{3,20}$/.test(rawProperty)) {
      return NextResponse.json(
        { error: "A valid GA4 property (e.g. 'properties/123456789' or numerical ID) is required." },
        { status: 400 },
      );
    }

    const property = rawProperty.startsWith("properties/") ? rawProperty : `properties/${rawProperty}`;

    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    let startDate: string;
    let endDate: string;

    if (typeof body?.startDate === "string" && dateRegex.test(body.startDate) &&
        typeof body?.endDate === "string" && dateRegex.test(body.endDate)) {
      startDate = body.startDate;
      endDate = body.endDate;
    } else {
      const days = Number.isFinite(body?.days) ? Math.min(Math.max(Math.trunc(body.days), 1), 480) : 28;
      endDate = new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
      startDate = new Date(Date.now() - (days + 1) * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
    }

    const dateRanges: Array<{ startDate: string; endDate: string }> = [{ startDate, endDate }];

    if (typeof body?.compareStartDate === "string" && dateRegex.test(body.compareStartDate) &&
        typeof body?.compareEndDate === "string" && dateRegex.test(body.compareEndDate)) {
      dateRanges.push({
        startDate: body.compareStartDate,
        endDate: body.compareEndDate,
      });
    }

    const metrics = Array.isArray(body?.metrics)
      ? body.metrics.filter((m: unknown): m is string => typeof m === "string" && ALLOWED_METRICS.has(m)).slice(0, 5)
      : ["sessions"];

    if (metrics.length === 0) {
      metrics.push("sessions");
    }

    const dimensions = Array.isArray(body?.dimensions)
      ? body.dimensions.filter((d: unknown): d is string => typeof d === "string" && ALLOWED_DIMENSIONS.has(d)).slice(0, 5)
      : [];

    const limit = Number.isFinite(body?.limit) ? Math.min(Math.max(Math.trunc(body.limit), 1), 1000) : 50;

    const ga4Payload: Record<string, any> = {
      dateRanges,
      metrics: metrics.map((name: string) => ({ name })),
      dimensions: dimensions.map((name: string) => ({ name })),
      limit,
    };

    if (body?.dimensionFilter && typeof body.dimensionFilter === "object") {
      ga4Payload.dimensionFilter = body.dimensionFilter;
    }

    const endpoint = `https://analyticsdata.googleapis.com/v1beta/${property}:runReport`;
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.gscToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(ga4Payload),
    });

    if (!res.ok) {
      const message =
        res.status === 401 ? "The Google connection expired. Reconnect Google Analytics."
        : res.status === 403 ? "This Google account does not have access to that GA4 property."
        : `Google Analytics Data API returned HTTP ${res.status}.`;
      return NextResponse.json({ error: message }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err?.message || "Failed to query Google Analytics 4." },
      { status: 500 },
    );
  }
}
