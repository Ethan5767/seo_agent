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

test("the scan bar never mixes the border shorthand with a borderStyle override", () => {
  // React: "Removing a style property during rerender (borderStyle) when a
  // conflicting property is set (border) can lead to styling bugs." Reported
  // from the live page on 2026-09-14.
  const btn = read("web", "components", "dashboard", "SectionScanButton.tsx");
  const shell = btn.slice(btn.indexOf("const shell"), btn.indexOf("};", btn.indexOf("const shell")));
  assert.ok(btn.includes("...shell, borderStyle"), "the dashed states moved; revisit this test");
  assert.doesNotMatch(shell, /\bborder:/);
});


test("a source only runs tools whose rows its page shows (no unseen spend)", () => {
  // Domain Overview's button ran `keywords` ($0.18) for a row `rankings` emits
  // (B-112); AI Mentions ran `mentions` ($0.03) for rows it never showed.
  const emits = {
    rankings: ["dfs.ranked_keyword", "dfs.domain_overview", "dfs.serp_rank"],
    ai: ["dfs.llm_mentions"],
    mentions: ["mention."],
  };
  for (const id of ["domain-overview", "ai-mentions"]) {
    const opt = TOOL_SOURCES[id].dataforseo;
    for (const tool of opt.tools) {
      const shown = (emits[tool] || []).some((c) => opt.codes.some((p) => c.startsWith(p) || p.startsWith(c)));
      assert.ok(shown, `${id} runs ${tool} but shows none of its rows`);
    }
  }
  assert.deepEqual(TOOL_SOURCES["domain-overview"].dataforseo.tools, ["rankings"]);
});


test("an unknown catalog never hides free rows behind a DataForSEO default", () => {
  assert.equal(effectiveSource("technical", null, []), "ours");
  assert.equal(effectiveSource("technical", null, undefined), "ours");
  assert.match(sourceBlocker("backlinks", "dataforseo", []), /not loaded/);
});

test("Scan all from a tool page runs free tools plus the chosen source, and names any paid one", () => {
  const btn = read("web", "components", "dashboard", "SectionScanButton.tsx");
  assert.match(btn, /onClick=\{\(\) => onScan\(domain, scanAllKeys\)\}/);
  assert.doesNotMatch(btn, /onScan\(domain, sectionKeys\)/);
  assert.match(btn, /scanAllPaid\.map/);
});


test("a scan that ran and found nothing is not 'no data yet' (operator, Crawl Issues)", async () => {
  const { sourceRan, TOOL_SOURCES } = await import("../lib/toolSources.ts");
  // The operator's saved 10:05 scan: Site Health ran, 12 flags, none crawl-type.
  const report = {
    site: [{ code: "site.pages_crawled" }, { code: "site.duplicate_page_titles", severity: "warn" },
           { code: "dfs.op.title_too_long", severity: "warn" }, { code: "dfs.op.frame", severity: "warn" }],
  };
  const crawl = TOOL_SOURCES["site-crawl"];
  assert.equal(sourceRan(report, crawl.dataforseo), true);
  assert.equal(rowsForView(report, viewById("site-crawl"), crawl.dataforseo).length, 0);
  const ours = rowsForView(report, viewById("site-crawl"), crawl.ours);
  assert.equal(ours.filter((r) => r.severity === "warn" || r.severity === "error").length, 1);
  // Only the free crawl ran: Site Health did not.
  assert.equal(sourceRan({ site: [{ code: "site.pages_crawled" }] }, crawl.dataforseo), false);
  assert.equal(sourceRan(null, crawl.dataforseo), false);
  const dash = read("web", "app", "ReaiDashboard.tsx");
  assert.match(dash, /checkedEmpty=\{checkedEmpty\}/);
});


test("every tool checks the live domain: no Source Code page, no repo sent to a scan", () => {
  // Operator, 2026-09-14: "all tool must check DOMAIN"; source code is hidden.
  const dash = read("web", "app", "ReaiDashboard.tsx");
  const app = read("web", "app", "ScannerApp.tsx");
  assert.doesNotMatch(dash, /label: "Source Code", view: "source-code"/);
  assert.equal(REPORT_VIEWS.some((v) => v.id === "source-code"), false);
  const at = app.indexOf('authedFetch("/api/scan", {');
  assert.ok(at > 0, "scan request moved");
  const body = app.slice(at, at + 500);
  assert.doesNotMatch(body, /github_token/);
  assert.doesNotMatch(body, /\brepo,/);
  assert.match(body, /filter\(\(k\) => k !== "source"\)/);
  const modal = read("web", "components", "dashboard", "ProjectModal.tsx");
  assert.match(modal, /<details[\s\S]{0,300}Advanced: source code repository/);
});

test("Backlink Gap is a real tool page on DataForSEO, not the old empty tab (B-116)", () => {
  const dash = read("web", "app", "ReaiDashboard.tsx");
  assert.match(dash, /\{ label: "Backlink Gap", view: "backlink-gap" \}/);
  assert.doesNotMatch(dash, /\{ label: "Backlink Gap", tab: "Backlink Gap" \}/);
  assert.deepEqual(TOOL_SOURCES["backlink-gap"].dataforseo.tools, ["backlink_gap"]);
  assert.ok(viewById("backlink-gap"));
});


test("Backlink Audit only waits for rows a scan can produce (B-115)", () => {
  assert.deepEqual(viewById("backlink-audit").codes, ["dfs.broken_backlinks"]);
});
