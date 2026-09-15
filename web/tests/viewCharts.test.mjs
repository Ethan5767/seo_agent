import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/** Every tool page's charts, from the row text the scanner writes. */
const V = await import("../lib/viewCharts.ts");

test("keyword rows yield positions, volume, difficulty and intent as stated", () => {
  const rows = [
    { code: "dfs.ranked_keyword", what: '"hospital phnom penh" — rank #8', detail: "position 8, ~720/mo searches" },
    { code: "dfs.serp_rank", what: '"orienda" — rank #1', detail: "position 1" },
    { code: "dfs.keyword_volume", what: '"clinic cambodia" — 1,300/mo searches', detail: "1300/mo" },
    { code: "dfs.keyword_difficulty", what: '"clinic cambodia" — difficulty 42/100', detail: "KD 42" },
    { code: "dfs.search_intent", what: '"clinic cambodia" — commercial intent' },
    { code: "dfs.keyword_gap", what: '"dentist" — 90/mo searches', detail: "90/mo" },
  ];
  const k = V.keywordCharts(rows);
  assert.equal(k.keywords, 4);
  assert.deepEqual(k.positions.map((b) => b.value), [1, 1, 0, 0, 0]);
  assert.deepEqual(k.topVolume, [{ label: "clinic cambodia", value: 1300 }, { label: "hospital phnom penh", value: 720 }, { label: "dentist", value: 90 }]);
  assert.deepEqual(k.difficulty.map((b) => b.value), [0, 1, 0, 0]);
  assert.deepEqual(k.intent, [{ label: "Commercial", value: 1 }]);
  assert.equal(k.totalVolume, 2110);
});

test("nothing stated means an empty series, not zero bars", () => {
  const k = V.keywordCharts([{ code: "dfs.keyword_idea", what: '"x"' }]);
  assert.deepEqual(k.positions, []);
  assert.deepEqual(k.difficulty, []);
  assert.deepEqual(k.topVolume, []);
});

test("findings pages chart the severity mix and the checks hitting most pages", () => {
  const f = V.findingCharts([
    { code: "dfs.op.no_image_alt", what: "Images missing alt", detail: "25 page(s)", severity: "warn" },
    { code: "dfs.op.title_too_long", what: "Title too long", detail: "4 page(s)", severity: "warn" },
    { code: "site.duplicate_page_titles", what: "Duplicate page titles", detail: "on 6 pages", severity: "warn" },
    { code: "dfs.op.is_https", what: "HTTPS", detail: "25 page(s)", severity: "ok" },
    { code: "tech.x", what: "Missing canonical", severity: "error" },
  ]);
  assert.deepEqual(f.severity.map((s) => s.value), [1, 3, 1, 0]);
  assert.deepEqual(f.topIssues[0], { label: "Images missing alt", value: 25 });
  assert.equal(f.graded, 5);
});

test("compare and backlink gap read their own rows", () => {
  const c = V.compareCharts([
    { code: "dfs.compare_domain", domain: "you.com", what: "you.com (you): Ranks for 128 keywords on Google", metrics: { keywords: 128, etv: 900.4 } },
    { code: "dfs.compare_domain", domain: "rival.com", what: "rival.com: Ranks for 300 keywords on Google" },
  ]);
  assert.deepEqual(c.keywords, [{ label: "you.com", value: 128 }, { label: "rival.com", value: 300 }]);
  assert.deepEqual(c.traffic, [{ label: "you.com", value: 900 }]);
  const g = V.backlinkGapCharts([{ code: "dfs.backlink_gap", what: "news.kh", detail: "rank 310 · 42 links · spam 12 · since 2024-01-01" }]);
  assert.deepEqual(g.topLinks, [{ label: "news.kh", value: 42 }]);
  assert.deepEqual(g.spam.map((b) => b.value), [1, 0, 0]);
});

test("every tool page, Site Audit's crawl tab, Search Console and GA4 draw charts", () => {
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  assert.match(dash, /<ViewCharts viewId=\{view\.id\} label=\{view\.label\} rows=\{rows as any\} report=\{report\} \/>/);
  assert.match(dash, /<ViewCharts viewId="site-crawl"/);
  const gsc = readFileSync(new URL("../components/dashboard/GscPanel.tsx", import.meta.url), "utf8");
  assert.match(gsc, /<TrendChart/);
  assert.match(gsc, /<DistributionBars/);
  const ga4 = readFileSync(new URL("../components/dashboard/Ga4Panel.tsx", import.meta.url), "utf8");
  assert.match(ga4, /<TrendChart/);
  assert.match(ga4, /<Donut/);
  const { REPORT_VIEWS } = { REPORT_VIEWS: null };
  for (const id of ["technical", "on-page", "core-web-vitals", "backlinks", "keyword-ideas", "compare-domains", "backlink-gap", "ai-mentions", "trust"]) {
    assert.notEqual(V.chartKind(id), "none", `${id} has no charts`);
  }
});
