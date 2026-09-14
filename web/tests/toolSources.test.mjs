import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The Data source dropdown on every tool page (operator decision 2026-09-14:
 * DataForSEO by default, our own tools kept, a source that cannot serve a page
 * listed disabled with its reason).
 */

const { TOOL_SOURCES, DFS_FLAGS, isEnabled, sourceBlocker, effectiveSource } =
  await import("../lib/toolSources.ts");
const { REPORT_VIEWS, viewById, rowsForView } = await import("../lib/reportViews.ts");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");
const read = (...p) => readFileSync(path.join(REPO, ...p), "utf8");

const serverKeys = () =>
  [...read("pipeline", "scanner", "server.py").matchAll(/Tool\("[^"]+", "([^"]+)"/g)].map((m) => m[1]);

test("every tool page has a source entry", () => {
  const missing = REPORT_VIEWS.filter((v) => v.section && !TOOL_SOURCES[v.id]).map((v) => v.id);
  assert.deepEqual(missing, [], "tool pages with no Data source dropdown: " + missing.join(", "));
});

test("every source lists real scanner tools", () => {
  const keys = new Set(serverKeys());
  assert.ok(keys.size > 20);
  for (const [id, s] of Object.entries(TOOL_SOURCES)) {
    for (const src of ["dataforseo", "ours"]) {
      const opt = s[src];
      if (!isEnabled(opt)) {
        assert.ok(opt.disabled.length > 10, `${id}/${src} is disabled without a reason`);
        continue;
      }
      for (const k of opt.tools) assert.ok(keys.has(k), `${id}/${src} runs unknown tool '${k}'`);
      assert.ok(opt.codes.length > 0, `${id}/${src} shows no codes`);
    }
  }
});

test("the DataForSEO option only runs DataForSEO tools, ours only free ones", () => {
  const src = read("pipeline", "scanner", "server.py");
  const group = Object.fromEntries(
    [...src.matchAll(/Tool\("[^"]+", "([^"]+)", "[^"]+", "([^"]+)"/g)].map((m) => [m[1], m[2]]),
  );
  for (const [id, s] of Object.entries(TOOL_SOURCES)) {
    if (isEnabled(s.dataforseo)) {
      for (const k of s.dataforseo.tools) assert.equal(group[k], "dataforseo", `${id}: DataForSEO option runs ${k} (${group[k]})`);
    }
    if (isEnabled(s.ours)) {
      for (const k of s.ours.tools) assert.notEqual(group[k], "dataforseo", `${id}: our-tools option would spend money on ${k}`);
    }
  }
});

test("every DataForSEO on-page flag is placed on exactly one page", () => {
  const src = read("pipeline", "scanner", "onpage_audit.py");
  const block = src.slice(src.indexOf("CHECKS = {"), src.indexOf("\n}", src.indexOf("CHECKS = {")));
  const flags = [...block.matchAll(/^\s+"([a-z0-9_]+)":/gm)].map((m) => m[1]);
  assert.ok(flags.length >= 50, `parsed ${flags.length} flags`);
  const placed = [...DFS_FLAGS.crawl, ...DFS_FLAGS.technical, ...DFS_FLAGS.onPage];
  assert.equal(new Set(placed).size, placed.length, "a flag is on two pages");
  assert.deepEqual([...placed].sort(), [...flags].sort());
});

const CATALOG_OK = [
  { key: "site", available: true }, { key: "backlinks", available: true },
  { key: "tech", available: true }, { key: "schema", available: true }, { key: "validate", available: true },
];
const CATALOG_PAUSED = [
  { key: "site", available: false, unavailable_reason: "paused by DATAFORSEO_PAUSE_SPEND=1" },
  { key: "backlinks", available: false, unavailable_reason: "paused by DATAFORSEO_PAUSE_SPEND=1" },
  { key: "tech", available: true }, { key: "schema", available: true }, { key: "validate", available: true },
];

test("DataForSEO is the default when it can serve the page", () => {
  assert.equal(effectiveSource("technical", null, CATALOG_OK), "dataforseo");
  assert.equal(effectiveSource("backlinks", null, CATALOG_OK), "dataforseo");
});

test("a saved choice of our tools is kept", () => {
  assert.equal(effectiveSource("technical", "ours", CATALOG_OK), "ours");
});

test("paused DataForSEO falls back to our tools, and says why", () => {
  assert.equal(effectiveSource("technical", "dataforseo", CATALOG_PAUSED), "ours");
  assert.match(sourceBlocker("technical", "dataforseo", CATALOG_PAUSED), /PAUSE_SPEND=1/);
});

test("a page with no free source has no usable source while DataForSEO is paused", () => {
  assert.equal(effectiveSource("backlinks", null, CATALOG_PAUSED), null);
  assert.match(sourceBlocker("backlinks", "ours", CATALOG_PAUSED), /backlink index/);
});

test("pages only we can serve open on our tools", () => {
  assert.equal(effectiveSource("core-web-vitals", null, CATALOG_OK), "ours");
  assert.equal(effectiveSource("source-code", null, CATALOG_OK), "ours");
});

test("the table shows only the chosen source's rows", () => {
  const report = {
    tech: [{ code: "tech.https", what: "HTTPS", why: "", fix: "", severity: "ok" }],
    site: [{ code: "dfs.op.is_http", what: "Served over HTTP", why: "", fix: "", severity: "error" }],
  };
  const view = viewById("technical");
  const dfsRows = rowsForView(report, view, TOOL_SOURCES.technical.dataforseo);
  const ourRows = rowsForView(report, view, TOOL_SOURCES.technical.ours);
  assert.deepEqual(dfsRows.map((r) => r.code), ["dfs.op.is_http"]);
  assert.deepEqual(ourRows.map((r) => r.code), ["tech.https"]);
});

test("the tool page wires the dropdown to both the table and the Test button", () => {
  // Implemented is not wired (B-007): assert the call sites.
  const dash = read("web", "app", "ReaiDashboard.tsx");
  const renderer = dash.slice(dash.indexOf("const view = viewById(activeView);"), dash.indexOf("<FixWithClaude", dash.indexOf("const view = viewById(activeView);")));
  assert.match(renderer, /effectiveSource\(/);
  assert.match(renderer, /rowsForView\(report, view, /);
  assert.match(renderer, /sourceTools=/);
  const btn = read("web", "components", "dashboard", "SectionScanButton.tsx");
  assert.match(btn, /<select[^>]*aria-label="Data source"/);
});
