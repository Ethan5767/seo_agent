import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, getScopedDb, checkRateLimit } from "@/lib/server-security";
import { listPullRequests, checksFor, isGhError } from "@/lib/githubServer";

/**
 * Open pull requests for a client's repo, each with its gate verdicts.
 *
 * This is what makes the Gate and Merge screens real. The 19 gates run as check
 * runs in the CLIENT repo's Actions, and until now nothing carried their result
 * back here — so those screens could only say "not connected". This is the wire.
 *
 * Authorisation shape, and the reason it is shaped this way:
 *   - the caller supplies a CLIENT ID, never a repository
 *   - the repo is read from that client's row, which is scoped to the caller
 *   - so a signed-in user can only ever reach repos attached to their own
 *     clients, even though the GitHub token itself can see every repo the
 *     operator's account collaborates on
 *
 * Accepting `repo` from the query string would collapse that entirely.
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    if (!id) return NextResponse.json({ error: "Missing client ID" }, { status: 400 });

    const auth = await authenticateRequest(req);
    if (!auth.user) return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });

    const limited = checkRateLimit(`gh-pulls:${auth.user.id}`, 30, 60_000);
    if (!limited.allowed) {
      return NextResponse.json({ error: "Too many requests" }, { status: 429 });
    }

    const db = getScopedDb(auth.user, auth.token);
    const { data: client, error } = await db
      .from("clients").select("id, repo").eq("id", id).eq("user_id", auth.user.id).single();
    if (error || !client) return NextResponse.json({ error: "Client not found" }, { status: 404 });
    if (!client.repo) {
      return NextResponse.json({ connected: false, reason: "This client has no GitHub repository set." }, { status: 200 });
    }

    // The operator's own GitHub OAuth token. They see a client's repo because
    // the client added them as a collaborator — read-only access is a normal
    // and supported outcome, and merge will simply fail with "not permitted".
    const token = req.headers.get("x-github-token") || process.env.GITHUB_OPERATOR_TOKEN || "";
    if (!token) {
      return NextResponse.json({
        connected: false,
        reason: "No GitHub token for this session. Sign in with GitHub, and make sure the connection requests the `repo` scope so private client repositories are visible.",
      }, { status: 200 });
    }

    const pulls = await listPullRequests(client.repo, token);
    if (isGhError(pulls)) {
      return NextResponse.json({ connected: false, reason: pulls.error }, { status: 200 });
    }

    // Gate verdicts per PR. Bounded to the newest few: this is one API call each
    // and the operator only acts on the top of the list.
    const withChecks = await Promise.all(
      pulls.slice(0, 10).map(async (pr) => {
        const checks = await checksFor(client.repo, pr.headSha, token);
        return { ...pr, checks: isGhError(checks) ? null : checks };
      }),
    );

    return NextResponse.json({ connected: true, repo: client.repo, pulls: withChecks }, { status: 200 });
  } catch (e) {
    console.error("github/pulls", e);
    return NextResponse.json({ error: "Could not list pull requests" }, { status: 500 });
  }
}
