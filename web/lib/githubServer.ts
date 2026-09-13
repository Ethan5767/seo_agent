/**
 * Server-side GitHub client for the operator console.
 *
 * The point of this module is that the whole cycle — see the pull request the
 * agent opened, read the gate verdicts, merge it — happens in this app instead
 * of in a browser tab on github.com. The client installs us on their repo once;
 * from then on the operator never leaves.
 *
 * Three rules, and they are the reason this file exists rather than the fetch
 * being inlined in a route:
 *
 * 1. SERVER ONLY. The installation token can write to a client's production
 *    repository. It must never be serialised into a page, a prop, or a client
 *    component. Nothing here is importable from the browser bundle — the routes
 *    that use it are all `route.ts`.
 *
 * 2. THE REPO IS NEVER TAKEN FROM THE REQUEST. A caller supplies a client id;
 *    the repo is read from that client's own record, and the caller must own
 *    the client. Accepting `repo` from the body would let any signed-in user
 *    aim our installation token at any repository we are installed on.
 *
 * 3. READS AND WRITES ARE DIFFERENT DOORS. `merge` is the only write, it is its
 *    own function, and it demands the exact head SHA the operator was looking
 *    at. If the branch moved since the page rendered, the merge fails instead
 *    of shipping something nobody reviewed.
 */

const API = "https://api.github.com";
const UA = "reai-seo-agent";

export type GhError = { error: string; status?: number };

export type PullRequest = {
  number: number;
  title: string;
  headSha: string;
  headRef: string;
  baseRef: string;
  author: string;
  draft: boolean;
  createdAt: string;
  url: string;
  /** GitHub's own mergeability verdict. null = still computing, ask again. */
  mergeable: boolean | null;
  /** "clean" | "blocked" | "dirty" | "behind" | "unstable" | … */
  mergeableState: string | null;
};

/** One check run — for us, one gate. */
export type CheckRun = {
  name: string;
  /** queued | in_progress | completed */
  status: string;
  /** success | failure | neutral | cancelled | timed_out | action_required | skipped | null */
  conclusion: string | null;
  detailsUrl: string | null;
  completedAt: string | null;
};

export type ChecksSummary = {
  /** null when GitHub has reported nothing yet — never render this as a pass. */
  runs: CheckRun[] | null;
  total: number;
  passed: number;
  failed: number;
  /** True only when every run completed AND every conclusion is a success-ish. */
  allGreen: boolean;
  /** Something ran but has not finished. */
  pending: boolean;
};

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": UA,
  };
}

/** Repos are `owner/name`. Anything else is refused rather than interpolated. */
export function parseRepo(repo: string): { owner: string; name: string } | null {
  const m = /^([A-Za-z0-9._-]{1,100})\/([A-Za-z0-9._-]{1,100})$/.exec((repo || "").trim());
  if (!m) return null;
  if (m[1] === "." || m[1] === ".." || m[2] === "." || m[2] === "..") return null;
  return { owner: m[1], name: m[2] };
}

async function gh<T>(path: string, token: string, init?: RequestInit): Promise<T | GhError> {
  try {
    const res = await fetch(`${API}${path}`, {
      ...init,
      headers: { ...headers(token), ...(init?.headers || {}) },
      cache: "no-store",
    });
    if (!res.ok) {
      // Say which failure it was. "Not connected" and "no permission" and
      // "rate limited" need different actions from the operator, and collapsing
      // them into one empty state is how a dashboard stops being useful.
      const detail =
        res.status === 401 ? "GitHub rejected the token — reconnect the client's repository"
        : res.status === 403 ? "GitHub refused: rate limited, or the installation lacks this permission"
        : res.status === 404 ? "Repository or pull request not found, or we are not installed on it"
        : `GitHub returned ${res.status}`;
      return { error: detail, status: res.status };
    }
    return (await res.json()) as T;
  } catch (e) {
    return { error: `could not reach GitHub: ${e instanceof Error ? e.message : "unknown"}` };
  }
}

export function isGhError(v: unknown): v is GhError {
  return Boolean(v && typeof v === "object" && "error" in (v as Record<string, unknown>));
}

/** Open pull requests, newest first. */
export async function listPullRequests(
  repo: string, token: string, limit = 20,
): Promise<PullRequest[] | GhError> {
  const parsed = parseRepo(repo);
  if (!parsed) return { error: `not a valid owner/name repository: ${repo}` };
  const raw = await gh<any[]>(
    `/repos/${parsed.owner}/${parsed.name}/pulls?state=open&sort=created&direction=desc&per_page=${Math.min(limit, 50)}`,
    token,
  );
  if (isGhError(raw)) return raw;
  return raw.map((p) => ({
    number: p.number,
    title: p.title ?? "",
    headSha: p.head?.sha ?? "",
    headRef: p.head?.ref ?? "",
    baseRef: p.base?.ref ?? "",
    author: p.user?.login ?? "unknown",
    draft: Boolean(p.draft),
    createdAt: p.created_at ?? "",
    url: p.html_url ?? "",
    mergeable: typeof p.mergeable === "boolean" ? p.mergeable : null,
    mergeableState: p.mergeable_state ?? null,
  }));
}

/**
 * The check runs for a commit — which, for a client repo running our reusable
 * workflow, IS the gate result. This is the thing the Gate screen could not
 * show before: the verdicts live in the client's Actions run, and this is how
 * they reach us.
 */
export async function checksFor(
  repo: string, sha: string, token: string,
): Promise<ChecksSummary | GhError> {
  const parsed = parseRepo(repo);
  if (!parsed) return { error: `not a valid owner/name repository: ${repo}` };
  if (!/^[0-9a-f]{7,40}$/i.test(sha || "")) return { error: "not a valid commit sha" };

  const raw = await gh<{ check_runs?: any[] }>(
    `/repos/${parsed.owner}/${parsed.name}/commits/${sha}/check-runs?per_page=100`, token,
  );
  if (isGhError(raw)) return raw;

  const runs: CheckRun[] = (raw.check_runs ?? []).map((r) => ({
    name: r.name ?? "",
    status: r.status ?? "",
    conclusion: r.conclusion ?? null,
    detailsUrl: r.details_url ?? null,
    completedAt: r.completed_at ?? null,
  }));

  // No check runs at all is NOT a pass. It usually means the workflow has not
  // started, or the client repo never installed the caller. Returning `null`
  // keeps that distinct from "ran and everything succeeded" — the same rule the
  // engine applies to itself when a gate has nothing to scan.
  if (runs.length === 0) return { runs: null, total: 0, passed: 0, failed: 0, allGreen: false, pending: false };

  const done = (r: CheckRun) => r.status === "completed";
  const good = (r: CheckRun) => r.conclusion === "success" || r.conclusion === "neutral" || r.conclusion === "skipped";
  const passed = runs.filter((r) => done(r) && good(r)).length;
  const failed = runs.filter((r) => done(r) && !good(r)).length;
  const pending = runs.some((r) => !done(r));

  return { runs, total: runs.length, passed, failed, allGreen: !pending && failed === 0, pending };
}

/**
 * Merge a pull request. The only write in this module.
 *
 * `expectedHeadSha` is required, not optional. The operator merges what they
 * were looking at; if the branch moved between the page rendering and the click
 * — the agent pushed again, someone else committed — GitHub refuses with 409
 * and nothing ships. Making the caller pass it means we cannot accidentally
 * merge a commit nobody has seen.
 */
export async function mergePullRequest(
  repo: string, number: number, expectedHeadSha: string, token: string,
  opts: { method?: "merge" | "squash" | "rebase"; title?: string } = {},
): Promise<{ merged: boolean; sha?: string; message: string } | GhError> {
  const parsed = parseRepo(repo);
  if (!parsed) return { error: `not a valid owner/name repository: ${repo}` };
  if (!Number.isInteger(number) || number <= 0) return { error: "not a valid pull request number" };
  if (!/^[0-9a-f]{40}$/i.test(expectedHeadSha || "")) {
    return { error: "a full 40-character head sha is required to merge" };
  }

  const res = await gh<{ merged?: boolean; sha?: string; message?: string }>(
    `/repos/${parsed.owner}/${parsed.name}/pulls/${number}/merge`, token,
    {
      method: "PUT",
      body: JSON.stringify({
        sha: expectedHeadSha,
        merge_method: opts.method ?? "squash",
        ...(opts.title ? { commit_title: opts.title } : {}),
      }),
    },
  );
  if (isGhError(res)) {
    if (res.status === 409) {
      return { error: "the branch moved since this page loaded — reload and check the change again before merging" };
    }
    if (res.status === 405) {
      return { error: "GitHub refused the merge: the pull request is not in a mergeable state" };
    }
    return res;
  }
  return { merged: Boolean(res.merged), sha: res.sha, message: res.message ?? "" };
}
