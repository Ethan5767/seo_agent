import { test } from "node:test";
import assert from "node:assert/strict";

/**
 * The tool catalog must report what runs, not what was hoped for.
 *
 * It replaced a file whose header claimed 160 tools, which held 148 entries,
 * none carrying any link to a tool the scanner would recognise. These tests pin
 * the property that mattered: every figure is a count of real things.
 */

const { summarize, categoriesOf, filterTools, costLabel } =
  await import("../lib/toolCatalog.ts");

const TOOLS = [
  { key: "seo", label: "On-page SEO", category: "On-page", group: "free", cost: "free", cost_num: 0, phase: 1, phase_label: "Page", checks: ["Page title", "Meta description"] },
  { key: "tech", label: "Technical", category: "Technical", group: "free", cost: "free", cost_num: 0, phase: 1, phase_label: "Page", checks: ["HTTPS"] },
  { key: "backlinks", label: "Backlinks (DataForSEO)", category: "Links", group: "dataforseo", cost: "~$0.025", cost_num: 0.025, phase: 3, phase_label: "Paid", checks: ["Referring domains"] },
  { key: "keywords", label: "Keywords (DataForSEO)", category: "Keywords", group: "dataforseo", cost: "~$0.18", cost_num: 0.18, phase: 3, phase_label: "Paid", checks: ["Competitors", "Keyword gap"] },
  { key: "source", label: "Source code", category: "Source code", group: "source", cost: "free (needs repo)", cost_num: 0, phase: 4, phase_label: "Source", checks: ["Route existence"] },
];

test("an empty catalog reports zeroes, never a placeholder count", () => {
  for (const empty of [null, undefined, []]) {
    assert.deepEqual(summarize(empty), {
      tools: 0, checks: 0, categories: 0, free: 0, paid: 0, paidCostUsd: 0,
    });
  }
});

test("counts are counts of real entries", () => {
  const s = summarize(TOOLS);
  assert.equal(s.tools, 5);
  assert.equal(s.checks, 7, "checks are summed from each tool's own list");
  assert.equal(s.categories, 5);
  assert.equal(s.free, 3, "source counts as free: it costs nothing to run");
  assert.equal(s.paid, 2);
});

test("the paid total is the sum of the paid tools, not an estimate", () => {
  assert.equal(summarize(TOOLS).paidCostUsd, 0.205);
});

test("malformed entries are skipped without throwing", () => {
  const s = summarize([null, 42, "x", TOOLS[0]]);
  assert.equal(s.tools, 1);
  assert.equal(s.checks, 2);
});

test("categories keep the scanner's order and do not repeat", () => {
  const cats = categoriesOf([...TOOLS, TOOLS[0]]);
  assert.deepEqual(cats, ["On-page", "Technical", "Links", "Keywords", "Source code"]);
});

test("filtering by category narrows, All does not", () => {
  assert.equal(filterTools(TOOLS, "All", "").length, 5);
  assert.equal(filterTools(TOOLS, "Links", "").length, 1);
});

test("the query searches checks, not just the label", () => {
  // "Keyword gap" is a check inside the Keywords tool, not in its label.
  const hits = filterTools(TOOLS, "All", "keyword gap");
  assert.deepEqual(hits.map((t) => t.key), ["keywords"]);
});

test("cost labels say what a tool really costs", () => {
  assert.equal(costLabel(TOOLS[0]), "free");
  assert.equal(costLabel(TOOLS[2]), "~$0.025");
  assert.equal(costLabel(TOOLS[4]), "free · needs repo");
});
