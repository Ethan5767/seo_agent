import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const token = cookieStore.get("gsc_access_token")?.value;

    if (!token) {
      return NextResponse.json({ error: "Google account not connected. Please connect via OAuth." }, { status: 401 });
    }

    const body = await request.json();
    const siteUrl = body.siteUrl || process.env.GSC_SITE_URL || "sc-domain:example.com";
    const days = body.days || 28;

    const endDate = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split("T")[0];
    const startDate = new Date(Date.now() - (days + 2) * 24 * 60 * 60 * 1000).toISOString().split("T")[0];

    const endpoint = `https://searchconsole.googleapis.com/webmasters/v3/sites/${encodeURIComponent(siteUrl)}/searchAnalytics/query`;

    const gscPayload = {
      startDate,
      endDate,
      dimensions: Array.isArray(body.dimensions) && body.dimensions.length > 0 ? body.dimensions : ["query"],
      rowLimit: body.rowLimit || 50,
      aggregationType: "byProperty",
    };

    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(gscPayload),
    });

    if (!res.ok) {
      const errText = await res.text();
      return NextResponse.json({ error: `Google Search Console API error: ${errText}` }, { status: res.status });
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err?.message || "Failed to query Google Search Console" }, { status: 500 });
  }
}
