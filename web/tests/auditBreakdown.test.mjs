import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const B = await import("../lib/auditBreakdown.ts");
const r = (code, severity, extra = {}) => ({ code, what: code, why: "", fix: "", detail: "", severity, ...extra });

const REPORT = {
  score: 17,
  score_version: 4,
  counts: { ok: 1, warn: 0, error: 1, info: 0 },
  graded: 2,
  score_breakdown: {
    total_weight: 12, passed_weight: 2, lost_weight: 10,
    categories: [
      { id: "titles", label: "Titles and descriptions", total_weight: 10, passed_weight: 0, lost_weight: 10, pass_rate: 0, graded: 1, ok: 0, warn: 0, error: 1 },
      { id: "technical", label: "Technical and mobile", total_weight: 2, passed_weight: 2, lost_weight: 0, pass_rate: 100, graded: 1, ok: 1, warn: 0, error: 0 },
    ],
  },
  seo: [r("health.title_missing", "error", { score_weight: 10, score_category: "titles", pages: ["https://x.com/"] })],
  tech: [r("onpage.charset", "ok", { score_weight: 2, score_category: "technical" })],
  rankings: [r("dfs.ranked_keyword", "ok")],
};

test("the audit lists match the scanner's", () => {
  assert.deepEqual([...B.ONPAGE_AUDIT_TOOLS], [
    "seo", "site", "onpage", "tech", "headers", "monitor", "schema", "validate",
    "internal", "aeo", "perf", "lh_perf", "lh_seo", "lh_a11y", "lh_bp", "lh_pages", "render", "media", "security", "url"]);
});

test("the display returns the backend score and weighted breakdown unchanged", () => {
  const s = B.auditScore(REPORT);
  assert.equal(s.score, 17);
  assert.equal(s.version, 4);
  assert.equal(s.graded, 2);
  const b = B.scoreBreakdown(REPORT);
  assert.equal(b.categories[0].pointsLost, 10);
  assert.equal(b.categories[0].passRate, 0);
  assert.equal(b.categories[1].passRate, 100);
});

test("a report without a backend score stays scoreless", () => {
  assert.equal(B.auditScore({ seo: [r("health.title_missing", "error")] }).score, null);
});

test("issue weight and category are backend fields, not inferred in the browser", () => {
  const issues = B.rankedIssues(REPORT);
  assert.equal(issues.length, 1);
  assert.equal(issues[0].points, 10);
  assert.equal(issues[0].category, "titles");
  const legacy = B.rankedIssues({ tech: [r("tech.https", "error")] });
  assert.equal(legacy[0].points, 0);
  assert.equal(legacy[0].category, null);
});

test("no client-side formula or score version constant remains", () => {
  const source = readFileSync(new URL("../lib/auditBreakdown.ts", import.meta.url), "utf8");
  assert.doesNotMatch(source, /SCORE_VERSION|categoryOf|perCheck|recomputed|savedScore/);
  assert.doesNotMatch(source, /100\s*\*.*(?:ok|passed).*\/(?:.*graded|.*total)/);
});
