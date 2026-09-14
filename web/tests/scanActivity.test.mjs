import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { applyScanEvent, outcomeOf, formatElapsed, MAX_LINES } = await import("../lib/scanActivity.ts");

function fold(events) {
  let tools = [];
  let t = 1000;
  for (const ev of events) tools = applyScanEvent(tools, ev, (t += 1000));
  return tools;
}

test("a tool runs, reports real steps, then finishes with its cost", () => {
  const [bl] = fold([
    { tool: "Backlinks (DataForSEO)", state: "running" },
    { tool: "Backlinks (DataForSEO)", state: "progress", status: "Requesting backlinks summary from DataForSEO", detail: { step: "request", phase: "start" } },
    { tool: "Backlinks (DataForSEO)", state: "progress", status: "backlinks summary answered", detail: { step: "request", phase: "done", ms: 812, cost: 0.024 } },
    { tool: "Backlinks (DataForSEO)", state: "done", status: "ok", cost: 0.024, rows: [{ code: "dfs.backlinks", severity: "info" }] },
  ]);
  assert.equal(bl.state, "done");
  assert.equal(bl.cost, 0.024);
  assert.deepEqual(bl.lines.map((l) => l.phase), ["start", "done"]);
  assert.equal(bl.lines[1].ms, 812);
  assert.equal(bl.finishedAt - bl.startedAt, 3000);
});

test("progress never overwrites a tool's state or rows", () => {
  const [t] = fold([
    { tool: "X", state: "running" },
    { tool: "X", state: "done", rows: [{ code: "a", severity: "ok" }], status: "ok", cost: 0 },
    { tool: "X", state: "progress", status: "late line", detail: {} },
  ]);
  assert.equal(t.state, "done");
  assert.equal(t.rows.length, 1);
});

test("the crawl bar uses DataForSEO's own page counts", () => {
  const [site] = fold([
    { tool: "Site Health (DataForSEO)", state: "running" },
    { tool: "Site Health (DataForSEO)", state: "progress", status: "Crawling: 6 of 25 pages", detail: { step: "crawl", phase: "progress", pages_crawled: 6, pages_in_queue: 9, max_crawl_pages: 25 } },
    { tool: "Site Health (DataForSEO)", state: "progress", status: "Crawling: 14 of 25 pages", detail: { step: "crawl", phase: "progress", pages_crawled: 14, pages_in_queue: 6, max_crawl_pages: 25 } },
  ]);
  assert.deepEqual(site.crawl, { crawled: 14, queue: 6, max: 25 });
});

test("our free crawl shows the page it is fetching", () => {
  const [c] = fold([
    { tool: "Multi-page crawl", state: "progress", status: "Fetching page 2 of up to 5", detail: { step: "page", n: 2, total: 5, url: "https://x.com/about" } },
  ]);
  assert.deepEqual(c.page, { n: 2, total: 5, url: "https://x.com/about" });
  assert.equal(c.state, "running");
});

test("phase markers and malformed events are ignored", () => {
  assert.deepEqual(fold([{ tool: "Phase 1/4", state: "phase" }, { log: "x" }, null]), []);
});

test("lines are capped so a long crawl stays readable", () => {
  const evs = [{ tool: "X", state: "running" }];
  for (let i = 0; i < MAX_LINES + 15; i++) evs.push({ tool: "X", state: "progress", status: `line ${i}`, detail: {} });
  const [t] = fold(evs);
  assert.equal(t.lines.length, MAX_LINES);
  assert.equal(t.lines.at(-1).text, `line ${MAX_LINES + 14}`);
});

test("outcome names a tool that did not run, and counts real issues", () => {
  const base = { name: "X", state: "done", startedAt: 0, lines: [], cost: 0, status: "" };
  assert.equal(outcomeOf({ ...base, rows: [{ code: "unavailable.backlinks", why: "paused", severity: "info" }] }).kind, "not-run");
  assert.deepEqual(outcomeOf({ ...base, rows: [{ code: "a", severity: "ok" }, { code: "b", severity: "warn" }] }),
    { kind: "issues", label: "2 checks · 1 issue" });
  assert.equal(formatElapsed(83_400), "01:23");
});

test("the panel is mounted on the tool page and fed by the reducer", () => {
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const app = readFileSync(new URL("../app/ScannerApp.tsx", import.meta.url), "utf8");
  const renderer = dash.slice(dash.indexOf("const view = viewById(activeView);"), dash.indexOf("<FixWithClaude", dash.indexOf("const view = viewById(activeView);")));
  assert.match(renderer, /<LiveScanActivity/);
  assert.match(app, /applyScanEvent\(/);
});

test("the free crawl finishes when the scanner says it has", () => {
  const [c] = fold([
    { tool: "Multi-page crawl", state: "progress", status: "Fetching page 1", detail: { step: "page", n: 1, total: 3, url: "https://x.com/" } },
    { tool: "Multi-page crawl", state: "progress", status: "Crawled 3 page(s)", detail: { step: "page", phase: "finished", n: 3, total: 3 } },
  ]);
  assert.equal(c.state, "done");
  assert.ok(c.finishedAt);
});
