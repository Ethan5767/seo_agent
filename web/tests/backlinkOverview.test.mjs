import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * Backlink Overview reads the rows the Python parsers produce from DataForSEO
 * sandbox responses (tests/fixtures/dfs_backlinks_*.json, regenerated into
 * web/tests/fixtures/backlink_overview_rows.json), so the two sides cannot drift.
 */
const { backlinkOverview } = await import("../lib/backlinkOverview.ts");
const rows = JSON.parse(readFileSync(new URL("./fixtures/backlink_overview_rows.json", import.meta.url), "utf8"));
const summary = JSON.parse(readFileSync(new URL("../../tests/fixtures/dfs_backlinks_summary.json", import.meta.url), "utf8")).tasks[0].result[0];

test("headline counts, follow split and profile breakdowns come from the summary", () => {
  const o = backlinkOverview(rows);
  assert.equal(o.measured, true);
  assert.equal(o.backlinks, summary.backlinks);
  assert.equal(o.referringDomains, summary.referring_domains);
  assert.equal(o.spamScore, summary.backlinks_spam_score);
  assert.deepEqual(o.follow, [
    { label: "Follow", value: summary.referring_domains - summary.referring_domains_nofollow },
    { label: "Nofollow", value: summary.referring_domains_nofollow },
  ]);
  assert.equal(o.types[0].label, "image");
  assert.ok(o.countries.every((c) => c.label !== ""));
});

test("history, top referring domains and anchors are listed as reported", () => {
  const o = backlinkOverview(rows);
  assert.equal(o.history.length, 14);
  assert.equal(o.referringDomains10.length, 4);
  assert.equal(o.anchors10.length, 4);
  assert.ok(o.newLast && typeof o.newLast.newDomains === "number");
});

test("nothing measured is not measured; an old text-only row still gives its two counts", () => {
  assert.equal(backlinkOverview([]).measured, false);
  const old = backlinkOverview([{ code: "dfs.backlinks", what: "18168 backlinks from 48 referring domains" }]);
  assert.equal(old.backlinks, 18168);
  assert.equal(old.referringDomains, 48);
  assert.deepEqual(old.follow, [], "no nofollow count, no split");
});

test("the page is registered, in the sidebar, has an address and runs its own tool", async () => {
  const { VIEW_TOOLS } = await import("../lib/sectionScans.ts");
  assert.deepEqual(VIEW_TOOLS["backlink-overview"], ["backlink_overview"]);
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  assert.match(dash, /\{ label: "Backlink Overview", view: "backlink-overview" \}/);
  assert.match(dash, /<BacklinkOverviewDashboard rows=\{\[\.\.\.rows, \.\.\.rowsForView\(report, viewById\("backlinks"\)!\)\]\} \/>/);
});
