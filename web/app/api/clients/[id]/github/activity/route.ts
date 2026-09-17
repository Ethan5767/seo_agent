import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, getScopedDb, checkRateLimit } from "@/lib/server-security";
import { activityFor, isGhError } from "@/lib/githubServer";

/**
 * The live step-by-step of the gates running on one commit.
 *
 * Same authorisation shape as the pulls and merge routes, and for the same
 * reason: the caller supplies a CLIENT ID, the repo is read from that client's
 * row, and the row is scoped to the caller. The GitHub token can reach every
 * repo the operator collaborates on, so accepting `repo` from the request would
 * remove the only boundary there is.
 *
 * The head SHA comes from the request because it identifies a commit, not a
 * repository - it cannot widen access, and it is validated as a hex SHA before
 * it reaches a URL.
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!id) return NextResponse.json({ error: "Missing client ID" }, { status: 400 });

  const auth = await authenticateRequest(req);
  if (!auth.user) return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });

  // Polled while a run is in progress, so the ceiling is higher than the other
  // GitHub routes - but it is still a ceiling, and it is per user.
  const limited = checkRateLimit(`gh-activity:${auth.user.id}`, 120, 60_000);
  if (!limited.allowed) {
    return NextResponse.json(
      { error: `Polling too fast. Retry in ${limited.retryAfterSeconds}s.` },
      { status: 429, headers: { "Retry-After": String(limited.retryAfterSeconds) } },
    );
  }

  const sha = (req.nextUrl.searchParams.get("sha") || "").trim();
  if (!/^[0-9a-f]{7,40}$/i.test(sha)) {
    return NextResponse.json({ error: "A commit sha is required." }, { status: 400 });
  }

  const db = getScopedDb(auth.user, auth.token);
  const { data: client, error } = await db
    .from("clients").select("id, repo").eq("id", id).eq("user_id", auth.user.id).single();
  if (error || !client) return NextResponse.json({ error: "Client not found" }, { status: 404 });
  if (!client.repo) {
    return NextResponse.json({ connected: false, reason: "This client has no GitHub repository set." });
  }

  const token = req.headers.get("x-github-token") || process.env.GITHUB_OPERATOR_TOKEN || "";
  if (!token) {
    return NextResponse.json({
      connected: false,
      reason: "No GitHub token in this session. Sign out and back in with GitHub to watch the gates run.",
    });
  }

  const activity = await activityFor(client.repo, sha, token);
  if (isGhError(activity)) {
    return NextResponse.json({ connected: false, reason: activity.error });
  }

  return NextResponse.json({ connected: true, ...activity });
}
