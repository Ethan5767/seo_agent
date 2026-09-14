import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { mergeScanReport } = await import("../lib/reportMerge.ts");

const codes = (rows) => rows.map((r) => r.code);
const BASE = {
  site: [{ code: "site.pages_crawled" }, { code: "dfs.op.is_http" }, { code: "dfs.op.no_h1_tag" }],
  backlinks: [{ code: "dfs.backlinks" }],
  seo: [{ code: "health.title_missing" }],
};

test("a scan without Site Health keeps the Site Health rows (the review's repro)", () => {
  const next = { site: [{ code: "site.pages_crawled" }], backlinks: [{ code: "dfs.backlinks" }] };
  const m = mergeScanReport(BASE, next, ["backlinks"]);
  assert.deepEqual(codes(m.site), ["site.pages_crawled", "dfs.op.is_http", "dfs.op.no_h1_tag"]);
  assert.deepEqual(codes(m.seo), ["health.title_missing"]);
});

test("a Site Health run replaces the old Site Health rows, not adds to them", () => {
  const next = { site: [{ code: "site.pages_crawled" }, { code: "dfs.op.is_http" }] };
  const m = mergeScanReport(BASE, next, ["site"]);
  assert.deepEqual(codes(m.site), ["site.pages_crawled", "dfs.op.is_http"]);
});

test("a refused Site Health run replaces the old rows with its reason", () => {
  const next = { site: [{ code: "site.pages_crawled" }, { code: "unavailable.site" }] };
  const m = mergeScanReport(BASE, next, ["site"]);
  assert.deepEqual(codes(m.site), ["site.pages_crawled", "unavailable.site"]);
});

test("other groups are still replaced whole by the tool that ran", () => {
  const next = { backlinks: [{ code: "unavailable.backlinks" }] };
  const m = mergeScanReport(BASE, next, ["backlinks"]);
  assert.deepEqual(codes(m.backlinks), ["unavailable.backlinks"]);
  assert.deepEqual(codes(m.site), codes(BASE.site));
});

test("ScannerApp merges through mergeScanReport", () => {
  const app = readFileSync(new URL("../app/ScannerApp.tsx", import.meta.url), "utf8");
  assert.match(app, /\.\.\.mergeScanReport\(baseReport, /);
  assert.doesNotMatch(app, /\.\.\.baseReport,\s*\.\.\.finalAudit,/);
});
