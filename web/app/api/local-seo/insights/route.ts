import { NextRequest, NextResponse } from "next/server";
import { gbpContext, fetchPrimaryLocation, unavailable } from "@/lib/gbp";

const PERFORMANCE_API = "https://businessprofileperformance.googleapis.com/v1";

/** Metrics the Business Profile Performance API exposes for customer actions. */
const METRICS = [
  "CALL_CLICKS",
  "WEBSITE_CLICKS",
  "BUSINESS_DIRECTION_REQUESTS",
  "BUSINESS_BOOKINGS",
] as const;

function daysAgo(n: number): { year: number; month: number; day: number } {
  const d = new Date(Date.now() - n * 86400000);
  return { year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() };
}

/**
 * Customer actions over the last 28 days, from Google.
 *
 * This route previously returned invented figures, and - worse - a *different*
 * set of invented figures once a Google cookie existed
 * (`totalInteractions: isConnected ? 1284 : 940`), so connecting an account
 * looked like a successful sync. It made no Google call. It now reads the real
 * Performance API and reports an explicit reason when it cannot.
 */
export async function GET(request: NextRequest) {
  const ctx = await gbpContext(request);
  if (!ctx.token) {
    return NextResponse.json(
      unavailable("no_token", ctx.reason || "Not connected. Connect Google to see customer actions."),
    );
  }

  const loc = await fetchPrimaryLocation(ctx.token);
  if (!loc.ok) {
    return NextResponse.json(unavailable(loc.reason!, loc.message!, ctx.accountType));
  }

  // `locations/123` from the Business Information API; the Performance API
  // takes the bare location id.
  const locationId = String(loc.location?.name || "").split("/").pop();
  if (!locationId) {
    return NextResponse.json(
      unavailable("api_error", "Google returned a location with no id.", ctx.accountType),
    );
  }

  const start = daysAgo(28);
  const end = daysAgo(1);
  const params = new URLSearchParams();
  for (const m of METRICS) params.append("dailyMetrics", m);
  params.set("dailyRange.start_date.year", String(start.year));
  params.set("dailyRange.start_date.month", String(start.month));
  params.set("dailyRange.start_date.day", String(start.day));
  params.set("dailyRange.end_date.year", String(end.year));
  params.set("dailyRange.end_date.month", String(end.month));
  params.set("dailyRange.end_date.day", String(end.day));

  const url = `${PERFORMANCE_API}/locations/${locationId}:fetchMultiDailyMetricsTimeSeries?${params}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${ctx.token}` },
    cache: "no-store",
  });

  let payload: any = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }

  if (!res.ok) {
    return NextResponse.json(
      unavailable(
        "api_error",
        payload?.error?.message ||
          `Business Profile Performance API returned HTTP ${res.status}.`,
        ctx.accountType,
      ),
    );
  }

  // Sum each metric's daily series. A metric Google did not return stays absent
  // rather than becoming a zero that reads like a measurement.
  const series: any[] = payload?.multiDailyMetricTimeSeries || [];
  const totals: Record<string, number> = {};
  for (const entry of series) {
    for (const m of entry?.dailyMetricTimeSeries || []) {
      const key = m?.dailyMetric;
      const points = m?.timeSeries?.datedValues || [];
      if (!key) continue;
      totals[key] = points.reduce(
        (sum: number, p: any) => sum + Number(p?.value ?? 0),
        totals[key] ?? 0,
      );
    }
  }

  const measured = Object.keys(totals).length > 0;
  return NextResponse.json({
    connected: true,
    available: measured,
    accountType: ctx.accountType,
    isLiveGoogleSync: true,
    dataStatus: measured
      ? "Live from the Google Business Profile Performance API (last 28 days)"
      : "Google returned no customer-action data for this location in the last 28 days.",
    metrics: measured
      ? {
          period: "Last 28 days",
          calls: totals.CALL_CLICKS ?? null,
          websiteClicks: totals.WEBSITE_CLICKS ?? null,
          directionRequests: totals.BUSINESS_DIRECTION_REQUESTS ?? null,
          bookings: totals.BUSINESS_BOOKINGS ?? null,
          totalInteractions: Object.values(totals).reduce((a, b) => a + b, 0),
        }
      : null,
  });
}
