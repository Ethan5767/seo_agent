/**
 * Google Business Profile access.
 *
 * The four `/api/local-seo/*` routes previously made no Google call at all.
 * They read a cookie and, if it was set, returned a hardcoded "Acme Roofing &
 * Home Services" fixture alongside `isLiveGoogleSync: true` and the string
 * "Live verified via Google Business Profile API". Connecting Google changed
 * the label and, in the insights route, swapped in a second set of invented
 * numbers so it looked like a sync had happened. Nothing synced.
 *
 * This module talks to the real API. Where the API cannot answer - no token,
 * no account, no location, or an endpoint this project is not allowlisted for -
 * callers get an explicit reason and no data, never a fixture.
 */

import type { NextRequest } from "next/server";

import { googleSession, reasonFor } from "@/lib/googleSession";

const ACCOUNTS_API = "https://mybusinessaccountmanagement.googleapis.com/v1";
const INFO_API = "https://mybusinessbusinessinformation.googleapis.com/v1";

/** Fields worth asking for; the Business Information API requires an explicit mask. */
const LOCATION_READ_MASK = [
  "name",
  "title",
  "storefrontAddress",
  "phoneNumbers",
  "categories",
  "websiteUri",
  "regularHours",
  "specialHours",
  "serviceArea",
  "latlng",
  "metadata",
].join(",");

export type GbpFailure =
  | "no_token"
  | "no_accounts"
  | "no_locations"
  | "api_error"
  | "not_implemented";

export interface GbpContext {
  token: string | null;
  /** Which Google connection the token came from. */
  accountType: "secondary_gbp" | "primary_unified" | "none";
  accountEmail: string | null;
  /** Why there is no token, when there is none. Null when there is one. */
  reason?: string | null;
}

/**
 * The access token to use for Business Profile calls, for THIS caller.
 *
 * A dedicated secondary connection wins: operators commonly manage a client's
 * Maps listing under a different Google account from Search Console, which is
 * why the secondary connection exists at all.
 *
 * It takes the request because it must. This function used to read the cookie
 * jar directly and hand back whatever token it found, so all four `local-seo`
 * routes served one operator's Business Profile - locations, reviews, posts,
 * the lot - to whoever signed in next in the same browser. `googleSession`
 * authenticates the caller and refuses a connection that is not theirs; the
 * whole failure is written up in `lib/googleSession.ts`.
 */
export async function gbpContext(req: NextRequest): Promise<GbpContext> {
  const session = await googleSession(req);
  if (session.state !== "owned") {
    return { token: null, accountType: "none", accountEmail: null, reason: reasonFor(session.state) };
  }
  if (session.gbpSecondaryToken) {
    return {
      token: session.gbpSecondaryToken,
      accountType: "secondary_gbp",
      accountEmail: session.gbpSecondaryEmail,
      reason: null,
    };
  }
  if (session.gscToken) {
    return {
      token: session.gscToken,
      accountType: "primary_unified",
      accountEmail: session.gscEmail,
      reason: null,
    };
  }
  return { token: null, accountType: "none", accountEmail: null, reason: reasonFor("not_connected") };
}

async function getJson(url: string, token: string): Promise<{ ok: boolean; data: any; status: number }> {
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  return { ok: res.ok, data, status: res.status };
}

export interface GbpLocationResult {
  ok: boolean;
  reason?: GbpFailure;
  /** Human-readable cause, straight from Google where there is one. */
  message?: string;
  accountName?: string;
  location?: any;
  /** Every location on the account, so a caller can offer a picker. */
  locations?: any[];
}

/**
 * The first Business Profile location on the connected account.
 *
 * Returns `ok: false` with a reason rather than substituting anything when the
 * account has no locations or the API refuses.
 */
export async function fetchPrimaryLocation(token: string): Promise<GbpLocationResult> {
  const accounts = await getJson(`${ACCOUNTS_API}/accounts`, token);
  if (!accounts.ok) {
    return {
      ok: false,
      reason: "api_error",
      message:
        accounts.data?.error?.message ||
        `Google Business Profile account lookup failed (HTTP ${accounts.status}).`,
    };
  }

  const account = accounts.data?.accounts?.[0];
  if (!account?.name) {
    return {
      ok: false,
      reason: "no_accounts",
      message:
        "This Google account has no Business Profile account. Connect the account that manages the Maps listing.",
    };
  }

  const locs = await getJson(
    `${INFO_API}/${account.name}/locations?readMask=${encodeURIComponent(LOCATION_READ_MASK)}&pageSize=100`,
    token,
  );
  if (!locs.ok) {
    return {
      ok: false,
      reason: "api_error",
      accountName: account.name,
      message:
        locs.data?.error?.message ||
        `Business Profile location lookup failed (HTTP ${locs.status}).`,
    };
  }

  const locations: any[] = locs.data?.locations || [];
  if (locations.length === 0) {
    return {
      ok: false,
      reason: "no_locations",
      accountName: account.name,
      message: "The connected Business Profile account manages no locations.",
    };
  }

  return { ok: true, accountName: account.name, location: locations[0], locations };
}

/**
 * Google's location shape, flattened to what the UI reads.
 * Anything Google did not return stays null or empty; nothing is filled in.
 */
export function normalizeLocation(loc: any) {
  const addr = loc?.storefrontAddress;
  return {
    locationName: loc?.name ?? null,
    businessName: loc?.title ?? null,
    primaryCategory: loc?.categories?.primaryCategory?.displayName ?? null,
    secondaryCategories:
      (loc?.categories?.additionalCategories || []).map((c: any) => c?.displayName).filter(Boolean),
    phone: loc?.phoneNumbers?.primaryPhone ?? null,
    websiteUrl: loc?.websiteUri ?? null,
    address: addr
      ? {
          street: (addr.addressLines || []).join(", "),
          city: addr.locality ?? null,
          state: addr.administrativeArea ?? null,
          postalCode: addr.postalCode ?? null,
          country: addr.regionCode ?? null,
        }
      : null,
    geo: loc?.latlng
      ? { latitude: loc.latlng.latitude ?? null, longitude: loc.latlng.longitude ?? null }
      : null,
    serviceAreas: (loc?.serviceArea?.places?.placeInfos || [])
      .map((p: any) => p?.placeName)
      .filter(Boolean),
    regularHours: loc?.regularHours?.periods ?? null,
    specialHours: loc?.specialHours?.specialHourPeriods ?? null,
    verifiedOnGoogle: loc?.metadata?.hasVoiceOfMerchant ?? null,
  };
}

/** The shape every local-seo route returns when it cannot show real data. */
export function unavailable(reason: GbpFailure, message: string, accountType = "none") {
  return {
    connected: reason !== "no_token",
    available: false,
    reason,
    accountType,
    isLiveGoogleSync: false,
    dataStatus: message,
    data: null,
  };
}
