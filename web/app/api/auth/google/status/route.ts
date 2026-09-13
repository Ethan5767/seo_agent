import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { PRIMARY_COOKIES, SECONDARY_COOKIES } from "@/lib/oauthCookies";

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
        gscError = sitesRes.status === 401
          ? "The Google connection expired. Reconnect to keep reading Search Console."
          : `Search Console returned HTTP ${sitesRes.status}`;
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
    // No placeholder. An account whose email we never received is an account
    // with no email to show, and "connected@google.account" looked to an
    // operator exactly like a real address they had signed in with.
    userEmail: userEmail || gbpSecondaryEmail || null,
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
        // Never probed. This said `true` with the comment "Auto-probed" beside
        // it, so the UI reported locations on an account that may have none.
        // null is "we have not asked", which is the truth until something does.
        hasLocations: null,
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

  // One list, in lib/oauthCookies.ts, so a cookie added to the flow cannot be
  // forgotten here and leave a disconnected account still holding a token.
  if (service === "gbp_secondary" || service === "all") {
    for (const c of SECONDARY_COOKIES) cookieStore.delete(c);
  }

  if (service === "primary" || service === "all") {
    for (const c of PRIMARY_COOKIES) cookieStore.delete(c);
  }

  return NextResponse.json({
    success: true,
    message: `Disconnected ${service} Google services successfully`,
  });
}
