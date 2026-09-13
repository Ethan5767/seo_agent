import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, getScopedDb, checkRateLimit, readJsonBodyWithLimit } from "@/lib/server-security";
import { checksFor, mergePullRequest, isGhError } from "@/lib/githubServer";

/**
 * Merge a client's pull request from this console.
 *
 * The only write in the GitHub integration, and the only place this product
 * changes a client's production site. It is deliberately awkward:
 *
 *   - the caller sends a CLIENT ID and a HEAD SHA, never a repository
 *   - the sha must match what the operator was looking at, or GitHub 409s and
 *     nothing ships (see githubServer.mergePullRequest)
 *   - the gates are re-checked HERE, server-side, immediately before merging.
 *     The page may have rendered green minutes ago; a gate can have gone red
 *     since. Trusting the browser's copy of the verdict would make the whole
 *     19-gate suite advisory.
 *   - `confirm: true` must be present. A merge is not something to reach by a
 *     stray fetch.
 *
 * The human is still the one clicking. This does not auto-merge; auto-merge is
 * a separate, opt-in path that lives in the client's own workflow.
 */
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    if (!id) return NextResponse.json({ error: "Missing client ID" }, { status: 400 });

    const auth = await authenticateRequest(req);
    if (!auth.user) return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });

    // Deliberately tighter than the read routes.
    const limited = checkRateLimit(`gh-merge:${auth.user.id}`, 10, 60_000);
    if (!limited.allowed) return NextResponse.json({ error: "Too many requests" }, { status: 429 });

    const body = await readJsonBodyWithLimit<{
      number?: number; headSha?: string; confirm?: boolean; method?: "merge" | "squash" | "rebase";
    }>(req, 16 * 1024);
    if (body.errorResponse) return body.errorResponse;

    const { number, headSha, confirm, method } = body.data ?? {};
    if (confirm !== true) {
      return NextResponse.json({ error: "confirm must be true to merge" }, { status: 400 });
    }
    if (!Number.isInteger(number) || (number as number) <= 0) {
      return NextResponse.json({ error: "A pull request number is required" }, { status: 400 });
    }
    if (!headSha || !/^[0-9a-f]{40}$/i.test(headSha)) {
      return NextResponse.json({ error: "A full 40-character head sha is required" }, { status: 400 });
    }

    const db = getScopedDb(auth.user, auth.token);
    const { data: client, error } = await db
      .from("clients").select("id, repo").eq("id", id).eq("user_id", auth.user.id).single();
    if (error || !client?.repo) return NextResponse.json({ error: "Client not found" }, { status: 404 });

    const token = req.headers.get("x-github-token") || process.env.GITHUB_OPERATOR_TOKEN || "";
    if (!token) return NextResponse.json({ error: "No GitHub token for this session" }, { status: 400 });

    // Re-verify the gates against the exact sha being merged. This is the whole
    // point of the gate suite: a red gate must make the merge impossible, not
    // merely discouraged in the UI.
    const checks = await checksFor(client.repo, headSha, token);
    if (isGhError(checks)) {
      return NextResponse.json({ error: `Could not read gate results: ${checks.error}` }, { status: 502 });
    }
    if (checks.runs === null) {
      return NextResponse.json({
        error: "No gate results for this commit. Nothing has been verified, so this will not be merged from here.",
      }, { status: 409 });
    }
    if (checks.pending) {
      return NextResponse.json({ error: "Gates are still running. Wait for them to finish." }, { status: 409 });
    }
    if (!checks.allGreen) {
      return NextResponse.json({
        error: `${checks.failed} gate(s) failed on this commit. Fix them before merging.`,
      }, { status: 409 });
    }

    const result = await mergePullRequest(client.repo, number as number, headSha, token, { method });
    if (isGhError(result)) return NextResponse.json({ error: result.error }, { status: 409 });

    return NextResponse.json({ merged: result.merged, sha: result.sha, message: result.message }, { status: 200 });
  } catch (e) {
    console.error("github/merge", e);
    return NextResponse.json({ error: "Could not merge" }, { status: 500 });
  }
}
