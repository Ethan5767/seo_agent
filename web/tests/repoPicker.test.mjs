import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * ADD CLIENT asked the operator to TYPE `owner/repo` while the app was already
 * holding a GitHub token with the `repo` scope.
 *
 * A typo does not fail where it is made. It writes a client row pointing at a
 * repository that does not exist, and the operator meets it later on the Gate
 * screen as "not found" - which reads like a permissions problem rather than a
 * misspelling, and sends them looking for a secret instead of a letter.
 */

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const code = (f) =>
  read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "").replace(/^\s*\/\/.*$/gm, "");

const PICKER = code("components/dashboard/RepoPicker.tsx");
const ROUTE = code("app/api/github/repos/route.ts");
const SERVER = code("lib/githubServer.ts");
const DASH = code("app/ReaiDashboard.tsx");

/** The create/edit project form, lifted out of the dashboard for Rule 1. */
const MODAL = readFileSync(
  new URL("../components/dashboard/ProjectModal.tsx", import.meta.url),
  "utf8",
);

/* ── the three states are three different facts ──────────────────────────── */

test("could-not-ask and you-have-none never render the same way", () => {
  // An empty dropdown that actually means "we never looked" is the same class of
  // lie as a gate that scanned nothing and reported a pass.
  assert.match(PICKER, /repos === null/, "the unknown state must be distinguishable from []");
  assert.match(PICKER, /repos\.length === 0[\s\S]{0,200}not a collaborator on any repository/,
    "an empty account must say so in words");
  assert.match(PICKER, /Reading your repositories from GitHub/, "loading is its own state");
});

test("the route keeps null and empty apart too", () => {
  // Collapsing them on the server would make the client's distinction useless.
  assert.match(ROUTE, /repos: null/, "no token / GitHub refused must return null, not []");
  assert.match(ROUTE, /connected: false/);
  assert.ok(!/repos: \[\]/.test(ROUTE), "the route must never invent an empty list");
});

test("a failure always names a next action", () => {
  for (const [what, src] of [["route", ROUTE], ["picker", PICKER]]) {
    assert.match(src, /Sign out and back in with GitHub|Try again|Type it instead/,
      `${what}: a dead end with no instruction is where operators give up`);
  }
});

/* ── typing by hand survives ─────────────────────────────────────────────── */

test("a local path is still enterable", () => {
  // No GitHub listing will ever contain a local checkout, and the pipeline
  // supports one as a target.
  assert.match(PICKER, /owner\/repo or a local path/);
  assert.match(PICKER, /Enter a path by hand/);
});

test("the manual escape hatch is reachable from the failure state", () => {
  const failure = PICKER.slice(PICKER.indexOf("repos === null ?"), PICKER.indexOf("      ) : ("));
  assert.match(failure, /setManual\(true\)/,
    "an operator who cannot list repos must not be stuck");
});

/* ── what the row tells you before you commit to it ──────────────────────── */

test("read-only access is shown at selection time", () => {
  // A client adds the operator as a collaborator and may grant read only. That
  // is a normal outcome, and finding out at merge time - three screens and one
  // saved client row later - is the bad version.
  assert.match(PICKER, /!r\.canPush && <span style=\{tag\("#b91c1c"\)\}>Read only/);
  assert.match(SERVER, /canPush: Boolean\(r\.permissions\?\.push\)/);
});

test("badges do not rely on colour alone", () => {
  // Each badge prints the word it colours (WCAG 1.4.1).
  for (const word of ["Private", "Archived", "Read only"]) {
    assert.ok(PICKER.includes(`>${word}<`), `${word} must be a label, not just a colour`);
  }
});

/* ── the listing itself ──────────────────────────────────────────────────── */

test("collaborator repositories are included, because that is the whole product", () => {
  // The repos that matter are mostly ones the operator does NOT own: a client
  // adds them to the client's own repo. A default listing would miss every one.
  assert.match(SERVER, /affiliation=owner,collaborator,organization_member/);
});

test("a truncated listing says so", () => {
  // Silently offering a partial list is how an operator concludes their repo is
  // not there and gives up.
  assert.match(SERVER, /truncated/);
  assert.match(ROUTE, /result\.truncated[\s\S]{0,200}type owner\/repo/);
});

test("pagination is bounded", () => {
  // An operator in a large org has thousands, and a picker that waits for all of
  // them is a picker nobody waits for.
  assert.match(SERVER, /Math\.min\(Math\.max\(opts\.maxPages \?\? \d+, 1\), \d+\)/);
});

/* ── the route is not a new way in ───────────────────────────────────────── */

test("listing requires a signed-in caller and is rate limited", () => {
  const authAt = ROUTE.indexOf("authenticateRequest");
  const ghAt = ROUTE.indexOf("listRepositories(");
  assert.ok(authAt !== -1 && authAt < ghAt, "authenticate before calling GitHub");
  assert.match(ROUTE, /checkRateLimit\(`gh-repos:\$\{auth\.user\.id\}`/);
});

test("the route widens nothing: it takes no input at all", () => {
  // It lists only what the operator's own token can already see. A filter read
  // from the request would be a parameter worth attacking.
  assert.ok(!/searchParams/.test(ROUTE), "no request input, so nothing to smuggle");
});

test("the GitHub token is never persisted", () => {
  assert.match(ROUTE, /x-github-token/);
  assert.ok(!/from\("clients"\)|insert\(|cookieStore\.set/.test(ROUTE),
    "the operator's token is per-request; storing it changes its blast radius");
});

/* ── it is actually wired ────────────────────────────────────────────────── */

test("the panel uses the picker and not a free-text box", () => {
  // B-007: a component nobody renders is not shipped.
  assert.match(MODAL, /<RepoPicker/);
  assert.ok(!/placeholder="owner\/repo or local path"/.test(MODAL + DASH),
    "the old free-text field is still there");
});

test("the picker is told when the panel is open, so it loads lazily", () => {
  // Up to five GitHub calls; most sessions never open ADD CLIENT.
  // The modal takes `open` as a prop now and passes it straight through, so the
  // laziness survives the extraction.
  assert.match(MODAL, /open=\{open\}/);
  assert.match(DASH, /open=\{showNewProjectModal\}/);
  assert.match(PICKER, /if \(open && repos === null && !busy && !reason\) void load\(\)/);
});
