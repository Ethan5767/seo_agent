import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * The dashboard charts read only measured values. Fixtures are the row formats
 * saved for the operator's projects on 2026-09-08 and 2026-09-14.
 */
const M = await import("../lib/dashboardMetrics.ts");

const REPORT = {
  score: 72,
  rankings: [
    { code: "dfs.ranked_keyword", what: '"orenda international hospital" — rank #1', detail: "position 1, ~140/mo searches", severity: "ok" },
    { code: "dfs.ranked_keyword", what: '"hospital phnom penh" — rank #8', detail: "position 8, ~720/mo searches", severity: "ok" },
    { code: "dfs.ranked_keyword", what: '"clinic" — rank #34', detail: "position 34", severity: "ok" },
    { code: "dfs.ranked_keyword", competitor: "rival.com", what: 'rival.com: "x" — rank #2', detail: "position 2", severity: "ok" },
    { code: "dfs.domain_overview", what: "Ranks for 128 keywords on Google", detail: "128 keywords", severity: "ok" },
  ],
  backlinks: [
    { code: "dfs.backlinks", what: "18168 backlinks from 48 referring domains", detail: "authority rank 268", severity: "ok" },
    { code: "dfs.broken_backlinks", what: "87 broken backlink(s)", detail: "87 broken", severity: "warn" },
  ],
  lh_perf: [{ code: "lh.lighthouse_performance", what: "Lighthouse: Performance", detail: "46/100", severity: "error" }],
  lh_seo: [{ code: "lh.lighthouse_seo", what: "Lighthouse: SEO", detail: "100/100", severity: "ok" }],
  site: [
    { code: "site.pages_crawled", what: "Pages crawled", detail: "25 pages", severity: "ok" },
    { code: "site.duplicate_page_titles", what: "Duplicate page titles", detail: "on 6 pages", severity: "warn" },
  ],
  aeo: [
    { code: "", what: "AI crawlers allowed", severity: "ok" },
    { code: "health.schema_business_missing", what: "schema business missing", severity: "warn" },
  ],
  ai: [{ code: "dfs.llm_mentions", what: "Orienda hospital: not cited by AI engines", detail: "0 mentions", severity: "warn" }],
};

test("ranked keywords are parsed, sorted, and a competitor's are left out", () => {
  const kws = M.rankedKeywords(REPORT);
  assert.deepEqual(kws.map((k) => [k.keyword, k.position, k.volume]), [
    ["orenda international hospital", 1, 140], ["hospital phnom penh", 8, 720], ["clinic", 34, null],
  ]);
  assert.deepEqual(M.positionDistribution(kws).map((b) => b.value), [1, 1, 0, 1, 0]);
});

test("organic, backlinks, Lighthouse and AI read the saved formats", () => {
  assert.deepEqual(M.organic(REPORT), { keywordsTotal: 128, traffic: null, trend: [] });
  assert.deepEqual(M.backlinks(REPORT), { backlinks: 18168, referringDomains: 48, rank: 268, broken: 87 });
  assert.deepEqual(M.lighthouse(REPORT).map((c) => c.score), [46, 100, null, null]);
  assert.deepEqual(M.aiSearch(REPORT), { passed: 1, failing: 1, mentions: 0 });
  const audit = M.siteAudit(REPORT);
  assert.equal(audit.score, 72);
  assert.equal(audit.pagesCrawled, 25);
});

test("not measured is null or empty, never a zero or a shape", () => {
  assert.equal(M.siteAudit(null), null);
  assert.equal(M.organic({}), null);
  assert.equal(M.backlinks({ site: [] }), null);
  assert.equal(M.aiSearch({}), null);
  assert.deepEqual(M.rankedKeywords({}), []);
  assert.deepEqual(M.lighthouse({}).map((c) => c.score), [null, null, null, null]);
  assert.deepEqual(M.healthTrend([], "x.com"), []);
});

test("health trend uses graded scans of this domain only, oldest first", () => {
  const scans = [
    { created_at: "2026-09-14T10:17:00Z", url: "https://www.oriendainternationalhospital.com.kh/en", score: 72, counts: { error: 5, warn: 29, ok: 88 } },
    { created_at: "2026-09-14T09:42:00Z", url: "https://github.com", score: 65, counts: {} },
    { created_at: "2026-09-14T04:19:00Z", url: "https://www.oriendainternationalhospital.com.kh/en", score: 33, counts: { error: 0, warn: 2, ok: 1 } },
    { created_at: "2026-09-13T00:00:00Z", url: "https://www.oriendainternationalhospital.com.kh/", score: null, counts: null },
  ];
  const t = M.healthTrend(scans, "oriendainternationalhospital.com.kh");
  assert.deepEqual(t.map((p) => p.value), [33, 72], "github.com scan and the ungraded one are excluded");
  assert.deepEqual(M.issueHistory(scans, "www.oriendainternationalhospital.com.kh").map((b) => b.errors), [0, 5]);
});

test("the Overview opens on the chart dashboard, fed the project's scans", () => {
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const overview = dash.slice(dash.indexOf('{activeTab === "Overview" && ('));
  assert.ok(overview.indexOf("<SeoDashboard") > 0 && overview.indexOf("<SeoDashboard") < overview.indexOf("<AuditHeroBar"));
  assert.match(dash, /scans=\{scans\}/);
  assert.match(readFileSync(new URL("../app/ScannerApp.tsx", import.meta.url), "utf8"), /scans=\{hist\}/);
  const charts = readFileSync(new URL("../components/dashboard/Charts.tsx", import.meta.url), "utf8");
  assert.match(charts, /if \(points\.length < 2\) return <Empty/, "one point is not a trend");
});
