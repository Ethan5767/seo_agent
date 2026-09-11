import { NextRequest, NextResponse } from "next/server";
import { gbpContext, fetchPrimaryLocation, unavailable } from "@/lib/gbp";

/**
 * Google reviews for the connected location.
 *
 * Reviews live on the legacy My Business v4 API, which Google gates behind a
 * per-project allowlist. That is exactly the sort of condition the previous
 * implementation papered over: it returned invented reviews with invented
 * sentiment while claiming "Live verified via Google Business Profile API".
 * If the call is refused, this says so and returns nothing.
 */
const V4_API = "https://mybusiness.googleapis.com/v4";

export async function GET(_request: NextRequest) {
  const ctx = await gbpContext();
  if (!ctx.token) {
    return NextResponse.json(
      unavailable("no_token", "Not connected. Connect Google to read your reviews."),
    );
  }

  const loc = await fetchPrimaryLocation(ctx.token);
  if (!loc.ok) {
    return NextResponse.json(unavailable(loc.reason!, loc.message!, ctx.accountType));
  }

  const parent = `${loc.accountName}/${String(loc.location?.name || "")}`;
  const res = await fetch(`${V4_API}/${parent}/reviews`, {
    headers: { Authorization: `Bearer ${ctx.token}` },
    cache: "no-store",
  });

  let payload: any = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }

  if (!res.ok) {
    return NextResponse.json(
      unavailable(
        "api_error",
        payload?.error?.message ||
          `Reviews are served by the legacy My Business v4 API, which returned HTTP ${res.status}. ` +
            "That API requires per-project access from Google.",
        ctx.accountType,
      ),
    );
  }

  const reviews = (payload?.reviews || []).map((r: any) => ({
    id: r?.reviewId ?? null,
    reviewer: r?.reviewer?.displayName ?? null,
    starRating: r?.starRating ?? null,
    comment: r?.comment ?? null,
    createTime: r?.createTime ?? null,
    reply: r?.reviewReply?.comment ?? null,
    replyTime: r?.reviewReply?.updateTime ?? null,
  }));

  return NextResponse.json({
    connected: true,
    available: true,
    accountType: ctx.accountType,
    isLiveGoogleSync: true,
    dataStatus: "Live from the Google Business Profile API",
    averageRating: payload?.averageRating ?? null,
    totalReviewCount: payload?.totalReviewCount ?? reviews.length,
    reviews,
  });
}

/**
 * Replying writes to a customer-visible surface, so it is never simulated.
 * The previous implementation mutated an in-memory array and reported success.
 */
export async function POST(_request: NextRequest) {
  return NextResponse.json(
    {
      ok: false,
      error:
        "Replying to reviews from REAI is not wired yet. It needs the legacy My Business v4 reviews.updateReply endpoint, which requires per-project access from Google.",
    },
    { status: 501 },
  );
}
