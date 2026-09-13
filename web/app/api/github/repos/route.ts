import { NextRequest, NextResponse } from "next/server";
import { authenticateRequest, checkRateLimit } from "@/lib/server-security";
import { listRepositories, isGhError } from "@/lib/githubServer";

/**
 * The repositories this operator can reach on GitHub.
 *
 * ADD CLIENT asked for `owner/repo` as free text while the app was already
 * holding a token with the `repo` scope. A typo there does not fail at the
 * point it is made: it writes a client row pointing at a repository that does
 * not exist, and the operator meets it later on the Gate screen as "not found",
 * which reads like a permissions problem rather than a misspelling.
 *
 * This route lists NOTHING the token cannot already see, and takes no input
 * that could widen it. It is not scoped to a client because there is no client
 * yet - this is what you call to create one.
 *
 * The GitHub token is the operator's own, from the Supabase GitHub session, and
 * it is never persisted. It arrives per-request in `x-github-token`, exactly as
 * the pulls and merge routes take it.
 */
export async function GET(req: NextRequest) {
  const auth = await authenticateRequest(req);
  if (!auth.user) {
    return NextResponse.json({ error: auth.error || "Unauthorized" }, { status: 401 });
  }

  // Each call is up to five GitHub requests, so this is tighter than the
  // per-client routes.
  const limited = checkRateLimit(`gh-repos:${auth.user.id}`, 12, 60_000);
  if (!limited.allowed) {
    return NextResponse.json(
      { error: `Too many requests. Retry in ${limited.retryAfterSeconds}s.` },
      { status: 429, headers: { "Retry-After": String(limited.retryAfterSeconds) } },
    );
  }

  const token = req.headers.get("x-github-token") || process.env.GITHUB_OPERATOR_TOKEN || "";
  if (!token) {
    // A 200 with `connected: false`, not an error: "we have no token" is a state
    // the panel renders, and the operator needs the instruction, not a status
    // code. Supabase hands back `provider_token` only on a fresh sign-in, so
    // this is the ordinary case after a page reload, and saying "signed out"
    // would be wrong - they are signed in.
    return NextResponse.json({
      connected: false,
      repos: null,
      reason:
        "No GitHub token in this session. Sign out and back in with GitHub to list your repositories - " +
        "the token is issued at sign-in and is not stored. You can still type owner/repo by hand.",
    });
  }

  const result = await listRepositories(token);
  if (isGhError(result)) {
    return NextResponse.json({ connected: false, repos: null, reason: result.error });
  }

  // `repos: null` and `repos: []` are different facts and the panel renders them
  // differently: "we could not ask" versus "you have none". Collapsing them is
  // how an empty dropdown starts looking like an account with no repositories.
  return NextResponse.json({
    connected: true,
    repos: result.repos,
    truncated: result.truncated,
    reason: result.truncated
      ? "Showing the 500 most recently updated repositories. If yours is not here, type owner/repo."
      : null,
  });
}
