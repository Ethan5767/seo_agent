/**
 * Keeping a Google connection alive past its first hour.
 *
 * THE BUG THIS EXISTS FOR. Google access tokens live about an hour. The OAuth
 * callback stored the access token in a 30-day cookie and the refresh token in
 * a one-year cookie, and nothing ever used the refresh token. So an hour after
 * an operator clicked Connect Google, every Search Console, Business Profile
 * and Analytics read failed with "The Google connection expired", and the only
 * cure was to connect again, every hour.
 *
 * The callback now records when the access token expires. `googleSession`
 * refreshes a token that has expired (or whose expiry was never recorded, a
 * connection from before this change) before any route sees it. This module is
 * the pure half, with no `next/*` import, so it is tested without a server.
 */

/** Refresh this long before Google's stated expiry, so a slow call cannot straddle it. */
export const EXPIRY_SKEW_MS = 60_000;

/** After a failed refresh, wait this long before asking Google again. */
export const REFRESH_BACKOFF_MS = 5 * 60_000;

export type RefreshResult =
  | { ok: true; accessToken: string; expiresAt: number }
  | { ok: false; error: string };

/**
 * Whether the stored access token should be refreshed now.
 *
 * `expiresAt` is epoch milliseconds, or 0 / NaN when never recorded. An unknown
 * expiry counts as expired: it is a connection older than this code, and one
 * cheap refresh settles it.
 */
export function needsRefresh(expiresAt: number, now = Date.now()): boolean {
  if (!Number.isFinite(expiresAt) || expiresAt <= 0) return true;
  return expiresAt - EXPIRY_SKEW_MS <= now;
}

/** When a token Google says lasts `expiresInSeconds` stops being usable. */
export function expiryFrom(expiresInSeconds: unknown, now = Date.now()): number {
  const s = Number(expiresInSeconds);
  return now + (Number.isFinite(s) && s > 0 ? s : 3600) * 1000;
}

/** Exchange a refresh token for a new access token. Never throws. */
export async function refreshAccessToken(
  refreshToken: string,
  clientId: string,
  clientSecret: string,
  fetchImpl: typeof fetch = fetch,
  now = Date.now(),
): Promise<RefreshResult> {
  if (!refreshToken) return { ok: false, error: "no refresh token" };
  if (!clientId || !clientSecret) return { ok: false, error: "GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is not set" };
  try {
    const res = await fetchImpl("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        refresh_token: refreshToken,
        grant_type: "refresh_token",
      }),
      signal: AbortSignal.timeout(10_000),
    });
    let doc: any = null;
    try {
      doc = await res.json();
    } catch {
      doc = null;
    }
    if (!res.ok || !doc?.access_token) {
      // `invalid_grant` = revoked, or issued to a different OAuth client. The
      // caller keeps the old token and Google's 401 tells the operator to reconnect.
      return { ok: false, error: doc?.error || `HTTP ${res.status}` };
    }
    return { ok: true, accessToken: doc.access_token, expiresAt: expiryFrom(doc.expires_in, now) };
  } catch (err: any) {
    return { ok: false, error: err?.message || "network error" };
  }
}
