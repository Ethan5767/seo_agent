import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

export async function GET(request: NextRequest) {
  const origin = request.nextUrl.origin;
  const cookieStore = await cookies();
  const queryClientId = request.nextUrl.searchParams.get("client_id");
  const storedClientId = cookieStore.get("google_client_id")?.value;
  const clientId = queryClientId || process.env.GOOGLE_CLIENT_ID || process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || storedClientId;

  if (!clientId) {
    // If no client_id is set in env or cookies, navigate to the dedicated Google Integration setup page
    return NextResponse.redirect(`${origin}/integrations/google?prompt=setup_required`);
  }

  const redirectUri = `${origin}/api/auth/google/callback`;
  const targetService = request.nextUrl.searchParams.get("service") || "unified";

  let scopes = [
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/business.manage",
    "https://www.googleapis.com/auth/analytics.readonly",
    "openid",
    "email",
    "profile",
  ].join(" ");

  // If user explicitly requests connecting secondary account specifically for Google Business Profile
  if (targetService === "gbp_secondary") {
    scopes = [
      "https://www.googleapis.com/auth/business.manage",
      "openid",
      "email",
      "profile",
    ].join(" ");
  }

  // Detect return destination (defaulting to /profile or /local-seo)
  const referer = request.headers.get("referer");
  let returnTo = request.nextUrl.searchParams.get("return_to");
  if (!returnTo && referer) {
    try {
      const refUrl = new URL(referer);
      if (refUrl.origin === origin && !refUrl.pathname.startsWith("/api/auth")) {
        returnTo = refUrl.pathname + refUrl.search;
      }
    } catch {}
  }
  if (!returnTo) {
    returnTo = targetService === "gbp_secondary" ? "/local-seo" : "/profile";
  }

  cookieStore.set("google_auth_return_to", returnTo, {
    path: "/",
    httpOnly: true,
    sameSite: "lax",
    maxAge: 1800,
  });

  const encodedState = `${targetService}:::${encodeURIComponent(returnTo)}`;

  const googleAuthUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  googleAuthUrl.searchParams.set("client_id", clientId);
  googleAuthUrl.searchParams.set("redirect_uri", redirectUri);
  googleAuthUrl.searchParams.set("response_type", "code");
  googleAuthUrl.searchParams.set("scope", scopes);
  googleAuthUrl.searchParams.set("state", encodedState);
  const promptMode = request.nextUrl.searchParams.get("prompt") || "select_account consent";
  googleAuthUrl.searchParams.set("access_type", "offline");
  googleAuthUrl.searchParams.set("prompt", promptMode);
  googleAuthUrl.searchParams.set("include_granted_scopes", "true");

  return NextResponse.redirect(googleAuthUrl.toString());
}
