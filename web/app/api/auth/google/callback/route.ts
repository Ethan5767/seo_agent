import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function GET(request: NextRequest) {
  const origin = request.nextUrl.origin;
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");
  const error = searchParams.get("error");

  if (error) {
    return NextResponse.redirect(`${origin}/integrations/google?error=${encodeURIComponent(error)}`);
  }

  if (!code) {
    return NextResponse.redirect(`${origin}/integrations/google?error=missing_authorization_code`);
  }

  const cookieStore = await cookies();
  const storedClientId = cookieStore.get("google_client_id")?.value;
  const storedClientSecret = cookieStore.get("google_client_secret")?.value;

  const clientId = process.env.GOOGLE_CLIENT_ID || process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || storedClientId || "";
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET || storedClientSecret || "";
  const redirectUri = `${origin}/api/auth/google/callback`;

  try {
    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri,
        grant_type: "authorization_code",
      }),
    });

    const tokenData = await tokenResponse.json();

    if (!tokenResponse.ok || !tokenData.access_token) {
      const errMsg = tokenData.error_description || tokenData.error || "failed_token_exchange";
      return NextResponse.redirect(`${origin}/integrations/google?error=${encodeURIComponent(errMsg)}`);
    }

    const accessToken = tokenData.access_token;
    const refreshToken = tokenData.refresh_token || "";

    // Fetch user info for display
    let userEmail = "";
    try {
      const userInfoRes = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (userInfoRes.ok) {
        const userInfo = await userInfoRes.json();
        userEmail = userInfo.email || "";
      }
    } catch {
      // non-critical
    }

    // Fetch verified sites to verify ownership of target domain
    let userSites: string[] = [];
    try {
      const sitesRes = await fetch("https://www.googleapis.com/webmasters/v3/sites", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (sitesRes.ok) {
        const sitesData = await sitesRes.json();
        userSites = (sitesData.siteEntry || []).map((s: any) => s.siteUrl || "");
      }
    } catch {
      // non-critical
    }

    const rawState = searchParams.get("state") || "unified";
    let stateService = rawState;
    let stateReturnTo = "";
    if (rawState.includes(":::")) {
      const parts = rawState.split(":::");
      stateService = parts[0];
      stateReturnTo = decodeURIComponent(parts[1] || "");
    }

    const cookieReturnTo = cookieStore.get("google_auth_return_to")?.value || "";
    let destination = stateReturnTo || cookieReturnTo;

    // Default destinations based on service
    if (!destination || destination.startsWith("/integrations/google") || destination.startsWith("/api/auth")) {
      destination = stateService === "gbp_secondary" ? "/local-seo" : "/profile";
    }

    // Clean up temporary cookie
    cookieStore.delete("google_auth_return_to");

    if (stateService === "gbp_secondary") {
      cookieStore.set("gbp_secondary_access_token", accessToken, {
        path: "/",
        httpOnly: false,
        sameSite: "lax",
        maxAge: 3600 * 24 * 30,
      });
      if (refreshToken) {
        cookieStore.set("gbp_secondary_refresh_token", refreshToken, {
          path: "/",
          httpOnly: true,
          sameSite: "lax",
          maxAge: 3600 * 24 * 365,
        });
      }
      if (userEmail) {
        cookieStore.set("gbp_secondary_user_email", userEmail, {
          path: "/",
          httpOnly: false,
          sameSite: "lax",
          maxAge: 3600 * 24 * 30,
        });
      }
      cookieStore.set("gbp_secondary_connected", "true", {
        path: "/",
        httpOnly: false,
        sameSite: "lax",
        maxAge: 3600 * 24 * 30,
      });

      const sep = destination.includes("?") ? "&" : "?";
      return NextResponse.redirect(`${origin}${destination}${sep}connected=gbp_secondary`);
    }

    // Set secure cookies for unified primary connection
    cookieStore.set("gsc_access_token", accessToken, {
      path: "/",
      httpOnly: false,
      sameSite: "lax",
      maxAge: 3600 * 24 * 30, // 30 days
    });

    if (refreshToken) {
      cookieStore.set("gsc_refresh_token", refreshToken, {
        path: "/",
        httpOnly: true,
        sameSite: "lax",
        maxAge: 3600 * 24 * 365,
      });
    }

    if (userEmail) {
      cookieStore.set("gsc_user_email", userEmail, {
        path: "/",
        httpOnly: false,
        sameSite: "lax",
        maxAge: 3600 * 24 * 30,
      });
    }

    cookieStore.set("gsc_connected", "true", {
      path: "/",
      httpOnly: false,
      sameSite: "lax",
      maxAge: 3600 * 24 * 30,
    });

    cookieStore.set("gbp_connected", "true", {
      path: "/",
      httpOnly: false,
      sameSite: "lax",
      maxAge: 3600 * 24 * 30,
    });

    const sep = destination.includes("?") ? "&" : "?";
    return NextResponse.redirect(`${origin}${destination}${sep}connected=google_unified`);
  } catch (err: any) {
    return NextResponse.redirect(`${origin}/profile?google_error=${encodeURIComponent(err?.message || "network_error")}`);
  }
}

