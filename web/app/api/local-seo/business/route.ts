import { NextRequest, NextResponse } from "next/server";
import { gbpContext, fetchPrimaryLocation, normalizeLocation, unavailable } from "@/lib/gbp";

/**
 * The connected Business Profile location.
 *
 * This route used to return a hardcoded "Acme Roofing & Home Services" in
 * Austin TX - name, phone, hours, holiday closures, service areas, all invented
 * - while reporting `isLiveGoogleSync: true` and "Live verified via Google
 * Business Profile API" whenever a cookie was present. It made zero Google
 * calls. It now makes the real call, and says so plainly when it cannot.
 */
export async function GET(_request: NextRequest) {
  const ctx = await gbpContext();

  if (!ctx.token) {
    return NextResponse.json(
      unavailable(
        "no_token",
        "Not connected. Connect the Google account that manages this Business Profile.",
      ),
    );
  }

  const result = await fetchPrimaryLocation(ctx.token);
  if (!result.ok) {
    return NextResponse.json(
      unavailable(result.reason!, result.message!, ctx.accountType),
    );
  }

  return NextResponse.json({
    connected: true,
    available: true,
    accountType: ctx.accountType,
    activeAccount: ctx.accountEmail,
    isLiveGoogleSync: true,
    dataStatus: "Live from the Google Business Profile API",
    locationCount: result.locations?.length ?? 1,
    business: normalizeLocation(result.location),
  });
}

/**
 * Editing a listing writes to Google, so it is not something to fake either.
 * The write path (locations.patch with an updateMask) is not wired yet; saying
 * so is better than accepting an edit into a variable and reporting success.
 */
export async function POST(_request: NextRequest) {
  return NextResponse.json(
    {
      ok: false,
      error:
        "Editing the Business Profile from REAI is not wired yet. Changes must be made in Google Business Profile until locations.patch is implemented.",
    },
    { status: 501 },
  );
}
