import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { action, accessToken, clientId, clientSecret } = body;
    const cookieStore = await cookies();

    if (action === "disconnect") {
      cookieStore.delete("gsc_access_token");
      cookieStore.delete("gsc_refresh_token");
      cookieStore.delete("gsc_user_email");
      cookieStore.delete("gsc_connected");
      return NextResponse.json({ success: true, message: "Disconnected successfully" });
    }

    if (action === "save_credentials") {
      if (clientId) {
        cookieStore.set("google_client_id", clientId, { path: "/", sameSite: "lax", maxAge: 3600 * 24 * 365 });
      }
      if (clientSecret) {
        cookieStore.set("google_client_secret", clientSecret, { path: "/", httpOnly: true, sameSite: "lax", maxAge: 3600 * 24 * 365 });
      }
      return NextResponse.json({ success: true, message: "OAuth client credentials stored successfully" });
    }

    if (accessToken) {
      // Live test the access token against Google Search Console API
      const testRes = await fetch("https://www.googleapis.com/webmasters/v3/sites", {
        headers: { Authorization: `Bearer ${accessToken.trim()}` },
        cache: "no-store",
      });

      if (!testRes.ok) {
        const errText = await testRes.text();
        return NextResponse.json(
          {
            success: false,
            error: `Google Search Console API verification failed (HTTP ${testRes.status}): ${errText}`,
          },
          { status: 400 }
        );
      }

      const sitesData = await testRes.json();
      const sites = (sitesData.siteEntry || []).map((s: any) => s.siteUrl || "");

      // Try fetching user email
      let email = "";
      try {
        const userRes = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
          headers: { Authorization: `Bearer ${accessToken.trim()}` },
        });
        if (userRes.ok) {
          const ud = await userRes.json();
          email = ud.email || "";
        }
      } catch {
        // non-critical
      }

      // Save token in cookie
      cookieStore.set("gsc_access_token", accessToken.trim(), {
        path: "/",
        sameSite: "lax",
        maxAge: 3600 * 24 * 30,
      });
      cookieStore.set("gsc_connected", "true", {
        path: "/",
        sameSite: "lax",
        maxAge: 3600 * 24 * 30,
      });
      if (email) {
        cookieStore.set("gsc_user_email", email, {
          path: "/",
          sameSite: "lax",
          maxAge: 3600 * 24 * 30,
        });
      }

      return NextResponse.json({
        success: true,
        message: "Google Search Console token verified & connected live!",
        sites,
        email,
      });
    }

    return NextResponse.json({ success: false, error: "Invalid request payload" }, { status: 400 });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err?.message || "Internal server error" }, { status: 500 });
  }
}
