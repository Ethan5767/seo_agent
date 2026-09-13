import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { authenticateRequest, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";
import {
  FLOW_COOKIES,
  PRIMARY_COOKIES,
  SECONDARY_COOKIES,
  ONE_YEAR,
  THIRTY_DAYS,
  oauthCookie,
  sameOriginPost,
} from "@/lib/oauthCookies";

/**
 * Manual credential entry, and disconnect.
 *
 * The escape hatch for an operator pasting a token by hand, plus the disconnect
 * button. It was open to anyone: no authentication, no origin check, no rate
 * limit, and it took an arbitrary string and used it as a bearer token against
 * two Google endpoints.
 *
 * Three things wrong with that, in order of how much they matter:
 *
 *   * `save_credentials` stores this deployment's OAuth CLIENT SECRET. Any page
 *     on the internet could POST one and overwrite it, so the next operator to
 *     press Connect would run the whole flow against the attacker's OAuth app
 *     and hand them the consent.
 *   * The token path made two outbound requests per call with attacker-chosen
 *     Authorization headers and echoed Google's error body back, which is an
 *     oracle for probing tokens through our server rather than theirs.
 *   * Every cookie it set lacked `secure`, and the access token lacked
 *     `httpOnly`, exactly as the callback did.
 *
 * Now: signed in, same origin, rate limited, and cookies through the one policy
 * in `lib/oauthCookies.ts`.
 */
export async function POST(request: NextRequest) {
  const auth = await authenticateRequest(request);
  if (!auth.user) {
    return NextResponse.json(
      { success: false, error: auth.error || "Sign in to connect a Google account." },
      { status: 401 },
    );
  }

  // A cookie-authenticated POST needs its own CSRF answer. The browser sends
  // Origin on every cross-site POST, and a same-origin fetch sends it too.
  if (!sameOriginPost(request)) {
    return NextResponse.json({ success: false, error: "Cross-origin request refused." }, { status: 403 });
  }

  const limit = checkRateLimit(`google-save-token:${auth.user.id}`, 10, 60_000);
  if (!limit.allowed) {
    return NextResponse.json(
      { success: false, error: "Too many attempts. Wait a minute and try again." },
      { status: 429 },
    );
  }

  const parsed = await readJsonBodyWithLimit<any>(request, 16 * 1024);
  if (parsed.errorResponse) return parsed.errorResponse;
  const body = parsed.data ?? {};
  const action = typeof body.action === "string" ? body.action : "";
  const accessToken = typeof body.accessToken === "string" ? body.accessToken.trim() : "";
  const clientId = typeof body.clientId === "string" ? body.clientId.trim() : "";
  const clientSecret = typeof body.clientSecret === "string" ? body.clientSecret.trim() : "";
  const cookieStore = await cookies();

  if (action === "disconnect") {
    for (const c of [...PRIMARY_COOKIES, ...SECONDARY_COOKIES, ...FLOW_COOKIES]) {
      cookieStore.delete(c);
    }
    return NextResponse.json({ success: true, message: "Disconnected successfully" });
  }

  if (action === "save_credentials") {
    if (clientId) cookieStore.set("google_client_id", clientId, oauthCookie(ONE_YEAR));
    if (clientSecret) cookieStore.set("google_client_secret", clientSecret, oauthCookie(ONE_YEAR));
    return NextResponse.json({ success: true, message: "OAuth client credentials stored successfully" });
  }

  if (accessToken) {
    // Live test the access token against Google Search Console API
    const testRes = await fetch("https://www.googleapis.com/webmasters/v3/sites", {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    });

    if (!testRes.ok) {
      // Google's body is not echoed back. It says nothing the operator can act
      // on that the status code does not, and repeating it turns this route into
      // a token-probing oracle.
      return NextResponse.json(
        {
          success: false,
          error:
            testRes.status === 401 || testRes.status === 403
              ? "Google rejected that token. Check it has the Search Console read scope and has not expired."
              : `Google Search Console could not be reached (HTTP ${testRes.status}).`,
        },
        { status: 400 },
      );
    }

    const sitesData = await testRes.json();
    const sites = (sitesData.siteEntry || []).map((s: any) => s.siteUrl || "");

    // Try fetching user email
    let email = "";
    try {
      const userRes = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (userRes.ok) {
        const ud = await userRes.json();
        email = ud.email || "";
      }
    } catch {
      // non-critical
    }

    cookieStore.set("gsc_access_token", accessToken, oauthCookie(THIRTY_DAYS));
    cookieStore.set("gsc_connected", "true", oauthCookie(THIRTY_DAYS));
    if (email) cookieStore.set("gsc_user_email", email, oauthCookie(THIRTY_DAYS));

    return NextResponse.json({
      success: true,
      message: "Google Search Console token verified & connected live!",
      sites,
      email,
    });
  }

  return NextResponse.json({ success: false, error: "Invalid request payload" }, { status: 400 });
}
