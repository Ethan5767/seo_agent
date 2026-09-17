/**
 * "I create a project, done — I also want to edit those details too. Example: I
 * put the wrong website URL, so I should be able to edit it."
 *
 * A project used to be write-once. A typo in the domain meant every later scan
 * measured the wrong site, and the only remedy was a second project carrying a
 * duplicate history.
 *
 * These are source-shape tests, in the same style as the other dashboard tests:
 * the defects that matter here are structural (a form that opens blank and
 * PATCHes, an ownership filter that is missing from the write, a warning that is
 * computed and never rendered), and each is visible in the source.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const ROUTE = read("app/api/clients/[id]/route.ts");
const DB = read("lib/db.ts");
const DASH = read("app/ReaiDashboard.tsx");
const MODAL = read("components/dashboard/ProjectModal.tsx");
const APP = read("app/ScannerApp.tsx");

test("the route exists and is a PATCH", () => {
  assert.match(ROUTE, /export async function PATCH\(/);
});

test("both the read and the write are scoped to the caller", () => {
  // Two `.eq("user_id", ...)` — one on the existence check, one on the update.
  // The update needs its own: an ownership check that is only performed on a
  // prior SELECT is a TOCTOU gap, and under the service-role fallback (B-066)
  // `.eq("user_id")` is the ONLY tenant boundary there is.
  const scoped = ROUTE.match(/\.eq\("user_id", auth\.user\.id\)/g) || [];
  assert.ok(scoped.length >= 2, `expected the read AND the write to be scoped, found ${scoped.length}`);
  const update = ROUTE.slice(ROUTE.indexOf('.update(patch)'));
  assert.match(update, /\.eq\("id", id\)[\s\S]{0,120}\.eq\("user_id", auth\.user\.id\)/,
    "the UPDATE itself must carry the ownership filter");
});

test("someone else's project is not found, not merely unchanged", () => {
  assert.match(ROUTE, /"Project not found"[\s\S]{0,60}404/,
    "an update that matches no row would otherwise report success");
});

test("a new website URL gets the same SSRF validation a scan target gets", () => {
  assert.match(ROUTE, /validateScanTargetUrlAsync\(body\.website\.trim\(\)\)/,
    "the website is what every future scan measures — correcting a typo must not " +
    "become a way to aim the scanner at an internal address");
  assert.match(ROUTE, /Rejected website/);
});

test("domain is derived from the validated website, never taken from the caller", () => {
  assert.match(ROUTE, /patch\.domain = new URL\(check\.normalizedUrl\)\.hostname/);
  // The caller's own `domain` must be skipped in the generic loop.
  assert.match(ROUTE, /if \(key === "website" \|\| key === "domain"\) continue;/);
});

test("identity columns cannot be patched", () => {
  const editable = ROUTE.match(/const EDITABLE = \[([^\]]*)\]/)[1];
  for (const forbidden of ["user_id", "id", "created_at"]) {
    assert.ok(!editable.includes(`"${forbidden}"`), `${forbidden} must not be editable`);
  }
});

test("an absent field is left alone, not blanked", () => {
  assert.match(ROUTE, /if \(!\(key in \(body \|\| \{\}\)\)\) continue;/,
    "PATCH semantics: a form that does not carry a field must not erase it");
});

test("an empty patch is refused rather than reported as saved", () => {
  assert.match(ROUTE, /"Nothing to update\."[\s\S]{0,40}400/);
});

test("the edit goes through authedFetch, not a bare fetch (B-103)", () => {
  const fn = DB.slice(DB.indexOf("export async function updateClient"));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /authedFetch\(/);
  assert.ok(!/[^d]\bfetch\(`\/api\/clients/.test(body),
    "a bare fetch carries no Supabase bearer and 401s");
});

test("updateClient has no direct-table fallback", () => {
  // saveClient falls back to a raw supabase insert. Doing that here would skip
  // the route's URL validation and its derivation of `domain`, leaving the two
  // fields disagreeing — a project that scans one site and reports another.
  const fn = DB.slice(DB.indexOf("export async function updateClient"));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.ok(!/supabase\s*\n?\s*\.from\("clients"\)/.test(body));
});

test("the edit form opens loaded with the existing project", () => {
  const fn = DASH.slice(DASH.indexOf("function openEditProject"));
  const body = fn.slice(0, fn.indexOf("\n  }\n"));
  // Every field the form can write must be loaded, or saving the URL blanks the rest.
  for (const setter of ["setNewBiz(", "setNewUrl(", "setNewModel(", "setNewRepo(", "setNewGoal(", "setNewKwList("]) {
    assert.ok(body.includes(setter), `openEditProject must load ${setter}`);
  }
});

test("opening Create after an Edit does not reopen the edited project", () => {
  // Every create entry point goes through openCreateProject(), which blanks the
  // form and clears editingProject. A leftover editingProject would silently
  // turn the next "Create" into an overwrite of the last project edited.
  const opener = DASH.slice(DASH.indexOf("function openCreateProject"));
  const body = opener.slice(0, opener.indexOf("\n  }\n"));
  assert.match(body, /setEditingProject\(null\)/);
  assert.match(body, /setNewKwList\(\[\]\)/);

  const direct = DASH.match(/setShowNewProjectModal\(true\)/g) || [];
  assert.equal(direct.length, 2,
    "only openCreateProject and openEditProject may open the modal directly");
});

test("a failed edit keeps the modal open and says why", () => {
  assert.match(DASH, /setProjectError\(res\.error\)/);
  assert.match(MODAL, /role="alert"[\s\S]{0,400}Not saved\./,
    "closing on failure leaves the operator believing a wrong URL was corrected");
});

test("changing the site warns before saving and after", () => {
  // Before: the form says the next scan is the first to measure the new site.
  assert.match(MODAL, /This changes the site that gets measured\./);
  // After: the count of scans that measured the old site, from the server.
  assert.match(DASH, /domainMoved\.staleScans/);
  assert.match(DASH, /Project now points at a different site/);
  assert.match(ROUTE, /domainChanged/);
  assert.match(ROUTE, /staleScans/);
});

test("the stale-scan warning is computed from real rows, not assumed", () => {
  assert.match(ROUTE, /\.from\("scans"\)[\s\S]{0,200}count: "exact"/,
    "the number of affected scans must be counted, not guessed");
  assert.match(ROUTE, /staleScans: count \?\? 0/);
});

test("the update reaches the dashboard through a declared prop", () => {
  // B-007: a handler nothing calls is not a feature.
  assert.match(APP, /async function handleUpdateClient/);
  assert.match(APP, /onUpdateClient=\{handleUpdateClient\}/);
  assert.match(DASH, /onUpdateClient\?:/);
  assert.match(DASH, /onUpdateClient,/);
  assert.match(DASH, /onUpdateClient\(editingProject\.id, profile\)/);
  assert.match(DASH, /openEditProject\(c\)/, "and an Edit control must call it");
});
