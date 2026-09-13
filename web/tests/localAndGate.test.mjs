import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * B-096 (Local was almost entirely invented) and the live gate feed.
 */
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const code = (f) =>
  read(f).replace(/\/\*[\s\S]*?\*\//g, "").replace(/\{\/\*[\s\S]*?\*\/\}/g, "").replace(/^\s*\/\/.*$/gm, "");

const DASH = code("app/ReaiDashboard.tsx");
const ACTIVITY = code("components/dashboard/GateActivity.tsx");

const { deriveDirectories, directoryLabel, directoryColor, directorySummary } =
  await import("../lib/localSignals.ts");

/* ── Local: what can be checked, and what nobody can ─────────────────────── */

test("the directories nobody can query are not shown at all", () => {
  // They were literals reading "Synced". Then they were honest "No public API"
  // tiles. Then they were removed on the operator's call: a tile that can only
  // ever say "nobody can check this" is screen spent on nothing actionable.
  const names = deriveDirectories([]).map((d) => d.name);
  for (const gone of ["Bing Places", "Apple Business Connect", "Waze", "YellowPages",
                      "Apple Maps", "Google Maps", "Yelp Biz"]) {
    assert.ok(!names.includes(gone), `${gone} is back on the screen`);
  }
  assert.deepEqual(names, ["Google Business Profile", "On-page local signals", "Yelp"]);
});

test("the reason they are gone survives in the source", () => {
  // Without it the next person to ask "where is Bing?" adds the tiles back -
  // which is exactly how six fabricated "Synced" badges got here.
  const src = read("lib/localSignals.ts");
  for (const name of ["Bing Places", "Apple Business Connect", "Waze", "YellowPages"]) {
    assert.ok(src.includes(name), `${name}'s reason is not recorded anywhere`);
  }
  assert.match(src, /NO API/);
});

test("nothing unmeasured is ever coloured as a pass", () => {
  for (const d of deriveDirectories([])) {
    if (d.state === "ok") continue;
    assert.notEqual(directoryColor(d.state), "#047857", `${d.name} is green without a measurement`);
  }
});

test("Google is unchecked, not verified, before a scan", () => {
  const g = deriveDirectories([]).find((d) => d.name === "Google Business Profile");
  assert.equal(g.state, "unchecked");
  assert.equal(directoryLabel(g.state), "Not checked");
});

test("Google reports a real verdict once GBP rows exist", () => {
  const ok = deriveDirectories([{ code: "gbp.reviews", severity: "ok" }, { code: "gbp.nap", severity: "ok" }]);
  assert.equal(ok.find((d) => d.name === "Google Business Profile").state, "ok");
  const bad = deriveDirectories([{ code: "gbp.reviews", severity: "ok" }, { code: "gbp.nap", severity: "warn" }]);
  assert.equal(bad.find((d) => d.name === "Google Business Profile").state, "problem",
    "one failing signal means the profile needs work");
});

test("Yelp is honest about being buildable but not built", () => {
  const y = deriveDirectories([]).find((d) => d.name === "Yelp");
  assert.equal(y.state, "not-built");
  assert.match(y.note, /Fusion API/, "say what would make it work");
});

test("the count never implies a denominator it did not check", () => {
  // The badge was the literal "5/6 Verified Active".
  assert.equal(directorySummary(deriveDirectories([])), "None checked yet");
  assert.equal(directorySummary(deriveDirectories([{ code: "gbp.nap", severity: "ok" }])), "1/1 verified");
  assert.equal(
    directorySummary(deriveDirectories([
      { code: "gbp.nap", severity: "ok" },
      { code: "local.google_maps_embed", severity: "warn" },
    ])),
    "1/2 verified",
  );
});

test("the free page signals are their own tile, and grade themselves", () => {
  const none = deriveDirectories([]).find((d) => d.name === "On-page local signals");
  assert.equal(none.state, "unchecked");

  const ok = deriveDirectories([
    { code: "local.google_maps_embed", severity: "ok" },
    { code: "local.opening_hours", severity: "ok" },
  ]).find((d) => d.name === "On-page local signals");
  assert.equal(ok.state, "ok");

  const bad = deriveDirectories([
    { code: "local.google_maps_embed", severity: "ok" },
    { code: "local.opening_hours", severity: "warn" },
  ]).find((d) => d.name === "On-page local signals");
  assert.equal(bad.state, "problem");
});

test("an optional signal does not fail the tile on its own", () => {
  // Geo coordinates are emitted as `info`, not `warn`: they are genuinely
  // optional, and grading them would make a good page read as broken.
  const t = deriveDirectories([
    { code: "local.google_maps_embed", severity: "ok" },
    { code: "local.geo_coordinates", severity: "info" },
  ]).find((d) => d.name === "On-page local signals");
  assert.equal(t.state, "ok");

  const onlyInfo = deriveDirectories([{ code: "local.geo_coordinates", severity: "info" }])
    .find((d) => d.name === "On-page local signals");
  assert.equal(onlyInfo.state, null === onlyInfo.state ? onlyInfo.state : "unchecked",
    "info alone is a fact, not a verdict");
});

test("every directory note says why, not just what", () => {
  for (const d of deriveDirectories([])) {
    assert.ok(d.note.length > 30, `${d.name}: the note is too thin to act on`);
  }
});

test("the invented local strings are gone from the dashboard", () => {
  for (const s of [
    "5/6 Verified Active", "184 Google reviews", "94% positive sentiment",
    "Medical Center / Hospital", "85% Positive", "90% Positive",
    'name: "Waze Local"', 'status: "Synced"', "Format Diff",
  ]) {
    assert.ok(!DASH.includes(s), `"${s}" is still rendered with nothing behind it`);
  }
});

test("the local checklist renders an empty state, not substitute rows", () => {
  assert.match(DASH, /No local signals measured yet/);
  assert.ok(!/activeLocalRows = \(gbpRows\.length > 0/.test(DASH),
    "the find-or-fabricate fallback is back");
});

/* ── Gate: the rail says what the screen does ────────────────────────────── */

test("the sidebar names the merge, because merging is the stage", () => {
  const nav = DASH.slice(DASH.indexOf("export const NAV_SECTIONS"), DASH.indexOf("export const RAIL_ICONS"));
  const gate = nav.slice(nav.indexOf('id: "Gate"'), nav.indexOf('id: "Gate"') + 300);
  assert.match(gate, /label: "Gate & Merge"/,
    "the rail said Gate while the screen said Gate & Merge, hiding the half that ships the work");
});

/* ── Gate: the live feed ─────────────────────────────────────────────────── */

test("no workflow run is not the same as a clean run", () => {
  assert.match(ACTIVITY, /jobs === null/);
  assert.match(ACTIVITY, /No workflow run for this commit/);
  assert.ok(!/jobs\.length === 0 \?[\s\S]{0,80}Passed/.test(ACTIVITY));
});

test("each step says what that gate reads and what it blocks on", () => {
  // A step name alone ("forbidden-sweep") tells a non-engineer nothing.
  assert.match(ACTIVITY, /PHASE_WHERE/);
  assert.match(ACTIVITY, /reads the pull request diff and the source tree/);
  assert.match(ACTIVITY, /reads the built HTML, page by page/);
  assert.match(ACTIVITY, /reads the JSON artifacts the pull request carries/);
  assert.match(ACTIVITY, /blocks when \{gate\.blocks\}/);
});

test("polling stops when the run stops", () => {
  // A finished run is finished; polling it forever burns the operator's GitHub
  // rate limit for nothing.
  assert.match(ACTIVITY, /if \(!running\) return;/);
  assert.match(ACTIVITY, /clearTimeout/);
});

test("a queued step is not drawn as a pass", () => {
  const d = ACTIVITY.slice(ACTIVITY.indexOf("function dot("), ACTIVITY.indexOf("export function GateActivity"));
  assert.match(d, /status !== "completed"/);
  assert.match(d, /Queued/);
  assert.match(d, /in_progress/);
  assert.ok(d.indexOf('case "success"') > d.indexOf('status !== "completed"'),
    "completion must be checked before any conclusion is trusted");
});

test("the feed is mounted on the pull request, not just written", () => {
  assert.match(DASH, /<GateActivity/);
  assert.match(DASH, /sha=\{pr\.headSha\}/);
});
