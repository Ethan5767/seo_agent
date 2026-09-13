/**
 * Whose Google connection is this?
 *
 * THE BUG THIS EXISTS FOR. The Google connection lived entirely in cookies -
 * `gsc_access_token`, `gsc_refresh_token`, `gsc_user_email`, `gbp_secondary_*` -
 * and a cookie belongs to a BROWSER, not to a signed-in user. Nothing tied any
 * of them to a Supabase account, `handleSignOut` cleared only the Supabase
 * session, and none of the six routes that read those cookies authenticated the
 * caller at all.
 *
 * So: operator A connects Google and their Search Console properties are read
 * through that cookie. A signs out. B signs in to the same browser with a
 * different account. The dashboard mounts, calls `/api/auth/google/status`, and
 * the cookie is still there - so B is shown A's Google email, A's verified
 * properties, A's queries, clicks and impressions, and through `lib/gbp.ts` A's
 * Business Profile locations, reviews and posts. B never did anything wrong and
 * has no way to tell the data is not theirs.
 *
 * That is a disclosure of one customer's Search Console to another, and it needs
 * no attacker: two people sharing a machine, or one operator with two accounts,
 * reproduce it by signing in.
 *
 * THE FIX, in two halves, because either alone leaves a hole:
 *
 *   1. OWNERSHIP. A `google_owner` cookie records which Supabase user id the
 *      connection belongs to. Every read compares it to the authenticated
 *      caller. A mismatch is not "show nothing" - the cookies are DELETED, so a
 *      stale connection cannot sit there waiting for its owner to sign back in.
 *
 *   2. SIGN-OUT. The client disconnects Google when the session ends or the user
 *      changes. Half 1 makes the leak harmless; half 2 stops the token lingering
 *      in the browser for thirty days after the person who owned it left.
 *
 * WHY TRUST-ON-FIRST-USE. The OAuth callback is a top-level redirect from
 * Google, and this app's Supabase session lives in localStorage, so the server
 * cannot identify the user during the callback - there is no session cookie and
 * no Authorization header on a browser navigation. The owner is therefore
 * claimed on the first AUTHENTICATED read after the connection is made. The
 * window that opens is: whoever is signed in, in this browser, at the moment the
 * OAuth flow returns. That is the person who just completed it.
 */

import type { NextRequest } from "next/server";
import { cookies } from "next/headers";
import { authenticateRequest } from "@/lib/server-security";
import { FLOW_COOKIES, PRIMARY_COOKIES, SECONDARY_COOKIES, ONE_YEAR, oauthCookie } from "@/lib/oauthCookies";

export const OWNER_COOKIE = "google_owner";

/**
 * Set by the OAuth callback, and by nothing else.
 *
 * Trust-on-first-use needs a bound on "first". Without this marker, ANY
 * connection with no owner is claimable - including one that predates this
 * code, sitting in a browser from before ownership existed. The very operator
 * who reported this bug would sign in and have the leaked connection claimed FOR
 * them, seeing the same wrong data with a fresh ownership stamp on it.
 *
 * So the claim is only allowed when the callback has just run in this browser.
 * An unowned connection with no pending claim is unattributable: it is cleared,
 * and the operator reconnects once. Short-lived, because the gap between the
 * callback returning and the dashboard's first authenticated read is seconds.
 */
export const CLAIM_COOKIE = "google_claim_pending";

/** The callback's window to be claimed. Long enough for a slow page load. */
const CLAIM_TTL = 300;

export type GoogleSessionState =
  /** No signed-in user. Nothing about a Google connection may be revealed. */
  | "unauthenticated"
  /** Signed in, no Google tokens in this browser. */
  | "not_connected"
  /** Signed in and the connection is theirs (claimed now, or already was). */
  | "owned"
  /** Signed in, but the connection belongs to somebody else. Cookies cleared. */
  | "foreign";

export type GoogleSession = {
  state: GoogleSessionState;
  userId: string | null;
  /** Only ever populated when state is "owned". */
  gscToken: string | null;
  gbpSecondaryToken: string | null;
  gscEmail: string | null;
  gbpSecondaryEmail: string | null;
};

const EMPTY = {
  gscToken: null, gbpSecondaryToken: null, gscEmail: null, gbpSecondaryEmail: null,
} as const;

/** Every cookie the Google connection owns, including the ownership marker. */
export const ALL_GOOGLE_COOKIES = [
  ...PRIMARY_COOKIES, ...SECONDARY_COOKIES, ...FLOW_COOKIES, OWNER_COOKIE, CLAIM_COOKIE,
] as const;

export async function clearGoogleCookies(): Promise<void> {
  const jar = await cookies();
  for (const name of ALL_GOOGLE_COOKIES) jar.delete(name);
}

/**
 * Resolve the caller's Google connection, or refuse.
 *
 * Call this instead of reading a `gsc_*` cookie directly. A route that reads the
 * jar itself has no idea whose tokens it found.
 */
export async function googleSession(req: NextRequest): Promise<GoogleSession> {
  const auth = await authenticateRequest(req);
  const jar = await cookies();

  const gscToken = jar.get("gsc_access_token")?.value || null;
  const gbpSecondaryToken = jar.get("gbp_secondary_access_token")?.value || null;
  const connected = Boolean(gscToken || gbpSecondaryToken);

  if (!auth.user) {
    // Deliberately NOT a disconnect. A request that simply forgot its bearer
    // token must not destroy a signed-in operator's live connection; refusing to
    // answer is enough, and every route here treats this as "not connected".
    return { state: "unauthenticated", userId: null, ...EMPTY };
  }

  if (!connected) {
    // No tokens, so no owner to keep. Drops a marker left behind by a disconnect
    // that raced, rather than leaving it to reject the next connection.
    if (jar.get(OWNER_COOKIE)) jar.delete(OWNER_COOKIE);
    return { state: "not_connected", userId: auth.user.id, ...EMPTY };
  }

  const owner = jar.get(OWNER_COOKIE)?.value;

  if (!owner) {
    if (!jar.get(CLAIM_COOKIE)) {
      // Unowned and not just connected: a connection from before ownership
      // existed, or one whose claim window has closed. It cannot be attributed
      // to anybody, so it is not attributed to whoever happens to be reading.
      // Costs one reconnect; the alternative is stamping the leaked connection
      // as belonging to the person it leaked to.
      for (const name of ALL_GOOGLE_COOKIES) jar.delete(name);
      return { state: "foreign", userId: auth.user.id, ...EMPTY };
    }
    // Claimed. The callback ran in this browser moments ago, so the signed-in
    // user is the one who completed the flow.
    jar.set(OWNER_COOKIE, auth.user.id, oauthCookie(ONE_YEAR));
    jar.delete(CLAIM_COOKIE);
  } else if (owner !== auth.user.id) {
    // The leak, caught. Delete rather than hide: a token that survives here is a
    // token waiting for its owner to sign back in on a machine they have left.
    for (const name of ALL_GOOGLE_COOKIES) jar.delete(name);
    return { state: "foreign", userId: auth.user.id, ...EMPTY };
  }

  return {
    state: "owned",
    userId: auth.user.id,
    gscToken,
    gbpSecondaryToken,
    gscEmail: jar.get("gsc_user_email")?.value || null,
    gbpSecondaryEmail: jar.get("gbp_secondary_user_email")?.value || null,
  };
}

/** The one sentence a screen shows for each non-owned state. */
export function reasonFor(state: GoogleSessionState): string | null {
  switch (state) {
    case "unauthenticated":
      return "Sign in to see which Google account is connected.";
    case "not_connected":
      return "No Google account connected. Connect one to read Search Console and Business Profile.";
    case "foreign":
      // Covers both shapes: a connection owned by someone else, and one that
      // cannot be attributed at all. The instruction is the same either way, and
      // saying which would tell the reader something about the other account.
      return "The Google connection in this browser is not yours and has been signed out. Connect your own Google account to continue.";
    default:
      return null;
  }
}


/**
 * Open the claim window. The OAuth callback calls this after a successful token
 * exchange; nothing else may, or the bound on trust-on-first-use is gone.
 */
export async function markClaimPending(): Promise<void> {
  const jar = await cookies();
  jar.set(CLAIM_COOKIE, "1", oauthCookie(CLAIM_TTL));
}
