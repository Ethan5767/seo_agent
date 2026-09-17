import { NextRequest, NextResponse } from "next/server";
import { googleSession, reasonFor } from "@/lib/googleSession";
import { checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";

/**
 * Search Console analytics for the caller's own connected property.
 *
 * This route took the access token straight from the cookie jar with no idea
 * whose it was and no authenticated caller at all, so it returned one operator's
 * queries, clicks and impressions to whoever happened to be signed in next.
 * `googleSession` is the whole fix - see `lib/googleSession.ts`.
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

    const rl = checkRateLimit(`gsc-query:${session.userId}`, 60, 60_000);
    if (!rl.allowed) {
      return NextResponse.json(
        { error: `Too many Search Console requests. Retry in ${rl.retryAfterSeconds}s.` },
        { status: 429, headers: { "Retry-After": String(rl.retryAfterSeconds) } },
      );
    }

    const { data: body, errorResponse } = await readJsonBodyWithLimit<any>(request, 32 * 1024);
    if (errorResponse) return errorResponse;

    // The property is caller-supplied, and the token bounds which ones Google
    // will answer for - but a property this connection does not own must not
    // even be attempted, or the 403 body becomes a probe for what exists.
    const siteUrl = typeof body?.siteUrl === "string" ? body.siteUrl.trim() : "";
    if (!siteUrl) {
      return NextResponse.json({ error: "siteUrl is required." }, { status: 400 });
    }
    if (!/^(sc-domain:[a-z0-9.-]{1,253}|https?:\/\/[^\s"'<>]{1,2000})$/i.test(siteUrl)) {
      return NextResponse.json({ error: "siteUrl must be a `sc-domain:` property or an http(s) URL." }, { status: 400 });
    }

    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    let startDate: string;
    let endDate: string;

    if (typeof body?.startDate === "string" && dateRegex.test(body.startDate) &&
        typeof body?.endDate === "string" && dateRegex.test(body.endDate)) {
      startDate = body.startDate;
      endDate = body.endDate;
    } else {
      const days = Number.isFinite(body?.days) ? Math.min(Math.max(Math.trunc(body.days), 1), 480) : 28;
      endDate = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
      startDate = new Date(Date.now() - (days + 2) * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
    }

    const rowLimit = Number.isFinite(body?.rowLimit) ? Math.min(Math.max(Math.trunc(body.rowLimit), 1), 25000) : 50;

    const allowedDimensions = new Set(["query", "page", "country", "device", "searchAppearance", "date"]);
    const dimensions = Array.isArray(body?.dimensions) && body.dimensions.length > 0
      ? body.dimensions.filter((d: unknown): d is string => typeof d === "string" && allowedDimensions.has(d)).slice(0, 5)
      : ["query"];

    // Validate & sanitize dimensionFilterGroups
    let dimensionFilterGroups: any[] | undefined = undefined;
    if (Array.isArray(body?.dimensionFilterGroups)) {
      const sanitized = body.dimensionFilterGroups
        .filter((g: any) => g && Array.isArray(g.filters))
        .map((g: any) => ({
          groupType: g.groupType === "or" ? "or" : "and",
          filters: g.filters
            .filter((f: any) => f && typeof f.dimension === "string" && typeof f.expression === "string")
            .map((f: any) => ({
              dimension: f.dimension,
              operator: ["equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex"].includes(f.operator)
                ? f.operator
                : "contains",
              expression: String(f.expression).slice(0, 500),
            })),
        }))
        .filter((g: any) => g.filters.length > 0);

      if (sanitized.length > 0) {
        dimensionFilterGroups = sanitized;
      }
    }

    const validSearchTypes = new Set(["web", "image", "video", "news", "discover", "googleNews"]);
    const searchType = typeof body?.searchType === "string" && validSearchTypes.has(body.searchType)
      ? body.searchType
      : undefined;

    const endpoint = `https://searchconsole.googleapis.com/webmasters/v3/sites/${encodeURIComponent(siteUrl)}/searchAnalytics/query`;

    const primaryPayload: Record<string, any> = {
      startDate,
      endDate,
      dimensions,
      rowLimit,
      aggregationType: "byProperty",
    };
    if (dimensionFilterGroups) primaryPayload.dimensionFilterGroups = dimensionFilterGroups;
    if (searchType) primaryPayload.type = searchType;

    const headers = {
      Authorization: `Bearer ${session.gscToken}`,
      "Content-Type": "application/json",
    };

    const hasComparison =
      typeof body?.compareStartDate === "string" && dateRegex.test(body.compareStartDate) &&
      typeof body?.compareEndDate === "string" && dateRegex.test(body.compareEndDate);

    if (hasComparison) {
      const compPayload: Record<string, any> = {
        ...primaryPayload,
        startDate: body.compareStartDate,
        endDate: body.compareEndDate,
      };

      const [primaryRes, compRes] = await Promise.all([
        fetch(endpoint, { method: "POST", headers, body: JSON.stringify(primaryPayload) }),
        fetch(endpoint, { method: "POST", headers, body: JSON.stringify(compPayload) }),
      ]);

      if (!primaryRes.ok) {
        const message =
          primaryRes.status === 401 ? "The Google connection expired. Reconnect Search Console."
          : primaryRes.status === 403 ? "This Google account does not have access to that property."
          : `Search Console returned HTTP ${primaryRes.status}.`;
        return NextResponse.json({ error: message }, { status: primaryRes.status });
      }

      const primaryData = await primaryRes.json();
      let comparisonRows: any[] = [];
      if (compRes.ok) {
        try {
          const compData = await compRes.json();
          comparisonRows = Array.isArray(compData?.rows) ? compData.rows : [];
        } catch {
          // Non-critical if comparison fails
        }
      }

      return NextResponse.json({
        ...primaryData,
        comparisonRows,
      });
    }

    const res = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(primaryPayload),
    });

    if (!res.ok) {
      // Google's body is not echoed back: on a 403 it names properties and
      // permissions, which is information about an account, not about this
      // request. The status code is what the caller can act on.
      const message =
        res.status === 401 ? "The Google connection expired. Reconnect Search Console."
        : res.status === 403 ? "This Google account does not have access to that property."
        : `Search Console returned HTTP ${res.status}.`;
      return NextResponse.json({ error: message }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "Failed to query Google Search Console" }, { status: 500 });
  }
}
