import { NextRequest, NextResponse } from "next/server";
import { gbpContext, fetchPrimaryLocation, unavailable } from "@/lib/gbp";

/**
 * Google Business Profile posts ("local posts").
 *
 * Like reviews, posts are on the legacy My Business v4 API and need per-project
 * access from Google. The previous implementation returned a fixed list of
 * invented posts and accepted new ones into a module-level variable, reporting
 * success for a post that was never published anywhere.
 */
const V4_API = "https://mybusiness.googleapis.com/v4";

export async function GET(request: NextRequest) {
  const ctx = await gbpContext(request);
  if (!ctx.token) {
    return NextResponse.json(
      unavailable("no_token", ctx.reason || "Not connected. Connect Google to see your posts."),
    );
  }

  const loc = await fetchPrimaryLocation(ctx.token);
  if (!loc.ok) {
    return NextResponse.json(unavailable(loc.reason!, loc.message!, ctx.accountType));
  }

  const parent = `${loc.accountName}/${String(loc.location?.name || "")}`;
  const res = await fetch(`${V4_API}/${parent}/localPosts`, {
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
          `Local posts are served by the legacy My Business v4 API, which returned HTTP ${res.status}. ` +
            "That API requires per-project access from Google.",
        ctx.accountType,
      ),
    );
  }

  const posts = (payload?.localPosts || []).map((p: any) => ({
    name: p?.name ?? null,
    summary: p?.summary ?? null,
    state: p?.state ?? null,
    topicType: p?.topicType ?? null,
    createTime: p?.createTime ?? null,
    searchUrl: p?.searchUrl ?? null,
  }));

  return NextResponse.json({
    connected: true,
    available: true,
    accountType: ctx.accountType,
    isLiveGoogleSync: true,
    dataStatus: "Live from the Google Business Profile API",
    posts,
  });
}

/** Publishing is a public action; it is never simulated. */
export async function POST(request: NextRequest) {
  return NextResponse.json(
    {
      ok: false,
      error:
        "Publishing a Google post from REAI is not wired yet. It needs the legacy My Business v4 localPosts.create endpoint, which requires per-project access from Google.",
    },
    { status: 501 },
  );
}
