/**
 * `fetch` that carries the signed-in user.
 *
 * This app stores the Supabase session in localStorage (the default for
 * `supabase-js` in the browser), so there is no session cookie and a route
 * handler cannot see who is calling unless the request says so. Most of the
 * dashboard's own calls already worked because they were scoped by a `user_id`
 * the route resolved some other way - but the Google routes read a cookie and
 * asked nobody, which is how one operator's Search Console reached the next
 * person to sign in.
 *
 * Anything that reads or writes per-user state must go through this. A plain
 * `fetch` to those routes now gets a 401, which is the point: an unauthenticated
 * request should not be able to find out whether a Google account is connected,
 * let alone read from it.
 */

import { supabase } from "@/lib/supabase";

export async function authedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  let token = "";
  try {
    const { data } = await supabase.auth.getSession();
    token = data.session?.access_token || "";
  } catch {
    // No session is a valid state; the route will answer "sign in" rather than
    // this throwing somewhere the caller cannot handle it.
  }
  const headers = new Headers(init.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}

/**
 * Everything the browser remembers about a Google connection.
 *
 * Sign-out cleared the Supabase session and nothing else, so these survived into
 * the next person's session: the property they had selected, the account email
 * shown in the header, and which data source the traffic screen was reading.
 * The cookies are cleared server-side by DELETE; these are the browser's half.
 */
export const GOOGLE_LOCAL_KEYS = [
  "reai_google_account",
  "reai_google_connected",
  "reai_gsc_property",
  "reai_traffic_source",
  "reai_traffic_autorefresh",
] as const;

/** Disconnect Google and forget it locally. Safe to call when already signed out. */
export async function purgeGoogleConnection(): Promise<void> {
  try {
    await fetch("/api/auth/google/status?service=all", { method: "DELETE", cache: "no-store" });
  } catch {
    // A failed network call must not stop the local half, or a user who signs
    // out offline keeps the previous account's property selected.
  }
  try {
    for (const k of GOOGLE_LOCAL_KEYS) localStorage.removeItem(k);
  } catch {
    // Private windows and blocked site data both throw here.
  }
}
