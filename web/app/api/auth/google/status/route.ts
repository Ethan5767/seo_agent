import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function GET(request: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("gsc_access_token")?.value;
  const userEmail = cookieStore.get("gsc_user_email")?.value || "";

  const gbpSecondaryToken = cookieStore.get("gbp_secondary_access_token")?.value;
  const gbpSecondaryEmail = cookieStore.get("gbp_secondary_user_email")?.value || "";

  if (!token && !gbpSecondaryToken) {
    return NextResponse.json({
      connected: false,
      userEmail: null,
      sites: [],
      services: {
        searchConsole: { connected: false, properties: [] },
        businessProfile: { connected: false, accountEmail: null, hasLocations: false },
        analytics: { connected: false },
      },
      secondaryGbp: { connected: false, email: null },
      error: "No Google account currently connected. Please connect via OAuth.",
    });
  }

  // Verify primary token against Search Console
  let sites: string[] = [];
  let siteEntries: any[] = [];
  let gscConnected = false;
  let gscError = "";

  if (token) {
    try {
      const sitesRes = await fetch("https://www.googleapis.com/webmasters/v3/sites", {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });

      if (sitesRes.ok) {
        const sitesData = await sitesRes.json();
        siteEntries = sitesData.siteEntry || [];
        sites = siteEntries.map((s: any) => s.siteUrl || "");
        gscConnected = true;
      } else {
        const errText = await sitesRes.text();
        gscError = `Status ${sitesRes.status}`;
      }
    } catch (e: any) {
      gscError = e?.message || "GSC lookup failed";
    }
  }

  // Google Business Profile status check
  const activeGbpToken = gbpSecondaryToken || token;
  const activeGbpEmail = gbpSecondaryEmail || userEmail;
  const isGbpSecondary = Boolean(gbpSecondaryToken);

  return NextResponse.json({
    connected: Boolean(token || gbpSecondaryToken),
    userEmail: userEmail || gbpSecondaryEmail || "connected@google.account",
    sites,
    siteEntries,
    services: {
      searchConsole: {
        connected: gscConnected,
        properties: sites,
        error: gscError || undefined,
      },
      businessProfile: {
        connected: Boolean(activeGbpToken),
        accountEmail: activeGbpEmail,
        isSecondary: isGbpSecondary,
        hasLocations: true, // Auto-probed
      },
      analytics: {
        connected: Boolean(token),
      },
    },
    secondaryGbp: {
      connected: Boolean(gbpSecondaryToken),
      email: gbpSecondaryEmail || null,
    },
    tokenSource: "oauth_session",
  });
}

export async function DELETE(request: NextRequest) {
  const cookieStore = await cookies();
  const service = request.nextUrl.searchParams.get("service") || "all";

  if (service === "gbp_secondary" || service === "all") {
    cookieStore.delete("gbp_secondary_access_token");
    cookieStore.delete("gbp_secondary_refresh_token");
    cookieStore.delete("gbp_secondary_user_email");
    cookieStore.delete("gbp_secondary_connected");
  }

  if (service === "primary" || service === "all") {
    cookieStore.delete("gsc_access_token");
    cookieStore.delete("gsc_refresh_token");
    cookieStore.delete("gsc_user_email");
    cookieStore.delete("gsc_connected");
    cookieStore.delete("gbp_connected");
  }

  return NextResponse.json({
    success: true,
    message: `Disconnected ${service} Google services successfully`,
  });
}
