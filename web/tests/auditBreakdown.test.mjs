import { test } from "node:test";
import assert from "node:assert/strict";

/**
 * "Why is the score 75?" answered from the report's own rows (operator,
 * 2026-09-15). The breakdown must add back to the score, count exactly the rows
 * the scanner graded, and never invent a weight.
 */
const B = await import("../lib/auditBreakdown.ts");

const r = (code, severity, extra = {}) => ({ code, what: code, why: "", fix: "", detail: "", severity, ...extra });

const REPORT = {
  score: 60,
  score_version: 3,
  seo: [
    r("health.title_length", "error", { pages: ["https://x.com/a", "https://x.com/b", "https://x.com/c"] }),
    r("health.desc_missing", "warn", { pages: ["https://x.com/a"] }),
    r("health.h1_count", "ok"),
    r("health.img_alt_missing", "warn", { pages: ["https://x.com/a", "https://x.com/b"] }),
  ],
  tech: [r("tech.https", "ok"), r("tech.mobile_viewport", "ok"), r("tech.xml_sitemap", "ok")],
  site: [r("site.pages_crawled", "ok"), r("site.orphan_check", "info")],
  // Not part of the audit: never graded, never in the breakdown.
  rankings: [r("dfs.ranked_keyword", "ok"), r("dfs.ranked_keyword", "ok")],
  lh_seo: [r("lh.lighthouse_seo", "error")],
  crawl: { requested: 5, pages: [
    { url: "https://x.com/", status: 200, title: "Home", has_description: true, h1_count: 1, words: 400, links_out: 12, links_in: 3, errors: 0, warnings: 0, issues: {} },
    { url: "https://x.com/a", status: 200, title: null, has_description: false, h1_count: 0, words: 90, links_out: 4, links_in: 1, errors: 1, warnings: 2, issues: { "health.title_length": "error", "health.desc_missing": "warn", "health.img_alt_missing": "warn" } },
  ] },
};

test("the audit lists match the scanner's", () => {
  assert.deepEqual([...B.ONPAGE_AUDIT_TOOLS], ["seo", "onpage", "tech", "schema", "validate", "internal"]);
  assert.deepEqual(new Set(B.SCORED_GROUPS), new Set([...B.ONPAGE_AUDIT_TOOLS, "site"]));
});

test("the score counts only the audit's groups, the scanner's way", () => {
  const s = B.auditScore(REPORT);
  // ok: h1, https, viewport, sitemap, pages_crawled = 5; failing: 3. info not graded.
  assert.equal(s.graded, 8);
  assert.equal(s.ok, 5);
  assert.equal(s.error, 1);
  assert.equal(s.warn, 2);
  assert.equal(s.score, 63);
  assert.equal(s.perCheck, 12.5);
});

test("nothing graded is no score, not zero", () => {
  const s = B.auditScore({ rankings: [r("dfs.ranked_keyword", "ok")] });
  assert.equal(s.score, null);
  assert.equal(s.perCheck, null);
});

test("the category losses add back to the score", () => {
  const b = B.scoreBreakdown(REPORT);
  const lost = b.categories.reduce((n, c) => n + c.pointsLost, 0);
  assert.ok(Math.abs(100 - lost - b.exact) < 1e-9, "100 minus every category's loss is the exact score");
  assert.equal(Math.round(b.exact), b.score);
  const titles = b.categories.find((c) => c.id === "titles");
  assert.equal(titles.failing, 2);
  assert.equal(titles.pointsLost, 25);
  // Largest loss first.
  assert.deepEqual(b.categories.map((c) => c.pointsLost), [...b.categories.map((c) => c.pointsLost)].sort((x, y) => y - x));
});

test("every graded check lands in exactly one category", () => {
  const b = B.scoreBreakdown(REPORT);
  assert.equal(b.categories.reduce((n, c) => n + c.graded, 0), b.graded);
});

test("codes map to the category an operator would look in", () => {
  assert.equal(B.categoryOf("health.title_missing"), "titles");
  assert.equal(B.categoryOf("site.duplicate_meta_descriptions"), "titles");
  assert.equal(B.categoryOf("health.h1_count"), "content");
  assert.equal(B.categoryOf("site.broken_internal_link"), "links");
  assert.equal(B.categoryOf("tech.internal_links"), "links");
  assert.equal(B.categoryOf("health.img_alt_missing"), "images");
  assert.equal(B.categoryOf("schema.structured_data"), "schema");
  assert.equal(B.categoryOf("health.noindex_present"), "indexing");
  assert.equal(B.categoryOf("valid.sitemap_valid"), "indexing");
  assert.equal(B.categoryOf("tech.https"), "technical");
  assert.equal(B.categoryOf("tech.open_graph_tags"), "social");
  assert.equal(B.categoryOf("something.unheard_of"), "technical");
});

test("issues rank errors first, then by pages affected", () => {
  const issues = B.rankedIssues(REPORT);
  assert.deepEqual(issues.map((i) => i.code), ["health.title_length", "health.img_alt_missing", "health.desc_missing"]);
  assert.equal(issues[0].pageCount, 3);
  assert.equal(issues[0].points, 12.5);
  assert.equal(issues[0].category, "titles");
  assert.ok(!issues.some((i) => i.code.startsWith("lh.") || i.code.startsWith("dfs.")), "paid rows are not audit issues");
});

test("a site-wide finding with no page list has no page count", () => {
  const issues = B.rankedIssues({ tech: [r("tech.xml_sitemap", "error")] });
  assert.equal(issues[0].pageCount, null);
});

test("crawled pages come from the report's summary, worst first", () => {
  const pages = B.crawledPages(REPORT);
  assert.equal(pages[0].url, "https://x.com/a");
  assert.equal(B.crawledPages({ seo: [] }), null, "an older scan without the summary says so");
});

test("an older score version is labelled, and the audit score is recomputed", () => {
  const old = { ...REPORT, score: 72, score_version: 2 };
  const s = B.auditScore(old);
  assert.equal(s.score, 63);
  assert.equal(s.savedScore, 72);
  assert.equal(s.recomputed, true);
  assert.equal(B.auditScore(REPORT).recomputed, false);
});
