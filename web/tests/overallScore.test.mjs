import { test } from "node:test";
import assert from "node:assert/strict";

const { overallScore, pillarScore, weightOf, OVERALL_PILLARS, CRITICAL, MEDIUM, LOW } =
  await import("../lib/overallScore.ts");

const row = (code, severity, what = code) => ({ code, severity, what });

/* ── weights ──────────────────────────────────────────────────────────────── */

test("a check's weight is its importance, not its outcome", () => {
  // The operator's example (2026-09-16): the old formula moved the score the
  // same amount for a missing <title> as for a missing apple-touch-icon.
  assert.equal(weightOf("health.title_missing"), CRITICAL);
  assert.equal(weightOf("onpage.apple_touch_icon"), LOW);
  assert.equal(weightOf("health.title_missing") / weightOf("onpage.apple_touch_icon"), 10);
});

test("a check nobody weighted is medium, never zero", () => {
  // A new check silently worth nothing is how a scoring table rots.
  assert.equal(weightOf("some.brand_new_check"), MEDIUM);
});

/* ── pillar score ─────────────────────────────────────────────────────────── */

test("the pillar score is the share of WEIGHT that passed", () => {
  // The doc's worked example: 1 critical failed, 3 high (2 passed), 10 low (all
  // passed) -> passed 20 of 35 -> 57.
  const report = {
    seo: [
      row("health.noindex_present", "error"),          // critical, failed: 0 of 10
      row("health.desc_missing", "ok"),                // high, passed: 5
      row("health.h1_count", "ok"),                    // high, passed: 5
      row("health.thin_content", "warn"),              // high, failed: 0 of 5
      ...Array.from({ length: 10 }, (_, i) => row(`onpage.url_case`, "ok", `low ${i}`)),
    ],
  };
  const p = pillarScore(report, OVERALL_PILLARS[0]);
  assert.equal(p.totalWeight, 35);
  assert.equal(p.passedWeight, 20);
  assert.equal(p.score, 57);
});

test("info rows and tools that did not run are outside the fraction", () => {
  const report = {
    seo: [row("health.title_missing", "ok"), row("crux.disabled", "info"),
          row("unavailable.lh_perf", "info"), row("unavailable.backlinks", "error")],
  };
  const p = pillarScore(report, OVERALL_PILLARS[0]);
  assert.equal(p.totalWeight, CRITICAL, "only the real check counted");
  assert.equal(p.score, 100);
});

test("a pillar with no gradeable rows is not measured, not zero", () => {
  const p = pillarScore({ seo: [row("crux.disabled", "info")] }, OVERALL_PILLARS[0]);
  assert.equal(p.measured, false);
  assert.equal(p.score, null, "0 would read as 'everything is broken'");
});

test("deductions name the failing checks, heaviest first", () => {
  const report = { seo: [row("onpage.apple_touch_icon", "warn"), row("health.title_missing", "error")] };
  const p = pillarScore(report, OVERALL_PILLARS[0]);
  assert.deepEqual(p.deductions.map((d) => d.code), ["health.title_missing", "onpage.apple_touch_icon"]);
  assert.equal(p.deductions[0].weight, CRITICAL);
});

/* ── overall ──────────────────────────────────────────────────────────────── */

test("no Overall Score until every pillar has run", () => {
  // The null -> 0 bug, in its composite form: three pillars unmeasured must not
  // drag a technically sound site to 25.
  const o = overallScore({ seo: [row("health.title_missing", "ok")] });
  assert.equal(o.score, null);
  assert.equal(o.measuredCount, 1);
  assert.equal(o.pillarCount, 4);
  assert.match(o.breakdown, /Technical 100/);
  assert.match(o.breakdown, /Content not measured/);
});

test("with every pillar measured the score is the weighted sum", () => {
  const report = {
    seo: [row("health.title_missing", "ok")],                 // technical 100, weight 35
    content: [row("content.thin", "error")],                  // content 0,     weight 35
    backlinks: [row("dfs.backlinks", "ok")],                  // backlinks 100, weight 20
    aeo: [row("aeo.crawler_blocked", "ok")],                  // aeo 100,       weight 10
  };
  const o = overallScore(report);
  assert.equal(o.measuredCount, 4);
  assert.equal(o.score, 65, "35*0 + 35*100? no: technical 100, content 0 -> 65");
  assert.equal(o.pillars.find((p) => p.key === "content").score, 0);
});

test("the pillar weights are declared, sum to 100, and are readable in one place", () => {
  assert.equal(OVERALL_PILLARS.reduce((s, p) => s + p.weight, 0), 100);
  assert.deepEqual(OVERALL_PILLARS.map((p) => p.key), ["technical", "content", "backlinks", "aeo"]);
});

test("an empty report measures nothing and says so", () => {
  const o = overallScore(null);
  assert.equal(o.score, null);
  assert.equal(o.measuredCount, 0);
  assert.deepEqual(o.topDeductions, []);
});

test("top deductions rank what actually moved the number", () => {
  const report = {
    seo: [row("onpage.url_case", "warn"), row("health.noindex_present", "error")],
    aeo: [row("aeo.crawler_blocked", "error")],
  };
  const o = overallScore(report);
  assert.equal(o.topDeductions[0].weight, CRITICAL);
  assert.ok(o.topDeductions.length >= 2);
});
