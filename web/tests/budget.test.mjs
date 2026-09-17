import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * The spend cap that replaced a blanket paid-tool ban.
 *
 * These tests never call DataForSEO. They exercise the decision function only,
 * which is the whole point of keeping it pure: the thing that guards real money
 * can be tested for free.
 */

const {
  PAID_TOOL_COSTS,
  FULL_SCAN_COST,
  DEFAULT_DAILY_BUDGET_USD,
  dailyBudgetUsd,
  estimateCost,
  isPaidTool,
  applyBudget,
} = await import("../lib/budget.ts");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(__dirname, "..", "..");

test("tool costs match the scanner's own catalog", () => {
  // Drift here would let a run be checked against the wrong price.
  const server = readFileSync(path.join(REPO, "pipeline", "scanner", "server.py"), "utf8");
  const rows = [...server.matchAll(/Tool\("([^"]+)", "([^"]+)", "([^"]+)", "([^"]+)", "([^"]*)", ([0-9.]+)/g)];
  assert.ok(rows.length > 0, "could not parse the scanner tool catalog");

  const fromPython = {};
  for (const [, , key, , group, , cost] of rows) {
    if (group === "dataforseo") fromPython[key] = Number(cost);
  }

  assert.deepEqual(
    Object.keys(PAID_TOOL_COSTS).sort(),
    Object.keys(fromPython).sort(),
    "the paid tool set differs from the scanner's dataforseo tools"
  );
  for (const [key, cost] of Object.entries(fromPython)) {
    assert.equal(
      PAID_TOOL_COSTS[key],
      cost,
      `cost for '${key}' drifted: budget.ts says ${PAID_TOOL_COSTS[key]}, server.py says ${cost}`
    );
  }
});

test("a full paid run is about fifty cents", () => {
  // The number that makes the cap legible. If this moves a lot, the default
  // budget should be revisited rather than quietly absorbing it.
  assert.ok(
    FULL_SCAN_COST > 0.4 && FULL_SCAN_COST < 0.7,
    `full scan cost is ${FULL_SCAN_COST}, outside the expected range`
  );
});

test("free tools always run, whatever the budget", () => {
  const d = applyBudget(["seo", "tech", "aeo", "lh_perf"], 999, 2);
  assert.deepEqual(d.allowed, ["seo", "tech", "aeo", "lh_perf"]);
  assert.deepEqual(d.blocked, []);
  assert.equal(d.estimatedCost, 0);
});

test("paid tools run when there is room", () => {
  const d = applyBudget(["seo", "backlinks", "rankings"], 0, 2);
  assert.deepEqual(d.allowed, ["seo", "backlinks", "rankings"]);
  assert.deepEqual(d.blocked, []);
  assert.equal(d.estimatedCost, 0.07);
  assert.equal(d.reason, undefined);
});

test("paid tools are dropped once the cap is reached, free ones survive", () => {
  const d = applyBudget(["seo", "keywords", "rank_trend"], 2, 2);
  assert.deepEqual(d.allowed, ["seo"], "the free tool must still run");
  assert.deepEqual(d.blocked, ["keywords", "rank_trend"]);
  assert.equal(d.estimatedCost, 0);
  assert.match(d.reason, /budget/i);
  assert.match(d.reason, /keywords/);
});

test("a partial budget admits what fits, in the order requested", () => {
  // $0.10 left: keywords ($0.18) does not fit, backlinks ($0.025) does.
  const d = applyBudget(["keywords", "backlinks", "gbp"], 1.9, 2);
  assert.deepEqual(d.blocked, ["keywords"]);
  assert.deepEqual(d.allowed, ["backlinks", "gbp"]);
  assert.ok(d.estimatedCost <= 0.1 + 1e-9);
});

test("no explicit selection admits the paid set only if it fits whole", () => {
  const roomy = applyBudget(undefined, 0, 2);
  assert.deepEqual(roomy.blocked, []);
  assert.equal(roomy.estimatedCost, FULL_SCAN_COST);

  const tight = applyBudget(undefined, 1.8, 2);
  assert.deepEqual(tight.blocked.sort(), Object.keys(PAID_TOOL_COSTS).sort());
  assert.equal(tight.estimatedCost, 0);
  assert.match(tight.reason, /paused until tomorrow/i);
});

test("spend already over the cap leaves nothing remaining", () => {
  const d = applyBudget(["keywords"], 5, 2);
  assert.equal(d.remaining, 0);
  assert.deepEqual(d.blocked, ["keywords"]);
});

test("a malformed budget env var falls back to the default, never wider", () => {
  assert.equal(dailyBudgetUsd({}), DEFAULT_DAILY_BUDGET_USD);
  assert.equal(dailyBudgetUsd({ SCAN_DAILY_BUDGET_USD: "" }), DEFAULT_DAILY_BUDGET_USD);
  assert.equal(dailyBudgetUsd({ SCAN_DAILY_BUDGET_USD: "abc" }), DEFAULT_DAILY_BUDGET_USD);
  assert.equal(dailyBudgetUsd({ SCAN_DAILY_BUDGET_USD: "-5" }), DEFAULT_DAILY_BUDGET_USD);
  assert.equal(dailyBudgetUsd({ SCAN_DAILY_BUDGET_USD: "0" }), 0, "an explicit zero is a real choice");
  assert.equal(dailyBudgetUsd({ SCAN_DAILY_BUDGET_USD: "10.5" }), 10.5);
});

test("a zero budget behaves exactly like the old blanket ban", () => {
  const d = applyBudget(["seo", "keywords", "backlinks"], 0, 0);
  assert.deepEqual(d.allowed, ["seo"]);
  assert.deepEqual(d.blocked, ["keywords", "backlinks"]);
});

test("estimateCost and isPaidTool agree with the table", () => {
  assert.equal(isPaidTool("keywords"), true);
  assert.equal(isPaidTool("seo"), false);
  assert.equal(estimateCost(["seo", "tech"]), 0);
  assert.equal(estimateCost(["backlinks", "gbp"]), 0.031);
});
