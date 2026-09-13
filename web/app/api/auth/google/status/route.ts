import { NextRequest, NextResponse } from "next/server";
import { clearGoogleCookies, googleSession, reasonFor } from "@/lib/googleSession";

/**
 * Which Google account is connected, for the signed-in caller.
 *
 * This route used to read `gsc_access_token` straight out of the cookie jar and
 * report on whatever it found, with no idea whose it was. It is the first thing
 * the dashboard calls on mount, so it was the route that actually delivered one
 * operator's Search Console to the next person to sign in. See
 * `lib/googleSession.ts` for the whole failure and the fix.
 */
const DISCONNECTED = {
  connected: false,
  userEmail: null as string | null,
  sites: [] as string[],
  siteEntries: [] as any[],
  services: {
    searchConsole: { connected: false, properties: [] as string[] },
    businessProfile: { connected: false, accountEmail: null, isSecondary: false, hasLocations: null },
    analytics: { connected: false },
  },
  secondaryGbp: { connected: false, email: null as string | null },
};

export async function GET(request: NextRequest) {
  const session = await googleSession(request);

  if (session.state !== "owned") {
    return NextResponse.json({ ...DISCONNECTED, reason: reasonFor(session.state) });
  }

  const token = session.gscToken;
  const userEmail = session.gscEmail || "";
  const gbpSecondaryToken = session.gbpSecondaryToken;
  const gbpSecondaryEmail = session.gbpSecondaryEmail || "";

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
        accountEmail: activeGbpEmail || null,
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
  });
}

/**
 * Disconnect.
 *
 * Deliberately does NOT require an authenticated caller. This is the endpoint
 * sign-out calls, and by then the Supabase session may already be gone - a
 * disconnect that refuses because you have signed out would leave the token in
 * the browser, which is the exact thing being fixed. It only ever deletes
 * cookies from the caller's own jar, so there is nothing to protect.
 */
export async function DELETE(request: NextRequest) {
  const { cookies } = await import("next/headers");
  const jar = await cookies();
  const service = request.nextUrl.searchParams.get("service") || "all";

  const { SECONDARY_COOKIES, PRIMARY_COOKIES, FLOW_COOKIES } = await import("@/lib/oauthCookies");

  if (service === "all") {
    await clearGoogleCookies();
  } else {
    if (service === "gbp_secondary") for (const c of SECONDARY_COOKIES) jar.delete(c);
    if (service === "primary") {
      for (const c of PRIMARY_COOKIES) jar.delete(c);
      for (const c of FLOW_COOKIES) jar.delete(c);
    }
  }

  return NextResponse.json({
    success: true,
    message: `Disconnected ${service} Google services successfully`,
  });
}
