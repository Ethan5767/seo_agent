import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { markClaimPending } from "@/lib/googleSession";
import {
  FLOW_COOKIES,
  ONE_YEAR,
  THIRTY_DAYS,
  nonceMatches,
  oauthCookie,
  safeReturnPath,
  safeService,
} from "@/lib/oauthCookies";

/**
 * The Google OAuth callback.
 *
 * Everything in the query string was handed to us by the browser and may have
 * been written by someone else. The nonce check below is what makes this a
 * continuation of a flow WE started; before it existed, a victim's browser could
 * be walked through a callback carrying an attacker's authorization code, and
 * the attacker's Google account would be bound into the victim's session.
 *
 * The tokens this route stores are bearer credentials for a client's Search
 * Console and Business Profile. They are httpOnly, and `oauthCookie` does not
 * take that as a parameter — see `lib/oauthCookies.ts`.
 */
export async function GET(request: NextRequest) {
  const origin = request.nextUrl.origin;
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");
  const error = searchParams.get("error");
  const cookieStore = await cookies();

  const fail = (reason: string) => {
    for (const c of FLOW_COOKIES) cookieStore.delete(c);
    return NextResponse.redirect(`${origin}/profile?error=${encodeURIComponent(`Google connection failed: ${reason}`)}`);
  };

  if (error) return fail(error);
  if (!code) return fail("missing_authorization_code");

  // CSRF. One comparison, before the code is spent: an authorization code is
  // exchanged exactly once, so a forged callback that reaches the token endpoint
  // has already burned the real user's code even if we reject the result.
  const expected = cookieStore.get("google_oauth_state")?.value;
  if (!nonceMatches(searchParams.get("state") || undefined, expected)) {
    return fail("state_mismatch_please_start_the_connection_again");
  }

  // Service and destination come from OUR cookies, never from `state`.
  const stateService = safeService(cookieStore.get("google_auth_service")?.value);
  const cookieReturnTo = safeReturnPath(cookieStore.get("google_auth_return_to")?.value);
  const destination = cookieReturnTo ?? (stateService === "gbp_secondary" ? "/local-seo" : "/profile");

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
      return fail(errMsg);
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

    // The flow is over; nothing downstream should be able to replay the nonce.
    for (const c of FLOW_COOKIES) cookieStore.delete(c);

    // Open the ownership claim window. The server cannot identify the Supabase
    // user during a top-level redirect - the session lives in localStorage - so
    // the first authenticated read claims the connection instead, and this
    // marker is what bounds "first" to a flow that actually just happened here.
    // Without it, a connection left over from before ownership existed would be
    // claimed by whoever signed in next, stamping the leak as legitimate.
    await markClaimPending();

    if (stateService === "gbp_secondary") {
      cookieStore.set("gbp_secondary_access_token", accessToken, oauthCookie(THIRTY_DAYS));
      if (refreshToken) {
        cookieStore.set("gbp_secondary_refresh_token", refreshToken, oauthCookie(ONE_YEAR));
      }
      if (userEmail) {
        cookieStore.set("gbp_secondary_user_email", userEmail, oauthCookie(THIRTY_DAYS));
      }
      cookieStore.set("gbp_secondary_connected", "true", oauthCookie(THIRTY_DAYS));

      const sep = destination.includes("?") ? "&" : "?";
      return NextResponse.redirect(`${origin}${destination}${sep}connected=gbp_secondary`);
    }

    cookieStore.set("gsc_access_token", accessToken, oauthCookie(THIRTY_DAYS));
    if (refreshToken) {
      cookieStore.set("gsc_refresh_token", refreshToken, oauthCookie(ONE_YEAR));
    }
    if (userEmail) {
      cookieStore.set("gsc_user_email", userEmail, oauthCookie(THIRTY_DAYS));
    }
    cookieStore.set("gsc_connected", "true", oauthCookie(THIRTY_DAYS));
    cookieStore.set("gbp_connected", "true", oauthCookie(THIRTY_DAYS));

    const sep = destination.includes("?") ? "&" : "?";
    return NextResponse.redirect(`${origin}${destination}${sep}connected=google_unified`);
  } catch (err: any) {
    return fail(err?.message || "network_error");
  }
}
