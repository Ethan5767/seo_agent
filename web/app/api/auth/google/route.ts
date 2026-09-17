import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import {
  FLOW_TTL,
  newStateNonce,
  oauthCookie,
  safeReturnPath,
  safeService,
} from "@/lib/oauthCookies";

/**
 * Start the Google OAuth flow.
 *
 * What travels in `state` is a nonce and nothing else. It used to carry
 * `service:::returnTo`, which put two decisions the callback acts on into a
 * string the attacker writes — see `lib/oauthCookies.ts`. Both now ride in
 * httpOnly cookies beside the nonce, so the callback reads them from us rather
 * than from the URL it was handed.
 */
export async function GET(request: NextRequest) {
  const origin = request.nextUrl.origin;
  const cookieStore = await cookies();
  const queryClientId = request.nextUrl.searchParams.get("client_id");
  const storedClientId = cookieStore.get("google_client_id")?.value;
  const clientId =
    queryClientId ||
    process.env.GOOGLE_CLIENT_ID ||
    process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ||
    storedClientId;

  if (!clientId) {
    // No client id anywhere: say so on the Account page (the separate Google
    // integration page was removed on 2026-09-14 at the operator's request).
    return NextResponse.redirect(
      `${origin}/profile?error=${encodeURIComponent("Google sign-in is not configured: set GOOGLE_CLIENT_ID in web/.env.local")}`,
    );
  }

  const redirectUri = `${origin}/api/auth/google/callback`;
  const targetService = safeService(request.nextUrl.searchParams.get("service"));

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

  // Where to land afterwards. Both candidates go through safeReturnPath: the
  // query parameter is supplied by whoever built the link, and the referer by
  // the browser, so neither is ours.
  let returnTo = safeReturnPath(request.nextUrl.searchParams.get("return_to"));
  if (!returnTo) {
    const referer = request.headers.get("referer");
    if (referer) {
      try {
        const refUrl = new URL(referer);
        if (refUrl.origin === origin) returnTo = safeReturnPath(refUrl.pathname + refUrl.search);
      } catch {
        // an unparseable referer is simply no referer
      }
    }
  }
  if (!returnTo) {
    returnTo = targetService === "gbp_secondary" ? "/local-seo" : "/profile";
  }

  // The CSRF defence. Unguessable, tied to this browser, single-use, and short
  // lived: the callback must present the same value or it is not our flow.
  const nonce = newStateNonce();
  cookieStore.set("google_oauth_state", nonce, oauthCookie(FLOW_TTL));
  cookieStore.set("google_auth_return_to", returnTo, oauthCookie(FLOW_TTL));
  cookieStore.set("google_auth_service", targetService, oauthCookie(FLOW_TTL));

  const googleAuthUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  googleAuthUrl.searchParams.set("client_id", clientId);
  googleAuthUrl.searchParams.set("redirect_uri", redirectUri);
  googleAuthUrl.searchParams.set("response_type", "code");
  googleAuthUrl.searchParams.set("scope", scopes);
  googleAuthUrl.searchParams.set("state", nonce);
  const promptMode = request.nextUrl.searchParams.get("prompt") || "select_account consent";
  googleAuthUrl.searchParams.set("access_type", "offline");
  googleAuthUrl.searchParams.set("prompt", promptMode);
  googleAuthUrl.searchParams.set("include_granted_scopes", "true");

  return NextResponse.redirect(googleAuthUrl.toString());
}
