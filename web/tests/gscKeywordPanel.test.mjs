import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const panel = readFileSync(new URL("../components/dashboard/GscKeywordPanel.tsx", import.meta.url), "utf8");
const dashboard = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");

test("Keyword Overview adds a GSC-only owned-site panel after its primary table", () => {
  const overview = dashboard.slice(dashboard.indexOf('view.id === "keyword-overview"'));
  assert.match(overview, /<GscKeywordPanel siteUrl=\{selectedGscProperty\}/);
  assert.match(overview, /googleConnected && selectedGscProperty/);
  assert.ok(
    overview.indexOf("<ReportTable") < overview.indexOf("<GscKeywordPanel"),
    "GSC must be additive below the DataForSEO Keyword Overview, not replace it",
  );
});

test("the panel requests only real query performance from the existing GSC route", () => {
  assert.match(panel, /authedFetch\("\/api\/gsc\/query"/);
  assert.match(panel, /dimensions: \["query"\], days: 28, rowLimit: 50/);
  for (const heading of ["Impressions", "Clicks", "CTR", "Avg position"]) {
    assert.match(panel, new RegExp(`>${heading}<`));
  }
});

test("the panel explicitly distinguishes GSC query performance from keyword research", () => {
  assert.match(panel, /Queries already earning impressions/);
  assert.match(panel, /not search volume, keyword discovery, or difficulty data/i);
  assert.match(panel, /DataForSEO Keyword Overview above remains the primary keyword research source/);
  assert.match(panel, /Google Search Console — your verified property/);
});
