import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { parseRepo, checksFor, mergePullRequest, listPullRequests, isGhError } =
  await import("../lib/githubServer.ts");

/* ── repo parsing is a security boundary, not a convenience ─────────────── */

test("only owner/name is accepted", () => {
  assert.deepEqual(parseRepo("acme/roofing-site"), { owner: "acme", name: "roofing-site" });
  assert.deepEqual(parseRepo("  acme/site  "), { owner: "acme", name: "site" });
  for (const bad of [
    "", "acme", "acme/site/extra", "../../etc/passwd", "acme/../../x",
    "acme/site?x=1", "acme/site#f", "a b/c", "acme/", "/site", "..\/..",
  ]) {
    assert.equal(parseRepo(bad), null, `must refuse: ${JSON.stringify(bad)}`);
  }
});

test("a repo string can never escape into the URL path", () => {
  // The whole reason parseRepo exists. If this regressed, `repo` from a request
  // body would be interpolated straight into api.github.com/repos/<here>.
  assert.equal(parseRepo("acme/site/../../orgs/victim"), null);
  assert.equal(parseRepo("acme/%2e%2e%2fvictim"), null);
});

/* ── no result is not a pass ────────────────────────────────────────────── */

test("no check runs yields null, never an all-green summary", async () => {
  const summary = await withFetch(
    () => ({ ok: true, json: async () => ({ check_runs: [] }) }),
    () => checksFor("acme/site", "a".repeat(40), "tok"),
  );
  assert.equal(summary.runs, null, "runs must be null so the UI cannot render a pass");
  assert.equal(summary.allGreen, false,
    "a PR whose workflow never started must never read as every gate passing");
});

test("a pending run is never counted as green", async () => {
  const summary = await withFetch(
    () => ({ ok: true, json: async () => ({ check_runs: [
      { name: "tier-check", status: "completed", conclusion: "success" },
      { name: "forbidden-sweep", status: "in_progress", conclusion: null },
    ] }) }),
    () => checksFor("acme/site", "b".repeat(40), "tok"),
  );
  assert.equal(summary.pending, true);
  assert.equal(summary.allGreen, false, "still running is not green");
  assert.equal(summary.passed, 1);
});

test("failures are counted, and skipped/neutral are not failures", async () => {
  const summary = await withFetch(
    () => ({ ok: true, json: async () => ({ check_runs: [
      { name: "a", status: "completed", conclusion: "success" },
      { name: "b", status: "completed", conclusion: "skipped" },
      { name: "c", status: "completed", conclusion: "neutral" },
      { name: "d", status: "completed", conclusion: "failure" },
    ] }) }),
    () => checksFor("acme/site", "c".repeat(40), "tok"),
  );
  assert.equal(summary.failed, 1);
  assert.equal(summary.passed, 3);
  assert.equal(summary.allGreen, false, "one red gate means not green");
});

/* ── the merge write ────────────────────────────────────────────────────── */

test("merging requires the exact 40-char head sha the operator saw", async () => {
  for (const bad of ["", "abc", "z".repeat(40), "a".repeat(39)]) {
    const r = await mergePullRequest("acme/site", 7, bad, "tok");
    assert.ok(isGhError(r), `must refuse sha ${JSON.stringify(bad)}`);
    assert.match(r.error, /40-character head sha/);
  }
});

test("a moved branch is refused with an instruction, not a raw 409", async () => {
  const r = await withFetch(
    () => ({ ok: false, status: 409, json: async () => ({}) }),
    () => mergePullRequest("acme/site", 7, "d".repeat(40), "tok"),
  );
  assert.ok(isGhError(r));
  assert.match(r.error, /branch moved/,
    "the operator must be told to re-review, not shown a status code");
});

test("a bad pull request number is refused before any request", async () => {
  for (const bad of [0, -1, 1.5, NaN]) {
    const r = await mergePullRequest("acme/site", bad, "e".repeat(40), "tok");
    assert.ok(isGhError(r), `must refuse number ${bad}`);
  }
});

test("merge defaults to squash", async () => {
  let sent = null;
  const r = await withFetch(
    (url, init) => { sent = JSON.parse(init.body); return { ok: true, json: async () => ({ merged: true, sha: "x" }) }; },
    () => mergePullRequest("acme/site", 7, "f".repeat(40), "tok"),
  );
  assert.equal(r.merged, true);
  assert.equal(sent.merge_method, "squash");
  assert.equal(sent.sha, "f".repeat(40), "the reviewed sha must be sent as the guard");
});

/* ── failures name themselves ───────────────────────────────────────────── */

test("each GitHub failure gives the operator a different next action", async () => {
  const cases = [[401, /reconnect/i], [403, /rate limited|permission/i], [404, /not found|not installed/i]];
  for (const [status, expected] of cases) {
    const r = await withFetch(
      () => ({ ok: false, status, json: async () => ({}) }),
      () => listPullRequests("acme/site", "tok"),
    );
    assert.ok(isGhError(r));
    assert.match(r.error, expected, `status ${status} must be actionable`);
  }
});

/* ── the token must not be reachable from the browser ───────────────────── */

test("this module is never imported by a client component", () => {
  // It handles a token that can write to a client's production repository.
  // A single `"use client"` file importing it would serialise that into the
  // browser bundle.
  const roots = ["app/ReaiDashboard.tsx", "app/ScannerApp.tsx", "lib/github.ts"];
  for (const f of roots) {
    let src;
    try { src = readFileSync(new URL(`../${f}`, import.meta.url), "utf8"); } catch { continue; }
    assert.ok(!/githubServer/.test(src),
      `${f} imports githubServer — the installation token would reach the browser`);
  }
});

/** Swap global.fetch for one call. */
async function withFetch(impl, fn) {
  const real = globalThis.fetch;
  globalThis.fetch = async (url, init) => impl(url, init ?? {});
  try { return await fn(); } finally { globalThis.fetch = real; }
}


/* ── route-level invariants ─────────────────────────────────────────────── */

const ROUTES = [
  "app/api/clients/[id]/github/pulls/route.ts",
  "app/api/clients/[id]/github/merge/route.ts",
];

test("no route ever takes the repository from the request", () => {
  // The GitHub token can reach every repo the operator collaborates on. The
  // only thing keeping one signed-in user off another's client repo is that the
  // repo is read from the client row, which is scoped by user_id. A `repo` read
  // from the body or query string would remove that entirely.
  for (const f of ROUTES) {
    const src = readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
    assert.ok(!/searchParams\.get\(\s*["']repo["']\s*\)/.test(src), `${f}: repo from query`);
    assert.ok(!/\brepo\s*[,}]/.test(src.split("readJsonBodyWithLimit")[1]?.split(";")[0] ?? ""),
      `${f}: repo destructured from the body`);
    assert.ok(/\.eq\("user_id", auth\.user\.id\)/.test(src),
      `${f}: the client lookup must be scoped to the caller`);
    assert.ok(/select\([^)]*repo/.test(src), `${f}: repo must come from the client row`);
  }
});

test("every route authenticates and rate limits before touching GitHub", () => {
  for (const f of ROUTES) {
    const src = readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
    const authAt = src.indexOf("authenticateRequest");
    const ghAt = Math.min(
      ...["listPullRequests(", "mergePullRequest(", "checksFor("]
        .map((s) => { const i = src.indexOf(s, src.indexOf("export async function")); return i === -1 ? Infinity : i; }));
    assert.ok(authAt !== -1 && authAt < ghAt, `${f}: authenticate before calling GitHub`);
    assert.ok(/checkRateLimit\(/.test(src), `${f}: must rate limit`);
  }
});

test("merge re-checks the gates server-side and refuses on anything but green", () => {
  const src = readFileSync(new URL("../app/api/clients/[id]/github/merge/route.ts", import.meta.url), "utf8");
  const checksAt = src.indexOf("checksFor(");
  const mergeAt = src.indexOf("mergePullRequest(");
  assert.ok(checksAt !== -1 && checksAt < mergeAt,
    "gates must be re-read immediately before merging — the page's copy may be stale");
  for (const guard of ["runs === null", "checks.pending", "!checks.allGreen"]) {
    assert.ok(src.includes(guard), `merge must refuse when: ${guard}`);
  }
  assert.ok(/confirm !== true/.test(src), "a merge must not be reachable by a stray fetch");
});
