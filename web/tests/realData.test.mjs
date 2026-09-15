import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * Screens that showed invented data as if measured (sweep of 2026-09-15).
 *
 * Each assertion names a literal that was on screen for every client. The
 * operator's rule: every number, badge and status comes from a real source, or
 * the screen says it was not measured.
 */

const src = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
/** Source with comments removed, so a comment explaining a removal does not trip the check. */
const code = (p) => src(p).replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1").replace(/\{\/\*[\s\S]*?\*\/\}/g, "");

test("Local: no fixture geo-grid, roofing copy, invented hours or verification ticks", () => {
  const lbm = code("components/dashboard/LocalBusinessManager.tsx");
  for (const lit of [
    "78% Map Pack Dominance", "#2.6", "Austin", "roof repair near me", "RoofingContractor",
    '"US"', "Matches Google Maps 100%", "Lat/Long coordinates synced", "Click-to-call schema verified",
    "+40%", "local crew", "homeowners", "https://example.com", '"08:00"', "Demo Data", "Real-Time Google Maps",
  ]) {
    assert.ok(!lbm.includes(lit), `LocalBusinessManager still renders ${lit}`);
  }
});

test("Local: reviews and posts are read in the shape the routes send", () => {
  const lbm = code("components/dashboard/LocalBusinessManager.tsx");
  const reviewsRoute = src("app/api/local-seo/reviews/route.ts");
  for (const field of ["reviewer", "starRating", "reply"]) {
    assert.match(reviewsRoute, new RegExp(`${field}:`));
    assert.match(lbm, new RegExp(`rev\\.${field}|r\\.${field}`), `UI does not read ${field}`);
  }
  assert.doesNotMatch(lbm, /rev\.authorName|rev\.replyText|post\.viewsCount/);
  assert.match(lbm, /setInsights\(insRes\)/, "insights.metrics must be the route's metrics, not metrics.metrics");
  assert.doesNotMatch(lbm, /method: "PUT"/, "the business route has no PUT");
});

test("Local: Google's hours are converted, and a day Google does not list gets no default", async () => {
  // starsOf / hoursFromGoogle are pure and exported; exercise them through a tiny
  // extraction rather than importing the TSX component.
  const lbm = src("components/dashboard/LocalBusinessManager.tsx");
  const body = lbm.slice(lbm.indexOf("const STAR_WORDS"), lbm.indexOf("type SubTab"));
  const js = body
    .replace(/export function/g, "function")
    .replace(/: Record<string, number>/g, "")
    .replace(/\(rating: string \| number \| null \| undefined\): number \| null/, "(rating)")
    .replace(/\(t: any\)/, "(t)")
    .replace(/\(periods: any\): Record<string, BusinessHours>/, "(periods)")
    .replace(/const out: Record<string, BusinessHours> = \{\};/, "const out = {};");
  const { starsOf, hoursFromGoogle } = new Function(`${js}; return { starsOf, hoursFromGoogle };`)();
  assert.equal(starsOf("FIVE"), 5);
  assert.equal(starsOf("STAR_RATING_UNSPECIFIED"), null);
  assert.equal(starsOf(null), null);
  const h = hoursFromGoogle([{ openDay: "MONDAY", openTime: { hours: 7 }, closeDay: "MONDAY", closeTime: { hours: 17, minutes: 30 } }]);
  assert.deepEqual(h, { monday: { open: "07:00", close: "17:30", isClosed: false } });
  assert.deepEqual(hoursFromGoogle(null), {});
});

test("Profile: GitHub status is asked of GitHub, and dead preference toggles are gone", () => {
  const prof = code("app/profile/page.tsx");
  for (const lit of ["Workspace Admin", "GitHub Verified", "✓ Connected", "GitHub OAuth 2.0", "Email Audit Summaries", "Auto-Fix PR Staging"]) {
    assert.ok(!prof.includes(lit), `profile still renders ${lit}`);
  }
  assert.match(prof, /authedFetch\("\/api\/github\/repos"/);
  assert.ok(prof.indexOf('authedFetch("/api/github/repos"') < prof.indexOf("if (loading) {"),
    "the GitHub check is a hook and must run before the loading early return");
});

test("Business Profile tile draws no gauge from a made-up score, and the connect banner claims nothing", () => {
  assert.doesNotMatch(code("components/dashboard/GbpMatrix.tsx"), /score=\{ok \? 100 : 50\}/);
  assert.doesNotMatch(code("components/dashboard/GoogleServicesHub.tsx"), /are active\./);
});
