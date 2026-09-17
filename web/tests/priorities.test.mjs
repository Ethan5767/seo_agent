import { test } from "node:test";
import assert from "node:assert/strict";

/**
 * derivePriorities must invent nothing.
 *
 * The list it replaces was three hardcoded findings that rendered identically
 * for every client whether or not a scan had ever run, complete with fabricated
 * impact numbers ("+10-18% CTR", "Severity Weight 9.5"). These tests pin the
 * two properties that matter: every field traces to a row the scanner produced,
 * and an unscanned report yields nothing rather than something.
 */

// Node strips the type annotations itself (v22.6+), so the module under test is
// imported directly rather than transpiled or duplicated.
const { derivePriorities, hasFindings } = await import("../lib/priorities.ts");

/** A report shaped exactly like pipeline/scanner/audit.py `assemble` returns. */
const REPORT = {
  site: [
    {
      code: "health.title_missing",
      what: "title missing",
      why: "Search engines use the title to understand the page.",
      fix: "Add a unique <title> to each page.",
      detail: "3 URLs returned 200 with no <title>.",
      severity: "error",
      pages: ["/a", "/b", "/c"],
    },
    {
      code: "health.meta_description_missing",
      what: "meta description missing",
      why: "The description is the snippet searchers read.",
      fix: "Write a description per page.",
      detail: "1 URL has no meta description.",
      severity: "warn",
      pages: ["/a"],
    },
    { code: "", what: "Canonical tag", why: "Present", fix: "passing", detail: "", severity: "ok" },
  ],
  aeo: [
    {
      code: "aeo.no_faq_schema",
      what: "no faq schema",
      why: "Answer engines extract FAQ blocks.",
      fix: "Add FAQPage JSON-LD.",
      detail: "No FAQPage markup found.",
      severity: "warn",
    },
  ],
  score: 87,
  counts: { error: 1, warn: 2, info: 0, ok: 1 },
  cost: 0.0231,
};

test("returns nothing when no scan has run", () => {
  assert.deepEqual(derivePriorities(null), []);
  assert.deepEqual(derivePriorities(undefined), []);
  assert.deepEqual(derivePriorities({}), []);
  assert.deepEqual(derivePriorities({ score: 100, counts: {} }), []);
});

test("hasFindings distinguishes an empty report from a populated one", () => {
  assert.equal(hasFindings(null), false);
  assert.equal(hasFindings({ score: 100, counts: {} }), false);
  assert.equal(hasFindings({ site: [] }), false);
  assert.equal(hasFindings(REPORT), true);
});

test("only errors and warnings become priorities", () => {
  const items = derivePriorities(REPORT);
  assert.equal(items.length, 3, "1 error + 2 warnings, the ok row excluded");
  assert.equal(
    items.some((i) => i.title.toLowerCase().includes("canonical")),
    false,
    "a passing check must never appear as a priority",
  );
});

test("errors rank above warnings", () => {
  const [first] = derivePriorities(REPORT);
  assert.equal(first.severity, "critical");
  assert.equal(first.id, "priority-health.title_missing");
});

test("every field traces to the report, with no invented numbers", () => {
  const [first] = derivePriorities(REPORT);
  const source = REPORT.site[0];
  assert.equal(first.whyItMatters, source.why);
  assert.equal(first.recommendedAction, source.fix);
  assert.equal(first.problem, source.detail);
  assert.deepEqual(first.affectedPages, source.pages);
  // The page count in the headline is a real count off row.pages.
  assert.match(first.title, /3 pages/);
  assert.equal(first.technicalDetails.metrics["Affected URLs"], 3);
});

test("no fabricated impact claims survive", () => {
  const blob = JSON.stringify(derivePriorities(REPORT));
  // The fixture this replaced promised percentage lifts and a severity weight.
  assert.equal(/\d+-\d+%/.test(blob), false, "no predicted percentage ranges");
  assert.equal(/Severity Weight/.test(blob), false, "no invented severity weight");
  assert.equal(/estimated \d/i.test(blob), false, "no invented estimates");
});

test("only health.* codes claim to be auto-fixable", () => {
  const items = derivePriorities(REPORT);
  for (const item of items) {
    const isHealth = item.id.includes("priority-health.");
    assert.equal(
      item.isAutoFixable,
      isHealth,
      `${item.id} must only claim auto-fix when the remediation rail has an acceptance for it`,
    );
  }
});

test("AEO findings are categorised as AI Search", () => {
  const aeo = derivePriorities(REPORT).find((i) => i.id.includes("aeo."));
  assert.ok(aeo, "the aeo finding should appear");
  assert.equal(aeo.category, "AI Search");
  assert.equal(aeo.source, "AI Visibility");
});

test("a malformed report does not throw", () => {
  assert.deepEqual(derivePriorities({ site: "not-an-array" }), []);
  assert.deepEqual(derivePriorities({ site: [null, 42, "x"] }), []);
});
